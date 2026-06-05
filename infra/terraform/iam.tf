resource "google_service_account" "atelier_runtime" {
  count        = var.env == "staging" ? 1 : 0
  account_id   = "atelier-runtime"
  display_name = "Atelier Runtime"
  project      = var.project_id
  description  = "Used by Cloud Run services and Vertex AI Memory Bank backends"

  depends_on = [google_project_service.required]
}

resource "google_service_account" "atelier_api" {
  count        = var.env == "staging" ? 1 : 0
  account_id   = "atelier-api-sa"
  display_name = "Atelier API Service Account"
  project      = var.project_id
  description  = "Used by the Atelier FastAPI Cloud Run service"

  depends_on = [google_project_service.required]
}

resource "google_project_iam_member" "runtime_vertex_user" {
  count   = var.env == "staging" ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:atelier-runtime@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "runtime_bigquery_data_editor" {
  count   = var.env == "staging" ? 1 : 0
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:atelier-runtime@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "api_sa_secret_accessor" {
  count   = var.env == "staging" ? 1 : 0
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:atelier-api-sa@${var.project_id}.iam.gserviceaccount.com"
}

resource "google_cloud_run_v2_service_iam_binding" "api_invoker" {
  project  = var.project_id
  location = var.region
  name     = "atelier-api-${var.env}"
  role     = "roles/run.invoker"
  members = [
    "allUsers",
    "serviceAccount:atelier-api-sa@${var.project_id}.iam.gserviceaccount.com"
  ]
}
