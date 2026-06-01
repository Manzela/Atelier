# Govern Pillar — Registry · Identity · Gateway · Policy · Security · Audit

> How Atelier ensures safe, auditable, and compliant autonomous agent operation.

## Overview

The **Govern** pillar provides six interlocking layers of control that ensure Atelier operates safely, within policy, and with full audit trails. Every design generation, evaluation, and deployment is governed by these controls.

```
┌─────────────────────────────────────────────────────────────────┐
│                        GOVERNANCE STACK                         │
├──────────┬──────────┬──────────┬──────────┬──────────┬─────────┤
│ Registry │ Identity │ Gateway  │  Policy  │ Security │  Audit  │
│          │          │          │          │          │         │
│ Feature  │ Firebase │ IAP +    │ Safety   │ PII      │ OTel +  │
│ routing  │ Auth +   │ Cloud    │ settings │ scrubber │ BQ      │
│ manifest │ IAP      │ Run      │ Governor │ KMS      │ traces  │
└──────────┴──────────┴──────────┴──────────┴──────────┴─────────┘
```

---

## 1. Registry — Feature Routing Manifest

All features are centrally registered in `features.json` with schema-validated metadata. The routing manifest controls which features are available per environment and tenant.

```json
// features.json (excerpt)
{
  "feature_id": "F0042",
  "name": "multi-judge-consensus",
  "status": "active",
  "phase": 2,
  "evidence_tests": ["test_consensus_basic", "test_consensus_quorum"]
}
```

**Key files:**

- [`features.json`](../../features.json) — Central feature registry
- [`scripts/gates/`](../../scripts/gates/) — Gate validation scripts

---

## 2. Identity — Firebase Auth + IAP

All API endpoints require authentication. Two layers enforce identity:

| Layer                   | Technology                 | Scope                |
| ----------------------- | -------------------------- | -------------------- |
| **Application auth**    | Firebase Authentication    | End-user JWT tokens  |
| **Infrastructure auth** | Identity-Aware Proxy (IAP) | Google Cloud ingress |

```python
# From atelier-core/src/atelier/auth/firebase.py

async def require_auth(request: Request) -> AuthenticatedUser:
    """Verify Firebase JWT and extract user claims.

    Bypass available via FIREBASE_DISABLE_AUTH=true (dev only).
    """
```

IAP is configured via Terraform to restrict Cloud Run ingress to authenticated Google accounts only:

```hcl
# From atelier-deploy/terraform/iap.tf

resource "google_iap_web_backend_service_iam_member" "iap_access" {
  role   = "roles/iap.httpsResourceAccessor"
  member = "serviceAccount:${google_service_account.api.email}"
}
```

---

## 3. Gateway — Cloud Run IAP-Protected Ingress

Cloud Run serves as the gateway with IAP-enforced access control. No public `allUsers` binding exists — all traffic must pass through IAP.

```hcl
# From atelier-deploy/terraform/main.tf

resource "google_cloud_run_v2_service" "api" {
  name     = "atelier-api-${var.environment}"
  location = var.region

  template {
    service_account = google_service_account.api.email
    # ...
  }
}

# IAP-protected ingress — see iap.tf
# The allUsers binding has been removed for security.
```

CORS is restricted to specific dashboard origins:

```python
# Multi-origin support via comma-separated env var
raw_origins = os.getenv("ATELIER_DASHBOARD_ORIGIN", "http://localhost:5173")
allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
```

---

## 4. Policy — Safety Settings + Governor Budget Caps

### Safety Settings (AG-04)

All LLM calls pass through `generate_content_config` with explicit safety thresholds:

```python
# AG-04 compliant — safety via generate_content_config
LlmAgent(
    model="gemini-3-pro",
    generate_content_config=genai_types.GenerateContentConfig(
        safety_settings=default_safety_settings(),
    ),
)
```

### Governor Usage Cap (token-only)

Usage governance is **token-only** (AT-095, §13.2): there is **no USD/cost cap and no dollar meter**. The sole cap is a **per-user lifetime 5,000,000-token** hard cap — a cumulative per-Firebase-uid counter (`input + output + thinking`) persisted in Firestore and enforced server-side **pre-flight** (before any Vertex call). A breach is **fail-loud** (never self-healed) and the API returns a structured, branded 402:

```json
{
  "error": "token_cap_exhausted",
  "code": 402,
  "title": "Account usage limit reached",
  "detail": "You've reached this account's usage limit. Contact administrator to continue.",
  "docs_url": "https://atelier.autonomous-agent.dev/docs/limits"
}
```

When the usage store itself is unavailable (transient outage or a corrupt counter) the Governor fails **closed** but acknowledges honestly with a distinct, retryable **HTTP 503** (`usage_unavailable` + `Retry-After`) — never the permanent cap message. A per-window request-rate limit returns **429**.

---

## 5. Security — PII Scrubber + KMS Per-Tenant Encryption

### PII Scrubber (AG-10)

The `PiiScrubSpanProcessor` redacts sensitive data from OpenTelemetry spans before they leave the process:

```python
# From atelier-core/src/atelier/observability/scrubber.py

class PiiScrubSpanProcessor(SpanProcessor):
    """Redacts PII from span attributes before export."""
```

### KMS Per-Tenant Encryption

Each tenant's data is encrypted with a dedicated Cloud KMS key, enabling GDPR right-to-be-forgotten via key destruction:

```hcl
# From atelier-deploy/terraform/main.tf

resource "google_kms_key_ring" "tenant_keys" {
  name     = var.kms_key_ring
  location = "global"
}

resource "google_kms_crypto_key" "default_tenant" {
  name            = "default-tenant"
  key_ring        = google_kms_key_ring.tenant_keys.id
  rotation_period = "7776000s"  # 90 days
}
```

---

## 6. Audit — OTel Traces + BigQuery Trajectory Recording

Every pipeline execution is instrumented with OpenTelemetry and recorded to BigQuery:

| Signal             | Destination     | Retention |
| ------------------ | --------------- | --------- |
| Distributed traces | Cloud Trace     | 30 days   |
| Structured logs    | Cloud Logging   | 90 days   |
| Trajectory records | BigQuery        | Permanent |
| Judge votes        | BigQuery (JSON) | Permanent |

The [Bench Dashboard](https://atelier.autonomous-agent.dev/bench/) provides real-time visibility into all governance metrics.

---

## Related Files

- [`firebase.py`](../../atelier-core/src/atelier/auth/firebase.py) — Firebase Auth middleware
- [`iap.tf`](../../atelier-deploy/terraform/iap.tf) — IAP configuration
- [`main.tf`](../../atelier-deploy/terraform/main.tf) — Cloud Run + KMS
- [`scrubber.py`](../../atelier-core/src/atelier/observability/scrubber.py) — PII redaction
- [`app.py`](../../atelier-core/src/atelier/api/app.py) — CORS + Governor error handling
- [`features.json`](../../features.json) — Feature registry
