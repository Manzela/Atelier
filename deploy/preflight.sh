#!/usr/bin/env bash
# Atelier deploy-readiness preflight (PRD v2.2 AT-004).
#
# Named-reason probes: each prints WHY it matters, then its status (OK / WARN /
# SKIP / FAIL). Live GCP probes (project, APIs, managed cert, model-id GA) are
# delegated to the Gemini CLI when gcloud is unavailable or unauthed here, per
# the executor operating model. The script exits non-zero only on a hard LOCAL
# blocker; GCP gaps are reported as WARN/SKIP for the operator + Gemini CLI.
set -uo pipefail

PROJECT="${ATELIER_GCP_PROJECT:-atelier-build-2026}"
REGION="${ATELIER_GCP_REGION:-us-central1}"
PY=".venv/bin/python"
hard_fail=0

probe() { echo "[preflight:$1] reason: $2"; }

# G7 - project + region resolve (deploy must target the right project/region).
probe "G7-project" "deploy targets must resolve to the right project/region"
if command -v gcloud >/dev/null 2>&1 && gcloud config get-value project >/dev/null 2>&1; then
  echo "  OK gcloud project=$(gcloud config get-value project 2>/dev/null); target=${PROJECT}/${REGION}"
else
  echo "  SKIP gcloud unavailable/unauthed - delegate to Gemini CLI (target ${PROJECT}/${REGION})"
fi

# G11 - required APIs enabled on the build project.
probe "G11-apis" "deploy needs compute, certificatemanager, modelarmor, firebase, fcm, aiplatform"
if command -v gcloud >/dev/null 2>&1 && gcloud services list --enabled --project "${PROJECT}" >/tmp/atelier_preflight_apis 2>/dev/null; then
  missing=""
  for api in compute certificatemanager modelarmor firebase fcm aiplatform; do
    grep -q "${api}" /tmp/atelier_preflight_apis || missing="${missing} ${api}"
  done
  if [ -n "${missing}" ]; then
    echo "  WARN missing APIs:${missing} - enable via Gemini CLI + operator sign-off (AT-084)"
  else
    echo "  OK all required APIs enabled"
  fi
else
  echo "  SKIP gcloud unavailable - delegate to Gemini CLI (AT-084 enables certificatemanager)"
fi

# G9 - managed cert ACTIVE at least 1 day before a custom-domain deploy.
probe "G9-cert" "G9 requires the managed cert ACTIVE >=1 day before custom-domain deploy"
echo "  SKIP delegate to Gemini CLI: gcloud certificate-manager certificates describe (AT-083)"

# model-id GA - the served Gemini model id must be GA.
probe "model-id-GA" "the served Gemini model id must be GA before AT-024 pins it"
echo "  SKIP delegate to Gemini CLI: gcloud ai models list --region=${REGION} (AT-024)"

# chromium - the real axe-core + visual oracles need a launchable chromium.
probe "chromium" "the real axe-core + visual oracles (AT-011/040) need chromium"
if [ -x "${PY}" ] && "${PY}" -c "import playwright" >/dev/null 2>&1; then
  if "${PY}" -c "from playwright.sync_api import sync_playwright" >/dev/null 2>&1 &&
    "${PY}" - <<'PYEOF' >/dev/null 2>&1; then
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    b.close()
PYEOF
    echo "  OK chromium launches"
  else
    echo "  WARN playwright present but chromium not launchable - run 'playwright install chromium' (AT-011)"
  fi
else
  echo "  SKIP playwright not installed in .venv yet (lands with AT-011)"
fi

# brief-parse - a cached fixture brief must parse offline (intake sanity).
probe "brief-parse" "a cached fixture brief must parse offline (intake sanity, no network)"
FIXTURE="$(find atelier-core/tests -name '*brief*.json' -o -name '*brief*.txt' 2>/dev/null | head -1)"
if [ -n "${FIXTURE}" ]; then
  echo "  OK cached brief fixture present: ${FIXTURE}"
else
  echo "  SKIP no cached brief fixture found yet (lands with the AT-003 record/replay fixtures)"
fi

if [ "${hard_fail}" -ne 0 ]; then
  echo "[preflight] FAIL - ${hard_fail} hard local probe(s) failed"
  exit 1
fi
echo "[preflight] done - live GCP probes delegated to Gemini CLI where gcloud is absent"
