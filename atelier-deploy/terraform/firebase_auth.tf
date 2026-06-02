# Firebase Auth / Identity Platform — Authorized Domains + Sign-In Config
#
# Manages the Identity Platform (Firebase Auth) project-level configuration
# as code. This is the Terraform equivalent of the Firebase Console
# "Authentication → Settings → Authorized Domains" page.
#
# Why this file exists (AT-083 deploy requirement):
#   Firebase Auth's Google SSO redirect flow rejects OAuth callbacks from
#   domains not in the authorized list. The custom domain
#   `atelier.autonomous-agent.dev` must be whitelisted before Google SSO
#   works on the production ALB. There is no `gcloud` CLI command for this;
#   the alternatives are the Firebase Console (manual, drift-prone) or the
#   Identity Toolkit v2 REST API. Terraform is the principled IaC path.
#
# Prereq: identitytoolkit.googleapis.com (already in main.tf L22).
#
# PRD Reference: §13.1 (Firebase Google SSO gating), AT-083 acceptance.
# ADR Reference: 0006 (Google-native stack).

resource "google_identity_platform_config" "auth" {
  project = var.project_id

  # Domains authorized for OAuth redirect callbacks (Google SSO).
  # Order: Firebase defaults first, then the custom domain, then any extra
  # domains (e.g. a Cloud Run *.run.app staging host). localhost is retained
  # for local development (`npm run dev`). additional_authorized_domains keeps
  # declaratively-managed staging domains from being stripped on apply, since
  # google_identity_platform_config replaces the whole list.
  authorized_domains = concat(
    [
      "localhost",
      "${var.project_id}.firebaseapp.com",
      "${var.project_id}.web.app",
      var.custom_domain,
    ],
    var.additional_authorized_domains,
  )

  # Google Sign-In provider configuration.
  sign_in {
    allow_duplicate_emails = false

    email {
      enabled           = true
      password_required = false
    }
  }

  # Do not auto-delete anonymous users (no anonymous auth in V1).
  autodelete_anonymous_users = false

  depends_on = [google_project_service.apis["identitytoolkit.googleapis.com"]]
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "auth_authorized_domains" {
  description = "Domains authorized for Firebase Auth OAuth redirects"
  value       = google_identity_platform_config.auth.authorized_domains
}
