# Atelier Terraform Variables
#
# All configurable parameters for the Atelier GCP infrastructure.
# Override via terraform.tfvars per environment (staging/production).

# --- Project ---

variable "project_id" {
  description = "GCP project ID (defaults to GOOGLE_CLOUD_PROJECT env var)"
  type        = string
  default     = null

  validation {
    condition     = var.project_id != null && var.project_id != ""
    error_message = "project_id must be set (via tfvars or GOOGLE_CLOUD_PROJECT env var)."
  }
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
  default     = "us-central1-docker.pkg.dev/atelier-build-2026/atelier/api:latest"
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

variable "agent_engine_id" {
  description = "Vertex Agent Engine id the session/memory services bind to (AT-080/082). Set by the operator after `make deploy-agent-engine`; empty until then."
  type        = string
  default     = ""
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
  default     = "auth.atelier.autonomous-agent.dev"
}

variable "custom_domain" {
  description = "Custom domain for the Atelier dashboard, authorized for Firebase SSO OAuth redirects (AT-083). Must match the domain served by the ALB (dns.tf / alb.tf)."
  type        = string
  default     = "atelier.autonomous-agent.dev"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]+[a-z0-9]$", var.custom_domain))
    error_message = "custom_domain must be a valid domain name (lowercase, no protocol prefix)."
  }
}

variable "additional_authorized_domains" {
  description = "Extra domains authorized for Firebase Auth OAuth redirects beyond the defaults + custom_domain (e.g. a Cloud Run *.run.app staging dashboard host). Because google_identity_platform_config replaces the whole list, staging domains must be declared here to survive an apply."
  type        = list(string)
  default     = []
}

# --- Networking ---

variable "enable_vpc" {
  description = "Whether to create a VPC for sandbox isolation"
  type        = bool
  default     = false
}

# --- Cloud Armor (AT-083 edge rate limiting) ---

variable "armor_rate_limit_count" {
  description = "Cloud Armor per-IP request count allowed within the rate-limit interval"
  type        = number
  default     = 60
}

variable "armor_rate_limit_interval_sec" {
  description = "Cloud Armor per-IP rate-limit interval in seconds"
  type        = number
  default     = 60
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

# --- IAP ---

variable "enable_iap" {
  description = "Front Cloud Run with Identity-Aware Proxy instead of the default ALB + Firebase SSO model (PRD 13.1). When false, the ALB grants run.invoker to allUsers and the app enforces Firebase SSO. When true, IAP gates ingress and the allUsers binding is removed."
  type        = bool
  default     = false
}

variable "iap_support_email" {
  description = "Support email for IAP OAuth consent screen"
  type        = string
  default     = "manzela@tngshopper.com"
}

variable "iap_allowed_members" {
  description = "IAP-allowed IAM members (e.g. user:x@y.com, group:z@y.com)"
  type        = list(string)
  default     = ["user:manzela@tngshopper.com"]
}
