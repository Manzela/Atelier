#!/usr/bin/env bash
# Atelier DevPost submission readiness audit (AT-111, PRD v2.2 §12 E11).
#
# Verifies the submission package is complete and, on request, that its links
# resolve. Run via `make submission-check`.
#
# Offline by default (audits file presence and required fields). Set
# CHECK_LINKS=1 to additionally probe the live URL and repository (needs network
# and the deployed stack).
#
# Exit codes:
#   0  package complete, all required fields present (and links resolve if checked)
#   1  one or more checks failed
set -uo pipefail

SUBMISSION="docs/SUBMISSION.md"
fail=0

require_file() {
  if [ -f "$1" ]; then
    echo "  OK   $1 present"
  else
    echo "  FAIL $1 missing" >&2
    fail=1
  fi
}

require_section() {
  # require_section <needle> <reason>
  if grep -qiF -- "$1" "${SUBMISSION}"; then
    echo "  OK   SUBMISSION contains '$1' (${2})"
  else
    echo "  FAIL SUBMISSION missing '$1' (${2})" >&2
    fail=1
  fi
}

check_url() {
  # check_url <url>
  local url="$1" status
  status="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "${url}" || echo "000")"
  if [ "${status}" -ge 200 ] && [ "${status}" -lt 400 ]; then
    echo "  OK   ${url} -> ${status}"
  else
    echo "  FAIL ${url} -> ${status}" >&2
    fail=1
  fi
}

echo "[submission] auditing ${SUBMISSION}"
require_file "${SUBMISSION}"
require_file "README.md"
require_file "docs/runbooks/rollback.md"

if [ -f "${SUBMISSION}" ]; then
  require_section "Built with Google Cloud" "attribution required"
  require_section "https://atelier.autonomous-agent.dev" "live URL"
  require_section "https://github.com/Manzela/Atelier" "repository"
  require_section "Track" "track declared"

  # The demo video is the operator's final live capture; warn (do not fail)
  # while it is still a placeholder so the gate passes before recording.
  if grep -qiF "TODO" "${SUBMISSION}"; then
    echo "  WARN ${SUBMISSION} still has TODO placeholders (e.g. the demo video URL)" >&2
  fi
fi

if [ "${CHECK_LINKS:-0}" = "1" ]; then
  echo "[submission] checking link resolution"
  check_url "https://github.com/Manzela/Atelier"
  check_url "https://atelier.autonomous-agent.dev"
fi

if [ "${fail}" -ne 0 ]; then
  echo "[submission] FAILED - package incomplete" >&2
  exit 1
fi
echo "[submission] package checks passed"
