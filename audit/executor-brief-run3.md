# Executor Brief — Round 3 (Audit Remediation Pass)

**Issued by:** Claude Opus 4.7 MAX (governor)
**Date:** 2026-05-21
**Source:** [`audit/audit-plan-run2.md`](audit-plan-run2.md) §9 + [`audit/findings-run2.md`](findings-run2.md) §6
**Target SLA:** 3-4 hours wall-clock
**Budget:** Sonnet 4.6 implementer tier (50 tool calls / 30K output) for routine items; escalate to Opus only for P0-1 mypy fixes.

---

## 0. Context

Round 2 (Antigravity + Gemini 2.5 Pro) closed 14/14 C-items but Round 2 audit surfaced **1 P0 + 5 P1 + 3 P2 + 1 process integrity** items that block sign-off. This brief converts those into a mechanical checklist. Close them all → governor issues APPROVED on Round 3.

**Hard constraints (CLAUDE.md invariants — all still apply):**

- No `SKIP=hook` env vars. No `--no-verify`. No `git push --force[-with-lease]` without explicit human approval recorded in commit message.
- All Python commits must pass `mypy --strict` for files touched.
- `<lockfile_only_installs>` — any new dep goes through `requirements.in` regen.
- Conventional Commits 1.0.0 enforced.
- Single-file responsibilities; one logical change per commit.

---

## 1. Sequential checklist (execute in order)

### R3-01 — P0: Fix mypy --strict on github_mcp.py (3 errors)

**Status to achieve:** `.venv/bin/mypy --strict atelier-core/src/atelier/integrations/github_mcp.py` exit 0

**Errors to fix:**

```
atelier-core/src/atelier/integrations/github_mcp.py:156: error: Returning Any from function declared to return "str"  [no-any-return]
atelier-core/src/atelier/integrations/github_mcp.py:226: error: Returning Any from function declared to return "str"  [no-any-return]
atelier-core/src/atelier/integrations/github_mcp.py:257: error: Type of variable becomes "Any | None" due to an unfollowed import  [no-any-unimported]
```

**Action:**

1. Read `atelier-core/src/atelier/integrations/github_mcp.py` lines 150-260
2. Lines 156 & 226: the function declares `-> str` but returns httpx response data that mypy infers as `Any`. Fix by:
   - Explicit cast: `return cast(str, response.json()["field"])` (import `from typing import cast`)
   - OR access the typed attribute properly: `return str(response.json()["field"])`
   - Pick the one that matches existing style. Do NOT add `# type: ignore` as a shortcut.
3. Line 257: unfollowed import — likely a missing type stub. Run `mypy --strict` locally to see the exact import. Options:
   - Install the stub: `pip install types-<package>` (add to `requirements-dev.in`, regenerate lock, commit lock first)
   - If stub does not exist: add `# type: ignore[no-any-unimported]` with a comment explaining which import and why no stub exists
4. Verify: `.venv/bin/mypy --strict atelier-core/src/atelier/integrations/github_mcp.py` → exit 0
5. ALSO verify: `.venv/bin/mypy --strict atelier-core/src/atelier/recorders/trajectory_recorder.py atelier-core/src/atelier/observability/__init__.py` → exit 0 (Pass 2 only checked github_mcp; other new files may have errors too)
6. Commit: `fix(types): resolve mypy --strict errors in github_mcp + trajectory_recorder per audit R3-01`

**Acceptance:** mypy exit 0 on all 3 new files. No `# type: ignore` without explanatory comment.

---

### R3-02 — P1: Backfill `evidence_tests` for 13 mandatory feature IDs

**Status to achieve:** `jq '.[] | select(.passes==true and (.evidence_tests | length == 0))' features.json | jq -s 'length'` returns 0

**The 13 IDs:** F0001a, F0001b, F0003, F0005, F0006, F0011, FA-002, FA-005, FA-006, FA-009, FA-010, FA-015, FA-016

**Action:**

1. For each ID, grep the existing test suite to find the test(s) that exercise it:

   ```
   grep -rln "BriefSpec\|brief_spec" atelier-core/tests/   # for F0001a
   grep -rln "model_registry\|gemini" atelier-core/tests/  # for FA-016
   ```

2. Populate the `evidence_tests` array in `features.json` with the actual test file path(s)
3. If an ID has NO existing test coverage:
   - **Option A** (preferred): write a 5-line smoke test asserting basic import + one invariant
   - **Option B**: change `passes` to `false`, add to backlog with `priority: P1`, note "no test coverage — Round 4 backfill"
4. **Forbidden:** Do NOT cite a test that doesn't actually exercise the feature. The reviewer will spot-check.
5. After each ID, re-run `pytest -q` to confirm any new smoke tests pass.
6. Commit: `chore(features): backfill evidence_tests for 13 mandatory IDs per audit R3-02`

**Acceptance:** `jq` query above returns 0. Spot-check by governor: 3 random IDs' cited tests actually exercise them.

---

### R3-03 — P1: ADR 0016 — axis_weights YAML as planning artifact (deferral)

**Status to achieve:** `docs/decisions/0016-axis-weights-yaml-as-planning-artifact.md` exists with 5 h2 sections; `DECISIONS.md` row added; comment header added to YAML.

**Action:**

1. Write `docs/decisions/0016-axis-weights-yaml-as-planning-artifact.md`:

   ```markdown
   # ADR 0016: axis_weights_heuristic.yaml as Phase-1 Planning Artifact

   **Status:** Accepted
   **Date:** 2026-05-21
   **Audit:** Run 2 P1-2 deferral

   ## Context

   axis_weights_heuristic.yaml uses a surface_types taxonomy (landing_page, pricing, checkout, ...).
   consensus/axis_weights.py uses the legacy visual_register taxonomy (corporate, luxury, ...).
   These are conceptually different categorizations, not just different keys.

   ## Decision

   For Phase 1, retain BOTH:

   - YAML stays as documented planning artifact for Phase-2 ConsensusAgent (N3d)
   - axis_weights.py keeps hardcoded \_WEIGHT_PRESETS keyed on visual_register for Phase-1 runtime
   - Reconciliation deferred to F0XXX (TBD feature) at N3d integration time

   ## Consequences

   - Pro: no schema risk for Phase-1 demo; existing tests pass
   - Pro: Phase-2 has a designed-for-purpose taxonomy ready
   - Con: dual schemas to maintain until reconciliation
   - Con: confusion risk for new contributors — mitigated by this ADR + YAML header comment

   ## Alternatives Considered

   - **Refactor now**: rejected — surface_types vs visual_register requires a design call (which taxonomy wins?), not a 60-min refactor. Out of scope for D7.
   - **Delete the YAML**: rejected — it IS the right Phase-2 taxonomy; deleting forces redesign in Phase 2.
   - **Convert visual_register → surface_types now**: rejected — breaks 30+ existing tests + plan-review-1 doesn't authorize it.

   ## Status

   Accepted 2026-05-21 per audit Run 2 P1-2.
   Tracked for unification: F0XXX (open at N3d integration).
   ```

2. Add comment header to top of `consensus/axis_weights_heuristic.yaml`:

   ```yaml
   # Planning artifact — Phase-1 runtime consumer is consensus/axis_weights.py (hardcoded dict).
   # Reconciliation of surface_types ↔ visual_register taxonomies deferred per ADR 0016.
   # DO NOT consume this file at runtime until ADR 0016 status changes to "Superseded".
   ```

3. Append row to `DECISIONS.md`:

   ```
   | 0016 | axis_weights YAML as Phase-1 planning artifact (deferral) | Accepted | 2026-05-21 |
   ```

4. Open `F0XXX` in `features.json` with `priority: P1`, `phase: 2`, `notes: "Unify axis_weights schemas per ADR 0016 at N3d ConsensusAgent integration"`. Use the next available `F0XXX` number.
5. Commit: `docs(adr): add ADR 0016 axis_weights YAML deferral per audit R3-03`

**Acceptance:** ADR file exists with 5 h2 sections (Context, Decision, Consequences, Alternatives Considered, Status). DECISIONS.md updated. YAML header comment present. Tracked feature in features.json.

---

### R3-04 — P1: TrajectoryRecorder trichotomy completion — track as Phase-2 feature

**Status to achieve:** Tracked feature in `features.json`; inline comment in `trajectory_recorder.py`.

**Action (path-b: track for Phase 2):**

1. Add `F0XXY` to `features.json` (next available number):

   ```json
   {
     "id": "F0XXY",
     "title": "TrajectoryRecorder full failure-trichotomy (self-heal + fail-soft partial-batch)",
     "priority": "P1",
     "phase": 2,
     "passes": false,
     "evidence_commits": [],
     "evidence_tests": [],
     "notes": "Phase-1 ships fail-loud-only. Add tenacity retry decorator (3 attempts, exp backoff on 503/429) for self-heal. Separate partial-batch errors from full-batch failures for fail-soft. Per audit Run 2 P1-3."
   }
   ```

2. Add inline comment in `atelier-core/src/atelier/recorders/trajectory_recorder.py` immediately before the `flush()` method (currently line ~182):

   ```python
   # Phase-1 scope: fail-loud only on BQ errors.
   # Self-heal (retry on 503/429) + fail-soft (partial-batch separation)
   # deferred to F0XXY per audit Run 2 P1-3. Full trichotomy required for Phase-2 production.
   ```

3. (Optional, ~10 min more) Update docstring of `flush()` to remove "Per the failure-trichotomy (CLAUDE.md): fail-loud" — replace with "Phase-1: fail-loud only. See F0XXY for trichotomy completion."
4. Commit: `chore(trajectory): track F0XXY for trichotomy completion per audit R3-04`

**Acceptance:** features.json has new entry; trajectory_recorder.py has inline comment citing F0XXY.

---

### R3-05 — P1: ATELIER_OBSERVABILITY_MODE — document as Phase-2 stub OR wire branching

**Status to achieve:** Either real branching exists, OR documented-as-stub with tracked feature.

**Action (path-b: document as Phase-2 stub):**

1. Edit `atelier-core/src/atelier/observability/__init__.py` — add module-level docstring after existing header:

   ```python
   # Phase-1 status: ATELIER_OBSERVABILITY_MODE is READ but NOT BRANCHED ON.
   # config/otel-collector-config.yaml statically routes to BOTH Phoenix and Google Cloud
   # regardless of mode value. Real conditional routing tracked as F0XXZ per audit Run 2 P1-4.
   ```

2. Add `F0XXZ` to `features.json` (next available number):

   ```json
   {
     "id": "F0XXZ",
     "title": "OTel collector pipeline conditional Phoenix/GCloud routing by ATELIER_OBSERVABILITY_MODE",
     "priority": "P1",
     "phase": 2,
     "passes": false,
     "evidence_commits": [],
     "evidence_tests": [],
     "notes": "Phase-1 collector always emits to both Phoenix and GCloud. Phase-2: when mode=prod, suppress otlp/phoenix exporter; when mode=dev, suppress googlecloud exporter. Per audit Run 2 P1-4."
   }
   ```

3. Update `docs/guides/phoenix-tracing.md` — add section after the env var examples:

   ```markdown
   ## Phase-1 limitation

   In Phase 1, the OTel collector pipeline (config/otel-collector-config.yaml) statically
   includes BOTH Phoenix and Google Cloud exporters. The ATELIER_OBSERVABILITY_MODE env var
   is read by atelier.observability but does not yet control exporter selection — tracked
   as F0XXZ for Phase 2 wiring.

   For Phase-1 testing: setting MODE=prod will not actually suppress Phoenix traces; the
   judge prompt context will still flow to both backends.
   ```

4. Commit: `docs(observability): document Phase-1 façade + track F0XXZ per audit R3-05`

**Acceptance:** observability module docstring updated; features.json has F0XXZ; phoenix-tracing.md docs updated.

**OR path-a:** Wire real branching at OTel bootstrap (~45 min). Skip path-b if you choose this. Add integration test asserting `MODE=prod` does not enable Phoenix exporter.

---

### R3-06 — P1: prettier autofix + handoff correction

**Status to achieve:** `pre-commit run prettier --all-files` exits 0 (no reformat); handoff doc accurate.

**Action:**

1. Run: `.venv/bin/pre-commit run prettier --all-files` (it auto-fixes; 9 files will be reformatted)
2. Stage and commit:

   ```
   git add -u
   git commit -m "style: prettier autofix per audit R3-06"
   ```

3. Update `audit/executor-handoff.md` (or write `audit/executor-handoff-run3.md`) — change the false "all pre-commit hooks pass" claim. Replace with:

   ```
   ## Pre-commit status (as of Run 3)
   - pytest: 249 passed (exit 0)
   - ruff + ruff-format: pass
   - mypy --strict: pass (after R3-01)
   - prettier: pass (after R3-06 autofix)
   - markdownlint: pass (after R3-09 node pin bump)
   - all other hooks: pass
   ```

4. Commit: `docs(audit): correct pre-commit status claim per R3-06`

**Acceptance:** Fresh `pre-commit run prettier --all-files` returns "Passed" or "No files to check".

---

### R3-07 — P1: Disclose force-with-lease usage in handoff

**Status to achieve:** Handoff doc has §4 entry acknowledging the force-with-lease incident.

**Action:**

1. Forensic check first: `git reflog phase/1 | head -50` — look for any "force-update" entries around the C5+C6 timeframe. Capture the commit SHA(s) involved.
2. Edit `audit/executor-handoff.md` §4 (Drift from the Brief), add row:

   ```
   | Used `git push --force-with-lease origin phase/1` once at [timestamp] | Amended commit [SHA] after [reason — e.g., test fixup]. Reflog confirmed no overwritten work from other collaborators. Disclosed per audit Run 2 P1-6. CLAUDE.md `<no_destructive_git>` deviation acknowledged. |
   ```

3. If the reflog shows force-pushes overwrote commits that other collaborators had pulled — **STOP**, surface to governor for re-assessment. (Unlikely on a solo phase branch but check.)
4. Commit: `docs(audit): disclose force-with-lease incident per audit R3-07`

**Acceptance:** Handoff §4 has the disclosure row; reflog forensics done.

---

### R3-08 — P2: release.yml main-only rationale comment

**Status to achieve:** `.github/workflows/release.yml` has a comment block explaining the main-only trigger.

**Action:**

1. Edit `.github/workflows/release.yml` — insert before line 5 (`on:`):

   ```yaml
   # Releases are cut from main only (release-please pattern).
   # Phase branches do not trigger releases — they merge to main first, then release fires.
   # Per audit R3-08: this is intentional, not an oversight from C9 phase/* trigger sweep.
   ```

2. Commit: `chore(ci): document release.yml main-only trigger per audit R3-08`

**Acceptance:** Comment block present at top of release.yml.

---

### R3-09 — P2: Remove stale asyncio_mode line + bump node pin

**Status to achieve:** No PytestConfigWarning; markdownlint installable.

**Action (two micro-edits in one commit):**

1. Edit `atelier-core/pyproject.toml` `[tool.pytest.ini_options]` section — remove the line `asyncio_mode = "auto"` (it's dead config; pytest-asyncio not installed).
2. Edit `.pre-commit-config.yaml` `default_language_version` block:

   ```yaml
   default_language_version:
     python: python3.11
     node: '22.13.0' # was '20.11.1' — bumped per audit R3-09 (markdownlint-cli@v0.48.0 transitive dep eslint-visitor-keys@5.0.1 requires node ^20.19.0 || ^22.13.0 || >=24)
   ```

3. Verify locally:

   ```
   .venv/bin/pre-commit clean
   .venv/bin/pre-commit install --install-hooks
   .venv/bin/pre-commit run markdownlint --all-files
   .venv/bin/pytest -q  # should not show asyncio_mode warning anymore
   ```

4. If markdownlint surfaces real content failures after install, fix the markdown content (do not just suppress).
5. Commit: `chore(tooling): bump node pin + remove dead asyncio_mode config per audit R3-09`

**Acceptance:** `pre-commit run markdownlint --all-files` exits 0 (or "no files to check"). `pytest -q` runs with no asyncio_mode warning.

---

### R3-10 — Updated handoff doc

**Status to achieve:** `audit/executor-handoff-run3.md` exists with all R3-NN closures cited.

**Action:**

1. Write `audit/executor-handoff-run3.md` mirroring `executor-handoff.md` structure:
   - Executive Summary (what closed, what's tracked-for-Phase-2)
   - Per-Item Table (R3-01 through R3-09 with status + commit SHAs)
   - Gaps and Known Issues (the F0XXY / F0XXZ tracked features + any remaining caveats)
   - Drift from this brief (any path-a vs path-b choices made; force-with-lease disclosure)
   - Test count delta (249 → final)
   - Mypy delta (was-failing → now-clean)
   - Pre-commit delta (was-dirty → now-clean)
   - Cost spent (estimate)
   - What I would NOT bet my job on (honest caveats)
   - Trailer: `READY-FOR-AUDIT-RUN-3: <ISO timestamp>`
2. Commit: `docs(audit): hand off Round 3 per audit-plan-run2 §9`

**Acceptance:** File exists; per-item table covers R3-01 through R3-09; ends with READY-FOR-AUDIT-RUN-3 trailer.

---

### R3-11 — Final verification (DO NOT SKIP)

**Status to achieve:** All gates clean before signaling READY.

**Action (run in this exact order):**

1. `.venv/bin/pre-commit run --all-files` → must exit 0
2. `.venv/bin/pytest -q` → must show ≥249 passed, exit 0
3. `.venv/bin/mypy --strict atelier-core/src/atelier/integrations/github_mcp.py atelier-core/src/atelier/recorders/trajectory_recorder.py atelier-core/src/atelier/observability/__init__.py` → exit 0
4. `jq '.[] | select(.passes==true and (.evidence_tests | length == 0))' features.json | jq -s 'length'` → must return 0
5. `git log --oneline phase/1 | head -20` — sanity check no unexpected commits
6. `git status` → clean working tree

**Acceptance:** All 6 checks exit 0 / return expected values. Capture the outputs in the executor-handoff-run3.md "Verification" section.

---

## 2. Forbidden actions (from CLAUDE.md, re-emphasized)

- `SKIP=<hook>` — NEVER. If a hook is broken, fix the hook or fix the code. Use `--no-verify` is also banned.
- `git push --force` or `--force-with-lease` — only with explicit human approval recorded in commit message.
- `git reset --hard`, `git checkout -- .`, `git clean -fd`, `rm -rf` on tracked paths — banned without human approval.
- `pip install LIB` ad-hoc — banned. Add to `requirements-dev.in` first.
- Modifying `agent-dag-pipeline/`, `google-adk/`, `hermes-agent/` upstream code — banned per ADR 0001.
- Bare `except:` or silent `try` blocks — banned. Every caught exception logged + re-raised or returned as structured error.
- Marking `passes: true` without populated `evidence_tests` — banned per R3-02.

## 3. Drift policy

If you encounter a situation not covered here:

- **Trivial detour** (e.g., a 2-line typo fix while editing nearby code): just do it, mention in commit message.
- **Substantive deviation** (e.g., path-a vs path-b choice not flagged here): pause, document in `executor-handoff-run3.md §4 (Drift)`, proceed with reasonable judgment.
- **Blocker** (e.g., mypy reveals a deeper bug that takes >1 hr to fix properly): STOP, surface to governor before continuing. Do NOT paper over.

## 4. Done condition

When all 11 R3-NN items show ✅ in `executor-handoff-run3.md` and the trailer `READY-FOR-AUDIT-RUN-3: <ISO timestamp>` is appended:

- Governor runs Round 3 audit (codebase-only verification, no Pass 2 unless surprises found)
- Expected outcome: **APPROVED**, merge phase/1 → main, ship D8 morning.

Estimated total wall-clock: 3-4 hours.
