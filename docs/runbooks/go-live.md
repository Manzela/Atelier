# Go-Live Runbook

The ordered, end-to-end sequence to take Atelier from a green `main` to a live
production submission. Every step is operator-run and requires GCP credentials;
this document supplies the exact command, the expected output, and the recovery
pointer for each.

Source of truth for resource names and variables:
`atelier-deploy/terraform/{main.tf,alb.tf,dns.tf,variables.tf}`. Recovery
procedures: [`rollback.md`](rollback.md).

Canonical coordinates: project `atelier-build-2026`, region `us-central1`,
domain `atelier.autonomous-agent.dev`.

---

## 0. Prerequisites (one-time)

### Tools

- `gcloud` CLI, authenticated: `gcloud auth login` and
  `gcloud auth application-default login`
- `terraform` >= 1.5
- `python` with `atelier-core` installed in `.venv` (Agent Engine deploy)
- `firebase` CLI (Hosting, if redeploying the dashboard)

### Access and external preconditions

- GCP project `atelier-build-2026` exists with billing enabled.
- Operator IAM: project `editor` (or the narrower set in `rollback.md` plus
  `aiplatform.admin` and `modelarmor.admin`).
- Domain `autonomous-agent.dev` registered, with registrar NS records delegated
  to the Cloud DNS zone created by `dns.tf`.
- Required APIs enabled: `run`, `aiplatform`, `bigquery`, `secretmanager`,
  `certificatemanager`, `dns`, `compute`, `modelarmor`.

### Verify the served model is GA (AT-024)

```bash
gcloud ai models list --region=us-central1 --project=atelier-build-2026 \
  | grep -i gemini-2.5-pro
```

Expected: a `gemini-2.5-pro` entry. If absent, do not proceed — the served-model
pin must resolve to a GA model.

### Create the Terraform state bucket (Terraform cannot self-create its backend)

```bash
gcloud storage buckets create gs://atelier-terraform-state \
  --project=atelier-build-2026 --location=us-central1 --uniform-bucket-level-access
```

Expected: `Creating gs://atelier-terraform-state/...done.` Skip if it already
exists.

---

## 1. Configure Terraform variables

```bash
cd atelier-deploy/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: set project_id and environment="production".
```

The `agent_engine_id` is intentionally left empty here; it is filled in step 3
after the Agent Engine is deployed.

---

## 2. Terraform init, plan, apply (infrastructure)

```bash
cd atelier-deploy/terraform
terraform init
terraform plan  -var-file=terraform.tfvars      # review the resource set
terraform apply -var-file=terraform.tfvars      # IRREVERSIBLE — creates billed infra
```

Expected: `Apply complete!` with the ALB IP, Cloud Run URL, and DNS zone in the
outputs. The managed certificate and ALB take time to warm up (cert provisioning
plus DNS propagation can run to the better part of a day); the domain will not
serve HTTPS until the certificate reaches `ACTIVE`.

Recovery: certificate stuck, DNS not resolving, or a bad revision —
[`rollback.md`](rollback.md).

---

## 3. Deploy the Agent Engine, then re-apply Terraform with its id

```bash
cd "$(git rev-parse --show-toplevel)"
export GOOGLE_CLOUD_PROJECT=atelier-build-2026
export GOOGLE_CLOUD_LOCATION=us-central1
make deploy-agent-engine
```

Expected: a final stdout line of the form
`projects/atelier-build-2026/locations/us-central1/reasoningEngines/<id>`. The
deploy is fail-loud and validates the `google-adk==2.1.x` pin before publishing.

Copy that resource name into `terraform.tfvars` as `agent_engine_id`, then
re-apply so the Cloud Run service points at the engine:

```bash
cd atelier-deploy/terraform
terraform apply -var-file=terraform.tfvars
```

---

## 4. Model Armor template (optional; enables the NL-injection guard, AT-081)

The before-model callback is fail-closed only when Model Armor is enabled. The
guard is off by default (`default_model_armor_config()` returns `None` unless
`ATELIER_MODEL_ARMOR_ENABLED` is truthy), so this step is optional for the
submission but recommended for production. There is no Terraform resource for the
template (provider gap), so it is created via `gcloud`.

```bash
gcloud model-armor templates create atelier-default \
  --location=us-central1 --project=atelier-build-2026 \
  --pi-and-jailbreak-filter-settings-enforcement=enabled \
  --malicious-uri-filter-settings-enforcement=enabled \
  --template-metadata-log-sanitize-operations
```

For the prompt-injection confidence threshold, add
`--pi-and-jailbreak-filter-settings-confidence-level=<LEVEL>`; run
`gcloud model-armor templates create --help` to confirm the accepted enum on the
installed CLI before setting it.

Then grant the API service account use of the template and turn the guard on at
the Cloud Run service:

```bash
gcloud run services update atelier-api --region=us-central1 \
  --update-env-vars=ATELIER_MODEL_ARMOR_ENABLED=true,ATELIER_MODEL_ARMOR_TEMPLATE=atelier-default
```

The `atelier-api` service account needs
`modelarmor.templates.useToSanitizeUserPrompt` (role `roles/modelarmor.user`).

---

## 5. Smoke probe (unauthenticated)

```bash
bash scripts/ci/smoke_probe.sh https://atelier.autonomous-agent.dev
```

Expected: `200` on `/health`, `/`, `/.well-known/agent-card.json`, and
`/openapi.json` (the last containing `/v1/generate`, `/v1/replay`, `/v1/dream`).

---

## 6. Production-readiness (authenticated, three live runs)

```bash
ATELIER_BASE_URL=https://atelier.autonomous-agent.dev \
ATELIER_ID_TOKEN="<firebase id token for a signed-in user>" \
make production-readiness
```

Expected: three consecutive golden-path runs, each terminating in `accepted`/`pass`
with `composite_score >= 0.70` and non-zero token usage. Each run takes 20-30
minutes (see ADR-0025); budget roughly 90 minutes for the set.

---

## 7. Final submission

```bash
make submission-check          # audits docs/SUBMISSION.md for required fields
```

Then:

1. Record the live production walkthrough video.
2. Paste the video URL into the `Demo video` row of
   [`../SUBMISSION.md`](../SUBMISSION.md) (replacing the `TODO` placeholder) and
   re-run `make submission-check` until it is clean.
3. File on DevPost (Track: Build) with the live URL, repository, and demo video.

---

## Step summary

| #   | Step                           | Command                                        | Credentialed | Reversible                      |
| --- | ------------------------------ | ---------------------------------------------- | ------------ | ------------------------------- |
| 0   | Prerequisites + state bucket   | `gcloud storage buckets create ...`            | yes          | n/a                             |
| 1   | Configure tfvars               | `cp terraform.tfvars.example terraform.tfvars` | no           | yes                             |
| 2   | Infra apply                    | `terraform apply`                              | yes          | via rollback.md                 |
| 3   | Agent Engine deploy + re-apply | `make deploy-agent-engine`                     | yes          | redeploy/rollback               |
| 4   | Model Armor (optional)         | `gcloud model-armor templates create ...`      | yes          | delete template                 |
| 5   | Smoke probe                    | `scripts/ci/smoke_probe.sh`                    | no           | n/a                             |
| 6   | Production-readiness           | `make production-readiness`                    | yes          | n/a                             |
| 7   | Submission                     | `make submission-check` + DevPost              | mixed        | DevPost editable until deadline |
