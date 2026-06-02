# Global external Application Load Balancer for Atelier (AT-083, PRD v2.2 §12 E8).
#
# Fronts the Cloud Run API/dashboard service with:
#   - a serverless network endpoint group (NEG) -> Cloud Run
#   - a backend service with a Cloud Armor security policy (adaptive L7 DDoS
#     defense + per-IP request-rate throttle)
#   - a URL map + HTTPS target proxy bound to the Certificate Manager cert map
#     (dns.tf) for *.atelier.autonomous-agent.dev
#   - a global static IP mapped to the apex domain via an A record
#   - an HTTP listener that redirects to HTTPS
#
# This is the public ingress for atelier.autonomous-agent.dev. Defense in depth:
# Cloud Armor throttles at the edge so the per-user token cap (AT-095) cannot be
# burned in a burst, and the application layer enforces Firebase Google SSO plus
# the token cap (PRD §13). The certificate must reach ACTIVE state (>= 1 day of
# DNS validation, G9) before the custom domain serves traffic.
#
# Apply is operator-gated (requires GCP credentials for the serving project).

# ---------------------------------------------------------------------------
# Global static IP
# ---------------------------------------------------------------------------

resource "google_compute_global_address" "atelier" {
  name        = "atelier-lb-ip-${var.environment}"
  description = "Global static IP for the Atelier external load balancer"
  project     = var.project_id

  depends_on = [google_project_service.apis["compute.googleapis.com"]]
}

# ---------------------------------------------------------------------------
# Serverless NEG -> Cloud Run
# ---------------------------------------------------------------------------

resource "google_compute_region_network_endpoint_group" "api" {
  name                  = "atelier-api-neg-${var.environment}"
  region                = var.region
  network_endpoint_type = "SERVERLESS"
  project               = var.project_id

  cloud_run {
    service = google_cloud_run_v2_service.api.name
  }

  depends_on = [google_project_service.apis["compute.googleapis.com"]]
}

# ---------------------------------------------------------------------------
# Cloud Armor security policy (adaptive DDoS + per-IP rate limit)
# ---------------------------------------------------------------------------

resource "google_compute_security_policy" "atelier" {
  name        = "atelier-armor-${var.environment}"
  description = "Adaptive L7 DDoS defense + per-IP request-rate throttle for the Atelier LB"
  project     = var.project_id

  adaptive_protection_config {
    layer_7_ddos_defense_config {
      enable = true
    }
  }

  # Per-client-IP request-rate throttle so a single source cannot burn the
  # per-user token cap (AT-095) in a burst.
  rule {
    action      = "throttle"
    priority    = 1000
    description = "Per-IP request-rate throttle (anti burn-the-cap)"

    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }

    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = var.armor_rate_limit_count
        interval_sec = var.armor_rate_limit_interval_sec
      }
    }
  }

  # Default allow; the application layer enforces auth and the token cap.
  rule {
    action      = "allow"
    priority    = 2147483647
    description = "Default rule"

    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }

  depends_on = [google_project_service.apis["compute.googleapis.com"]]
}

# ---------------------------------------------------------------------------
# Backend service (serverless NEG + Cloud Armor)
# ---------------------------------------------------------------------------

resource "google_compute_backend_service" "api" {
  name                  = "atelier-api-backend-${var.environment}"
  project               = var.project_id
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  security_policy       = google_compute_security_policy.atelier.id
  timeout_sec           = 120

  backend {
    group = google_compute_region_network_endpoint_group.api.id
  }

  log_config {
    enable      = true
    sample_rate = 1.0
  }
}

# ---------------------------------------------------------------------------
# URL maps (main + HTTP->HTTPS redirect)
# ---------------------------------------------------------------------------

resource "google_compute_url_map" "atelier" {
  name            = "atelier-urlmap-${var.environment}"
  project         = var.project_id
  default_service = google_compute_backend_service.api.id
}

resource "google_compute_url_map" "https_redirect" {
  name    = "atelier-https-redirect-${var.environment}"
  project = var.project_id

  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

# ---------------------------------------------------------------------------
# Target proxies (HTTPS bound to the Certificate Manager cert map; HTTP redirect)
# ---------------------------------------------------------------------------

resource "google_compute_target_https_proxy" "atelier" {
  name            = "atelier-https-proxy-${var.environment}"
  project         = var.project_id
  url_map         = google_compute_url_map.atelier.id
  certificate_map = "//certificatemanager.googleapis.com/${google_certificate_manager_certificate_map.atelier.id}"
}

resource "google_compute_target_http_proxy" "atelier" {
  name    = "atelier-http-proxy-${var.environment}"
  project = var.project_id
  url_map = google_compute_url_map.https_redirect.id
}

# ---------------------------------------------------------------------------
# Global forwarding rules (443 HTTPS, 80 HTTP redirect)
# ---------------------------------------------------------------------------

resource "google_compute_global_forwarding_rule" "https" {
  name                  = "atelier-https-fr-${var.environment}"
  project               = var.project_id
  load_balancing_scheme = "EXTERNAL_MANAGED"
  port_range            = "443"
  target                = google_compute_target_https_proxy.atelier.id
  ip_address            = google_compute_global_address.atelier.id
}

resource "google_compute_global_forwarding_rule" "http" {
  name                  = "atelier-http-fr-${var.environment}"
  project               = var.project_id
  load_balancing_scheme = "EXTERNAL_MANAGED"
  port_range            = "80"
  target                = google_compute_target_http_proxy.atelier.id
  ip_address            = google_compute_global_address.atelier.id
}

# ---------------------------------------------------------------------------
# Apex DNS A record -> load balancer IP
# ---------------------------------------------------------------------------

resource "google_dns_record_set" "apex" {
  name         = "atelier.autonomous-agent.dev."
  type         = "A"
  ttl          = 300
  managed_zone = google_dns_managed_zone.atelier.name
  project      = var.project_id

  rrdatas = [google_compute_global_address.atelier.address]
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "load_balancer_ip" {
  description = "Global static IP of the Atelier external load balancer"
  value       = google_compute_global_address.atelier.address
}
