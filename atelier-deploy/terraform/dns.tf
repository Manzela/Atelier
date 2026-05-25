# DNS + Wildcard Certificate for *.atelier.autonomous-agent.dev
#
# Provisions a Cloud DNS managed zone and a Google-managed SSL certificate
# for the wildcard domain. The cert is validated via DNS challenge.
#
# Prerequisites:
#   - Domain `autonomous-agent.dev` must be registered and NS records
#     must point to Cloud DNS name servers.
#   - `dns.googleapis.com` and `certificatemanager.googleapis.com` must
#     be enabled (added below).
#
# AG-11 / Infra

# ---------------------------------------------------------------------------
# Enable required APIs
# ---------------------------------------------------------------------------

resource "google_project_service" "dns" {
  project = var.project_id
  service = "dns.googleapis.com"

  disable_dependent_services = false
  disable_on_destroy         = false
}

resource "google_project_service" "certificate_manager" {
  project = var.project_id
  service = "certificatemanager.googleapis.com"

  disable_dependent_services = false
  disable_on_destroy         = false
}

# ---------------------------------------------------------------------------
# Cloud DNS Managed Zone
# ---------------------------------------------------------------------------

resource "google_dns_managed_zone" "atelier" {
  name        = "atelier-zone"
  dns_name    = "atelier.autonomous-agent.dev."
  description = "Managed DNS zone for Atelier services"
  project     = var.project_id
  labels      = var.labels

  visibility = "public"

  dnssec_config {
    state = "on"
  }

  depends_on = [google_project_service.dns]
}

# ---------------------------------------------------------------------------
# A Record — Cloud Run custom domain mapping
# ---------------------------------------------------------------------------

resource "google_dns_record_set" "api" {
  name         = "api.atelier.autonomous-agent.dev."
  type         = "CNAME"
  ttl          = 300
  managed_zone = google_dns_managed_zone.atelier.name
  project      = var.project_id

  rrdatas = ["ghs.googlehosted.com."]
}

# Wildcard CNAME for subdomains
resource "google_dns_record_set" "wildcard" {
  name         = "*.atelier.autonomous-agent.dev."
  type         = "CNAME"
  ttl          = 300
  managed_zone = google_dns_managed_zone.atelier.name
  project      = var.project_id

  rrdatas = ["ghs.googlehosted.com."]
}

# ---------------------------------------------------------------------------
# Google-Managed Wildcard Certificate (Certificate Manager)
# ---------------------------------------------------------------------------

resource "google_certificate_manager_dns_authorization" "atelier" {
  name        = "atelier-dns-auth"
  description = "DNS authorization for Atelier wildcard certificate"
  domain      = "atelier.autonomous-agent.dev"
  project     = var.project_id

  depends_on = [google_project_service.certificate_manager]
}

# DNS record for certificate validation
resource "google_dns_record_set" "cert_validation" {
  name         = google_certificate_manager_dns_authorization.atelier.dns_resource_record[0].name
  type         = google_certificate_manager_dns_authorization.atelier.dns_resource_record[0].type
  ttl          = 300
  managed_zone = google_dns_managed_zone.atelier.name
  project      = var.project_id

  rrdatas = [google_certificate_manager_dns_authorization.atelier.dns_resource_record[0].data]
}

resource "google_certificate_manager_certificate" "wildcard" {
  name        = "atelier-wildcard-cert"
  description = "Google-managed wildcard cert for *.atelier.autonomous-agent.dev"
  project     = var.project_id
  labels      = var.labels

  managed {
    domains = [
      "atelier.autonomous-agent.dev",
      "*.atelier.autonomous-agent.dev",
    ]
    dns_authorizations = [
      google_certificate_manager_dns_authorization.atelier.id,
    ]
  }

  depends_on = [google_dns_record_set.cert_validation]
}

# ---------------------------------------------------------------------------
# Certificate Map (for Load Balancer integration)
# ---------------------------------------------------------------------------

resource "google_certificate_manager_certificate_map" "atelier" {
  name        = "atelier-cert-map"
  description = "Certificate map for Atelier services"
  project     = var.project_id
  labels      = var.labels
}

resource "google_certificate_manager_certificate_map_entry" "wildcard" {
  name         = "atelier-wildcard-entry"
  map          = google_certificate_manager_certificate_map.atelier.name
  certificates = [google_certificate_manager_certificate.wildcard.id]
  hostname     = "*.atelier.autonomous-agent.dev"
  project      = var.project_id
  labels       = var.labels
}

resource "google_certificate_manager_certificate_map_entry" "apex" {
  name         = "atelier-apex-entry"
  map          = google_certificate_manager_certificate_map.atelier.name
  certificates = [google_certificate_manager_certificate.wildcard.id]
  hostname     = "atelier.autonomous-agent.dev"
  project      = var.project_id
  labels       = var.labels
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "dns_zone_name_servers" {
  description = "Name servers for the Atelier DNS zone"
  value       = google_dns_managed_zone.atelier.name_servers
}

output "wildcard_cert_id" {
  description = "Certificate Manager wildcard certificate ID"
  value       = google_certificate_manager_certificate.wildcard.id
}

output "cert_map_id" {
  description = "Certificate map ID for Load Balancer integration"
  value       = google_certificate_manager_certificate_map.atelier.id
}
