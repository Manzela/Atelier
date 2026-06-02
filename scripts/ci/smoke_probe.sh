#!/usr/bin/env bash
# Atelier live smoke probe / synthetic monitor (AT-083, PRD v2.2 §12 E8).
#
# Verifies the public endpoints of the deployed stack respond correctly. Runs
# the UNAUTHENTICATED checks that gate the deploy; the authenticated
# POST /v1/generate -> /v1/replay walkthrough is exercised by the AT-110
# production-readiness gate against a signed-in session.
#
# Usage:
#   scripts/ci/smoke_probe.sh [BASE_URL]
#   BASE_URL defaults to ATELIER_BASE_URL, then https://atelier.autonomous-agent.dev
#
# Exit codes:
#   0  every probe passed
#   1  one or more probes failed (the deploy gate blocks)
set -uo pipefail

BASE_URL="${1:-${ATELIER_BASE_URL:-https://atelier.autonomous-agent.dev}}"
fail=0

probe_status() {
  # probe_status <path> <expected_status> <reason>
  local path="$1" expected="$2" reason="$3" url status
  url="${BASE_URL}${path}"
  status="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "${url}" || echo "000")"
  if [ "${status}" = "${expected}" ]; then
    echo "  OK   ${path} -> ${status} (${reason})"
  else
    echo "  FAIL ${path} -> ${status}, expected ${expected} (${reason})" >&2
    fail=1
  fi
}

probe_contains() {
  # probe_contains <path> <substring> <reason>
  local path="$1" needle="$2" reason="$3" url body
  url="${BASE_URL}${path}"
  body="$(curl -sS --max-time 20 "${url}" || echo "")"
  if printf '%s' "${body}" | grep -q -- "${needle}"; then
    echo "  OK   ${path} contains '${needle}' (${reason})"
  else
    echo "  FAIL ${path} missing '${needle}' (${reason})" >&2
    fail=1
  fi
}

echo "[smoke] probing ${BASE_URL}"
probe_status "/health" "200" "Cloud Run health"
probe_status "/" "200" "dashboard root (served unauthenticated)"
probe_status "/.well-known/agent-card.json" "200" "A2A agent card"
probe_status "/openapi.json" "200" "OpenAPI schema"
probe_contains "/openapi.json" "/v1/generate" "generate route advertised"
probe_contains "/openapi.json" "/v1/replay" "replay route advertised"
probe_contains "/openapi.json" "/v1/dream" "dream route advertised"

if [ "${fail}" -ne 0 ]; then
  echo "[smoke] FAILED - one or more probes did not pass" >&2
  exit 1
fi
echo "[smoke] all probes passed"
