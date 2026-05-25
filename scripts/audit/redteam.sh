#!/usr/bin/env bash
# scripts/audit/redteam.sh
#
# Red-team audit script — run before any phase tag to verify security
# invariants, protocol compliance, and regression baseline.
#
# Usage:
#   bash scripts/audit/redteam.sh
#
# Exit codes:
#   0 — all checks pass
#   1 — at least one check failed (details printed above exit)

set -euo pipefail

PASS=0
FAIL=0

pass() {
  echo "[PASS] $1"
  PASS=$((PASS + 1))
}
fail() {
  echo "[FAIL] $1"
  FAIL=$((FAIL + 1))
}

echo "================================================="
echo "Red Team Audit — Atelier phase/2"
echo "================================================="

echo ""
echo "--- 1. Unresolved TODO/FIXME/XXX markers ---"
TODO_COUNT=$(grep -nERI "(TODO|FIXME|XXX)" atelier-core/src atelier-deploy/terraform 2>/dev/null | wc -l | tr -d ' ')
if [ "$TODO_COUNT" -gt 0 ]; then
  fail "Found ${TODO_COUNT} unresolved markers:"
  grep -nERI "(TODO|FIXME|XXX)" atelier-core/src atelier-deploy/terraform 2>/dev/null | head -20
else
  pass "No unresolved TODO/FIXME/XXX markers"
fi

echo ""
echo "--- 2. Terraform allUsers IAM bindings ---"
if grep -nERI "allUsers" atelier-deploy/terraform 2>/dev/null | grep -v "#"; then
  fail "CRITICAL: allUsers binding found in Terraform"
else
  pass "No allUsers bindings in Terraform"
fi

echo ""
echo "--- 3. Hardcoded i-for-ai project IDs in Terraform ---"
if grep -nERI 'project[[:space:]]*=[[:space:]]*"i-for-ai"' atelier-deploy/terraform 2>/dev/null; then
  fail "CRITICAL: Hardcoded i-for-ai project ID in Terraform"
else
  pass "No hardcoded i-for-ai project IDs in Terraform"
fi

echo ""
echo "--- 4. SessionBackend Protocol compliance ---"
if python3 -c "
import sys
sys.path.insert(0, 'atelier-core/src')
try:
    from atelier.memory.session_protocol import SessionBackend
    from atelier.memory.bigquery_session import BigQuerySessionBackend
    from google.adk.sessions.base_session_service import BaseSessionService
    b = BigQuerySessionBackend()
    ok = isinstance(b, SessionBackend) and isinstance(b, BaseSessionService)
    sys.exit(0 if ok else 1)
except Exception as e:
    print(e)
    sys.exit(1)
" 2>/dev/null; then
  pass "BigQuerySessionBackend satisfies SessionBackend Protocol and BaseSessionService"
else
  fail "BigQuerySessionBackend Protocol compliance check failed"
fi

echo ""
echo "--- 5. AG-06 stitch_degraded semantic fix in runner.py ---"
if grep -q "stitch_degraded = False" atelier-core/src/atelier/orchestrator/runner.py 2>/dev/null; then
  pass "AG-06 semantic fix present: stitch_degraded=False on governor fail-soft"
else
  fail "CRITICAL: AG-06 semantic fix missing from runner.py"
fi

echo ""
echo "--- 6. Firebase Auth wired into API endpoints ---"
if grep -q "require_auth" atelier-core/src/atelier/api/app.py atelier-core/src/atelier/api/replay.py 2>/dev/null; then
  pass "require_auth dependency wired in API layer"
else
  fail "CRITICAL: require_auth missing from API layer"
fi

echo ""
echo "--- 7. denied_count fix: score_result returns WebResearchResult for denied ---"
if python3 -c "
import sys
sys.path.insert(0, 'atelier-core/src')
try:
    from atelier.intake.web_research import score_result, DomainTrustConfig, WebResearchResult
    cfg = DomainTrustConfig(frozenset(), frozenset(), frozenset({'denied.com'}), 0.6, 0.8)
    r = score_result('https://denied.com', 'T', 'S', 'q', cfg)
    assert isinstance(r, WebResearchResult), 'Not a WebResearchResult'
    assert r.trust_tier == -1, f'trust_tier={r.trust_tier} not -1'
    sys.exit(0)
except Exception as e:
    print(e)
    sys.exit(1)
" 2>/dev/null; then
  pass "score_result returns trust_tier=-1 for denied domains (denied_count functional)"
else
  fail "denied_count fix not present: score_result does not return trust_tier=-1"
fi

echo ""
echo "--- 8. Full unit test suite ---"
FIREBASE_DISABLE_AUTH=true ATELIER_ENV=development \
  python3 -m pytest atelier-core/tests/unit/ -q --no-header --tb=line 2>&1 | tail -5
if [ "${PIPESTATUS[0]:-0}" -eq 0 ]; then
  pass "Unit test suite passes"
else
  fail "Unit test suite has failures"
fi

echo ""
echo "================================================="
echo "Audit complete: ${PASS} passed, ${FAIL} failed"
echo "================================================="

[ "$FAIL" -eq 0 ]
