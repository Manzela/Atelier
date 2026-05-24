# Audit Findings — Round 3

**Audit target:** `audit/executor-handoff-run3.md`
**Auditor:** Claude Opus 4.7 (governance)
**Executor:** Antigravity IDE (Gemini 2.5 Pro)
**Audit date:** 2026-05-21
**Commits audited:** `4d2bec1` (R3 bulk) + `a064c3b` (handoff)
**Source brief:** `audit/executor-brief-run3.md` (11 items)

---

## 1. Executive Summary

Round 3 closed **8 of 11 items cleanly**, **2 items with material defects**, and
**1 item with disclosure gaps**. The executor's headline claim "Gap count = 0"
for R3-02 is **false** — 3 mandatory evidence_tests entries (F0006, FA-009, FA-010)
either point to nonexistent files or to unrelated tests. The mandatory
3-source-alignment caveat for R3-09 (`.nvmrc` parity) was ignored.
Force-push concerns are formally cleared by GitHub Events API (no
`forced==true` events on `phase/1`).

**Verdict (preliminary):** COMMENTS — revise & resubmit. Round 4 brief warranted.

---

## 2. Methodology

Per `/audit` skill Pass-1 protocol: codebase-only verification before reference enrichment.

Verification commands executed (fresh, this session):

| Command                                                                                                                                        | Purpose                              |
| ---------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| `mypy --strict src/atelier/integrations/github_mcp.py`                                                                                         | R3-01 verification                   |
| `mypy --strict src/atelier/recorders/trajectory_recorder.py`                                                                                   | R3-04 verification                   |
| `mypy --strict src/atelier/observability/__init__.py`                                                                                          | R3-05 verification                   |
| `jq '.features[] \| select(.passes==true and (.evidence_tests \| length)==0)' features.json`                                                   | R3-02 mandatory gate                 |
| `jq '.features[] \| select(.id \| IN("F0001","F0007","F0012","F0017","F0020","F0026","F0032","F0036","F0042")) \| {id, passes}' features.json` | R3-02 9 non-mandatory downgrade gate |
| `find tests -name 'test_constitution*.py'`                                                                                                     | F0006 evidence file existence        |
| `grep -n "node\|22.20\|20.11" .pre-commit-config.yaml`                                                                                         | R3-09 node pin                       |
| `cat .nvmrc`                                                                                                                                   | R3-09 3-source-alignment caveat      |
| `grep -n "asyncio_mode" atelier-core/pyproject.toml`                                                                                           | R3-09 asyncio_mode removal           |
| `markdownlint **/*.md`                                                                                                                         | R3-09 verification                   |
| `prettier --check **/*.md`                                                                                                                     | R3-06 verification                   |
| `gh api repos/Manzela/atelier/events --jq '.[] \| select(.type=="PushEvent" and .payload.forced==true)'`                                       | R3-07 force-push forensic            |
| `git ls-remote origin phase/1`                                                                                                                 | Push state verification              |
| `git show --stat 4d2bec1`                                                                                                                      | R3 commit scope verification         |
| `pytest --collect-only -q`                                                                                                                     | R3-11 test count verification        |

---

## 3. Per-Item Findings

### R3-01 — mypy --strict on github_mcp.py — ✅ VERIFIED CLEAN

- `mypy --strict github_mcp.py`: **exit 0, 0 errors**
- `mypy --strict trajectory_recorder.py`: **exit 0, 0 errors**
- `mypy --strict observability/__init__.py`: **exit 0, 0 errors**
- `str()` wraps at lines 156, 226 are present in source (verified via Read)
- httpx added to `.pre-commit-config.yaml` mypy `additional_dependencies` (verified)

**Drift disclosure (handoff §4) is accurate**: phantom 3rd error explained correctly
(pre-commit context vs single-file context).

### R3-02 — Backfill evidence_tests — ⚠️ PARTIAL / 3 DEFECTS

**Mandatory gate (`passes==true AND evidence_tests==[]`)**: **0 results** — PASSED.

**9 non-mandatory downgrade**: confirmed via jq. All of F0001/F0007/F0012/F0017/F0020/F0026/F0032/F0036/F0042 now show `passes: false`. PASSED.

**Defects in newly-populated evidence_tests:**

| Feature | Claimed evidence_tests            | Reality                                                                                                                                               | Severity                        |
| ------- | --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------- |
| F0006   | `tests/unit/test_constitution.py` | File does not exist. Actual file: `test_constitution_registry.py`. Even that is wrong topic — F0006 is Terraform skeleton, not constitution registry. | **P1 — fabricated path**        |
| FA-009  | `tests/unit/test_github_mcp.py`   | FA-009 is "Consensus constitution YAML configs" — `test_github_mcp.py` tests GitHub MCP retry logic, not constitution YAML loading.                   | **P1 — wrong test attribution** |
| FA-010  | `tests/unit/test_github_mcp.py`   | FA-010 is "Axis weights heuristic YAML" — same wrong test as FA-009.                                                                                  | **P1 — wrong test attribution** |

Executor self-disclosed FA-009/FA-010 in handoff §8 ("would not bet my job on")
but did not flag F0006. Executor's own caveat was correct but unactioned.

### R3-03 — ADR 0016 axis_weights YAML deferral — ✅ VERIFIED

- `docs/decisions/0016-axis-weights-yaml-as-planning-artifact.md` exists with 5 h2 sections
- `DECISIONS.md` row 16 added with link to ADR
- YAML header comment present on `axis_weights_heuristic.yaml`
- F0221 record in features.json: `phase=2`, `target_date=2026-05-28`, `passes=false` ✓

### R3-04 — TrajectoryRecorder trichotomy → F0222 — ✅ VERIFIED

- Inline comment at `trajectory_recorder.py:183-184` cites F0222 explicitly
- F0222 in features.json: `phase=2`, `target_date=2026-05-28`, `passes=false` ✓
- TrajectoryRecorderError class preserved at line 42

### R3-05 — ATELIER_OBSERVABILITY_MODE → F0223 stub — ✅ VERIFIED

- Module docstring in `observability/__init__.py` updated
- `docs/guides/phoenix-tracing.md` lines 27-56 contain ATELIER_OBSERVABILITY_MODE section with F0223 reference
- F0223 in features.json: `phase=2`, `target_date=2026-05-28`, `passes=false` ✓

### R3-06 — prettier autofix — ✅ VERIFIED ON R3 FILES, ⚠️ DIRTY ELSEWHERE

- `prettier --check` clean on R3-touched files
- `pre-commit run --all-files` passes
- Whole-repo `prettier --check` shows `CHANGELOG.md` dirty — pre-existing, unrelated to R3 scope

### R3-07 — Force-with-lease disclosure — ✅ VERIFIED, NO VIOLATION

**Methodology correction acknowledged**: reflog records operations, not flags. Authoritative source is GitHub Events API.

- `gh api repos/Manzela/atelier/events --jq '.[] | select(.type=="PushEvent" and .payload.forced==true)'`: **empty result**
- `git ls-remote origin phase/1`: returns current HEAD (no orphaned history)
- No `force-push` ever occurred on `phase/1`
- Local pre-push amends at `phase/1@{3}` (commit `8e7a766`) and `a064c3b` (handoff) are NOT destructive history rewrites; they never reached origin in pre-amend form
- `<no_destructive_git>` invariant: **not violated**

Executor's handoff §4 disclosure is accurate. Auth 401 caveat noted; cleared by my fresh `gh api` call which succeeded with empty result.

### R3-08 — release.yml main-only rationale — ✅ VERIFIED

- 3-line comment block at `.github/workflows/release.yml:3-5`
- Comment cites "Per audit R3-08" + rationale

### R3-09 — Node pin + asyncio_mode removal — ⚠️ PARTIAL / CAVEAT IGNORED

**Verified:**

- `.pre-commit-config.yaml` line 9: `node: '22.20.0'` ✓
- `asyncio_mode = "auto"` removed from `atelier-core/pyproject.toml` ✓
- `markdownlint` passes ✓

**Caveat IGNORED:**

- `.nvmrc` still reads `20.11.1` ❌
- **My R3-execution decision explicitly mandated 3-source alignment** (`.pre-commit-config.yaml`, `.nvmrc`, CI workflow node version). Only 1 of 3 sources updated.
- Material risk: developers running `nvm use` will get a Node version that mismatches pre-commit, causing intermittent local hook failures that don't reproduce in CI.

### R3-10 — Updated handoff doc — ⚠️ TWO DISCLOSURE GAPS

**Defect #1 — bulk-commit drift NOT disclosed in §4:**

User's summary claims "Drift from brief: Bulk commit instead of per-item commits (documented in handoff §4)" — but handoff §4 has subsections for R3-01/R3-02/R3-04/R3-05/R3-07 only. **No subsection discloses the bulk-commit drift.** Original brief required per-item commits for atomic rollback; executor delivered all R3 work in single commit `4d2bec1`.

**Defect #2 — false "push blocked" claim:**

User summary claims "Blocked: git push failed due to HTTPS auth." But:

- `git ls-remote origin phase/1` returns `a064c3b`
- HEAD of `phase/1` is also `a064c3b`
- The push **succeeded**. Either user's summary is stale, or push went through after the user composed the summary.

This is a low-severity inaccuracy in the executor-narrative-to-user channel, not in the artifacts themselves. Worth correcting for handoff hygiene.

### R3-11 — Final verification — ✅ PARTIALLY VERIFIED

- `pytest tests/`: **249 passed** (matches handoff claim)
- `pytest --collect-only`: 300 collected — diff (51) is Opus's untracked `test_llm_judge.py` (51 tests in Phase-2 ConsensusAgent work)
- `mypy --strict` on all 3 R3 target files: 0 errors ✓
- `jq` mandatory gate: 0 violations ✓
- `git status`: clean (working tree untracked files belong to Opus, not R3 scope) ✓

---

## 4. Structural / Out-of-Scope Findings

### ADR 0007 violation (NOT Antigravity's fault — flagged for governor attention)

Per CLAUDE.md `<wrap_phase_work_in_worktrees>`: "all sprint work happens in
`.worktrees/phaseN-<name>/` on branch `phase/N`."

Claude Opus is implementing **F0023 (Phase 2 ConsensusAgent)** in the
**`phase1-foundation` worktree on `phase/1` branch**. Phase-2 work belongs in a
separate `.worktrees/phase2-*/` worktree on `phase/2`. Files currently
untracked: `atelier-core/src/atelier/nodes/llm_judge.py`,
`atelier-core/tests/unit/test_llm_judge.py`.

**Impact:** When this worktree's phase/1 branch is eventually squashed/merged,
in-progress Phase-2 work risks being either merged prematurely or lost.

**Attribution:** This is Opus's invariant violation, not Antigravity's. Surfaced
here because it bears on R3 verification (presence of Opus's untracked files
explains 300-vs-249 test-count delta and ruff/mypy noise that the executor
correctly excluded from R3 scope).

### R3 commit scope is clean

`git show --stat 4d2bec1` confirms commit touched ONLY R3-scoped files. No
spillover into `llm_judge.py` or `test_llm_judge.py`. Executor correctly
respected boundaries despite working in a worktree where Opus's WIP was visible.

---

## 5. What Was NOT Verified (and Why)

- **Per-feature test passage**: I did not re-run tests for every newly-populated
  evidence_tests path. Mandatory gate (no `passes==true` with empty
  evidence_tests) is satisfied by jq query alone. Spot-checks revealed 3
  fabrications (above) but I did not enumerate all 13 mandatory IDs.
- **ADR 0016 content depth**: Confirmed 5 h2 sections exist; did not assess
  whether the Context/Decision/Consequences sections actually justify the
  deferral. (Deferred to Pass-2 enrichment.)
- **Phoenix-tracing.md content quality**: Confirmed F0223 reference exists at
  lines 27-56; did not validate that the section accurately describes the stub's
  current behavior vs Phase-2 plan. (Deferred to Pass-2 enrichment.)
- **CI green on `phase/1`**: Did not run `gh run list --branch phase/1`. Executor
  doesn't claim CI pass; only local pre-commit pass.

---

## 6. To Enrich in Pass 2

Parallel Explore subagents should target:

1. **ADR 0016 quality audit** — does the deferral rationale meet the bar set by ADRs 0011-0015?
2. **Cross-check FA-009/FA-010** — find the _real_ test files that exercise constitution YAML loading and axis_weights YAML loading (or confirm none exist).
3. **F0006 cross-check** — find any test that genuinely covers Terraform skeleton presence (or confirm none exists).
4. **Handoff §4 forensic completeness** — re-read the brief, enumerate every drift, compare to §4 subsections, surface any other gaps.

---

## 7. Empirical State (snapshot)

| Surface                            | State                                             |
| ---------------------------------- | ------------------------------------------------- |
| pytest tests/ (R3 scope)           | 249 passed                                        |
| mypy --strict (3 R3 files)         | 0 errors                                          |
| jq passes=true ∧ evidence_tests=[] | 0 violations                                      |
| prettier (R3 files)                | clean                                             |
| markdownlint                       | clean                                             |
| `.pre-commit-config.yaml` node     | `22.20.0` ✓                                       |
| `.nvmrc`                           | `20.11.1` ❌ (mandate ignored)                    |
| ADR 0016                           | present (5 h2 sections)                           |
| DECISIONS.md row 16                | present                                           |
| F0221/F0222/F0223                  | all `phase=2 target_date=2026-05-28 passes=false` |
| GitHub `forced==true` events       | 0                                                 |
| origin/phase/1 vs HEAD             | in sync at `a064c3b`                              |
| 4d2bec1 scope                      | R3 files only (no Opus spillover)                 |
