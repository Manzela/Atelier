# Rollback Runbook

Covers three failure modes: Certificate Manager cert stuck in a non-ACTIVE state,
DNS misconfiguration preventing name resolution, and a bad Cloud Run deploy that
must be rolled back to a prior revision.

Source of truth for resource names: `atelier-deploy/terraform/main.tf`,
`atelier-deploy/terraform/dns.tf`, `atelier-deploy/terraform/variables.tf`.

---

## Prerequisites

### Required tools

- `gcloud` CLI authenticated to project `atelier-build-2026`
- `firebase` CLI authenticated (`firebase login`) — for Hosting rollback only
- `python` with `atelier-core` installed (Agent Engine rollback only)

### Verify auth and project before any step

```bash
gcloud auth print-identity-token --quiet > /dev/null \
  && echo "auth ok"

gcloud config set project atelier-build-2026
gcloud config set run/region us-central1
```

Expected output: `auth ok` followed by two `Updated property` lines.

If this fails: run `gcloud auth login` or `gcloud auth application-default login`.

### Required IAM roles

| Task                                | Minimum role                                                                                                                   |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Cloud Run traffic migration         | `roles/run.admin` on project `atelier-build-2026`                                                                              |
| Certificate Manager describe/verify | `roles/certificatemanager.viewer` (read) — no write needed for verification; `roles/certificatemanager.editor` to re-provision |
| Cloud DNS record inspection         | `roles/dns.reader`                                                                                                             |
| Firebase Hosting rollback           | Firebase project `atelier-build-2026` with `roles/firebasehosting.admin`                                                       |
| Agent Engine re-deploy              | `roles/aiplatform.admin`                                                                                                       |

---

## Section 1: Certificate failure recovery

**When to use**: `https://atelier.autonomous-agent.dev` or any subdomain returns a
certificate error, or the cert is stuck in state `PROVISIONING` for more than 20 minutes.

### 1.1 Describe the cert state

The certificate is `atelier-wildcard-cert` in project `atelier-build-2026`.
The DNS authorization resource is `atelier-dns-auth`.

```bash
gcloud certificate-manager certificates describe atelier-wildcard-cert \
  --project atelier-build-2026
```

Expected output (healthy):

```
...
managed:
  ...
  state: ACTIVE
...
```

If `state: PROVISIONING` or `state: FAILED`, continue to 1.2.

### 1.2 Check the DNS authorization record

The DNS authorization `atelier-dns-auth` requires a CNAME record in the
`atelier-zone` Cloud DNS managed zone. This record is provisioned by Terraform
resource `google_dns_record_set.cert_validation` (`atelier-deploy/terraform/dns.tf`
lines 93-101).

Retrieve the expected record from the authorization:

```bash
gcloud certificate-manager dns-authorizations describe atelier-dns-auth \
  --project atelier-build-2026 \
  --format="value(dnsResourceRecord)"
```

This prints three fields: `name`, `type` (`CNAME`), and `data`.

Verify the record exists in Cloud DNS:

```bash
gcloud dns record-sets list \
  --zone atelier-zone \
  --project atelier-build-2026 \
  --filter="type=CNAME"
```

If the cert-validation CNAME is absent or points to the wrong data value, re-apply
Terraform:

```bash
cd atelier-deploy
terraform apply -target=google_dns_record_set.cert_validation \
  -var="project_id=atelier-build-2026"
```

Pass criteria: the record in Cloud DNS matches the `data` field from step 1.2 exactly.

### 1.3 Wait for ACTIVE state

Certificate Manager polls DNS every ~10 minutes after a record change.
Re-provision of a Google-managed cert after a DNS fix typically completes within
15-30 minutes. Re-check with:

```bash
gcloud certificate-manager certificates describe atelier-wildcard-cert \
  --project atelier-build-2026 \
  --format="value(managed.state)"
```

Pass criteria: output is `ACTIVE`.

If state remains `FAILED` after 30 minutes of the DNS record being correct, verify
that the cert map entries are intact:

```bash
gcloud certificate-manager maps describe atelier-cert-map \
  --project atelier-build-2026
```

Both entries (`atelier-wildcard-entry` for `*.atelier.autonomous-agent.dev` and
`atelier-apex-entry` for `atelier.autonomous-agent.dev`) must be present. If
either is missing, re-apply Terraform:

```bash
cd atelier-deploy
terraform apply -target=google_certificate_manager_certificate_map_entry.wildcard \
  -target=google_certificate_manager_certificate_map_entry.apex \
  -var="project_id=atelier-build-2026"
```

### What to do if this step fails

Escalate to on-call per `on-call.md`. Attach the full output of
`gcloud certificate-manager certificates describe atelier-wildcard-cert --format=json`.

---

## Section 2: DNS failure recovery

**When to use**: `atelier.autonomous-agent.dev` or subdomains fail to resolve, or
`dig` shows incorrect answers.

### 2.1 Verify NS delegation

The Cloud DNS managed zone `atelier-zone` is authoritative for `atelier.autonomous-agent.dev.`
(zone `dns_name` in `atelier-deploy/terraform/dns.tf` line 40). The parent zone for
`autonomous-agent.dev` must delegate with NS records to the Cloud DNS name servers.

Retrieve the Cloud DNS name servers:

```bash
gcloud dns managed-zones describe atelier-zone \
  --project atelier-build-2026 \
  --format="value(nameServers)"
```

Compare against what the parent zone currently delegates to:

```bash
dig NS atelier.autonomous-agent.dev +short
```

If the NS answers from `dig` differ from the Cloud DNS name servers, the parent
zone delegation is missing or stale. Update the NS records at the registrar or
parent Cloud DNS zone to match.

### 2.2 Verify service CNAME records

Two CNAME records route traffic to Google-hosted backends
(`ghs.googlehosted.com.`): `api.atelier.autonomous-agent.dev.` and
`*.atelier.autonomous-agent.dev.` — defined in `google_dns_record_set.api` and
`google_dns_record_set.wildcard` (`atelier-deploy/terraform/dns.tf` lines 58-77).

```bash
gcloud dns record-sets list \
  --zone atelier-zone \
  --project atelier-build-2026
```

Expected CNAME targets:

| Record                              | Type  | Target                  |
| ----------------------------------- | ----- | ----------------------- |
| `api.atelier.autonomous-agent.dev.` | CNAME | `ghs.googlehosted.com.` |
| `*.atelier.autonomous-agent.dev.`   | CNAME | `ghs.googlehosted.com.` |

If either record is absent or points elsewhere, re-apply Terraform:

```bash
cd atelier-deploy
terraform apply \
  -target=google_dns_record_set.api \
  -target=google_dns_record_set.wildcard \
  -var="project_id=atelier-build-2026"
```

### 2.3 Verify the cert-validation CNAME

As described in Section 1.2, the cert-validation record must also be present.
Confirm it appears in the `gcloud dns record-sets list` output with type `CNAME`
and matches the value from:

```bash
gcloud certificate-manager dns-authorizations describe atelier-dns-auth \
  --project atelier-build-2026 \
  --format="value(dnsResourceRecord.data)"
```

### 2.4 DNS propagation check

Cloud DNS changes propagate quickly (typically under 60 seconds globally). Verify
with:

```bash
dig api.atelier.autonomous-agent.dev CNAME +short
# Expected: ghs.googlehosted.com.

dig atelier.autonomous-agent.dev +short
# Expected: a Google IP from the ghs pool
```

Pass criteria: both records resolve to the expected targets.

### What to do if this step fails

If NS delegation is correct and records are correct but resolution still fails
after 5 minutes, verify DNSSEC is not causing a validation failure. The zone has
DNSSEC enabled (`dnssec_config.state = "on"` in `dns.tf` line 47-49). If the DS
record is missing at the parent registrar, DNSSEC will break resolution.
Escalate to on-call per `on-call.md`.

---

## Section 3: Deploy failure recovery

### 3.1 Cloud Run: roll back to the last-known-good revision

**When to use**: a deploy to `atelier-api-staging` introduced a regression
(health probe failing, 5xx rate elevated, startup crashes).

The service is `atelier-api-staging` in region `us-central1`, provisioned by
`google_cloud_run_v2_service.api` (`atelier-deploy/terraform/main.tf` lines 132-207).
The service name includes the `environment` variable value: `atelier-api-staging`
for the default `staging` environment.

#### 3.1.1 List revisions

```bash
gcloud run revisions list \
  --service atelier-api-staging \
  --region us-central1 \
  --project atelier-build-2026 \
  --sort-by="~creationTimestamp" \
  --limit 10
```

Identify the last-known-good revision by timestamp and tag. Revisions named
`atelier-api-staging-NNNNN` where NNNNN is a Cloud Run-assigned suffix.

#### 3.1.2 Route 100% traffic to the prior revision

```bash
gcloud run services update-traffic atelier-api-staging \
  --region us-central1 \
  --project atelier-build-2026 \
  --to-revisions REVISION_NAME=100
```

Replace `REVISION_NAME` with the name from 3.1.1 (example:
`atelier-api-staging-00042-abc`).

Expected output: `Traffic:  100% REVISION_NAME`.

#### 3.1.3 Verify the health probe

```bash
SVCURL=$(gcloud run services describe atelier-api-staging \
  --region us-central1 \
  --project atelier-build-2026 \
  --format="value(status.url)")

curl -sI "${SVCURL}/health" | head -n 1
```

Note: IAP is active (`iap.tf`). The `/health` endpoint may require a valid
identity token. Use:

```bash
curl -sI "${SVCURL}/health" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  | head -n 1
```

Pass criteria: `HTTP/2 200`.

### 3.2 Firebase Hosting: revert the pinned Cloud Run revision

Firebase Hosting rewrites `/api/**` to `atelier-api-staging` in `us-central1`
with `pinTag: true` (`firebase.json` — `hosting[0].rewrites[0]`).

#### 3.2.1 List recent Hosting releases

```bash
firebase hosting:channel:list --project atelier-build-2026
```

Identify the last-known-good release ID from the `RELEASE TIME` column.

#### 3.2.2 Roll back the live channel

Refer to the official Firebase CLI documentation for `firebase hosting:clone` or
`firebase hosting:rollback` for the exact flags available in the installed CLI
version. As of Firebase CLI v13+, the rollback command is:

```bash
firebase hosting:rollback --project atelier-build-2026 --site atelier-build-2026
```

This promotes the most recent non-current release to live. If you need to target
a specific release, use `firebase hosting:clone` to copy a named version to the
live channel — see the Firebase Hosting CLI reference at
`https://firebase.google.com/docs/hosting/manage-hosting-resources`.

Pass criteria: the rollback completes without error and `firebase hosting:channel:list`
shows the expected release as `CURRENT`.

#### 3.2.3 Verify via curl

```bash
curl -sI "https://atelier-build-2026.web.app/api/health" | head -n 1
```

Pass criteria: `HTTP/2 200` (or the same response as before the bad deploy).

### 3.3 Agent Engine: re-deploy the Atelier Planner

**When to use**: the Vertex AI Agent Engine deployment of `atelier-planner-engine`
is in a broken state and must be re-deployed.

The deploy entrypoint is `atelier-core/src/atelier/agent_engine_deploy.py`. It
reads `GOOGLE_CLOUD_PROJECT` (default `atelier-build-2026`) and
`GOOGLE_CLOUD_LOCATION` (default `us-central1`).

#### 3.3.1 Set environment and run

```bash
cd /path/to/atelier-repo
export GOOGLE_CLOUD_PROJECT=atelier-build-2026
export GOOGLE_CLOUD_LOCATION=us-central1

python -m atelier.agent_engine_deploy
```

Expected terminal output:

```
INFO  Initializing vertexai for project atelier-build-2026 in us-central1
INFO  Deploying to Vertex AI Agent Engine...
INFO  Deployment complete. Resource name: projects/.../locations/us-central1/reasoningEngines/...
```

Pass criteria: `Deployment complete. Resource name:` line printed with no
`Deployment failed` log entry.

#### 3.3.2 Verify the deployed agent

```bash
gcloud ai reasoning-engines list \
  --project atelier-build-2026 \
  --region us-central1 \
  --filter="displayName=atelier-planner-engine"
```

Expected output: one row with state `ACTIVE`.

### What to do if any 3.x step fails

1. Check Cloud Run logs:
   `gcloud run revisions logs tail atelier-api-staging --region us-central1 --project atelier-build-2026`
2. Check Cloud Build history for the image that was deployed:
   `gcloud builds list --project atelier-build-2026 --limit 5`
3. Escalate to on-call per `on-call.md`.

---

## Section 4: Verification checklist

Run after any rollback to confirm the full stack is healthy.

### 4.1 Health probe

```bash
SVCURL=$(gcloud run services describe atelier-api-staging \
  --region us-central1 \
  --project atelier-build-2026 \
  --format="value(status.url)")

curl -sI "${SVCURL}/health" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  | head -n 1
```

Pass: `HTTP/2 200`.

### 4.2 Certificate ACTIVE

```bash
gcloud certificate-manager certificates describe atelier-wildcard-cert \
  --project atelier-build-2026 \
  --format="value(managed.state)"
```

Pass: `ACTIVE`.

### 4.3 DNS propagation

```bash
dig api.atelier.autonomous-agent.dev CNAME +short
```

Pass: `ghs.googlehosted.com.`

### 4.4 Firebase Hosting live channel

```bash
firebase hosting:channel:list --project atelier-build-2026 \
  --site atelier-build-2026 2>/dev/null | grep CURRENT
```

Pass: the expected release version shows `CURRENT`.

### 4.5 Agent Engine

```bash
gcloud ai reasoning-engines list \
  --project atelier-build-2026 \
  --region us-central1 \
  --filter="displayName=atelier-planner-engine" \
  --format="value(state)"
```

Pass: `ACTIVE`.
