resource "google_service_account" "atelier_runtime" {
  account_id   = "atelier-runtime"
  display_name = "Atelier Runtime"
  project      = var.project_id
  description  = "Used by Cloud Run services and Vertex AI Memory Bank backends"
}

resource "google_service_account" "atelier_api" {
  account_id   = "atelier-api-sa"
  display_name = "Atelier API Service Account"
  project      = var.project_id
  description  = "Used by the Atelier FastAPI Cloud Run service"
}

resource "google_project_iam_member" "runtime_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.atelier_runtime.email}"
}

resource "google_project_iam_member" "runtime_bigquery_data_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.atelier_runtime.email}"
}

resource "google_project_iam_member" "api_sa_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.atelier_api.email}"
}
