# Atelier Terraform Variables
#
# All configurable parameters for the Atelier GCP infrastructure.
# Override via terraform.tfvars per environment (staging/production).

# --- Project ---

variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "i-for-ai"
}

variable "region" {
  description = "Primary GCP region for Cloud Run + Vertex AI"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Deployment environment: staging | production"
  type        = string
  default     = "staging"
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Environment must be 'staging' or 'production'."
  }
}

# --- Cloud Run ---

variable "api_image" {
  description = "Container image URL for the Atelier API service"
  type        = string
  default     = "us-central1-docker.pkg.dev/i-for-ai/atelier/api:latest"
}

variable "api_min_instances" {
  description = "Minimum number of API instances (0 for scale-to-zero)"
  type        = number
  default     = 0
}

variable "api_max_instances" {
  description = "Maximum number of API instances"
  type        = number
  default     = 10
}

variable "api_memory" {
  description = "Memory limit per API instance"
  type        = string
  default     = "1Gi"
}

variable "api_cpu" {
  description = "CPU limit per API instance"
  type        = string
  default     = "1"
}

# --- BigQuery ---

variable "bq_dataset_location" {
  description = "BigQuery dataset location"
  type        = string
  default     = "US"
}

variable "bq_trajectory_retention_days" {
  description = "Trajectory record retention in days (NULL = no expiry)"
  type        = number
  default     = null
}

# --- KMS ---

variable "kms_key_ring" {
  description = "KMS key ring name for per-tenant encryption"
  type        = string
  default     = "atelier-tenant-keys"
}

# --- Identity Platform ---

variable "auth_domain" {
  description = "Custom auth domain for Identity Platform"
  type        = string
  default     = "auth.atelier.dev"
}

# --- Networking ---

variable "enable_vpc" {
  description = "Whether to create a VPC for sandbox isolation"
  type        = bool
  default     = false
}

# --- Labels ---

variable "labels" {
  description = "Common labels applied to all resources"
  type        = map(string)
  default = {
    app     = "atelier"
    team    = "manzela"
    managed = "terraform"
  }
}
