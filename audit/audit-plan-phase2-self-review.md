# Audit Plan — Phase 2 Self-Review Fix Items

**Status**: Pass 1 complete. Awaiting approval before any implementation.

---

## P0 — Must fix before staging Antigravity's PR

### P0-1: `replay.py` ruff complexity (NEW-1)

**What**: C901 + PLR0915 on `_load_session_replay()`. Will block pre-commit.
**Where**: `replay.py:120` — function has 59 statements, complexity 11.
**Fix**: Extract two helpers:
  - `_build_spans(rows)` — span construction loop (lines 198-217)
  - `_build_gate_scores(judge_votes_raw)` — JSON parsing + GateScore build
    (lines 230-248)
**Effort**: 15 min.

### P0-2: `replay.py` unit test for tenant_id filter (NEW-3)

**What**: BUG 3's security fix has no test. A future refactor could silently
remove the WHERE clause and no test would catch it.
**Where**: New test in `tests/unit/test_replay_api.py`.
**Fix**: Add a test that patches `bigquery.Client`, asserts the query contains
`AND tenant_id = @tenant_id`, and verifies the parameter is set to the value
passed from the caller.
**Effort**: 20 min.

### P0-3: `web_research.py` core unit tests (NEW-4)

**What**: Zero coverage on domain scoring and fail-soft path.
**Where**: New `tests/unit/test_web_research.py`.
**Fix**: Tests for:
  1. `score_result()` with tier-1, tier-2, unknown, denied domains
  2. `generate_research_queries()` output length and format
  3. `research_brief()` with a mocked `_search_with_grounding` returning results
  4. Fail-soft: `research_brief()` returns empty report when grounding raises
**Effort**: 25 min.

---

## P1 — Fix before merge

### P1-1: `denied_count` residual dead code (BUG 1 residual)

**What**: `score_result()` returns `None` for denied domains; `trust_tier == -1`
branch in `research_brief()` is unreachable. The docstring is misleading.
**Where**: `web_research.py:109,430`
**Fix** (two options, pick one):
  - Option A (minimal): Add `report.denied_count += 1` before `return None` in
    `score_result()` — but then the function needs the report as a parameter,
    which changes its signature.
  - Option B (clean): Change `score_result()` to always return a
    `WebResearchResult`, using `trust_tier = -1` for denied. Then the
    `research_brief()` loop naturally handles it. The `.top_results` property
    already filters `trust_tier > 0`, so denied results won't contaminate output.
  - Option C (simplest): Remove the `denied_count` counter entirely and
    update the docstring to match reality.
**Effort**: 10 min.

### P1-2: `judge_votes` column verification (NEW-2)

**What**: `replay.py:230` reads `judge_votes` from `trajectory_records` but
`TrajectoryRecord.to_bq_row()` does not emit this column.
**Where**: `nodes/trajectory.py:to_bq_row()`, `replay.py:230`
**Fix**: Either:
  - Confirm the column exists in the BQ table DDL (check via `bq show`) and
    add it to `to_bq_row()` if missing, OR
  - Remove the gate-score reconstruction from `replay.py` and replace with a
    stub returning `[]` until the column is confirmed.
**Effort**: 10 min investigation + fix.

### P1-3: `redteam_audit.sh` triage (NEW-5)

**What**: Untracked file with emojis, no conventional commit.
**Where**: `redteam_audit.sh` at repo root.
**Fix**: Delete it (the audit content is superseded by the formal audit files
here), or strip emojis and commit as `chore(audit): add redteam audit script`.
**Effort**: 5 min.

---

## P2 — Nice to have

### P2-1: `replay.py` inject BigQuery client for testability

**What**: `bigquery.Client(project=project)` instantiated inline at line 160.
Makes the function hard to unit test without a live BQ connection.
**Fix**: Add an optional `bq_client` parameter to `_load_session_replay()`.
Tests inject a mock; production passes `None` (falls back to default init).
**Effort**: 10 min.

---

## To enrich in pass 2

- Verify `judge_votes` column against live BQ DDL (`bq show atelier-build-2026:atelier_trajectories.trajectory_records`)
- Confirm `trust_tier: int` docstring in `WebResearchResult` is updated to match chosen fix for P1-1
- Cross-check `redteam_audit.sh` content for any findings not already covered here
