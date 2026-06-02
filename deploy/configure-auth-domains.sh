#!/usr/bin/env bash
# configure-auth-domains.sh — Add custom domain to Firebase Auth authorized domains.
#
# Uses the Identity Toolkit v2 REST API to whitelist atelier.autonomous-agent.dev
# for Google SSO OAuth redirect callbacks. This is the operator-runnable
# equivalent of: Firebase Console → Authentication → Settings → Authorized Domains.
#
# The same configuration is also managed declaratively in:
#   atelier-deploy/terraform/firebase_auth.tf
# This script exists as an immediate unblock when Terraform apply is not yet run.
#
# Usage:
#   ./deploy/configure-auth-domains.sh [--project PROJECT_ID] [--domain DOMAIN]
#
# Prerequisites:
#   - gcloud CLI authenticated (`gcloud auth login`)
#   - identitytoolkit.googleapis.com API enabled on the project
#   - Caller has roles/identitytoolkit.admin or roles/firebase.admin
#
# PRD Reference: §13.1 (Firebase Google SSO), AT-083 acceptance.
# Idempotent: safe to run multiple times.

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults (overridable via flags)
# ---------------------------------------------------------------------------
PROJECT_ID="${CLOUDSDK_CORE_PROJECT:-atelier-build-2026}"
CUSTOM_DOMAIN="atelier.autonomous-agent.dev"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT_ID="$2"
      shift 2
      ;;
    --domain)
      CUSTOM_DOMAIN="$2"
      shift 2
      ;;
    -h | --help)
      echo "Usage: $0 [--project PROJECT_ID] [--domain DOMAIN]"
      echo "  --project  GCP project ID (default: \$CLOUDSDK_CORE_PROJECT or atelier-build-2026)"
      echo "  --domain   Custom domain to authorize (default: atelier.autonomous-agent.dev)"
      exit 0
      ;;
    *)
      echo "Unknown flag: $1"
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------
if ! command -v gcloud &>/dev/null; then
  echo "ERROR: gcloud CLI not found. Install: https://cloud.google.com/sdk/docs/install"
  exit 1
fi

if ! command -v jq &>/dev/null; then
  echo "ERROR: jq not found. Install: brew install jq"
  exit 1
fi

TOKEN=$(gcloud auth print-access-token 2>/dev/null) || {
  echo "ERROR: gcloud auth failed. Run 'gcloud auth login' first."
  exit 1
}

API_BASE="https://identitytoolkit.googleapis.com/admin/v2/projects/${PROJECT_ID}/config"

echo "━━━ Firebase Auth Authorized Domains ━━━"
echo "Project:       ${PROJECT_ID}"
echo "Custom domain: ${CUSTOM_DOMAIN}"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Get current authorized domains
# ---------------------------------------------------------------------------
echo "→ Fetching current authorized domains..."
CURRENT_CONFIG=$(curl -sf \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "x-goog-user-project: ${PROJECT_ID}" \
  "${API_BASE}" 2>&1) || {
  echo "ERROR: Failed to fetch Identity Platform config."
  echo "  Ensure identitytoolkit.googleapis.com is enabled:"
  echo "  gcloud services enable identitytoolkit.googleapis.com --project=${PROJECT_ID}"
  exit 1
}

CURRENT_DOMAINS=$(echo "${CURRENT_CONFIG}" | jq -r '.authorizedDomains // [] | .[]' 2>/dev/null)
echo "  Current domains:"
echo "${CURRENT_DOMAINS}" | sed 's/^/    - /'

# ---------------------------------------------------------------------------
# Step 2: Check if domain is already authorized (idempotent)
# ---------------------------------------------------------------------------
if echo "${CURRENT_DOMAINS}" | grep -qxF "${CUSTOM_DOMAIN}"; then
  echo ""
  echo "✓ Domain '${CUSTOM_DOMAIN}' is already authorized. Nothing to do."
  exit 0
fi

# ---------------------------------------------------------------------------
# Step 3: Build the new domain list (existing + custom)
# ---------------------------------------------------------------------------
# The Identity Toolkit API replaces the entire list, so we must send all
# existing domains plus the new one.
NEW_DOMAINS_JSON=$(echo "${CURRENT_CONFIG}" | jq --arg d "${CUSTOM_DOMAIN}" \
  '.authorizedDomains + [$d] | unique')

echo ""
echo "→ Adding '${CUSTOM_DOMAIN}' to authorized domains..."

# ---------------------------------------------------------------------------
# Step 4: PATCH the config with the updated domain list
# ---------------------------------------------------------------------------
PATCH_RESPONSE=$(curl -sf -X PATCH \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "x-goog-user-project: ${PROJECT_ID}" \
  -H "Content-Type: application/json" \
  "${API_BASE}?updateMask=authorizedDomains" \
  -d "{\"authorizedDomains\": ${NEW_DOMAINS_JSON}}" 2>&1) || {
  echo "ERROR: Failed to update authorized domains."
  echo "  Ensure your account has roles/identitytoolkit.admin or roles/firebase.admin."
  exit 1
}

# ---------------------------------------------------------------------------
# Step 5: Verify the update
# ---------------------------------------------------------------------------
UPDATED_DOMAINS=$(echo "${PATCH_RESPONSE}" | jq -r '.authorizedDomains // [] | .[]' 2>/dev/null)

if echo "${UPDATED_DOMAINS}" | grep -qxF "${CUSTOM_DOMAIN}"; then
  echo ""
  echo "✓ Success! Updated authorized domains:"
  echo "${UPDATED_DOMAINS}" | sed 's/^/    - /'
  echo ""
  echo "Google SSO will now accept OAuth redirects from https://${CUSTOM_DOMAIN}"
else
  echo ""
  echo "WARNING: PATCH succeeded but '${CUSTOM_DOMAIN}' not found in response."
  echo "  Response domains:"
  echo "${UPDATED_DOMAINS}" | sed 's/^/    - /'
  exit 1
fi
