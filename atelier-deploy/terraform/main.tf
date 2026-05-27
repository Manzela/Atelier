# Atelier Main Terraform Configuration
#
# Enables required GCP APIs and provisions core infrastructure.
# Each resource group is in a separate section for clarity.

# ---------------------------------------------------------------------------
# GCP API Enablement (18 APIs per PRD §7)
# ---------------------------------------------------------------------------

locals {
  required_apis = [
    "run.googleapis.com",                    # Cloud Run
    "artifactregistry.googleapis.com",       # Artifact Registry
    "aiplatform.googleapis.com",             # Vertex AI
    "bigquery.googleapis.com",               # BigQuery
    "bigquerystorage.googleapis.com",        # BigQuery Storage API
    "cloudkms.googleapis.com",               # KMS
    "secretmanager.googleapis.com",          # Secret Manager
    "cloudtrace.googleapis.com",             # Cloud Trace
    "logging.googleapis.com",               # Cloud Logging
    "monitoring.googleapis.com",             # Cloud Monitoring
    "identitytoolkit.googleapis.com",        # Identity Platform
    "compute.googleapis.com",               # Compute (for VPC)
    "vpcaccess.googleapis.com",              # Serverless VPC Access
    "servicenetworking.googleapis.com",      # Service Networking
    "cloudbuild.googleapis.com",             # Cloud Build
    "containerregistry.googleapis.com",      # Container Registry (legacy)
    "iam.googleapis.com",                    # IAM
    "cloudresourcemanager.googleapis.com",   # Resource Manager
  ]
}

resource "google_project_service" "apis" {
  for_each = toset(local.required_apis)

  project = var.project_id
  service = each.value

  disable_dependent_services = false
  disable_on_destroy         = false
}

# ---------------------------------------------------------------------------
# Service Accounts
# ---------------------------------------------------------------------------

# Atelier API service account (Cloud Run)
resource "google_service_account" "api" {
  account_id   = "atelier-api"
  display_name = "Atelier API Service Account"
  description  = "Cloud Run service account for the Atelier API. Minimal permissions."
  project      = var.project_id
}

# Atelier Worker service account (long-running agent tasks)
resource "google_service_account" "worker" {
  account_id   = "atelier-worker"
  display_name = "Atelier Worker Service Account"
  description  = "Cloud Run service account for long-running agent tasks. Has Vertex AI + BigQuery access."
  project      = var.project_id
}

# --- IAM Bindings ---

# API SA → Vertex AI User (for model inference)
resource "google_project_iam_member" "api_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# API SA → BigQuery Data Editor (for trajectory recording)
resource "google_project_iam_member" "api_bq" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# API SA → Secret Manager Accessor
resource "google_project_iam_member" "api_secrets" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# API SA → Cloud Trace Agent
resource "google_project_iam_member" "api_trace" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# Worker SA → Vertex AI Admin (for training jobs)
resource "google_project_iam_member" "worker_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.admin"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

# Worker SA → BigQuery Admin (for DPO dataset management)
resource "google_project_iam_member" "worker_bq" {
  project = var.project_id
  role    = "roles/bigquery.admin"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

# Worker SA → KMS CryptoKey Encrypter/Decrypter
resource "google_project_iam_member" "worker_kms" {
  project = var.project_id
  role    = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

# ---------------------------------------------------------------------------
# Artifact Registry
# ---------------------------------------------------------------------------

resource "google_artifact_registry_repository" "atelier" {
  location      = var.region
  repository_id = "atelier"
  format        = "DOCKER"
  description   = "Atelier container images (API, Worker, Training)"
  labels        = var.labels

  depends_on = [google_project_service.apis["artifactregistry.googleapis.com"]]
}

# ---------------------------------------------------------------------------
# Cloud Run — API Service
# ---------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "api" {
  name     = "atelier-api-${var.environment}"
  location = var.region
  labels   = var.labels

  template {
    service_account = google_service_account.api.email

    scaling {
      min_instance_count = var.api_min_instances
      max_instance_count = var.api_max_instances
    }

    containers {
      image = var.api_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          memory = var.api_memory
          cpu    = var.api_cpu
        }
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }

      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }

      env {
        name  = "GCP_REGION"
        value = var.region
      }

      env {
        name  = "BQ_DATASET"
        value = "atelier_trajectories"
      }

      env {
        name  = "OTEL_EXPORTER_OTLP_ENDPOINT"
        value = "https://cloudtrace.googleapis.com"
      }

      env {
        name  = "OTEL_SERVICE_NAME"
        value = "atelier-api"
      }

      env {
        name  = "ATELIER_DASHBOARD_ORIGIN"
        value = "https://atelier.autonomous-agent.dev,https://atelier-build-2026.web.app"
      }

      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        initial_delay_seconds = 5
        period_seconds        = 5
        failure_threshold     = 3
      }
    }
  }

  depends_on = [google_project_service.apis["run.googleapis.com"]]
}

# IAP-protected ingress — see iap.tf
# The allUsers binding has been removed for security.
# Access is now controlled via Identity-Aware Proxy (IAP).

# ---------------------------------------------------------------------------
# KMS — Per-Tenant Encryption (GDPR right-to-be-forgotten)
# ---------------------------------------------------------------------------

resource "google_kms_key_ring" "tenant_keys" {
  name     = var.kms_key_ring
  location = "global"
  project  = var.project_id

  depends_on = [google_project_service.apis["cloudkms.googleapis.com"]]
}

# Default tenant key (for development/staging)
resource "google_kms_crypto_key" "default_tenant" {
  name            = "default-tenant"
  key_ring        = google_kms_key_ring.tenant_keys.id
  rotation_period = "7776000s" # 90 days

  lifecycle {
    prevent_destroy = true
  }
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "api_url" {
  description = "Cloud Run API service URL"
  value       = google_cloud_run_v2_service.api.uri
}

output "api_service_account" {
  description = "API service account email"
  value       = google_service_account.api.email
}

output "worker_service_account" {
  description = "Worker service account email"
  value       = google_service_account.worker.email
}

output "artifact_registry" {
  description = "Artifact Registry repository URL"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.atelier.repository_id}"
}

output "kms_key_ring" {
  description = "KMS key ring resource name"
  value       = google_kms_key_ring.tenant_keys.id
}
