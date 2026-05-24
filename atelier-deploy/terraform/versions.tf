# Atelier Terraform — GCP Infrastructure-as-Code
#
# Provisions all GCP resources for the Atelier autonomous design agent:
#   - Cloud Run services (API + Worker)
#   - BigQuery datasets (trajectories + DPO)
#   - Artifact Registry (container images)
#   - KMS (per-tenant encryption for GDPR)
#   - Identity Platform (multi-tenant auth)
#   - Cloud Trace + Cloud Logging
#   - Secret Manager
#   - VPC + Cloud NAT (for outbound-only sandbox)
#
# Usage:
#   cd atelier-deploy/terraform
#   terraform init
#   terraform plan -var-file=envs/staging/terraform.tfvars
#   terraform apply -var-file=envs/staging/terraform.tfvars
#
# PRD Reference: §7 (Infrastructure), §15 (Security)
# Audit Reference: §1 (Sandbox), §3 (OTel), §5 (Trajectory)

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
  }

  # Backend — GCS for state locking (created manually)
  backend "gcs" {
    bucket = "atelier-terraform-state"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}
