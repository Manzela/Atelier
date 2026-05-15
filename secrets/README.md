# Atelier Secrets

> **NEVER commit plaintext secrets to this repo.** The `.gitignore` blocks `*.env`, `*.json`, `*.txt`, `*.pem`, `*.key` here. Only `*.sops` (encrypted) + `*.template.txt` (placeholder) + this `README.md` may be committed.

## Production secret backend: GCP Secret Manager

All Atelier production secrets live in **GCP Secret Manager** on the `i-for-ai` project (or the dedicated Atelier project once created — see PRD §15 D2).

### Stored secrets

| Secret name                  | Purpose                                                                                                                           | Resource                                                                        |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `atelier-geap-api-key`       | Gemini Enterprise Agent Platform API key (used as `X-Goog-Api-Key` header for GEAP-direct calls; ADC is preferred for production) | `projects/85113401879/secrets/atelier-geap-api-key`                             |
| `atelier-stitch-mcp-key`     | Stitch MCP API key (already configured in `~/.claude.json` user MCP scope as Bearer header on the Stitch HTTP endpoint)           | TBD — stored in `~/.claude.json` user scope; not yet mirrored to Secret Manager |
| `atelier-telegram-bot-token` | Telegram bot for async tasks + approval gates                                                                                     | TBD — Phase 1 D2                                                                |
| `atelier-stripe-publishable` | Stripe public key                                                                                                                 | TBD — Phase 1 D2                                                                |
| `atelier-stripe-secret`      | Stripe secret key                                                                                                                 | TBD — Phase 3 (when billing goes live)                                          |
| `atelier-vanta-api-key`      | Vanta evidence collection (compliance scaffold)                                                                                   | TBD — month 6                                                                   |

### Retrieve a secret at runtime

```bash
# Single retrieval (returns latest version)
gcloud secrets versions access latest \
  --secret=atelier-geap-api-key \
  --project=i-for-ai

# In Python (atelier-core code)
from google.cloud import secretmanager

client = secretmanager.SecretManagerServiceClient()
name = "projects/i-for-ai/secrets/atelier-geap-api-key/versions/latest"
response = client.access_secret_version(request={"name": name})
api_key = response.payload.data.decode("UTF-8")
```

### Add a new secret

```bash
# Pipe value via stdin (NEVER write the value to a file or echo it on the command line)
printf "%s" "<paste-value-here>" | gcloud secrets create <secret-name> \
  --data-file=- \
  --replication-policy="automatic" \
  --labels="project=atelier" \
  --project=i-for-ai
```

### Rotate a secret

```bash
# Add a new version (latest pointer auto-updates)
printf "%s" "<new-value>" | gcloud secrets versions add <secret-name> \
  --data-file=- \
  --project=i-for-ai

# Disable old version after grace period
gcloud secrets versions disable <old-version-number> \
  --secret=<secret-name> \
  --project=i-for-ai
```

### IAM — who can read which secret

By default, secrets are readable by:

- Project owners (Daniel, currently)
- Service accounts explicitly granted `roles/secretmanager.secretAccessor`

Atelier service accounts (Phase 1 D2 setup):

- `atelier-api-sa@i-for-ai.iam.gserviceaccount.com` — runtime API
- `atelier-agent-sa@i-for-ai.iam.gserviceaccount.com` — long-running agent jobs
- `atelier-eval-sa@i-for-ai.iam.gserviceaccount.com` — eval suite jobs
- `atelier-deploy-sa@i-for-ai.iam.gserviceaccount.com` — CI/CD via Workload Identity Federation

Each SA gets `roles/secretmanager.secretAccessor` on only the secrets it needs.

## Optional: sops + age (deferred)

Per PRD §10 inheritance map, `sops + age` is the AutonomousAgent ADR 0004 pattern for offline-dev secret encryption committed to git. **Atelier defers sops + age** in favor of Secret Manager for everything because:

1. Atelier is cloud-deployed from D1 (no offline mode)
2. Secret Manager has CMEK + IAM + audit log + versioning + GCP Access Transparency
3. Avoids dual-key-management surface

If later we need offline dev workflows, `.sops.yaml` template ready to drop in.

## What NEVER goes here

- Plaintext API keys / tokens
- Service account JSON files
- TLS private keys
- BYOK customer KMS keys (those go in **per-tenant Cloud KMS** key rings, not here)
- Trajectory data with PII (those go to BigQuery + per-subject KMS encryption)
