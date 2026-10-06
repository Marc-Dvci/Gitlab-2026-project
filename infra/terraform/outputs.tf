output "service_url" {
  value = google_cloud_run_v2_service.joule.uri
}

output "wif_provider" {
  description = "Set as the GCP_WIF_PROVIDER CI/CD variable."
  value       = google_iam_workload_identity_pool_provider.gitlab.name
}

output "artifact_registry_repo" {
  description = "Set as the GCP_AR_REPO CI/CD variable."
  value       = google_artifact_registry_repository.joule.repository_id
}
