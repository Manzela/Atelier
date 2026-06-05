output "cloud_run_url" {
  value = google_cloud_run_v2_service.atelier_api.uri
}

output "atelier_runtime_sa_email" {
  value = var.env == "staging" ? google_service_account.atelier_runtime[0].email : "atelier-runtime@${var.project_id}.iam.gserviceaccount.com"
}

output "atelier_api_sa_email" {
  value = var.env == "staging" ? google_service_account.atelier_api[0].email : "atelier-api-sa@${var.project_id}.iam.gserviceaccount.com"
}
