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
