# Joule Thief on Google Cloud — designed to stay inside the free tier:
#   Cloud Run (scale to zero), Artifact Registry (<0.5 GB with the cleanup policy), Cloud Scheduler
#   (3 free jobs), Workload Identity Federation (free), optional always-free e2-micro runner.

locals {
  services = ["run.googleapis.com", "artifactregistry.googleapis.com", "iam.googleapis.com",
    "iamcredentials.googleapis.com", "sts.googleapis.com", "cloudscheduler.googleapis.com",
  "compute.googleapis.com", "secretmanager.googleapis.com"]
}

resource "google_project_service" "apis" {
  for_each           = toset(local.services)
  service            = each.value
  disable_on_destroy = false
}

data "google_project" "this" {}

# ── Artifact Registry: keep only the last 5 images (storage has embodied carbon, and the free tier is 0.5 GB)
resource "google_artifact_registry_repository" "joule" {
  location      = var.region
  repository_id = "joule-thief"
  format        = "DOCKER"
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 5
    }
  }
  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      older_than = "604800s"
    }
  }
  depends_on = [google_project_service.apis]
}

# ── Keyless CI: GitLab OIDC → Workload Identity Federation (no service-account keys)
resource "google_iam_workload_identity_pool" "gitlab" {
  workload_identity_pool_id = "gitlab"
  display_name              = "GitLab CI"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "gitlab" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.gitlab.workload_identity_pool_id
  workload_identity_pool_provider_id = "gitlab-com"
  display_name                       = "gitlab.com"
  attribute_mapping = {
    "google.subject"          = "assertion.sub"
    "attribute.project_path"  = "assertion.project_path"
    "attribute.ref"           = "assertion.ref"
    "attribute.ref_protected" = "assertion.ref_protected"
  }
  attribute_condition = "assertion.project_path == '${var.gitlab_project_path}' && assertion.ref_protected == 'true'"
  oidc {
    issuer_uri        = "https://gitlab.com"
    allowed_audiences = ["https://gitlab.com"]
  }
}

locals {
  ci_principal = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.gitlab.name}/attribute.project_path/${var.gitlab_project_path}"
}

resource "google_service_account" "runtime" {
  account_id   = "joule-runtime"
  display_name = "Joule Thief Cloud Run runtime"
}

# Direct federation: the CI identity itself gets the narrow roles it needs.
resource "google_project_iam_member" "ci_run_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = local.ci_principal
}

resource "google_artifact_registry_repository_iam_member" "ci_push" {
  location   = google_artifact_registry_repository.joule.location
  repository = google_artifact_registry_repository.joule.name
  role       = "roles/artifactregistry.writer"
  member     = local.ci_principal
}

resource "google_service_account_iam_member" "ci_act_as_runtime" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = local.ci_principal
}

# ── GitLab token for the dispatcher tick (Secret Manager free tier: 6 active versions)
resource "google_secret_manager_secret" "gitlab_token" {
  count     = var.gitlab_token == "" ? 0 : 1
  secret_id = "joule-gitlab-token"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "gitlab_token" {
  count       = var.gitlab_token == "" ? 0 : 1
  secret      = google_secret_manager_secret.gitlab_token[0].id
  secret_data = var.gitlab_token
}

resource "google_secret_manager_secret_iam_member" "runtime_reads_token" {
  count     = var.gitlab_token == "" ? 0 : 1
  secret_id = google_secret_manager_secret.gitlab_token[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

# ── The control room: scale to zero, one small instance at most, no CPU when idle
resource "google_cloud_run_v2_service" "joule" {
  name                = "joule-thief"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.runtime.email
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = var.image
      resources {
        limits            = { cpu = "1", memory = "512Mi" }
        cpu_idle          = true
        startup_cpu_boost = false
      }
      env {
        name  = "JOULE_TICK_KEY"
        value = var.tick_key
      }
      env {
        name  = "JOULE_PROJECT"
        value = var.gitlab_project_path
      }
      env {
        name  = "JOULE_FLOW_CONSUMER_ID"
        value = var.flow_consumer_id
      }
      dynamic "env" {
        for_each = var.gitlab_token == "" ? [] : [1]
        content {
          name = "JOULE_GITLAB_TOKEN"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.gitlab_token[0].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version, traffic]
  }
  depends_on = [google_project_service.apis, google_secret_manager_secret_iam_member.runtime_reads_token]
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.joule.name
  location = google_cloud_run_v2_service.joule.location
  role     = "roles/run.invoker"
  member   = "allUsers" # public dashboard for judges; /api/tick requires the shared key
}

# ── The hands-off heartbeat: one dispatcher tick every 30 minutes (free tier: 3 jobs)
resource "google_cloud_scheduler_job" "tick" {
  count     = var.tick_key == "" ? 0 : 1
  name      = "joule-thief-tick"
  region    = var.region
  schedule  = "*/30 * * * *"
  time_zone = "Etc/UTC"
  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.joule.uri}/api/tick"
    headers     = { "X-Joule-Key" = var.tick_key }
  }
  depends_on = [google_project_service.apis]
}

# ── Optional: always-free e2-micro runner in Oregon (79 g/kWh, 87% CFE) for deferrable CI jobs,
#    instead of GitLab.com hosted runners in South Carolina (576 g/kWh, 31% CFE).
resource "google_compute_instance" "green_runner" {
  count        = var.enable_green_runner ? 1 : 0
  name         = "joule-green-runner"
  machine_type = "e2-micro"
  zone         = "us-west1-b"
  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 30
      type  = "pd-standard"
    }
  }
  network_interface {
    network = "default"
    access_config {}
  }
  scheduling {
    preemptible       = false
    automatic_restart = true
  }
  metadata_startup_script = templatefile("${path.module}/runner-startup.sh.tftpl", { runner_token = var.runner_token })
  depends_on              = [google_project_service.apis]
}
