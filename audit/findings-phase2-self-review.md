# Audit Findings — Phase 2 Deferred Items Self-Review

**Target**: Antigravity's self-review document vs actual codebase
**Pass 1 date**: 2026-05-25
**Auditor**: Claude (orchestrator)
**Method**: Every cited file and line read directly. No trust in summaries.

---

## Test Count Discrepancy

The self-review claims `527 passed`. The actual suite collected **577 tests**;
the last clean run produced **518 passed**. Neither matches the claim. Likely
reflects a unit-only count from an intermediate run. Not a blocker but the
claim is unverified.

---

## BUG 1 — Domain Extraction (AG-09): Core Fix Verified; Residual Not Fixed

**Claim**: Fixed by using `chunk.web.domain` instead of `_extract_domain(url)`.

**Verified (the fix is real)**: `web_research.py:348`
`actual_domain = getattr(web, "domain", "")` is used for trust scoring.
The redirect URI is no longer passed to `score_result()`. Lines 354-358 build
`scoring_url = f"https://{actual_domain}"` and pass that to `score_result()`.
Trust lattice scoring is now functional.

**Residual bug still present** (`web_research.py:430`): `denied_count` is still
dead code. `score_result()` returns `None` for denied domains (line 181) and
never produces a `WebResearchResult` with `trust_tier == -1`. The batch loop
at line 429 only iterates non-None results. `result.trust_tier == -1` is
structurally unreachable at runtime. `denied_count` will always be 0.
The docstring `trust_tier: -1 for denied domains` is misleading.
**Severity**: Low. Trust scoring works; only the counter is wrong.

---

## BUG 2 — Client Caching (AG-09): Verified Correct

`web_research.py:266`: `_genai_client: Any | None = None` at module level.
`_get_genai_client()` checks `if _genai_client is not None` before creating.
Parallel WRAI queries share a single auth handshake. **No issues.**

---

## BUG 3 — IDOR / Tenant Filter (AG-13): Verified Correct

`replay.py:162-171`: `WHERE session_id = @session_id AND tenant_id = @tenant_id`
with parameterized `bigquery.ScalarQueryParameter`. Caller at line 319 passes
`tenant_id=user.tenant_id`. Application-level check at line 326 is the second
layer. Defense-in-depth is complete and correct.

---

## New Issues Not Present in the Self-Review

### NEW-1: `replay.py` ruff C901 + PLR0915 violations

`_load_session_replay()` (line 120) has cyclomatic complexity 11 (limit 10)
and 59 statements (limit 50). Will fail pre-commit once the file is staged.

### NEW-2: `judge_votes` column not confirmed in `trajectory_records` schema

`replay.py:230` reads `row.get("judge_votes", "[]")`. The canonical
`to_bq_row()` in `nodes/trajectory.py` does not include a `judge_votes` column.
If the column is absent, gate scores will always be empty in the replay UI.
Needs verification against the actual BQ table DDL before the column can be
trusted.

### NEW-3: `replay.py` BQ path has zero unit tests

The previous `_load_session_replay()` stub (returned `None` always) has been
replaced with a real 160-line BQ query function. There are no tests for this
path. The BigQuery client is instantiated directly inside the function (not
injected), making the tenant_id filter behavior — the core security fix from
BUG 3 — untested in the test suite. The security guarantee from BUG 3 is
correct in code but unverified by a test.

### NEW-4: `web_research.py` has zero unit tests

`generate_research_queries()`, `score_result()`, `_search_with_grounding()`
(fail-soft path), and `research_brief()` have no tests at all. The trust
lattice scoring logic is untested.

### NEW-5: `redteam_audit.sh` is untracked and needs triage

File appeared in `git status ??`. Must be either committed with conventional
commit or deleted. Contains shell emojis (`🔴`, `✅`, `⚠️`) which violate the
project's no-emoji policy in source files.

---

## Verified Correct (self-review claims confirmed)

| Claim | File:Line | Status |
|-------|-----------|--------|
| `stitch_degraded = False` on governor None | `runner.py:208` | Confirmed |
| `degradation_reason` / `user_message` in return dict | `runner.py:209,226` | Confirmed |
| Both LlmAgent sites use `generate_content_config` | `generator_ensemble.py:54`, `brief_parser.py:66` | Confirmed |
| `BigQuerySessionBackend` subclasses `BaseSessionService` | `bigquery_session.py:38` | Confirmed |
| All 4 abstract methods implemented | Lines 97,151,220,279 | Confirmed |
| `runner.py` uses injected `session_service` (no InMemoryRunner) | `runner.py:163,173` | Confirmed |
