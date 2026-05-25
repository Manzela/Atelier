# Executor Brief — Round 6

**Executor:** Antigravity IDE (Claude Opus 4.6 Thinking)
**Date issued:** 2026-05-21T17:30Z
**Author:** Claude Code (Opus 4.7 MAX) — Atelier sprint orchestrator
**Source spec:** `docs/superpowers/specs/2026-05-21-post-r4-strategic-roadmap-design.md` (SHA `0e1c3b1` on `phase/1`)
**R5 prior:** `audit/executor-handoff-run5.md` (APPROVED — see §1 below)
**Worktree:** `.worktrees/phase1-foundation/` on branch `phase/1` ONLY. DO NOT touch `.worktrees/phase2-consensus-agent/` — that worktree is reserved for the parallel SOTA Protocol implementation (§18–§21 per spec §22.3) being authored by the orchestrator.
**Wall-clock budget:** ~30 min
**Commit policy:** Per-item commits, Conventional Commits 1.0.0, NO `--no-verify` ever.
**Tone:** Strictly mechanical. No architectural judgment calls — if a step requires design intuition, FAIL-LOUD and surface to orchestrator instead of guessing.

---

## §1. R5 verdict (informational — already executed by you)

**APPROVED with one trivial flag.** Independent verification:

| Claim                                     | Method                                            | Result                                                                                                   |
| ----------------------------------------- | ------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| R5-01 `phase/2` branch from `phase/1` tip | `git rev-parse phase/2` + `git merge-base`        | ✅ Both = `0e1c3b1`                                                                                      |
| R5-01 worktree exists                     | `git worktree list`                               | ✅ `.worktrees/phase2-consensus-agent/`                                                                  |
| R5-02 `bbd1d17` protection script         | `git show --stat bbd1d17` + `ls`                  | ✅ 25-line script committed                                                                              |
| R5-03a/b features.json normalized         | `jq` Gate 1 + Gate 2                              | ✅ Both return 0                                                                                         |
| R5-03c/d pre-commit + CI gates            | `grep` `.pre-commit-config.yaml` + `cat` workflow | ✅ Both wired                                                                                            |
| R5-04 six migration scripts               | `wc -l scripts/migration/*`                       | ✅ 5 of 6 exact LoC; `05_verify_no_orphans.py` is **150 lines**, handoff said 146 (4-line drift, accept) |
| R5-05 handoff doc committed               | `git log`                                         | ✅ `f07d319`                                                                                             |
| Totals 219/27/192                         | `jq`                                              | ✅ Exact match                                                                                           |

**One unverifiable claim:** §8 test count discrepancy (300 spec vs 296 + 1 collection error). The worktree has no `.venv/` and no pytest on the system path used by orchestrator. **Falls into R6-04 scope below.**

---

## §2. Strategic context for R6

The spec's §13.1 (Phase 1 Gate — 11 hard gates) cannot be validated until:

1. GCP migration has READ the current state of `i-for-ai` (mechanical, safe).
2. `atelier-build-2026` project state is VERIFIED (existence + billing + IAM).
3. A single gate-runner script wires all 11 gates into one machine-verified exit code.
4. `tests/eval/` exists with the 50-task WebGen-Bench subset, since one Phase 1 Gate criterion is "pytest tests/eval/ no regression."
5. The test count discrepancy is investigated and resolved.

The orchestrator is authoring §18–§21 SOTA Protocol modules in parallel on `phase/2`. R6 stays entirely on `phase/1` and contains zero work that touches `optimize/`, `memory/`, `router/`, or `reward/` source trees.

**Out of scope for R6:**

- ❌ Implementing §18-§21 Protocol modules (orchestrator owns)
- ❌ Writing ADRs 0027-0030 (orchestrator owns — these encode architectural decisions)
- ❌ Bootstrapping a new GCP project from scratch (Daniel-gated)
- ❌ Running terraform `apply` (Daniel-gated)
- ❌ Pushing `phase/1` to remote (Daniel-gated until orchestrator clears for push)
- ❌ Any work in `.worktrees/phase2-consensus-agent/`
- ❌ Any `--no-verify`, `git push --force`, `git reset --hard`, `git checkout -- .`, `git clean -fd`

---

## §3. R6 items

### R6-01: Execute migration READ phase against `i-for-ai`

**Intent:** Capture the live resource inventory of `i-for-ai` so the migration cutover plan has ground truth.

**Files:**

- Execute: `scripts/migration/01_inventory.sh` (already committed, defaults to `DRY_RUN=0` only when invoked with `--wet` flag — verify; if it defaults to wet, set `DRY_RUN=0` explicitly here since read operations are safe)
- Create: `audit/migration/inventory-i-for-ai-2026-05-21.json` (gcloud asset output)
- Create: `audit/migration/inventory-i-for-ai-2026-05-21.log` (stderr + run metadata)

**Steps:**

1. `gcloud auth list` → must show authenticated principal with access to `i-for-ai`. If unauthenticated, STOP and surface `audit/migration/R6-01-AUTH-MISSING.md` documenting the gap.
2. Run `scripts/migration/01_inventory.sh i-for-ai` redirecting stdout to the JSON file, stderr to the log file.
3. Verify the JSON is well-formed: `jq '.' audit/migration/inventory-i-for-ai-2026-05-21.json > /dev/null`.
4. Compute summary stats with `jq` and append to the log file: total assets, asset types breakdown, regions touched.
5. Commit: `chore(migration): capture i-for-ai inventory snapshot (R6-01)`

**Acceptance:**

- JSON file exists and is well-formed
- `gcloud asset` did NOT error
- Inventory includes at minimum the asset types from `01_inventory.sh`'s gcloud filter (likely `cloudfunctions`, `run`, `aiplatform`, `bigquery`, `storage`, `iam`)

**Approval status:** Self-execute. No Daniel gate.

---

### R6-02: Classify the inventory by migration disposition

**Intent:** Tag every resource as MIGRATE / RETIRE / IGNORE so the wet cutover has zero ambiguity.

**Files:**

- Execute: `scripts/migration/02_classify.py`
- Create: `audit/migration/classification-2026-05-21.json` (output)
- Create: `audit/migration/classification-summary-2026-05-21.md` (human-readable rollup)

**Steps:**

1. `python scripts/migration/02_classify.py --input audit/migration/inventory-i-for-ai-2026-05-21.json --output audit/migration/classification-2026-05-21.json`
2. Validate output schema: each entry must have `{resource_name, resource_type, disposition: "MIGRATE"|"RETIRE"|"IGNORE", rationale}`.
3. Write summary markdown: counts per disposition, list of any UNKNOWN dispositions (script bugs to flag).
4. Commit: `chore(migration): classify i-for-ai resources by disposition (R6-02)`

**Acceptance:**

- All resources from R6-01 inventory appear in the classification (one-to-one)
- Zero UNKNOWN dispositions (or, if any exist, they are listed in the summary md and flagged in `§8 What I would NOT bet my job on` of the R6 handoff)
- Summary md is committed alongside JSON

**Approval status:** Self-execute. No Daniel gate.

---

### R6-03: Verify `atelier-build-2026` project state

**Intent:** Before any migration write happens, confirm the destination project exists, is correctly billed, has the required APIs enabled, and IAM is sane. DO NOT create the project — that's Daniel's call.

**Files:**

- Create: `audit/migration/atelier-build-2026-readiness-2026-05-21.md`
- Create (only if gaps found): `audit/migration/atelier-build-2026-daniel-action-checklist.md`

**Steps:**

1. `gcloud projects describe atelier-build-2026 --format=json` — capture output. If 404, STOP and write the action checklist with: "Daniel must run `gcloud projects create atelier-build-2026 --organization=<ORG_ID>`."
2. `gcloud billing projects describe atelier-build-2026 --format=json` — must show `billingEnabled: true`. If false, add to action checklist.
3. `gcloud services list --enabled --project=atelier-build-2026 --format='value(config.name)'` — verify presence of: `aiplatform.googleapis.com`, `run.googleapis.com`, `bigquery.googleapis.com`, `cloudtrace.googleapis.com`, `secretmanager.googleapis.com`, `firestore.googleapis.com`. For any missing, add to action checklist.
4. `gcloud projects get-iam-policy atelier-build-2026 --format=json` — verify Daniel's principal has `roles/owner` or equivalent. Note any anomalies (overly permissive principals, service accounts from `i-for-ai` carried over).
5. Write `atelier-build-2026-readiness-2026-05-21.md` with a green/red checklist of all 4 above categories.
6. Commit: `chore(migration): verify atelier-build-2026 readiness (R6-03)`

**Acceptance:**

- Readiness markdown exists and lists every gap (or "no gaps") explicitly
- If gaps exist, action checklist file also exists and is human-actionable
- ZERO write operations against `atelier-build-2026`

**Approval status:** Self-execute (read-only). No Daniel gate.

---

### R6-04: Investigate test count discrepancy

**Intent:** R5 §8 flagged "300 spec vs 296 collected + 1 collection error in `test_api.py`." Resolve.

**Files:**

- Modify: whatever causes the collection error (likely `atelier-core/tests/unit/test_api.py` or an import in it)
- Modify (if applicable): missing test files that account for the 4-test gap, or update spec §22.3 footnote noting 296 is the new baseline

**Steps:**

1. From `.worktrees/phase1-foundation/atelier-core/`, ensure a venv exists. If not: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`. Commit `.venv` is gitignored (verify).
2. Run `.venv/bin/pytest --collect-only --quiet 2>&1 | tee /tmp/r6-04-collect.log`.
3. Grep for `ERROR` and `error during collection` to find the collection error. Read the offending file, identify root cause (likely missing import, syntax error, or test fixture issue).
4. Fix the collection error. The fix must be MINIMAL — do NOT refactor surrounding code.
5. Re-run collection: must succeed with no errors.
6. Compare collected count to 300. If still short, search git history for any test files that may have been moved/deleted: `git log --diff-filter=D --name-only --since="2026-05-15" -- atelier-core/tests/unit/`. Document the delta in commit message.
7. If reconciliation finds 300 is wrong baseline (e.g., 4 tests legitimately removed in a prior cleanup), edit spec §22.3 only the test-count number — preserve all surrounding prose verbatim.
8. Commit: `fix(tests): resolve collection error in <file> + reconcile test count baseline (R6-04)`

**Acceptance:**

- `pytest --collect-only` exits 0 with zero errors
- Test count is documented (either matches 300 or spec updated with rationale)
- No test was deleted or weakened to make the number line up

**Approval status:** Self-execute. No Daniel gate.

**FAIL-LOUD condition:** If the collection error reveals a genuine bug in production code (not test code), STOP and surface — do not auto-fix production code under this brief.

---

### R6-05: Phase 1 Gate runner script

**Intent:** Wire all 11 §13.1 hard gates into one executable that exits 0 (pass) or non-zero (fail with structured output).

**Files:**

- Create: `scripts/gates/phase_1_gate.sh` (bash, +x, ~120 LoC)
- Create: `scripts/gates/README.md` (1-page usage + exit-code contract)

**Steps:**

1. Re-read spec §13.1 (lines 3245-3260) for the 11 gates verbatim.
2. Implement each gate as a bash function `gate_NN_<short_name>` returning 0/1. Aggregate via:

   ```bash
   set +e
   fail_count=0
   gate_01_migration_no_orphans || ((fail_count++))
   # ... all 11
   set -e
   [ $fail_count -eq 0 ]
   ```

3. For gates that are blocked on Daniel actions (terraform apply, push, project create), the gate function must return 1 with a `BLOCKED: <reason>` log line — do NOT silently skip.
4. Each gate emits one line to stdout: `[PASS] gate_NN: <description>` or `[FAIL] gate_NN: <description> — <reason>`.
5. Tail summary: `Phase 1 Gate: X/11 passing — <BLOCKING|READY-TO-TAG>`.
6. Write `README.md` documenting: invocation (`./scripts/gates/phase_1_gate.sh`), exit codes (0 = all pass, 1 = at least one fail, 2 = script error), one-paragraph rationale.
7. Run the script — capture output to `audit/gates/phase_1_gate-2026-05-21.log`. Most gates will currently FAIL because the underlying infrastructure isn't live yet — that's expected. The script's CORRECTNESS (not the gate results) is what's being committed.
8. Commit: `feat(gates): add Phase 1 Gate runner wiring all 11 §13.1 checks (R6-05)`

**Acceptance:**

- Script exists and is executable
- Running the script produces structured output for all 11 gates
- Exit code matches gate aggregate
- `audit/gates/phase_1_gate-2026-05-21.log` captures the current baseline

**Approval status:** Self-execute. No Daniel gate.

---

### R6-06: WebGen-Bench 50-task subset harness scaffolding

**Intent:** Phase 1 Gate requires "50/484 WebGen-Bench subset passing in CI." Scaffold the harness so the test directory exists, the 50 deterministic task IDs are locked, and the runner is wired even if it fails today.

**Files:**

- Create: `atelier-core/tests/eval/__init__.py` (empty)
- Create: `atelier-core/tests/eval/test_webgen_50.py` (parametrized over 50 task IDs)
- Create: `atelier-core/tests/eval/webgen_50_task_ids.json` (the deterministic subset)
- Create: `atelier-core/tests/eval/README.md`

**Steps:**

1. Pull the upstream WebGen-Bench task list. If `agent-dag-pipeline` sibling repo has it cached, read from there: `~/Professional Profile/agent-dag-pipeline/data/webgen_bench_tasks.json` or similar. Otherwise FAIL-LOUD with `audit/r6-06-webgen-source-missing.md` noting the source must be located before this gate can be wired.
2. Deterministic 50-task subset selection: SHA-256 sort by task_id, take first 50. Commit the selected IDs to `webgen_50_task_ids.json`.
3. Write `test_webgen_50.py`:

   ```python
   import json, pytest
   from pathlib import Path

   _IDS = json.loads(Path(__file__).parent.joinpath("webgen_50_task_ids.json").read_text())

   @pytest.mark.parametrize("task_id", _IDS)
   def test_webgen_task(task_id: str) -> None:
       """Phase 1 Gate: pipeline must produce non-error output for this task.
       Currently a placeholder that XFAILs — full wiring lands in §22.3 D17."""
       pytest.xfail(f"WebGen-Bench harness not yet wired to live pipeline (task {task_id})")
   ```

4. README documents: source of the 50, regeneration command, current XFAIL status + when it lifts.
5. Verify pytest collects all 50 cleanly: `pytest atelier-core/tests/eval/test_webgen_50.py --collect-only` → 50 cases.
6. Commit: `feat(eval): scaffold WebGen-Bench 50-task subset harness (R6-06)`

**Acceptance:**

- `tests/eval/` directory exists with 4 files
- 50 task IDs locked deterministically
- Pytest collects exactly 50 cases, all XFAILing (not erroring)
- README explicit about the placeholder status

**Approval status:** Self-execute. No Daniel gate.

**FAIL-LOUD condition:** If the WebGen-Bench source can't be located in any sibling repo or upstream pin, do NOT fabricate task IDs. Surface in `audit/r6-06-webgen-source-missing.md` and move on to R6-07.

---

### R6-07: Handoff document

**Intent:** Per-item table + caveats + push state + READY-FOR-AUDIT trailer.

**Files:**

- Create: `audit/executor-handoff-run6.md`

**Required sections (mirror R3/R4/R5 format):**

1. **§1 Per-item commit table** — SHA, subject, files-changed-count for each of R6-01 through R6-07
2. **§2-§7** — one section per item with what shipped + acceptance verification command output
3. **§8 What I would NOT bet my job on** — every assumption, every unverified claim
4. **§9 Push state** — what's local-only vs remote (expect: all R6 commits local; phase/1 still NOT pushed because Daniel hasn't approved push timing)
5. **§10 Daniel-gated follow-ups for R7** — checklist of items that need Daniel before R7 can start (e.g., "Daniel must run `gcloud projects create atelier-build-2026` if R6-03 found it missing")
6. **`READY-FOR-AUDIT-RUN-6`** trailer with ISO-8601 timestamp

**Approval status:** Self-execute.

---

## §4. Approval gates summary

| Item                                                      | Self-execute | Daniel-approval-required before this happens      |
| --------------------------------------------------------- | ------------ | ------------------------------------------------- |
| R6-01 inventory                                           | ✅ Yes       | — (read-only)                                     |
| R6-02 classify                                            | ✅ Yes       | — (read-only)                                     |
| R6-03 verify destination                                  | ✅ Yes       | — (read-only)                                     |
| R6-04 test discrepancy                                    | ✅ Yes       | —                                                 |
| R6-05 gate runner                                         | ✅ Yes       | —                                                 |
| R6-06 WebGen harness                                      | ✅ Yes       | —                                                 |
| R6-07 handoff                                             | ✅ Yes       | —                                                 |
| **R7-future:** push phase/1 + execute branch protection   | ❌ No        | Daniel push approval                              |
| **R7-future:** terraform apply against atelier-build-2026 | ❌ No        | Daniel apply approval after R6-03 readiness clean |
| **R7-future:** execute migration scripts 03-06 wet        | ❌ No        | Daniel migration approval                         |

---

## §5. Failure-handling trichotomy reminder

Per CLAUDE.md:

- **Fail-loud** (alert + halt): unauthenticated gcloud, missing destination project, production code bug discovered during R6-04, WebGen source not locatable
- **Fail-soft** (degrade + log + acknowledge): individual gate failures in R6-05 (expected), missing optional APIs in R6-03 (flag in checklist)
- **Self-heal** (retry up to 3): transient gcloud 429/503, transient pip install timeouts

---

## §6. Spec invariants you MUST honor

From CLAUDE.md `<no_unverified_apis>`, `<compile_then_commit>`, `<no_speculation>`, `<no_test_driven_slop>`, `<no_silent_error_suppression>`, `<json_state_files>`, `<no_destructive_git>`, `<lockfile_only_installs>`, `<wrap_dont_fork>`, `<conventional_commits_required>`, `<wrap_phase_work_in_worktrees>`.

Specific to R6:

- All new Python files must pass `mypy --strict` BEFORE commit.
- All new bash scripts must pass `shellcheck` + `shfmt` (already wired in pre-commit).
- No new pip dependencies — if you need one, FAIL-LOUD and surface, do NOT add ad-hoc.
- features.json schema gates added in R5-03c/d are mandatory pre-commit — if any R6 edit touches features.json (unlikely), gates must still pass.

---

## §7. Out-of-scope reaffirmation

You will NOT:

- Touch any file under `atelier-core/src/atelier/optimize/`, `memory/`, `router/`, `reward/` (orchestrator's SOTA scope on `phase/2`)
- Write any of ADRs 0027, 0028, 0029, 0030 (orchestrator's scope — these encode architectural decisions for §18-§21)
- Create or modify any file in `.worktrees/phase2-consensus-agent/`
- Push any branch to origin
- Run `terraform apply` against any project
- Execute migration scripts 03 (`terraform_apply.sh`) or 04 (`decommission.sh`) or 06 (`weekly_cost_tail.sh`) in WET mode

---

**Brief locked. Spawn when ready.**
**Author:** Claude Code (Opus 4.7 MAX, Atelier orchestrator)
**Issued:** 2026-05-21T17:30Z
