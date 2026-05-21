# Plan Review 1 — Executor Brief Verification & Implementation Plan

**Reviewed by:** Governor / Auditor agent (Opus 4.7 MAX)
**Date:** 2026-05-21 (Sprint D7 of 21)
**Plan under review:**

- Primary: `/Users/danielmanzela/.gemini/antigravity-ide/brain/e9962ddd-ddea-4979-a1d2-fa00102a9019/implementation_plan.md` (173 lines)
- Exported copy: `/Users/danielmanzela/Downloads/Executor Brief Verification & Implementation Plan .md` (byte-identical)

**Source contract:** [`audit/executor-brief.md`](executor-brief.md) (1234 lines, 15 C-items, P0-P2 tiers)

---

## Verdict

> ### ⚠️ COMMENTS — REVISE AND RESUBMIT (NOT YET APPROVED)
>
> The plan is **directionally correct** — it identifies all 15 C-items with the right priority tiers, names the right files, and estimates ~8-9 hours of work (matches my brief's estimate). The Gap Analysis Matrix is honest about what exists vs. what's missing. The 5-level execution dependency ordering is sound.
>
> But the plan **loses critical precision** that my brief encodes as contract terms. As written, it would let the executor produce work that _looks_ compliant in shape but fails the auditor's exact verification commands. **15 specific revisions required** before execution authorization.
>
> **Estimated revision effort:** 30-45 min to incorporate revisions into a Plan v2. Plan v2 should be re-submitted for approval before execution begins.

---

## Verification of Plan's Factual Claims

Before commenting, I verified the plan's baseline claims against current repo state:

| Claim                                                          | Verified? | Notes                                                                   |
| -------------------------------------------------------------- | --------- | ----------------------------------------------------------------------- |
| 177 tests baseline                                             | ✅        | `pytest -q` → 177 passed in 0.31s (overtakes my brief's stale 87)       |
| 7 commits on `phase/1`                                         | ✅        | `git log --oneline phase/1` matches                                     |
| C1: only 1/205 features passing                                | ✅        | `jq '.features\|map(select(.passes==true))\|length' features.json` = 1  |
| C3: existing YAML uses `visual_registers`, not `surface_types` | ✅        | Confirmed in `consensus/axis_weights_heuristic.yaml:8-30`               |
| C3: weights NOT normalized                                     | ✅        | Corporate preset sums to 5.5, not 1.0                                   |
| C4: `consensus/research-trust.yaml` missing                    | ✅        | `ls consensus/` confirms absent                                         |
| C5: no `github_mcp.py` in integrations                         | ✅        | Only `stitch_mcp.py` present                                            |
| C6: no `atelier/recorders/` directory                          | ✅        | Directory does not exist                                                |
| C7: `gemini-2.5-flash-preview-05-20` pinned, ADR 0014 missing  | ✅        | Confirmed via `model_registry.py` + `ls docs/decisions/`                |
| C12: stale "75/75" refs clean                                  | ✅        | Re-verified: `grep -rn "75/75\|75 tests" docs/ README.md` returns empty |
| Plan's "≥188 final test target" math (177 + C5 6 + C6 5)       | ✅        | Arithmetic correct                                                      |

**Verdict on factual integrity:** the plan does NOT lie about state. ✅

---

## Must-Fix Revisions (15 items)

These must be addressed before approval. Numbered M1-M15 for cross-reference.

### M1 — C1: Enumerate the EXACT 21 feature IDs (NOT "≥21 features")

**Plan says (line 79):** "Set ≥21 features to `passes: true`"

**Problem:** Open-ended. Executor will pick an arbitrary 21 from the 205-feature pool. Auditor's verification command checks for SPECIFIC IDs.

**Required:** Plan v2 must enumerate the 21 mandatory feature IDs from `executor-brief.md` §4 C1:

```
F0001a, F0001b, F0002, F0003, F0004, F0005, F0006,
F0009, F0010, F0011,
FA-001, FA-002, FA-003, FA-005, FA-006, FA-007, FA-008, FA-009, FA-010,
FA-015, FA-016
```

Each entry must include the SHA(s) from `git log phase/1 --oneline` that prove implementation, plus a `tests/` path that proves test coverage. No fabricated SHAs (auditor will `git show <SHA>` each one).

---

### M2 — C3: Acknowledge full impact scope (YAML rewrite ≠ 30 min)

**Plan says (line 15):** "30 min" effort for C3.

**Problem:** Schema rewrite of `axis_weights_heuristic.yaml` cascades into:

- `atelier-core/src/atelier/models/axis_weights.py` (220 lines, hardcodes `_WEIGHT_PRESETS` keyed on visual_register strings)
- `atelier-core/tests/unit/test_axis_weights.py` (tests assume `visual_register` API)
- Any ConsensusAgent code that calls `compute_axis_weights(visual_register=...)` (need to grep)

Plan's open question (line 45) acknowledges "update `axis_weights.py` to consume the new schema" but does NOT cost it. Realistic effort: **90 min, not 30 min.**

**Required:** Plan v2 must split C3 into:

- C3a: YAML rewrite (30 min)
- C3b: `axis_weights.py` consumer refactor + tests update (60 min)
- C3c: Migration note in ADR (15 min) — document that `visual_register` is now an INPUT to surface-type mapping, not a direct preset key

---

### M3 — C3 + C13: Reconcile newly-discovered `consensus/constitutions/` directory

**Plan does not mention:** `consensus/constitutions/apple-grade.yaml` (2099B) and `consensus/constitutions/brutalist.yaml` (1681B) exist — created in commit `fe7fd96`. Apple-grade.yaml has 5 principles (P1-P5) with weights, already structured.

**Conflict:** My brief's C13 specifies a `constitution-apple-grade/` _directory_ with `index.json` + per-principle `.md` files. The existing `apple-grade.yaml` is a single YAML file in a _different_ path.

**Required:** Plan v2 must declare ONE of:

- **Option A** (preferred — minimal change): Adopt `consensus/constitutions/apple-grade.yaml` as canonical, REVISE brief's C13 expectation accordingly, and document in handoff that `consensus/constitution-apple-grade/` empty dir is deleted (with `git rm`).
- **Option B** (expensive): Migrate apple-grade.yaml's 5 principles into the `constitution-apple-grade/{P1,P2,P3,P4,P5}.md` + `index.json` format per brief, deprecate the YAML.

Same question applies to brutalist.yaml. Either way, the plan must explicitly handle the duplication, not silently leave both.

---

### M4 — C5: Enumerate 6 specific test cases (NOT "6+ tests covering: ...")

**Plan says (line 104):** "6+ tests covering: success, 404, 5xx retry, auth failure, rate limit, env token"

**Problem:** Comma-separated list is too vague. My brief's §4 C5 specifies them as named test functions with explicit assertions:

```python
test_fetch_readme_success            # 200 OK + decoded base64 content assertion
test_fetch_readme_404_returns_none   # NOT raises; returns None per fail-soft
test_fetch_file_5xx_retries_then_fails  # 3 retries with backoff, then GitHubMCPError
test_auth_401_raises_typed_error     # GitHubMCPError.kind == "auth"
test_rate_limit_429_respects_retry_after  # honors X-RateLimit-Reset header
test_env_token_fallback              # uses GITHUB_TOKEN env when no kwarg
```

**Required:** Plan v2 must use these exact test function names (or document why renaming).

---

### M5 — C6: Acknowledge forbidden APIs + failure-trichotomy mapping + table name

**Plan says (lines 107-110):** "BQ streaming insert, async context manager, OTel span emission, insertId for idempotency"

**Missing from plan (specified in brief §4 C6):**

1. **Forbidden APIs:** `LoadJob`, `client.load_table_from_*`, `client.load_table_from_dataframe`. These are batch jobs, not streaming. Auditor greps for these as red flags.
2. **Required API:** `client.insert_rows_json(table, rows, row_ids=...)` (the streaming `insertAll` endpoint).
3. **Table FQN:** `i-for-ai.atelier_trajectories.trajectory_records` (NOT a placeholder; auditor checks exact string).
4. **Failure trichotomy mapping** (per my brief + CLAUDE.md):
   - Schema mismatch / quota exceeded → **fail-loud** (raise + log + halt)
   - Transient 503 / connection reset → **self-heal** (3 retries w/ exp backoff, then escalate)
   - Single-row insertion error in batch → **fail-soft** (log row + insertId, continue batch, surface count to OTel span attr `bq.insert_errors`)
5. **OTel span:** `bigquery.insert_rows_json` (not just "emit span"; auditor checks span name).

**Required:** Plan v2 must list all 5 of these as explicit acceptance criteria for C6.

---

### M6 — C6: Enumerate 5 specific test cases

**Plan says (line 113):** "5+ tests with mocked BQ client"

**Required (per brief §4 C6):**

```python
test_insert_single_row_success           # mock returns [], assert insert_rows_json called with [{...,insertId:...}]
test_insert_batch_with_partial_failure   # mock returns [{"index":2,"errors":[...]}], assert row 2 logged but batch returns success_count=4
test_context_manager_auto_flush_on_exit  # __aexit__ flushes pending buffer
test_503_retries_3_times_then_raises     # tenacity / backoff config verified
test_insert_id_idempotency               # same row submitted twice = same insertId
```

---

### M7 — C7: List required ADR h2 sections + DECISIONS.md update

**Plan says (line 116):** "ADR documenting the model deviation with migration plan"

**Required (per brief §4 C7):**

- Required h2 sections (auditor greps for these literal strings):
  - `## Context` — why pinned to `gemini-2.5-flash-preview-05-20` (Vertex AI quota / availability date)
  - `## Decision` — pin this version explicitly; do NOT silently track gemini-3-flash
  - `## Consequences` — affects model_registry.py, test mocks, cost estimates
  - `## Alternatives Considered` — wait for gemini-3-flash GA, use gemini-2.5-pro
  - `## Status` — Accepted / Date / Author
- Update `DECISIONS.md` index at repo root with new row pointing to ADR 0014
- Update `model_registry.py` docstring with `# Pin justified in ADR 0014` comment + link

---

### M8 — C8: Resolve plan's own open question about otelcol dry-run

**Plan asks (line 51):** "Should we add it to dev deps or just validate YAML parse?"

**Required answer (per brief §4 C8):** YAML parse validation only. Reason: otelcol binary install is out-of-scope for a sprint (introduces brew/Docker dep). Validation: `python -c "import yaml; yaml.safe_load(open('config/otel-collector-config.yaml'))"` exit 0.

Plan v2 must close this question explicitly, not leave it open.

---

### M9 — C9: Enumerate ALL workflow files needing `phase/*` triggers

**Plan says (line 122):** "Add `phase/*` to `on.push.branches` and `on.pull_request.branches`" — singular "CI workflow files" (plural noun but no enumeration).

**Verified workflow files** (`.github/workflows/`):

- `ci.yml` — already has `phase` references (4 matches) per plan's own admission
- `release.yml` — does NOT have `phase` references

**Required:** Plan v2 must:

1. List BOTH workflow files as targets
2. Specify the YAML structure to add: `branches: [main, "phase/*"]` (not just "phase/\*")
3. Verify with `gh workflow list && gh run list --branch phase/1 --limit 1` after change (run should be visible)

---

### M10 — C10: Address ALL pre-commit hooks, not just ruff

**Plan says (line 130):** "Bump ruff to v0.15.x"

**Problem:** My brief's §4 C10 calls out ruff specifically as the visible drift, but mentions that running `pre-commit autoupdate` will bring all 8 hooks (mypy, markdownlint, prettier, detect-secrets, commitlint, etc.) into sync. Cherry-picking only ruff leaves the other hooks at risk of similar drift.

**Required:** Plan v2 must:

1. Run `pre-commit autoupdate` (updates all hooks)
2. Run `pre-commit run --all-files` to confirm no new failures
3. Pin any hook version that the autoupdate moved to a major-version bump (note in commit message)
4. Document any hooks that REFUSED to update (e.g., a pinned commitlint version) with rationale

---

### M11 — C11: Add `testpaths` + `addopts`, not just `pythonpath`

**Plan says (line 133):** "Add `[tool.pytest.ini_options]` with `pythonpath`"

**Required (per brief §4 C11):**

```toml
[tool.pytest.ini_options]
pythonpath = ["atelier-core/src"]
testpaths = ["atelier-core/tests"]
addopts = "-q --strict-markers --strict-config"
```

All three keys are required. `--strict-markers` catches typos in `@pytest.mark.xxx`. `--strict-config` catches typos in pyproject.toml options. Plan must include both.

---

### M12 — C13: Specify the per-principle file structure

**Plan says (lines 136-137):** "5+ principle markdown files with do/don't examples"

**Required (per brief §4 C13):** Each `{P1,P2,...}.md` must contain:

```markdown
# {Principle Name}

{1-paragraph definition with REAL Apple HIG citation, e.g.,
"Per Apple Human Interface Guidelines §Hierarchy (https://developer.apple.com/...),
information density should..." — fabricated URLs caught by markdown-link-check}

## Do

- {3 concrete examples, each with code snippet or screenshot ref}

## Don't

- {3 anti-examples, each with code snippet or screenshot ref}

## Edge case

- {1 nuanced scenario where the rule has a documented exception}
```

Plus `index.json`:

```json
{
  "version": 1,
  "principles": [
    {"id": "P1", "file": "P1.md", "weight": 0.3},
    {"id": "P2", "file": "P2.md", "weight": 0.2},
    ...
  ]
}
```

where weights sum to 1.0 ± 0.01. Auditor verifies via `jq '[.principles[].weight] | add' index.json`.

See M3 — this requirement may be subsumed by adopting `consensus/constitutions/apple-grade.yaml` instead. Plan must declare which path it's taking.

---

### M13 — C14: Verify ATELIER_OBSERVABILITY_MODE flag IS IMPLEMENTED first, cite ADR 0006

**Plan says (line 140):** "Add `## Local development observability` section documenting Phoenix dev mode"

**Critical finding:** I grep'd for `ATELIER_OBSERVABILITY_MODE` and `phoenix` in `atelier-core/src/atelier/observability/` — **NO RESULTS**. The flag itself does not exist in code yet. C14 cannot be documentation-only if the flag isn't implemented.

**Required:** Plan v2 must either:

- **Option A:** Verify the flag IS implemented elsewhere (different directory, init code), provide grep evidence — then C14 stays docs-only.
- **Option B:** Add a code task to implement the flag (env var read in observability init, conditional Phoenix exporter mount), THEN write the docs. This expands C14 from 10 min to ~45 min.

Also: README section MUST cite ADR 0006 (Google-Native rationale: Phoenix is dev-only because production uses Cloud Trace + BigQuery; otherwise reader assumes Phoenix is a production dep, contradicting ADR 0006).

---

### M14 — Plan must explicitly acknowledge the 6 non-C-item brief sections

**Plan addresses:** Only the C-items (§4) plus a Verification Plan section.

**Missing acknowledgment of brief sections** (executor MUST adhere to these during execution):

- **§2 Operating constraints** — the verbatim CLAUDE.md XML invariants apply throughout (no_unverified_apis, compile_then_commit, no_speculation, lockfile_only_installs, conventional_commits_required, wrap_phase_work_in_worktrees, etc.)
- **§3 Pre-flight checks** — executor must run `git status` (clean tree), `pytest -q` (177 pass baseline), `pre-commit run --all-files` (current state) BEFORE first modification. Output captured.
- **§6 Handoff protocol** — executor produces `audit/executor-handoff.md` ending with literal `READY-FOR-AUDIT:` signal line + table of C1-C15 status + verification command output for each
- **§7 Anti-patterns** — 14 cheats auditor will look for (hardcoded test values, mocking what should integrate, fake commit SHAs, dummy ADR with no actual decision, etc.)
- **§10 16-item self-check** — executor runs this before signaling READY
- **§11 Sign-off** — executor declaration that nothing in the brief was skipped or partially completed

**Required:** Plan v2 must add a top-level section "Brief Compliance Acknowledgment" listing these 6 sections explicitly so the executor doesn't only optimize for the visible C-items table.

---

### M15 — Plan must resolve all 3 of its own Open Questions explicitly

**Open Q1 (line 45) — C3 schema replace vs alongside:** Recommendation is to fully replace (per M2 + M3 above). Plan v2 must record this decision in the body, not leave it as a question.

**Open Q2 (line 48) — httpx in deps:** **Resolved by me now:** `httpx==0.28.1` is in `requirements.lock`. Plan v2 should remove this as an open question.

**Open Q3 (line 51) — otelcol binary:** Resolved by M8 above (YAML parse only, no binary install).

All 3 open questions must be closed in Plan v2; an "Open Questions" section that's still open after review means re-litigation during execution.

---

## Should-Fix Revisions (5 items)

Lower priority. Address in Plan v2 if effort allows; otherwise document as known gaps in handoff.

### S1 — Add a Level 0 (Pre-flight verification) before Level 1

Plan starts at Level 1 (Sprint State). Should start at Level 0:

- `git status` clean
- `pytest -q` → 177 pass
- `pre-commit run --all-files` → output captured (likely has existing failures; baseline known)
- `git log --oneline phase/1 | wc -l` = 7

Capture all outputs in `audit/executor-handoff.md` under "Pre-flight baseline."

### S2 — Add a Level 6 (Post-flight + Handoff) after Level 5

Plan ends at Level 5 (C15 STATUS.md update). Should end at Level 6:

- Full test suite re-run (≥188 pass target)
- `mypy --strict` re-run (no new errors)
- `pre-commit run --all-files` (no new failures)
- `git log --oneline phase/1 | wc -l` (one commit per C-item ≈ 14 new commits)
- Write `audit/executor-handoff.md` with per-C-item status + verification output
- End handoff doc with `READY-FOR-AUDIT:` literal signal

### S3 — Effort estimate is optimistic; add 25% buffer

Plan estimates: 30 + 120 + 240 + 90 + 5 = 485 min ≈ 8 hr. With M2's C3 expansion (+60 min), M13's C14 possible expansion (+35 min), and realistic context-switch overhead, realistic effort is **10-12 hours.** Plan v2 should acknowledge this.

### S4 — Sequence dependency: C13 must wait on M3 decision

If M3 lands on "Option A" (adopt YAML), C13 work drops to ~10 min (just delete empty dir). If "Option B" (migrate to MD), C13 stays at 60 min. Plan v2 should sequence M3 decision BEFORE Level 4 begins to avoid wasted work.

### S5 — Add an explicit "rollback plan" for risky changes

C3 schema rewrite, C10 hook autoupdate, and C11 pyproject changes can all break currently-passing 177 tests. Plan v2 should add: "If `pytest -q` fails after a change, executor MUST revert that change and surface the failure to the governor before attempting alternative approaches. No silent fixes."

---

## Plan Strengths (acknowledge what's working)

These should be preserved in Plan v2 — they are good and complete:

- ✅ Gap Analysis Matrix is **honest** about state (1/205, missing dir, wrong schema). No false claims.
- ✅ P0/P1/P2 prioritization correct (matches my brief's tier assignments).
- ✅ 5-level execution dependency ordering is sound: state → config → code → hygiene → final pointer.
- ✅ C6 CAUTION block correctly identifies the data-model-vs-writer gap (high-value catch — this is the most subtle issue in the brief).
- ✅ Plan correctly flagged 3 open questions BEFORE executing, rather than guessing — good discipline.
- ✅ Verification Plan section correctly names the 4 final-suite commands (`pytest -q`, `mypy --strict`, `pre-commit run --all-files`, `jq features.json`).
- ✅ ≥188 final test target arithmetic is correct.

---

## Re-submission Process

1. Executor produces **Plan v2** incorporating M1-M15 (must-fix) + S1-S5 (should-fix, optional but recommended).
2. Save to same path or `audit/implementation-plan-v2.md` in worktree.
3. Notify governor (this agent) for re-review.
4. On governor APPROVAL, executor begins C1-C15 execution following Plan v2.
5. Executor produces `audit/executor-handoff.md` with `READY-FOR-AUDIT:` signal at bottom when done.
6. Governor performs final re-audit against original `executor-brief.md` (5-agent parallel pass per brief §9).

**Estimated turnaround:**

- Plan v2 drafting: 30-45 min
- Plan v2 re-review: 15 min
- Execution: 10-12 hr (per S3)
- Handoff doc: 30 min
- Re-audit: 60 min

**Total to closeout:** ~14 hours of executor wall-time + 2 hours of governor wall-time. Should complete by end of D8 (2026-05-22) if started today.

---

## Iron Law Enforcement

Per `superpowers:verification-before-completion`: **executor cannot claim "DONE" without running fresh verification commands and capturing exit codes + output in the handoff doc.** No `# should pass now`. No `# pre-commit said OK earlier`. Every claim in `executor-handoff.md` needs:

- The exact command run
- The exit code
- Stdout/stderr (or snippet showing the pass signal)
- A claim that maps to that evidence

The governor will spot-check 5 random claims by re-running the commands. Mismatches → REJECTED, cycle back to executor.

Three REJECTED cycles in a row → governor surfaces non-convergence to the user with recommendation to descope or extend sprint.

---

**Signed:** Governor / Auditor agent
**Awaiting:** Plan v2 from executor with M1-M15 addressed
**Do not begin C1-C15 execution until Plan v2 approved.**
