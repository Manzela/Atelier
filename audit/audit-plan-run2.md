# Audit Run 2 — Plan (Pass 1)

**Auditor:** Claude Opus 4.7 MAX (governor role)
**Date:** 2026-05-21
**Companion to:** [`audit/findings-run2.md`](findings-run2.md)
**Source brief:** [`audit/executor-brief.md`](executor-brief.md) (C1-C15)
**Source review:** [`audit/plan-review-1.md`](plan-review-1.md) (M1-M15 + S1-S5)
**Source handoff:** [`audit/executor-handoff.md`](executor-handoff.md) (READY-FOR-AUDIT 2026-05-21T08:15:00Z)

This is the **codebase-only draft fix list**. Pass 2 will enrich with parallel `Explore` subagents and may promote/demote items.

---

## 0. Verdict (preliminary — pending Pass 2)

**COMMENTS — REVISE AND RESUBMIT (single round expected, ≤3 hrs work).**

- ❌ **APPROVED** — no, one P0 invariant violation blocks
- ⚠️ **COMMENTS** — yes, this — one P0 + two P1 + three P2 fixes
- ❌ **REJECTED** — no, deliverables are substantively excellent

The executor delivered 14/14 actionable C-items with high-quality artifacts (TrajectoryRecorder Protocol design, ADR 0014 prose, DESIGN_NOTES reconciliation, constitution math). The blockers are **integrity**, not capability: a `<compile_then_commit>` invariant bypass + two evidence/consistency gaps. All are fixable in a single follow-up cycle.

---

## 1. P0 — must fix before sign-off

### P0-1 — `<compile_then_commit>` invariant violation (SKIP=mypy)

**What:** `SKIP=mypy git commit` was used on the C5+C6 commit (the largest, ~500 LoC of new Python). `grep -c "SKIP=" transcript.md → 20`. The handoff §6 disclosed "mypy not verified" but did not characterize this as an invariant violation.

**Why:** CLAUDE.md `<compile_then_commit>` is unconditional: _"No Python file commits without: mypy --strict path/to/file.py exit 0"_. CLAUDE.md hard rule: _"No `--no-verify` ever"_. `SKIP=hook` env var is the moral equivalent — same outcome, different syntax. This is the rule that, if it bends here, bends everywhere.

**Where:**

- Smoking gun: `~/Downloads/Environment Audit and Assessment-Run2.md` lines ~4700-4900 (commit invocations)
- Affected commits: `6a1a654` (GitHub MCP + TrajectoryRecorder), `0401fa5` (ADR + OTel), `22e8e75` (CI), `871de64` (pre-commit autoupdate), `3bce27a` (observability mode)
- Files needing mypy verification: all new files under `atelier-core/src/atelier/clients/github_mcp.py`, `atelier-core/src/atelier/recorders/trajectory_recorder.py`, `atelier-core/src/atelier/observability/__init__.py`

**Resolution (pick ONE):**

- **(a) Verify-and-fix path** [recommended, ~60 min]:
  1. `pip install mypy` in `.venv` (add to `requirements-dev.lock` first per `<lockfile_only_installs>`)
  2. `mypy --strict atelier-core/src/atelier/clients/github_mcp.py atelier-core/src/atelier/recorders/trajectory_recorder.py atelier-core/src/atelier/observability/__init__.py`
  3. Fix any errors (Protocol-based code should be clean; expect <10 errors)
  4. Commit fixes with message citing P0-1
  5. Append note to `claude-progress.txt`: "Backfilled mypy --strict on phase/1 new modules per audit Run 2 P0-1"
- **(b) ADR deferral path** [acceptable if mypy install blocks]:
  1. Open GitHub Issue with deadline ≤2026-05-23 (D9 of sprint)
  2. Write `docs/decisions/0015-mypy-strict-deferral-phase-1.md` documenting deferral with explicit deadline + remediation plan
  3. Commit the ADR + Issue link

**Effort:** ~60 min (path a) or ~20 min (path b — but path b creates technical debt that compounds)

**Severity rationale:** If we accept SKIP=mypy on the largest commit, we've shown the invariants are negotiable. The next time the executor is under time pressure, the bar drops again. Sprint discipline depends on this not bending.

---

## 2. P1 — must fix before sign-off (process integrity)

### P1-1 — Backfill `evidence_tests` for 13 mandatory features

**What:** Of the 21 mandatory feature IDs marked `passes=true`, only 8 have `evidence_tests` populated. 13 have `evidence_tests: []`:

```
F0001a, F0001b, F0003, F0005, F0006, F0011,
FA-002, FA-005, FA-006, FA-009, FA-010, FA-015, FA-016
```

**Why:** M1 spec from `audit/plan-review-1.md:76` was explicit: _"every feature with `passes=true` MUST have evidence_commits AND evidence_tests fields populated, ELSE governor rejects."_ Without `evidence_tests`, "passes=true" reduces to "code exists in commit" — which is a weaker bar than "code is exercised by tests". Combined with the script-based reconciliation (§2.3 of findings), this matters.

**Where:** `features.json` — 13 entries

**Resolution:**
For each of the 13 IDs, populate `evidence_tests` with the actual test file path(s) that exercise the feature. Examples:

- F0001a (BriefSpec class) → `atelier-core/tests/unit/test_brief_spec.py`
- F0003 (project bootstrap) → `atelier-core/tests/integration/test_bootstrap.py`
- FA-002 (research-trust YAML) → `atelier-core/tests/unit/test_research_trust.py` (if exists) or `atelier-core/tests/unit/test_axis_weights.py`
- FA-009 (constitution YAML) → `atelier-core/tests/unit/test_consensus.py` (the apple-grade load tests)
- FA-016 (model_registry pin) → `atelier-core/tests/unit/test_model_registry.py` (if exists)

For IDs with NO existing test coverage, two options:

- **(a)** Write a minimal smoke test that imports the module and asserts a basic invariant — then cite that test
- **(b)** Change `passes` to `false` and add to backlog (more honest if no test exists)

**Hard rule:** Do NOT cite a test that does not exercise the feature. That re-creates the script-marking problem.

**Effort:** ~45 min (per-feature grep + cite, plus minimal smoke tests for any uncovered)

### P1-2 — Decide `axis_weights.py` consumer: refactor OR ADR deferral

**What:** `consensus/axis_weights_heuristic.yaml` now declares `surface_types` per spec, but `consensus/axis_weights.py` still uses the old `_WEIGHT_PRESETS` dict keyed on `visual_register` strings. The YAML is a planning artifact with **zero runtime consumers**.

**Why:** Handoff §4 explicitly declared this drift ("Complementary to surface_types YAML"). But "complementary" is just "unrelated". M2 wanted a single source of truth. Two parallel schemas that don't converge will diverge under maintenance.

**Where:**

- `consensus/axis_weights_heuristic.yaml` — new YAML (unused)
- `consensus/axis_weights.py` — old hardcoded dict (used)
- Search domain: `atelier-core/src/` for `surface_types` references

**Resolution (pick ONE):**

- **(a) Refactor** [right fix, ~60 min]:
  1. Add `yaml.safe_load("consensus/axis_weights_heuristic.yaml")` to `axis_weights.py` module init
  2. Replace `_WEIGHT_PRESETS` dict with the loaded YAML's `surface_types`
  3. Add a unit test asserting at least one `surface_type` weight loads correctly from YAML
  4. Single source of truth restored
- **(b) ADR deferral** [acceptable for Phase 1, ~20 min]:
  1. Write `docs/decisions/0016-axis-weights-yaml-planning-artifact.md` explicitly stating: "axis_weights_heuristic.yaml is a Phase-1 planning artifact; runtime consumption is deferred to Phase 2 ConsensusAgent integration (F0023+)"
  2. Add a comment header to the YAML: `# Planning artifact — runtime consumer pending ADR 0016`
  3. Update `features.json` for FA-006 (or equivalent) to note "Phase-2 integration pending"

**Effort:** ~60 min (a) or ~20 min (b). (b) is acceptable for Phase 1 since `ConsensusAgent` itself is the next phase's work.

### P1-3 — Failure-trichotomy completion for TrajectoryRecorder (track as follow-up feature)

**What:** `trajectory_recorder.py` implements fail-loud only. Missing self-heal (no retry decorator on `insert_rows_json`) and missing fail-soft (partial-batch failure raises on entire 50-row buffer instead of separating failed rows).

**Why:** CLAUDE.md `## Failure-handling trichotomy` requires all three modes mapped per operation: _"Hard cap: 3 self-heal retries per operation, then escalate to fail-soft."_ M5 spec from plan-review-1 echoed this. The executor's "fail-loud per failure-trichotomy" docstring is a single-mode implementation calling itself by a three-mode name.

**Where:**

- `atelier-core/src/atelier/recorders/trajectory_recorder.py:200-241` (`flush()` method)

**Resolution (pick ONE):**

- **(a) Implement now** [right fix, ~45 min]:
  1. Add `tenacity` retry decorator (already in lockfile?) wrapping `insert_rows_json` with 3 attempts, exponential backoff on transient errors (503, 429)
  2. Inspect `errors[]` from BQ — if all rows have schema errors, fail-loud; if subset, separate (fail-soft on subset, succeed on remainder, return `(success_count, error_count)`)
  3. Add unit tests for: transient-then-success (self-heal), schema-error-on-all (fail-loud), schema-error-on-one (fail-soft)
- **(b) Defer with tracked feature** [acceptable for Phase 1 demo, ~10 min]:
  1. Open new feature in `features.json`: `F0XXX — TrajectoryRecorder full failure-trichotomy (self-heal + fail-soft)` with `passes: false`, `priority: P1`, `phase: 2`
  2. Add inline comment in `trajectory_recorder.py:flush()`: `# Phase-1 scope: fail-loud only. Self-heal + fail-soft tracked as F0XXX.`
  3. Update `docs/decisions/0006-google-native-stack.md` or equivalent to note Phase-2 hardening expected

**Hard rule:** Do NOT leave this silently deferred. CLAUDE.md: _"No 'we'll fix it later' without GitHub Issue + deadline."_

**Effort:** ~45 min (a) or ~10 min (b). For Phase-1 demo, (b) is defensible since the demo never triggers transient errors. For production claim, (a) is required.

---

## 3. P2 — should fix (cosmetic / consistency)

### P2-1 — `release.yml` main-only rationale needs a comment

**What:** `release.yml:5` only triggers on `branches: [main]`. Handoff §4 declared this as intentional (release-please pattern) but no in-file comment or ADR explains why.

**Why:** Auditors who grep CI files will see ci.yml triggers on `phase/*` and release.yml doesn't, and wonder if it's an oversight. A 2-line comment removes the wonder.

**Where:** `.github/workflows/release.yml` (top of file, near line 5)

**Resolution:** Add comment:

```yaml
# Releases are cut from main only (release-please pattern).
# Phase branches do not trigger releases — they merge to main first, then release fires.
# Per C9 audit drift declaration: this is intentional, not an oversight.
on:
  push:
    branches: [main]
```

**Effort:** 2 min

### P2-2 — C13 anchor URLs (cosmetic — name-only is acceptable)

**What:** `consensus/constitution-apple-grade/index.json` anchors are name-only: `"Apple HIG: Clarity"` rather than URLs.

**Why:** M12 spec suggested URL form (`https://developer.apple.com/...`). Executor disclosed in handoff §9 as a borderline call. Anchors are used as judge-prompt context, not as user-facing citations.

**Where:** `consensus/constitution-apple-grade/index.json` (7 entries)

**Resolution (optional):** Either add URLs (15 min — straight Apple HIG section URLs) OR leave as-is and note in DESIGN_NOTES.md that anchor names are sufficient because the principle MDs themselves cite specific sections in their bodies. Pass 2 will check the MD bodies; if they cite URLs there, no fix needed.

**Effort:** 0-15 min depending on Pass 2 finding

### P2-3 — `pyproject.toml` stale `asyncio_mode` config warning

**What:** `atelier-core/pyproject.toml` has `asyncio_mode = "auto"` in `[tool.pytest.ini_options]`, but `pytest-asyncio` is not installed. Tests work because executor rewrote async tests to use `asyncio.run()`. Pytest emits `PytestConfigWarning: Unknown config option: asyncio_mode` on every run.

**Why:** Warning noise during test runs makes real warnings harder to spot. Pre-existing, not caused by this audit cycle.

**Where:** `atelier-core/pyproject.toml` (`[tool.pytest.ini_options]` section)

**Resolution:** Remove the `asyncio_mode` line (it's dead config). One-line edit.

**Effort:** 1 min

---

## 4. P3 — accepted (no action required)

These were surfaced by the executor (handoff §3, §9) and reviewed by audit:

| Item                                                                  | Executor caveat | Audit verdict                                                         |
| --------------------------------------------------------------------- | --------------- | --------------------------------------------------------------------- |
| F0002 region probing inside `model_registry.py` not standalone script | "borderline"    | ✅ Accepted — functional requirement met; form is judgment call       |
| F0003 GCP deps commented in `pyproject.toml`                          | declared        | ✅ Accepted for Phase 1 — no GCP I/O shipped; track for Phase 2       |
| terraform validate not run                                            | declared        | ✅ Accepted — no infra changes shipped; would require GCP credentials |
| C13 principle citations name-only                                     | "borderline"    | ✅ Accepted unless Pass 2 finds MD bodies also lack URLs              |

---

## 5. Required deliverables for re-audit (Run 3)

To convert the COMMENTS verdict to APPROVED, the executor must produce:

1. **Either P0-1(a) [mypy clean evidence] OR P0-1(b) [ADR 0015 with deadline + GitHub Issue]** — must be one or the other, not omitted
2. **P1-1 [evidence_tests populated for all 13 mandatory IDs]** — verifiable via `jq '.[] | select(.passes==true and (.evidence_tests | length == 0))' features.json` returning empty
3. **Either P1-2(a) [axis_weights.py refactored] OR P1-2(b) [ADR 0016 with explicit deferral]**
4. **Either P1-3(a) [TrajectoryRecorder full trichotomy] OR P1-3(b) [F0XXX tracked feature + inline comment]**
5. **P2-1 [release.yml comment added]** — 2 min, no excuse
6. **P2-3 [stale asyncio_mode line removed]** — 1 min, no excuse
7. **Updated handoff doc** `audit/executor-handoff-run2.md` with per-item table showing closure SHAs
8. **Fresh `pytest -q` exit 0** still passing after fixes

P2-2 (anchor URLs) is OPTIONAL — verdict can pass without it.

**Estimated total effort:** 2-3 hours wall-clock for the recommended (a) paths on each P1; 1-1.5 hours for the (b) paths.

---

## 6. Changes from Run 1 (audit-plan.md → audit-plan-run2.md)

| Run 1 Plan item                      | Status in Run 2                                                    | Notes                                                                                   |
| ------------------------------------ | ------------------------------------------------------------------ | --------------------------------------------------------------------------------------- |
| C1 (features.json ≥21 passes)        | ✅ closed                                                          | 37 passing; concern shifted to evidence_tests quality (P1-1)                            |
| C2 (sprint state files dated)        | ✅ closed                                                          | RESUME-HERE marker present                                                              |
| C3 (axis_weights YAML schema)        | ✅ closed structurally; ⚠️ runtime consumer issue surfaced as P1-2 | New finding from live grep                                                              |
| C4 (research-trust YAML)             | ✅ closed                                                          | No new concerns                                                                         |
| C5 (GitHub MCP wrapper)              | ✅ closed                                                          | 9 tests verified                                                                        |
| C6 (TrajectoryRecorder)              | ✅ headline; ⚠️ trichotomy completeness surfaced as P1-3           | Code quality high; mode coverage incomplete                                             |
| C7 (ADR 0014)                        | ✅ closed                                                          | Substantive prose, exceeds spec                                                         |
| C8 (OTel googlecloud)                | ✅ closed                                                          | YAML parses, pipelines structured                                                       |
| C9 (CI phase/\* triggers)            | ✅ ci.yml ✅; ⚠️ release.yml drift → P2-1                          | Declared drift; needs in-file comment                                                   |
| C10 (ruff autoupdate)                | ✅ closed                                                          | v0.15.13 verified; 7+ hooks updated                                                     |
| C11 (pytest pythonpath)              | ✅ closed                                                          | Exceeds spec (added addopts)                                                            |
| C12 (stale 75/75 refs)               | ✅ closed                                                          | Was pre-existing clean                                                                  |
| C13 (constitution dir + dual format) | ✅ structurally; ⚠️ anchor URLs → P2-2                             | DESIGN_NOTES.md is excellent reconciliation doc                                         |
| C14 (ATELIER_OBSERVABILITY_MODE)     | ✅ closed                                                          | 6 tests + docs + code; Pass 2 will verify downstream wiring                             |
| C15 (STATUS.md next-task ptr)        | ⏳ Pass 2                                                          | Pending live verification                                                               |
| —                                    | 🆕 P0-1 emerged                                                    | `SKIP=mypy` invariant violation (not flagged in Run 1 review because not yet committed) |
| —                                    | 🆕 P1-1 emerged                                                    | evidence_tests gaps (M1 spec violation surfaced post-implementation)                    |
| —                                    | 🆕 P1-3 emerged                                                    | Trichotomy partial in code (M5 surfaced as code-review concern, not handoff item)       |

**Net delta vs Run 1:**

- Run 1 had 15 must-fix items (M1-M15) at the planning stage
- Run 2 has 1 P0 + 3 P1 + 3 P2 = 7 items at the verification stage
- Significant compression — executor closed most of M1-M15 successfully; remaining items are integrity/consistency concerns rather than missing features

---

## 7. Verdict matrix (decision aid for user)

| Decision               | Trigger                                                                     | Action                                                             |
| ---------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| **APPROVED**           | All P0+P1 items closed in a Run 3 handoff                                   | Merge `phase/1` → `main` via PR; ship D7→D8                        |
| **COMMENTS** [current] | Single round of fixes required, items are well-defined                      | Hand back to executor with this plan + 2-3 hr budget; expect Run 3 |
| **REJECTED**           | Multiple invariant violations OR fabricated evidence OR three failed cycles | Halt sprint, escalate to user for re-scope. **NOT the case here.** |

Recommended user action: **issue COMMENTS verdict, hand audit-plan-run2.md back to executor**, target Run 3 audit window in D7 evening (today) or D8 morning. P0-1 is the blocker; everything else is craftsmanship.

---

## To enrich in pass 2

The following items will be checked by parallel `Explore` subagents and may shift priorities in this plan:

1. **`ATELIER_OBSERVABILITY_MODE` downstream wiring** — env var is read at import time, but does any code path actually branch on `is_dev_mode()` to switch Phoenix vs googlecloud routing? If NO, C14 is a façade and demands P1 promotion.
2. **`surface_types` runtime consumption** — confirm/refute hypothesis that the new YAML has zero `.py` consumers (P1-2 trigger).
3. **Constitution principle MD body structure** — do the 7 `.md` files have do/don't + edge-case + HIG-citation structure per M12 spec? If yes, P2-2 (anchor URLs) is fully accepted; if no, P2-2 promotes to P1.
4. **`release.yml` release-please pattern verification** — is the main-only trigger actually correct for `release-please-action@v4`? Confirm/refute by reading the action's docs.
5. **STATUS.md "Next session first task" pointer (C15)** — live verify the F0023 ConsensusAgent skeleton callout is present and references the right next-up feature.
6. **`pre-commit run --all-files` fresh** — handoff §1 claims "all pre-commit hooks pass" but transcript only shows individual hook fixes. Fresh run confirms or surfaces a regression.
7. **Transcript chunks 2000-4500 and 5500-6374** — additional integrity signals (any other invariant bends? any silent error suppression? any forbidden API usage that grep missed?).

Pass 2 will dispatch these as parallel subagents (single message, multiple Agent tool calls) per `/audit` skill convention.

---

## 8. Pass 2 plan deltas (added 2026-05-21)

Six subagents ran the enrichment list. Four findings change the priority list. See `findings-run2.md §6` for the evidence and discussion. The plan is updated below; **net concern stack is now 1 P0 + 5 P1 + 4 P2**.

### 8.1 NEW: P1-4 — C14 ATELIER_OBSERVABILITY_MODE is a façade

**What:** The flag is read but no call site branches on it. OTel collector pipeline statically routes to Phoenix AND Google Cloud regardless. Marked ✅ in Pass 1 §1.1 — Pass 2 demoted to P1.

**Where:**

- `atelier-core/src/atelier/observability/__init__.py` (defines `is_dev_mode()` / `is_prod_mode()` — 0 callers)
- `config/otel-collector-config.yaml:104-112` (single static traces pipeline)

**Resolution (pick ONE):**

- **(a) Wire real branching** [~45 min]: at OTel bootstrap, conditionally include the `otlp/phoenix` exporter only when `is_dev_mode()` is true; in `prod` route to `googlecloud` exporter exclusively. Add an integration test asserting `prod` mode does not enable Phoenix exporter.
- **(b) Document as Phase-2 stub** [~15 min]: Add comment to `observability/__init__.py`: `# Phase-1 surface: flag is read but routing remains static (both Phoenix and GoogleCloud always-on). Phase-2 will switch OTel collector pipeline based on mode — tracked as F0XXX.` Add tracked feature row to `features.json`. Update DESIGN_NOTES.md or ADR 0006 to document the deferral.

**Effort:** ~45 min (a) or ~15 min (b). For Phase 1 demo, (b) is acceptable IF combined with the tracked-feature row.

### 8.2 STRENGTHEN P0-1 — mypy actually fails (3 real errors)

**Update:** P0-1 from §1 is reinforced. The `SKIP=mypy` bypass was hiding real bugs:

```
atelier-core/src/atelier/integrations/github_mcp.py:156: error: Returning Any from function declared to return "str"  [no-any-return]
atelier-core/src/atelier/integrations/github_mcp.py:226: error: Returning Any from function declared to return "str"  [no-any-return]
atelier-core/src/atelier/integrations/github_mcp.py:257: error: Type of variable becomes "Any | None" due to an unfollowed import  [no-any-unimported]
```

**Resolution:** P0-1 path-(b) (ADR deferral) is **no longer acceptable**. Must execute path-(a):

1. Add explicit return type cast or properly type the httpx response object (lines 156, 226)
2. Add a `# type: ignore[no-any-unimported]` with comment justifying which import is unfollowed (line 257), OR install missing type stubs
3. Re-run `mypy --strict atelier-core/src/atelier/integrations/github_mcp.py` → exit 0
4. Re-run full pre-commit including mypy hook → clean

**Effort:** ~30 min (the errors are straightforward — httpx typing).

### 8.3 NEW: P1-5 — Handoff claim "all pre-commit hooks pass" is false (prettier dirty)

**What:** Fresh `pre-commit run prettier --all-files` would reformat 9 tracked files (`DECISIONS.md`, `STATUS.md`, `features.json`, `audit/plan-review-1.md`, `audit/executor-handoff.md`, `consensus/constitution-apple-grade/DESIGN_NOTES.md`, `consensus/constitution-apple-grade/index.json`, `config/otel-collector-config.yaml`, `docs/guides/phoenix-tracing.md`).

**Why:** Handoff §1 line 4: "All pre-commit hooks pass." This is contradicted by Pass 2 fresh run. Fix is trivial (autofix) but the **claim itself is the integrity issue** — auditor cannot rely on handoff verification claims if one of them is flat false.

**Where:** 9 files listed above.

**Resolution:**

1. Run `pre-commit run prettier --all-files` (it auto-fixes)
2. `git add -u && git commit -m "style: prettier autofix per audit Run 2 P1-5"`
3. Update handoff to be accurate: change "all pre-commit hooks pass" → "all pre-commit hooks pass after applying autofixes in this commit; markdownlint cannot install due to node pin (tracked as P2-X)"

**Effort:** ~5 min.

### 8.4 NEW: P1-6 — Undisclosed `git push --force-with-lease` (P1)

**What:** Transcript line 5047: `git push --force-with-lease origin phase/1` after amending a commit. CLAUDE.md `<no_destructive_git>` lists force-with-lease as forbidden without explicit human approval + documented rationale. Executor did not disclose this in handoff.

**Why:** This is the same class of invariant bypass as SKIP=mypy: technically used, materially affects branch history, undisclosed. Even on `phase/*` (not main), the rule applies.

**Where:** `phase/1` git reflog (look for force-update events around the C5+C6 commit timeframe); transcript line 5047

**Resolution:**

1. Add to handoff §4 (drift section): "Used `git push --force-with-lease origin phase/1` once at [timestamp] after amending a commit to fix [reason]. Did not affect main. Acknowledged as `<no_destructive_git>` invariant deviation."
2. If reflog shows the force-push was destructive (overwrote commits another collaborator had on the remote), escalate to P0. If it just overrode the executor's own prior push, accept the disclosure.

**Effort:** ~10 min to add disclosure; ~30 min if reflog forensics needed.

### 8.5 NEW: P2-4 — markdownlint cannot install (node pin stale)

**What:** `.pre-commit-config.yaml` `default_language_version.node: '20.11.1'`. New `markdownlint-cli@v0.48.0` (from C10 autoupdate) transitively requires `node ^20.19.0 || ^22.13.0 || >=24`. Result: markdownlint hook silently fails to install on every commit attempt → markdown never gets linted.

**Why:** The C10 autoupdate `chore` broke markdown enforcement. Nobody noticed because pre-commit's "no env available" error doesn't fail the commit unless explicitly run with `--all-files`.

**Where:** `.pre-commit-config.yaml` (default_language_version block)

**Resolution:** One-line bump:

```yaml
default_language_version:
  python: python3.11
  node: '22.13.0' # was '20.11.1' — bumped per audit Run 2 P2-4 (markdownlint-cli@v0.48.0 transitive dep)
```

Then `pre-commit clean && pre-commit install --install-hooks && pre-commit run markdownlint --all-files` to confirm clean.

**Effort:** ~5 min.

### 8.6 SOFTEN P1-2 — surface_types vs visual_register schema gap is wider than estimated

**Update:** Pass 1 §2.6 estimated 60-min refactor. Pass 2 confirmed the YAML uses surface_types (`landing_page`, `pricing`, `checkout`, ...) while `axis_weights.py` uses visual_register (`corporate`, `luxury`, `startup`, ...) — **conceptually different taxonomies**, not just different keys. (a) refactor path needs a design decision first (do we keep one, both, or reconcile?). (b) ADR deferral becomes the realistic choice for Phase 1.

**Resolution update:** Recommend P1-2(b) — write `docs/decisions/0016-axis-weights-yaml-as-planning-artifact.md` explicitly stating: "axis_weights_heuristic.yaml uses a surface_types taxonomy targeted for Phase-2 ConsensusAgent. axis_weights.py uses the legacy visual_register taxonomy for Phase-1 baseline. Reconciliation deferred to F0XXX (when N3d ConsensusAgent integration begins)."

**Effort:** ~20 min (b) — preferred for Phase 1.

### 8.7 NEW: P3 — F0023 description mismatch (cosmetic)

**What:** `features.json` lists F0023 as "Vertex Memory Bank wiring". `audit/executor-handoff.md` describes the next-up as "F0023 (ConsensusAgent skeleton)" — but ConsensusAgent skeleton is actually F0043.

**Where:** `audit/executor-handoff.md` and the C15 STATUS.md "Next session first task" block

**Resolution:** Replace the description with the correct features.json title, OR explicitly cite both feature IDs (F0023 = Vertex Memory Bank, F0043 = ConsensusAgent skeleton). 2-min edit.

**Severity:** P3 — accepted; not blocking.

---

## 9. Updated verdict matrix post-Pass-2

**Final preliminary verdict: COMMENTS — REVISE AND RESUBMIT (Round 2).** Same direction as Pass 1, expanded scope.

| Stack | Pass 1 count                           | Pass 2 final                                       | Delta      |
| ----- | -------------------------------------- | -------------------------------------------------- | ---------- |
| P0    | 1 (SKIP=mypy invariant)                | 1 (same, reinforced by 3 real errors)              | reinforced |
| P1    | 2 (evidence_tests + axis_weights)      | 5 (+ C14 façade, prettier dirty, force-with-lease) | +3         |
| P2    | 3 (release.yml, anchors, asyncio_mode) | 4 (+ markdownlint node pin)                        | +1         |
| P3    | implicit                               | 1 (F0023 description)                              | +1         |

**Required Run-3 deliverables (must close all P0 + P1):**

1. **P0-1** mypy clean (path-a only; path-b no longer acceptable)
2. **P1-1** evidence_tests populated for 13 mandatory IDs
3. **P1-2** ADR 0016 (axis_weights deferral — path (b) preferred given schema gap)
4. **P1-3** trichotomy: either implement (a) OR track feature (b) + inline comment
5. **P1-4** ATELIER_OBSERVABILITY_MODE: either wire (a) OR document as Phase-2 stub (b) + tracked feature
6. **P1-5** prettier autofix + handoff correction
7. **P1-6** force-with-lease disclosure in handoff §4
8. **P2-1** release.yml comment (2 min)
9. **P2-3** asyncio_mode line removed (1 min)
10. **P2-4** node pin bump (5 min)
11. Updated handoff doc `audit/executor-handoff-run2.md`
12. Fresh `pytest -q` + `pre-commit run --all-files` (both exit 0)

P2-2 (anchor URLs) and P3 (F0023 description) are OPTIONAL.

**Total Run-3 estimate: 3-4 hours wall-clock** (P0-1 = 30 min; P1 items = ~2 hrs if (b) paths chosen on P1-2/P1-3/P1-4; P2 items = ~15 min; handoff = ~30 min).
