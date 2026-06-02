# Identity-Aware Proxy (IAP) — OPT-IN alternative ingress (disabled by default).
#
# The default public ingress model for Atelier (PRD section 13.1) is the
# external Application Load Balancer (alb.tf) with Firebase Google SSO enforced
# at the application layer and Cloud Armor at the edge. Under that model the
# Cloud Run service grants `roles/run.invoker` to allUsers (alb.tf) so the load
# balancer can reach it, and the FastAPI Firebase middleware gates the /v1/*
# routes.
#
# IAP is retained as an alternative ingress for an internal/staff-only
# deployment. It is gated behind `var.enable_iap` (default false) because (a) it
# conflicts with the allUsers binding the ALB path requires, and (b)
# `google_iap_brand` relies on the deprecated IAP OAuth Admin API. Enable it
# only for an IAP-fronted, non-public deployment.

# ---------------------------------------------------------------------------
# Enable IAP API
# ---------------------------------------------------------------------------

resource "google_project_service" "iap" {
  count   = var.enable_iap ? 1 : 0
  project = var.project_id
  service = "iap.googleapis.com"

  disable_dependent_services = false
  disable_on_destroy         = false
}

# ---------------------------------------------------------------------------
# IAP Brand (OAuth consent screen)
# ---------------------------------------------------------------------------

resource "google_iap_brand" "atelier" {
  count             = var.enable_iap ? 1 : 0
  support_email     = var.iap_support_email
  application_title = "Atelier Autonomous Design Agent"
  project           = var.project_id

  depends_on = [google_project_service.iap]
}

# ---------------------------------------------------------------------------
# IAP OAuth Client
# ---------------------------------------------------------------------------

resource "google_iap_client" "atelier_api" {
  count        = var.enable_iap ? 1 : 0
  display_name = "Atelier API IAP Client"
  brand        = google_iap_brand.atelier[0].name
}

# ---------------------------------------------------------------------------
# Cloud Run IAM — only IAP-authenticated users can invoke
# ---------------------------------------------------------------------------

resource "google_cloud_run_v2_service_iam_member" "api_iap" {
  count    = var.enable_iap ? 1 : 0
  name     = google_cloud_run_v2_service.api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-iap.iam.gserviceaccount.com"

  depends_on = [google_project_service.iap]
}

# Allow specific users/groups via IAP
resource "google_iap_web_iam_member" "api_users" {
  for_each = var.enable_iap ? toset(var.iap_allowed_members) : toset([])

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
