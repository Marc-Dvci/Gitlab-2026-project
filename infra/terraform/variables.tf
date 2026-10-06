variable "project_id" {
  type        = string
  description = "Google Cloud project ID."
}

variable "region" {
  type        = string
  default     = "europe-north1" # Hamina: 98% CFE (Google 2024), seawater cooling, frequent negative prices
  description = "Home region for the control room and the Artifact Registry repository."
}

variable "gitlab_project_path" {
  type        = string
  description = "GitLab project path allowed to deploy through Workload Identity Federation, e.g. my-group/joule-thief."
}

variable "image" {
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
  description = "Initial container image; CI deploys new revisions afterwards."
}

variable "tick_key" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Shared secret Cloud Scheduler sends to /api/tick. Leave empty to disable the scheduler job."
}

variable "enable_green_runner" {
  type        = bool
  default     = false
  description = "Create an always-free e2-micro GitLab runner in us-west1 (Oregon) for deferrable CI jobs."
}

variable "runner_token" {
  type        = string
  default     = ""
  sensitive   = true
  description = "GitLab runner authentication token (glrt-...) for the green runner."
}

variable "gitlab_token" {
  type        = string
  default     = ""
  sensitive   = true
  description = "Project access token (api scope) used by the dispatcher tick. Stored in Secret Manager."
}

variable "flow_consumer_id" {
  type        = string
  default     = ""
  description = "AI Catalog consumer id of the surge-worker flow (empty: fall back to developer/v1)."
}
