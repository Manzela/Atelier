resource "google_artifact_registry_repository" "atelier_images" {
  location      = var.region
  repository_id = "atelier-images"
  format        = "DOCKER"
  project       = var.project_id
  description   = "Atelier container images"
}

resource "google_cloud_run_v2_service" "atelier_api" {
  name     = "atelier-api-${var.env}"
  location = var.region
  project  = var.project_id

  template {
    service_account = google_service_account.atelier_api.email
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/atelier-images/atelier-api:latest"
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
}
