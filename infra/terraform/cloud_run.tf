resource "google_artifact_registry_repository" "atelier_images" {
  count         = var.env == "staging" ? 1 : 0
  location      = var.region
  repository_id = "atelier-images"
  format        = "DOCKER"
  project       = var.project_id
  description   = "Atelier container images"

  depends_on = [google_project_service.required]
}

resource "google_cloud_run_v2_service" "atelier_api" {
  name                = "atelier-api-${var.env}"
  location            = var.region
  project             = var.project_id
  deletion_protection = false

  # Production: restrict to internal+load-balancer traffic only;
  # staging: allow all traffic for easier developer testing.
  ingress = var.env == "production" ? "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER" : "INGRESS_TRAFFIC_ALL"

  template {
    service_account = "atelier-api-sa@${var.project_id}.iam.gserviceaccount.com"
    containers {
      # Pin to an immutable digest supplied at plan time via var.api_image.
      # Never deploy :latest — mutable tags make rollbacks ambiguous and
      # allow a re-pushed tag to silently change prod behavior.
      image = var.api_image
      ports {
        container_port = 8080
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
      startup_probe {
        timeout_seconds   = 240
        period_seconds     = 240
        failure_threshold  = 1
        tcp_socket {
          port = 8080
        }
      }
      env {
        name  = "FIREBASE_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "ATELIER_ENV"
        value = var.env
      }
      env {
        name  = "ATELIER_DASHBOARD_ORIGIN"
        value = var.env == "staging" ? "https://atelier-dashboard-537337457799.us-central1.run.app,https://atelier-build-2026-21a9e.web.app" : "https://atelier.autonomous-agent.dev,https://atelier-build-2026.web.app"
      }
      env {
        name  = "ATELIER_GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "ATELIER_JUDGE_MODE"
        value = "llm"
      }
      env {
        name  = "ATELIER_MODEL_ARMOR_ENABLED"
        value = "true"
      }
      env {
        name  = "ATELIER_MODEL_ARMOR_TEMPLATE"
        value = "atelier-default"
      }
      env {
        name  = "ATELIER_STITCH_ENABLED"
        value = "false"
      }
      env {
        # The per-user lifetime token cap (AT-095) and fleet circuit-breaker
        # (AT-097) must hold across instances and survive scale-to-zero. The
        # Firestore backend uses atomic firestore.Increment, so a counter shared
        # by every instance enforces the cap; the in-memory backend is per-instance
        # process state and fails open on a public, autoscaled, min=0 service.
        name  = "ATELIER_USAGE_BACKEND"
        value = "firestore"
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "true"
      }
      env {
        name  = "SESSION_BACKEND"
        value = "vertex"
      }
      env {
        name  = "AGENT_ENGINE_ID"
        value = var.agent_engine_id
      }
      env {
        name  = "FIXER_MODEL"
        value = "gemini-2.5-flash"
      }
    }
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
  }

  depends_on = [
    google_project_service.required
  ]

  lifecycle {
    # var.api_image pins the plan-time digest, but the live revision is rolled by
    # `gcloud run deploy` in the deploy workflow. Ignore image drift so a later
    # `terraform apply` does not revert the running revision to the plan-time
    # value (restored 2026-06-09: the immutable-digest change dropped this block,
    # which would otherwise make Terraform fight the deploy pipeline).
    ignore_changes = [template[0].containers[0].image]
  }
}

resource "google_storage_bucket" "rag_datastore_staging" {
  name          = "atelier-rag-staging-${var.project_id}-${var.env}"
  location      = var.region
  force_destroy = true

  uniform_bucket_level_access = true

  depends_on = [google_project_service.required]
}
