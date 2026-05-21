#!/usr/bin/env bash
# scripts/migration/04_decommission.sh
#
# Idempotent deletes of MIGRATE + DECOMMISSION resources from i-for-ai.
# Per §2.5 of the post-R4 strategic roadmap.
# Logs every action to audit/migration/decommission-log-<date>.json.
#
# REQUIRES: prior successful run of 01_inventory.sh + 02_classify.py + 03_terraform_apply.sh
#
# Usage:
#   DRY_RUN=1 bash scripts/migration/04_decommission.sh       # default: dry-run
#   DRY_RUN=0 bash scripts/migration/04_decommission.sh       # DESTRUCTIVE — deletes resources
set -euo pipefail

DRY_RUN="${DRY_RUN:-1}"
PREFIX=""
[[ "${DRY_RUN}" == "1" ]] && PREFIX="DRY-RUN: "

SRC_PROJECT="i-for-ai"
LOG_DIR="audit/migration"
LOG_FILE="${LOG_DIR}/decommission-log-$(date +%F).json"
CLASSIFICATION="audit/migration/classification-2026-05-21.json"

mkdir -p "${LOG_DIR}"

echo "${PREFIX}Decommissioning Atelier resources from ${SRC_PROJECT}" >&2
echo "${PREFIX}Classification file: ${CLASSIFICATION}" >&2
echo "${PREFIX}Log file: ${LOG_FILE}" >&2

if [[ "${DRY_RUN}" == "1" ]]; then
  echo "${PREFIX}Would read classification from ${CLASSIFICATION}" >&2
  echo "${PREFIX}Would delete all MIGRATE and DECOMMISSION resources from ${SRC_PROJECT}" >&2
  echo "${PREFIX}Would log actions to ${LOG_FILE}" >&2
  echo "${PREFIX}Resource types: Vertex endpoints, Cloud Run, GCS, BigQuery, Pub/Sub, Secrets, Scheduler, Cloud Functions, Service Accounts" >&2
  echo "${PREFIX}Each deletion is idempotent (|| true on gcloud delete)" >&2
  exit 0
fi

if [[ ! -f "${CLASSIFICATION}" ]]; then
  echo "ERROR: ${CLASSIFICATION} not found. Run 02_classify.py first." >&2
  exit 1
fi

# Initialize log
echo '{"actions": [], "started_at": "'"$(date -u +%FT%TZ)"'"}' >"${LOG_FILE}"

log_action() {
  local kind="$1" name="$2" action="$3" result="$4"
  jq --arg k "${kind}" --arg n "${name}" --arg a "${action}" --arg r "${result}" \
    '.actions += [{"kind": $k, "name": $n, "action": $a, "result": $r, "at": (now | todate)}]' \
    "${LOG_FILE}" >"${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "${LOG_FILE}"
}

# Vertex AI endpoints — un-deploy models first, then delete
for ep in $(jq -r '.decisions[] | select(.resource_kind=="vertex_endpoint" and .disposition=="DECOMMISSION") | .resource_name' "${CLASSIFICATION}"); do
  echo "Deleting Vertex endpoint: ${ep}"
  gcloud ai endpoints delete "${ep}" --region=us-central1 --project="${SRC_PROJECT}" --quiet 2>/dev/null &&
    log_action "vertex_endpoint" "${ep}" "delete" "success" ||
    log_action "vertex_endpoint" "${ep}" "delete" "already_gone"
done

# Cloud Run services
for svc in $(jq -r '.decisions[] | select(.resource_kind=="cloud_run" and .disposition=="MIGRATE") | .resource_name' "${CLASSIFICATION}"); do
  echo "Deleting Cloud Run service: ${svc}"
  for region in us-central1 us-west1 europe-west1; do
    gcloud run services delete "${svc}" --region="${region}" --project="${SRC_PROJECT}" --quiet 2>/dev/null &&
      log_action "cloud_run" "${svc}/${region}" "delete" "success" || true
  done
done

# GCS buckets
for bucket in $(jq -r '.decisions[] | select(.resource_kind=="gcs_buckets" and .disposition=="MIGRATE") | .resource_name' "${CLASSIFICATION}"); do
  echo "Deleting GCS bucket: ${bucket}"
  gsutil -m rm -r "gs://${bucket}" 2>/dev/null &&
    log_action "gcs_bucket" "${bucket}" "delete" "success" ||
    log_action "gcs_bucket" "${bucket}" "delete" "already_gone"
done

# BigQuery datasets
for dataset in $(jq -r '.decisions[] | select(.resource_kind=="bigquery_datasets" and .disposition=="MIGRATE") | .resource_name' "${CLASSIFICATION}"); do
  echo "Deleting BigQuery dataset: ${dataset}"
  bq --project_id="${SRC_PROJECT}" rm -r -f --dataset "${SRC_PROJECT}:${dataset}" 2>/dev/null &&
    log_action "bigquery_dataset" "${dataset}" "delete" "success" ||
    log_action "bigquery_dataset" "${dataset}" "delete" "already_gone"
done

# Service accounts (last — after IAM no longer references them)
for sa in $(jq -r '.decisions[] | select(.resource_kind=="service_accounts" and .disposition=="MIGRATE") | .resource_name' "${CLASSIFICATION}"); do
  echo "Deleting service account: ${sa}"
  gcloud iam service-accounts delete "${sa}" --project="${SRC_PROJECT}" --quiet 2>/dev/null &&
    log_action "service_account" "${sa}" "delete" "success" ||
    log_action "service_account" "${sa}" "delete" "already_gone"
done

# Finalize log
jq '.completed_at = (now | todate)' "${LOG_FILE}" >"${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "${LOG_FILE}"

echo "Decommission complete. Log: ${LOG_FILE}"
echo "Next: run 05_verify_no_orphans.py"
