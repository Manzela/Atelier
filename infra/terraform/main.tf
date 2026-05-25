provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  common_labels = {
    env     = var.env
    project = "atelier"
    managed = "terraform"
  }
}
