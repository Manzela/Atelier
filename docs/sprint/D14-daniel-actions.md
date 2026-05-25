# Daniel Actions — Day 14 (2026-05-28)

These are GCP-gated actions that require your interactive credentials.
All code is ready; these are the deployment steps.

## Order-dependent actions (run in sequence)

### 1. Create IAM service account

```bash
gcloud iam service-accounts create atelier-runtime \
  --project=atelier-build-2026 \
  --display-name="Atelier Runtime SA" \
  --description="Main runtime SA for Atelier Cloud Run + BigQuery + Vertex"
```

### 2. Apply Terraform (review plan first)

```bash
cd infra/terraform
terraform init
terraform plan -var-file=staging.tfvars   # REVIEW OUTPUT
terraform apply -var-file=staging.tfvars  # Only after reviewing plan
```

Expected outputs: `staging_url` (Cloud Run URL), `bigquery_dataset_id`

### 3. Migrate GEAP secret

```bash
bash scripts/migration/07_migrate_geap_secret.sh --wet
```

### 4. Apply branch protection

```bash
bash scripts/governance/protect_phase_1.sh --apply
```

### 5. Deploy to Cloud Run (live)

```bash
agents-cli deploy \
  --project=atelier-build-2026 \
  --target=cloud_run \
  --service=atelier-staging
```

After this: verify health endpoint responds.

### 6. Submit to UIBench (2h session)

Go to UIBench submission portal → submit Atelier → record DPO labels.

### 7. Phase 1 Gate G1 — verify Cloud Run /health

```bash
STAGING_URL=$(gcloud run services describe atelier-staging \
  --project=atelier-build-2026 \
  --region=europe-west4 \
  --format='value(status.url)')
curl -sf "$STAGING_URL/health"  # Should return 200
```

## Tag the gate (after all 7 steps pass)

```bash
git tag -a v0.1.0-phase-1-gate -m "Phase 1 Gate: all 7 criteria green"
git push origin v0.1.0-phase-1-gate
```
