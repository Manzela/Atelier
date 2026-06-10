variable "project_id" {
  type    = string
  default = "atelier-build-2026"
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "Primary region — us-central1 for Vertex AI parity with public benchmarks"
}

variable "env" {
  type    = string
  default = "staging"
  validation {
    condition     = contains(["staging", "production"], var.env)
    error_message = "env must be staging or production."
  }
}

variable "agent_engine_id" {
  type        = string
  description = "The deployed Vertex AI Agent Engine (Reasoning Engine) resource ID"
  default     = "8092258795629051904"
}

variable "api_image" {
  type        = string
  description = <<-EOT
    Immutable container image reference for the Cloud Run API, including
    digest (e.g. us-central1-docker.pkg.dev/PROJECT/atelier-images/atelier-api@sha256:...).
    Must be set at plan/apply time — no default is provided intentionally
    so that deploying without an explicit digest fails loudly.
  EOT
}
