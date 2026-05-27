#!/usr/bin/env bash
# scripts/gates/phase_1_gate.sh
#
# Wire all §13.1 Phase 1 Gate hard gates into one machine-verified exit code.
# Per the post-R4 strategic roadmap (§4.3 + §13.1).
#
# Exit codes:
#   0 = all gates pass (READY-TO-TAG)
#   1 = at least one gate failed (BLOCKING)
#   2 = script error (internal fault)
#
# Usage:
#   ./scripts/gates/phase_1_gate.sh
set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "${REPO_ROOT}" || exit 2

fail_count=0
pass_count=0
total_gates=0

gate() {
  local gate_num="$1"
  local desc="$2"
  shift 2
  total_gates=$((total_gates + 1))

  if "$@" >/dev/null 2>&1; then
    echo "[PASS] gate_${gate_num}: ${desc}"
    pass_count=$((pass_count + 1))
  else
    echo "[FAIL] gate_${gate_num}: ${desc}"
    fail_count=$((fail_count + 1))
  fi
}

gate_with_reason() {
  local gate_num="$1"
  local desc="$2"
  local reason="$3"
  shift 3
  total_gates=$((total_gates + 1))

  if "$@" >/dev/null 2>&1; then
    echo "[PASS] gate_${gate_num}: ${desc}"
    pass_count=$((pass_count + 1))
  else
    echo "[FAIL] gate_${gate_num}: ${desc} — ${reason}"
    fail_count=$((fail_count + 1))
  fi
}

# ─── §4.3 Criterion 1: Surface converges end-to-end ───
gate_with_reason "01" "Surface converges end-to-end (Cloud Run POST)" \
  "BLOCKED: Cloud Run staging not deployed yet" \
  false

# ─── §4.3 Criterion 2: Cloud Run deployment working ───
gate_with_reason "02" "Cloud Run deployment working" \
  "BLOCKED: atelier-build-2026 project not created yet" \
  false

# ─── §4.3 Criterion 3: OTel + Cloud Trace functional ───
gate_with_reason "03" "OTel + Cloud Trace functional" \
  "BLOCKED: requires live Cloud Run + Cloud Trace" \
  false

# ─── §4.3 Criterion 4: BigQuery trajectory ingest ───
gate_with_reason "04" "BigQuery trajectory ingest working" \
  "BLOCKED: requires live BigQuery dataset in atelier-build-2026" \
  false

# ─── §4.3 Criterion 5: 50/484 WebGen-Bench subset ───
gate_05_webgen() {
  if [ -d "atelier-core/tests/eval" ] && [ -f "atelier-core/tests/eval/test_webgen_50.py" ]; then
    .venv/bin/pytest atelier-core/tests/eval/ -q --tb=no 2>/dev/null
  else
    return 1
  fi
}
gate_with_reason "05" "50/484 WebGen-Bench subset passing" \
  "tests/eval/ harness not yet wired or all xfail" \
  gate_05_webgen

# ─── §4.3 Criterion 6: README + ROADMAP + first 5 ADRs ───
gate_06_docs() {
  [ -f "README.md" ] || return 1
  [ -f "ROADMAP.md" ] || [ -f "docs/ROADMAP.md" ] || return 1
  local adr_count
  adr_count=$(find docs/decisions -name '0*.md' 2>/dev/null | head -5 | wc -l)
  [ "${adr_count}" -ge 5 ]
}
gate_with_reason "06" "README + ROADMAP + first 5 ADRs" \
  "Missing README, ROADMAP, or fewer than 5 ADRs" \
  gate_06_docs

# ─── §4.3 Criterion 7: Cost ≤ $1,200 ───
gate_with_reason "07" "Cost ≤ \$1,200 of \$5K budget" \
  "BLOCKED: requires billing query against atelier-build-2026" \
  false

# ─── §13.1 Gate 8: orphan-zero (05_verify_no_orphans.py) ───
gate_08_orphans() {
  if [ -f "scripts/migration/05_verify_no_orphans.py" ]; then
    DRY_RUN=0 python3 scripts/migration/05_verify_no_orphans.py
  else
    return 1
  fi
}
gate_with_reason "08" "Migration orphan-zero (05_verify_no_orphans.py)" \
  "BLOCKED: requires classification + both projects accessible" \
  gate_08_orphans

# ─── §13.1 Gate 9: gcloud asset search empty ───
gate_09_asset_search() {
  local result
  result=$(gcloud asset search-all-resources --project=i-for-ai --filter='name~atelier' --format=json 2>/dev/null)
  [ "${result}" = "[]" ] || [ -z "${result}" ]
}
gate_with_reason "09" "gcloud asset search-all-resources returns empty for atelier in i-for-ai" \
  "Atelier resources still exist in i-for-ai" \
  gate_09_asset_search

# ─── §13.1 Gate 10: terraform plan zero drift ───
gate_with_reason "10" "terraform plan shows zero drift" \
  "BLOCKED: atelier-build-2026 project not created, terraform not initialized" \
  false

# ─── §13.1 Gate 11: CI green 3 consecutive ───
gate_11_ci() {
  local recent_runs
  recent_runs=$(gh run list --branch=phase/1 --limit=3 --json conclusion -q '.[].conclusion' 2>/dev/null)
  local success_count
  success_count=$(echo "${recent_runs}" | grep -c "success" || true)
  [ "${success_count}" -ge 3 ]
}
gate_with_reason "11" "CI green for 3 consecutive runs on phase/1" \
  "Fewer than 3 consecutive green CI runs" \
  gate_11_ci

# ─── §13.1 Gate 12: No --no-verify in past 24h ───
gate_12_no_verify() {
  local suspect_commits
  suspect_commits=$(git log --since="24 hours ago" --format="%H %s" | grep -ci "no.verify" || true)
  [ "${suspect_commits}" -eq 0 ]
}
gate "12" "No --no-verify commits in past 24h" \
  gate_12_no_verify

# ─── §13.1 Gate 13: pytest tests/eval/ no regression ───
gate_13_eval() {
  if [ -d "atelier-core/tests/eval" ]; then
    .venv/bin/pytest atelier-core/tests/eval/ -q --tb=no 2>/dev/null
  else
    return 1
  fi
}
gate_with_reason "13" "pytest tests/eval/ shows no regression" \
  "tests/eval/ not yet wired or failing" \
  gate_13_eval

# ─── §13.1 Gate 14: jq evidence_tests type check ───
gate_14_evidence_type() {
  local count
  count=$(jq '[.features[] | select(.evidence_tests | type != "array")] | length' .local/sprint/features.json)
  [ "${count}" -eq 0 ]
}
gate "14" "R4-audit jq gate: evidence_tests all array-typed" \
  gate_14_evidence_type

# ─── §13.1 Gate 15: jq passes+evidence check ───
gate_15_passes_evidence() {
  local count
  count=$(jq '[.features[] | select(.passes==true and (.evidence_tests | length)==0)] | length' .local/sprint/features.json)
  [ "${count}" -eq 0 ]
}
gate "15" "No passes:true without backing evidence_tests" \
  gate_15_passes_evidence

# ─── §13.1 Gate 16: .local/sprint/features.json schema validation ───
gate_16_schema() {
  local malformed
  malformed=$(jq '[.features[] | select(
    (.id | type) != "string" or
    (.passes | type) != "boolean" or
    (.evidence_tests | type) != "array"
  )] | length' .local/sprint/features.json)
  [ "${malformed}" -eq 0 ]
}
gate "16" ".local/sprint/features.json schema: all entries have id/passes/evidence_tests" \
  gate_16_schema

# ─── §13.1 Gate 17: §18-§21 protocol modules mypy --strict ───
gate_17_protocol_mypy() {
  local modules_found=0
  for mod in router memory reward optimize; do
    if [ -d "atelier-core/src/atelier/${mod}" ]; then
      modules_found=$((modules_found + 1))
    fi
  done
  if [ "${modules_found}" -eq 0 ]; then
    return 1
  fi
  .venv/bin/mypy --strict atelier-core/src/atelier/router/ atelier-core/src/atelier/memory/ \
    atelier-core/src/atelier/reward/ atelier-core/src/atelier/optimize/ 2>/dev/null
}
gate_with_reason "17" "§18-§21 protocol modules pass mypy --strict" \
  "Protocol modules not yet created or mypy fails" \
  gate_17_protocol_mypy

# ─── §13.1 Gate 18: ADR 0027-0030 at least one committed ───
gate_18_adr() {
  local adr_count
  adr_count=$(find docs/decisions -name '002[7-9]*.md' -o -name '0030*.md' 2>/dev/null | wc -l)
  [ "${adr_count}" -ge 1 ]
}
gate_with_reason "18" "At least one ADR from 0027-0030 series committed" \
  "No ADR 0027-0030 found in docs/decisions/" \
  gate_18_adr

# ─── Summary ───
echo ""
echo "═══════════════════════════════════════════════════════"
if [ "${fail_count}" -eq 0 ]; then
  echo "Phase 1 Gate: ${pass_count}/${total_gates} passing — READY-TO-TAG"
  exit 0
else
  echo "Phase 1 Gate: ${pass_count}/${total_gates} passing, ${fail_count} failing — BLOCKING"
  exit 1
fi
