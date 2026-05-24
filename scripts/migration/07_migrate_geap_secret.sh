#!/usr/bin/env bash
# 07_migrate_geap_secret.sh — Migrate atelier-geap-api-key from i-for-ai to atelier-build-2026
#
# USAGE:
#   ./scripts/migration/07_migrate_geap_secret.sh          # DRY-RUN (default)
#   ./scripts/migration/07_migrate_geap_secret.sh --wet    # LIVE migration (Daniel-approved only)
#
# The script NEVER logs secret payloads. Only SHA-256 hashes and byte lengths.
#
# Per <no_destructive_git> spirit: --dry-run is the default. Wet-run requires
# explicit --wet flag AND Daniel Manzela's approval.

set -euo pipefail

readonly SRC_PROJECT="i-for-ai"
readonly DST_PROJECT="atelier-build-2026"
readonly SECRET_NAME="atelier-geap-api-key"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly REPO_ROOT
readonly LOG_FILE="${REPO_ROOT}/audit/migration/secret-cutover-2026-05-24.log"

DRY_RUN=1
if [[ "${1:-}" == "--wet" ]]; then
  DRY_RUN=0
fi

# --- Logging helper (timestamps, never logs secret values) ---
log() {
  local ts
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "[${ts}] $*" | tee -a "${LOG_FILE}"
}

# --- Ensure log directory exists ---
mkdir -p "$(dirname "${LOG_FILE}")"

log "========================================"
log "Secret migration: ${SECRET_NAME}"
log "Source: ${SRC_PROJECT} → Destination: ${DST_PROJECT}"
log "Mode: $(if [[ ${DRY_RUN} -eq 1 ]]; then echo 'DRY-RUN'; else echo 'WET (LIVE)'; fi)"
log "========================================"

# --- Step 1: Read secret from source project ---
log "Step 1: Reading secret from ${SRC_PROJECT}..."
SRC_PAYLOAD="$(gcloud secrets versions access latest \
  --secret="${SECRET_NAME}" \
  --project="${SRC_PROJECT}" 2>&1)" || {
  log "FAIL-LOUD: Cannot read secret from ${SRC_PROJECT}. Error: ${SRC_PAYLOAD}"
  exit 1
}

SRC_SHA256="$(printf '%s' "${SRC_PAYLOAD}" | shasum -a 256 | awk '{print $1}')"
SRC_LENGTH="${#SRC_PAYLOAD}"

log "Source SHA-256: ${SRC_SHA256}"
log "Source length (bytes): ${SRC_LENGTH}"

if [[ ${DRY_RUN} -eq 1 ]]; then
  log "DRY-RUN complete. Secret payload read from ${SRC_PROJECT}, SHA-256 captured."
  log "To perform the actual migration, re-run with --wet (requires Daniel approval)."
  log "========================================"
  exit 0
fi

# --- WET MODE BELOW ---
log "WET MODE: Proceeding with live migration..."

# --- Step 2: Create secret in destination project ---
log "Step 2: Creating secret ${SECRET_NAME} in ${DST_PROJECT}..."
if gcloud secrets describe "${SECRET_NAME}" --project="${DST_PROJECT}" &>/dev/null; then
  log "Secret ${SECRET_NAME} already exists in ${DST_PROJECT}. Adding new version."
else
  gcloud secrets create "${SECRET_NAME}" \
    --project="${DST_PROJECT}" \
    --replication-policy=automatic 2>&1 | while read -r line; do log "  ${line}"; done
  log "Secret created in ${DST_PROJECT}."
fi

# --- Step 3: Add version with the payload ---
log "Step 3: Adding secret version to ${DST_PROJECT}..."
printf '%s' "${SRC_PAYLOAD}" | gcloud secrets versions add "${SECRET_NAME}" \
  --project="${DST_PROJECT}" \
  --data-file=- 2>&1 | while read -r line; do log "  ${line}"; done

# --- Step 4: Verify round-trip ---
log "Step 4: Verifying round-trip SHA-256..."
DST_PAYLOAD="$(gcloud secrets versions access latest \
  --secret="${SECRET_NAME}" \
  --project="${DST_PROJECT}" 2>&1)" || {
  log "FAIL-LOUD: Cannot read secret back from ${DST_PROJECT}. Error: ${DST_PAYLOAD}"
  exit 1
}

DST_SHA256="$(printf '%s' "${DST_PAYLOAD}" | shasum -a 256 | awk '{print $1}')"
DST_LENGTH="${#DST_PAYLOAD}"

log "Destination SHA-256: ${DST_SHA256}"
log "Destination length (bytes): ${DST_LENGTH}"

if [[ "${SRC_SHA256}" != "${DST_SHA256}" ]]; then
  log "FAIL-LOUD: SHA-256 MISMATCH! Source: ${SRC_SHA256}, Destination: ${DST_SHA256}"
  log "CRITICAL: Secret cutover is CORRUPTED. Manual intervention required."
  exit 1
fi

log "✅ SHA-256 MATCH CONFIRMED: ${SRC_SHA256} == ${DST_SHA256}"
log "✅ Length MATCH CONFIRMED: ${SRC_LENGTH} == ${DST_LENGTH}"
log "✅ Secret ${SECRET_NAME} successfully migrated from ${SRC_PROJECT} to ${DST_PROJECT}."
log "========================================"
