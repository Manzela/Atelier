#!/usr/bin/env bash
# scripts/migration/01_inventory.sh
#
# Enumerate every billable/persistent resource in i-for-ai that touches Atelier.
# Per §2.1 of the post-R4 strategic roadmap.
#
# Usage:
#   DRY_RUN=1 bash scripts/migration/01_inventory.sh          # default: dry-run
#   DRY_RUN=0 bash scripts/migration/01_inventory.sh > audit/migration/inventory-i-for-ai-$(date +%F).json
set -euo pipefail

DRY_RUN="${DRY_RUN:-1}"
PROJECT="i-for-ai"
PREFIX=""
[[ "${DRY_RUN}" == "1" ]] && PREFIX="DRY-RUN: "

echo "${PREFIX}Inventorying all resources in project ${PROJECT}" >&2

if [[ "${DRY_RUN}" == "1" ]]; then
  echo "${PREFIX}Would run: gcloud asset search-all-resources --project=${PROJECT} --filter='name~atelier|labels.product=atelier'" >&2
  echo "${PREFIX}Would enumerate: Cloud Run, Vertex AI endpoints, tuned models, BigQuery, GCS, Pub/Sub, Cloud SQL, Firestore, Cloud Build, Artifact Registry, Cloud Functions, Service Accounts, Secrets, Scheduler, Workflows" >&2
  echo "${PREFIX}Output would be saved to audit/migration/inventory-i-for-ai-<date>.json" >&2
  exit 0
fi

gcloud config set project "${PROJECT}" --quiet

manifest=$(jq -n --arg project "${PROJECT}" '{project: $project, snapshot_at: now | todate, resources: {}}')

# 1. Cloud Run services
manifest=$(echo "${manifest}" | jq --argjson v "$(gcloud run services list --format=json)" '.resources.cloud_run = $v')

# 2. Vertex AI endpoints
manifest=$(echo "${manifest}" | jq --argjson v "$(gcloud ai endpoints list --region=us-central1 --format=json 2>/dev/null || echo '[]')" '.resources.vertex_endpoints_us_central1 = $v')

# 3. Vertex AI tuned models
manifest=$(echo "${manifest}" | jq --argjson v "$(gcloud ai models list --region=us-central1 --format=json 2>/dev/null || echo '[]')" '.resources.vertex_tuned_models = $v')

# 4. BigQuery datasets
manifest=$(echo "${manifest}" | jq --argjson v "$(bq ls --format=prettyjson --max_results=200 2>/dev/null || echo '[]')" '.resources.bigquery_datasets = $v')

# 5. GCS buckets
manifest=$(echo "${manifest}" | jq --argjson v "$(gcloud storage buckets list --format=json)" '.resources.gcs_buckets = $v')

# 6. Pub/Sub
manifest=$(echo "${manifest}" | jq --argjson v "$(gcloud pubsub topics list --format=json 2>/dev/null || echo '[]')" '.resources.pubsub_topics = $v')

# 7. Cloud SQL / Firestore
manifest=$(echo "${manifest}" | jq --argjson v "$(gcloud sql instances list --format=json 2>/dev/null || echo '[]')" '.resources.cloud_sql = $v')
manifest=$(echo "${manifest}" | jq --argjson v "$(gcloud firestore databases list --format=json 2>/dev/null || echo '[]')" '.resources.firestore = $v')

# 8. Cloud Build / Artifact Registry
manifest=$(echo "${manifest}" | jq --argjson v "$(gcloud builds triggers list --format=json 2>/dev/null || echo '[]')" '.resources.cloud_build_triggers = $v')
manifest=$(echo "${manifest}" | jq --argjson v "$(gcloud artifacts repositories list --format=json 2>/dev/null || echo '[]')" '.resources.artifact_registry = $v')

# 9. Service accounts
manifest=$(echo "${manifest}" | jq --argjson v "$(gcloud iam service-accounts list --format=json)" '.resources.service_accounts = $v')

# 10. Secret Manager
manifest=$(echo "${manifest}" | jq --argjson v "$(gcloud secrets list --format=json 2>/dev/null || echo '[]')" '.resources.secrets = $v')

# 11. Cloud Scheduler
manifest=$(echo "${manifest}" | jq --argjson v "$(gcloud scheduler jobs list --format=json 2>/dev/null || echo '[]')" '.resources.scheduler_jobs = $v')

echo "${manifest}" | jq '.'
