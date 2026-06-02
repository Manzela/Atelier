#!/usr/bin/env bash
# Atelier Agent Engine deploy (AT-082, PRD v2.2 §12 E8).
#
# Deploys the planner agent to Vertex AI Agent Engine via
# `python -m atelier.agent_engine_deploy`, which prints the deployed resource
# name on stdout and exits non-zero (fail-loud) on any failure.
#
# Operator-gated: requires Application Default Credentials for the serving
# project and the Vertex AI Agent Engine API enabled. Run from the repo root.
set -euo pipefail

PROJECT="${GOOGLE_CLOUD_PROJECT:-atelier-build-2026}"
LOCATION="${GOOGLE_CLOUD_LOCATION:-us-central1}"
PY="${PY:-.venv/bin/python}"

echo "[agent-engine] deploying planner: project=${PROJECT} location=${LOCATION}"

if [ ! -x "${PY}" ]; then
  echo "[agent-engine] FAIL: python interpreter not found at ${PY}" >&2
  exit 1
fi

# The module logs to stderr and prints only the resource name to stdout, so the
# final stdout line is the deployed Agent Engine resource name.
if ! resource_name="$(
  GOOGLE_CLOUD_PROJECT="${PROJECT}" GOOGLE_CLOUD_LOCATION="${LOCATION}" \
    "${PY}" -m atelier.agent_engine_deploy | tail -n1
)"; then
  echo "[agent-engine] FAIL: deploy command exited non-zero" >&2
  exit 1
fi

echo "[agent-engine] deployed resource_name=${resource_name}"
