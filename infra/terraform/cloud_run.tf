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
  # L23: production must be INGRESS_TRAFFIC_ALL, not INTERNAL_LOAD_BALANCER. The
  # canonical path is a Firebase Hosting CNAME whose /v1/** rewrite reaches Cloud
  # Run as ordinary internet traffic (NOT internal-LB traffic), so an internal-only
  # ingress would 404 the live product. This matches the deployed reality and the
  # explicit --ingress=all on the gcloud deploy; the security boundary is app-layer
  # require_auth on /v1/*, not network ingress. (Reconciled IaC<->CD drift.)
  ingress = "INGRESS_TRAFFIC_ALL"

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
          # L22: the in-request axe a11y gate (the convergence-determiner) runs a
          # headless Chromium per candidate; <~2Gi OOMs it and every candidate then
          # fails the gate. 4Gi/2vCPU matches the gcloud-deploy flags so IaC and CD
          # agree on the floor.
          cpu    = "2"
          memory = "4Gi"
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
        # The canonical domain (atelier.autonomous-agent.dev) is served by the
        # STAGING service via Firebase Hosting (the LIVE-5 topology), so the
        # staging CORS allowlist MUST include it — otherwise the browser's
        # cross-origin preflight to the run.app API is rejected ("Disallowed CORS
        # origin", 400) and every generation from the canonical domain fails with
        # a "Pipeline error". Both run.app dashboard hosts are listed so the app
        # also works when opened directly on Cloud Run.
        name  = "ATELIER_DASHBOARD_ORIGIN"
        value = var.env == "staging" ? "https://atelier.autonomous-agent.dev,https://atelier-dashboard-537337457799.us-central1.run.app,https://atelier-dashboard-2h56glloxa-uc.a.run.app,https://atelier-build-2026-21a9e.web.app" : "https://atelier.autonomous-agent.dev,https://atelier-build-2026.web.app,https://atelier-build-2026-21a9e.web.app"
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
      # L09 / JAM-BUG-2: min=0 + max=3 + per-instance concurrency=1 gave a
      # 3-request hard ceiling, so a view-mount burst of /v1/platform/* preflights
      # raced cold starts and Google Frontend shed one with a CORS-less 429. A warm
      # baseline + headroom removes the capacity cliff.
      min_instance_count = 1
      max_instance_count = 10
    }
    # L09: lift per-instance request concurrency so one warm instance absorbs the
    # whole platform-read burst instead of forcing a scale-up race (kept in sync
    # with the --concurrency flag on the gcloud deploy in .github/workflows/deploy.yml).
    max_instance_request_concurrency = 10
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
