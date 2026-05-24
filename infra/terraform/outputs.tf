output "cloud_run_url" {
  value = google_cloud_run_v2_service.atelier_api.uri
}

output "atelier_runtime_sa_email" {
  value = google_service_account.atelier_runtime.email
}

output "atelier_api_sa_email" {
  value = google_service_account.atelier_api.email
}
