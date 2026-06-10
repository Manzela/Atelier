#!/usr/bin/env bash
# Single-endpoint smoke check for the deploy pipeline's verify-before-shift and
# staging gates, where the surface under test is one Cloud Run service (an API
# OR a dashboard, on its own URL) rather than the integrated canonical layout
# that scripts/ci/smoke_probe.sh expects.
#
# Usage:  scripts/ci/smoke_endpoint.sh <url> <expected_status> [reason]
# Exit 0 if the endpoint returns <expected_status>, else exit 1 (gates the deploy).
#
# Retries absorb Cloud Run cold-starts and brief hosting/CDN propagation after a
# fresh revision; a genuinely wrong status still fails after the retries.
set -uo pipefail

url="${1:?usage: smoke_endpoint.sh <url> <expected_status> [reason]}"
expected="${2:?expected status required}"
reason="${3:-}"

status="$(curl -sS -o /dev/null -w '%{http_code}' \
  --max-time 25 --retry 4 --retry-delay 5 --retry-all-errors \
  "${url}" || echo '000')"

if [ "${status}" = "${expected}" ]; then
  echo "  OK   ${url} -> ${status} (${reason})"
  exit 0
fi
echo "  FAIL ${url} -> ${status}, expected ${expected} (${reason})" >&2
exit 1
