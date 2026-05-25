# Identity-Aware Proxy (IAP) configuration for Atelier API
#
# Replaces the previous allUsers Cloud Run IAM binding (AG-03 / B3).
# All API access now flows through IAP for:
#   - Google Identity authentication
#   - Context-aware access policies
#   - Audit logging of all API calls

# ---------------------------------------------------------------------------
# Enable IAP API
# ---------------------------------------------------------------------------

resource "google_project_service" "iap" {
  project = var.project_id
  service = "iap.googleapis.com"

  disable_dependent_services = false
  disable_on_destroy         = false
}

# ---------------------------------------------------------------------------
# IAP Brand (OAuth consent screen)
# ---------------------------------------------------------------------------

resource "google_iap_brand" "atelier" {
  support_email     = var.iap_support_email
  application_title = "Atelier Autonomous Design Agent"
  project           = var.project_id

  depends_on = [google_project_service.iap]
}

# ---------------------------------------------------------------------------
# IAP OAuth Client
# ---------------------------------------------------------------------------

resource "google_iap_client" "atelier_api" {
  display_name = "Atelier API IAP Client"
  brand        = google_iap_brand.atelier.name
}

# ---------------------------------------------------------------------------
# Cloud Run IAM — only IAP-authenticated users can invoke
# ---------------------------------------------------------------------------

resource "google_cloud_run_v2_service_iam_member" "api_iap" {
  name     = google_cloud_run_v2_service.api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-iap.iam.gserviceaccount.com"

  depends_on = [google_project_service.iap]
}

# Allow specific users/groups via IAP
resource "google_iap_web_iam_member" "api_users" {
  for_each = toset(var.iap_allowed_members)

  project = var.project_id
  role    = "roles/iap.httpsResourceAccessor"
  member  = each.value
}

# ---------------------------------------------------------------------------
# Data source for project number (needed for IAP SA)
# ---------------------------------------------------------------------------

data "google_project" "current" {
  project_id = var.project_id
}
