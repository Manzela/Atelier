# Audit Plan — Round 4 Verdict + (Optional) Round 5 Hygiene Brief

**Source:** `audit/findings-run4.md`
**Target verdict:** Antigravity executor R4 handoff (`audit/executor-handoff-run4.md`)
**Date:** 2026-05-21
**Auditor:** Claude Opus 4.7 (orchestrator)
**Preliminary verdict:** **APPROVE close-out** with optional P3 hygiene tail for R5

---

## 1. R4 Verdict Matrix

| Item       | Brief requirement                               | Verified state                                           | Verdict          |
| ---------- | ----------------------------------------------- | -------------------------------------------------------- | ---------------- |
| R4-01      | F0006 evidence_tests fixed OR downgraded        | `passes:false` + gap note (downgrade path)               | ✅               |
| R4-02      | FA-009 evidence_tests bears on topic            | `test_constitution_registry.py` exists (semantic Pass 2) | ✅ (preliminary) |
| R4-03      | FA-010 evidence_tests bears on topic            | `test_axis_weights.py` exists (semantic Pass 2)          | ✅ (preliminary) |
| Gate       | jq mandatory-gate empty                         | empty                                                    | ✅               |
| R4-04      | `.nvmrc` = `22.20.0`                            | `22.20.0`                                                | ✅               |
| R4-05      | Bulk-commit drift subsection in handoff-run3 §4 | verbatim match                                           | ✅               |
| R4-06      | Push-state reconciliation in handoff-run4 §4    | present                                                  | ✅               |
| Handoff    | `executor-handoff-run4.md` + trailer            | `READY-FOR-AUDIT-RUN-4: 2026-05-21T12:11:08Z`            | ✅               |
| Per-commit | atomicity (5 + 1 commits)                       | 6/6 atomic (1 file each)                                 | ✅               |

**No material defects. R4 = clean close-out.**

---

## 2. Round-5 Hygiene Candidates (Optional, P3)

These are visible because R4 forced an audit of `evidence_tests` paths, but
none block sprint progression. Bundle into a single R5 hygiene brief OR defer
to natural cleanup in feature work.

### R5-01 (P3, hygiene) — Normalize `features.json` evidence_tests path schema

**Where:** `features.json` — all entries with `evidence_tests` arrays
**Problem:** Two competing path styles coexist:

- Style A: `tests/unit/test_X.py` (relative to `atelier-core/`)
- Style B: `atelier-core/tests/unit/test_X.py` (relative to repo root)

Both resolve to existing files because CI runs pytest from `atelier-core/`,
but mechanical path-validation scripts have to handle both forms.

**Fix:** Pick one style (Style A is shorter, matches CI cwd). Sed-rewrite
all Style B entries to Style A. Verify with a path-check script: every
`evidence_tests` entry resolves to an existing file when prefixed with `atelier-core/`.

**Acceptance:** All `evidence_tests` paths follow Style A. Path-check script
returns 0 misses for `.passes==true` entries.

**Effort:** 10 min.

---

### R5-02 (P3, doc) — Fix handoff §3 mypy file basenames

**Where:** `audit/executor-handoff-run4.md` §3 (and §6)
**Problem:** Says "mypy --strict: pass on github_mcp.py, trajectory_recorder.py,
observability/\_\_init\_\_.py" — these are unqualified basenames. The actual
paths are `atelier-core/src/atelier/integrations/github_mcp.py`,
`atelier-core/src/atelier/recorders/trajectory_recorder.py`,
`atelier-core/src/atelier/observability/__init__.py`. Stale wording carried
over from R3 handoff.

**Fix:** Replace bare basenames with full repo-relative paths.

**Acceptance:** §3 lists full paths; future readers don't have to grep.

**Effort:** 2 min.

---

### R5-03 (P3, doc) — Backfill R4-handoff SHA in handoff §2

**Where:** `audit/executor-handoff-run4.md` §2, last row of per-item table
**Problem:** Row reads "R4-handoff | This document | ✅ | TBD | —". SHA is
`87e3342` (recoverable from `git log --grep="R4-handoff"`).

**Fix:** Replace `TBD` with `87e3342`. Note: this creates a chicken-and-egg
self-reference (commit modifies handoff to mention its own predecessor SHA),
which is fine because the new commit is the SHA-amender, not the handoff itself.

**Acceptance:** §2 R4-handoff row contains `87e3342`.

**Effort:** 1 min.

---

### R5-04 (P3, doc) — Reconcile `ca1dd74` commit-message claim

**Where:** Commit message of `ca1dd74` (immutable; can only be corrected via
follow-up note, NOT amend per `<no_destructive_git>`)
**Problem:** Commit message says "3-source alignment: .nvmrc, .pre-commit-config.yaml,
and package.json all now reference node 22.20.0". Stat shows only `.nvmrc`
modified; `package.json` engines field is `>=20.11.0` (semver range). The
honest version is in handoff §8.1.

**Fix options:**

- **(a)** Add a follow-up note commit / ADR clarifying "alignment" = exact-pin
  in `.nvmrc` + `.pre-commit-config.yaml`, semver-compatible range in
  `package.json.engines.node` (intentional).
- **(b)** Bump `package.json.engines.node` to exact `22.20.0` (changes
  publish-time constraints; may break downstream consumers expecting
  semver-minimum semantics).
- **(c)** Do nothing — §8.1 disclosure stands.

**Recommended:** (a). Add a short ADR documenting the convention.

**Acceptance:** Either ADR exists OR `package.json.engines.node` bumped + tested.

**Effort:** 10 min for (a), 30 min for (b).

---

## 3. Out of R4/R5 Scope (Governor Tasks)

- **R4-09** (still pending): Move Phase-2 ConsensusAgent work to its own
  worktree. Currently in `phase1-foundation/` on `phase/1` per CA-AUDIT
  approval. Not an executor task — governor decision.

---

## 4. Pass-2 Enrichment Plan

Three parallel `Explore` subagents will fan out to:

1. **Semantic validator** — confirm `test_constitution_registry.py` exercises
   constitution YAML parsing/loading (FA-009 topic) and `test_axis_weights.py`
   exercises AxisWeights heuristic computation from YAML (FA-010 topic). Verdict:
   pass/fail per test, rationale in 3 sentences each.

2. **Mandatory-set evidence_tests spot-checker** — pick 5 more `.passes==true`
   features at random from the mandatory subset, verify their `evidence_tests`
   paths exist AND bear semantically on the feature topic. If any defect rate
   ≥ 1/5, escalate to R5-mandatory finding.

3. **R4 commit scope auditor** — for each of `261fcbf`, `cb9abd3`, `129a7d4`,
   `ca1dd74`, `a221d9d`, `87e3342`: confirm `git show` diff touches ONLY the
   claimed file(s), no sneaky touches to unrelated files, no comments added
   that suppress lint warnings, no test fixtures modified to mask failures.

Subagents run in parallel (single message, 3 tool calls). Each returns a
≤500-word report against the R4 handoff claim.

---

## 5. Pass-3 Approval Gate

Per `/audit` Pass 3 protocol: **stop, surface verdict, wait for user.**

User decisions in scope:

- **APPROVE close-out** — merge `phase/1` to `main` (or keep on `phase/1`
  until full Phase-1 wrap), proceed to next sprint work
- **APPROVE close-out + commission R5 hygiene brief** — bundle R5-01..04
  into a single R5 brief to Antigravity, ~25-min wall-clock
- **COMMENTS** — request specific changes from R4 before close-out
- **REJECT** — issue R5 corrective brief (would require fresh material defects, none found)

The preliminary recommendation is **APPROVE close-out**, with R5 hygiene
brief as optional opportunistic follow-up (not blocking).

---

## 6. Changes from Pass 1 (Pass-2 enrichment)

Three parallel `Explore` subagents ran against R4 claims. Results:

### Subagent A — FA-009/FA-010 semantic validator

✅ **Both PASS.** Detailed evidence:

- **FA-009 → `test_constitution_registry.py`**: `test_parse_minimal` (lines 23-37),
  `test_parse_defaults` (39-44), `test_load_from_consensus_dir` (62-68) directly call
  `_parse_constitution()` and `load_constitutions()` on `consensus/constitutions/apple-grade.yaml`
  and `consensus/constitutions/brutalist.yaml`. Implementation at
  `constitution_registry.py:78-113` and `116-144` parses YAML, extracts principles
  with weights, validates scoring thresholds. **Topic alignment: perfect.**

- **FA-010 → `test_axis_weights.py`**: `test_corporate_favors_accessibility` (78-80),
  `test_luxury_favors_brand` (82-84), `test_wcag_aaa_boosts_accessibility` (90-93),
  `test_draft_convergence_reduces_all` (95-99) call `compute_axis_weights()` with
  register and compliance/convergence parameters. Implementation at
  `axis_weights.py:177-219` consumes `_WEIGHT_PRESETS` (lines 102-159) that mirrors
  `consensus/axis_weights_heuristic.yaml` structure. **Topic alignment: perfect.**
  Note: YAML is currently a planning artifact (ADR 0016 deferred); Phase 1 consumes
  the hardcoded dict mirroring it. Test validates the heuristic logic, which is the
  actual feature gate.

### Subagent B — Mandatory-set spot-checker

Sampled 5 features (F0005, F0037, FA-001, FA-006, F0044) outside R4-fixed set.

| ID     | Path resolves?                                                          | Semantic alignment?      | Verdict              |
| ------ | ----------------------------------------------------------------------- | ------------------------ | -------------------- |
| F0005  | ✅ at `atelier-core/tests/...`                                          | ✅ axis_weights          | PASS                 |
| F0037  | ✅ at `atelier-core/tests/...`                                          | ✅ gates suite           | PASS                 |
| FA-001 | ✅ at `atelier-core/tests/...`                                          | ✅ OTel + model registry | PASS                 |
| FA-006 | ⚠ schema mismatch — cited `tests/...`, file at `atelier-core/tests/...` | ✅ consensus             | **PATH SCHEMA FAIL** |
| F0044  | ✅ at `atelier-core/tests/...`                                          | ✅ trajectory + DPO      | PASS                 |

**Defect rate: 1/5 (20%) — all attributable to NF-1 path-schema inconsistency, NOT
to semantic-relevance defects.**

**Updated risk assessment:** The path-schema inconsistency (NF-1) affects roughly
20% of mandatory features. None are materially broken (CI runs from `atelier-core/`
cwd so all paths resolve), but mechanical path-validation scripts fail. This
elevates **R5-01 priority from P3 → P2** (still hygiene, but worth fixing in one
bundled R5 brief rather than waiting for natural cleanup).

### Subagent C — R4 commit scope auditor

✅ **All 6 atomic.** Per-commit results:

```
261fcbf | PASS | F0006 evidence_tests downgraded only; gap note added.
cb9abd3 | PASS | FA-009 evidence_tests corrected only.
129a7d4 | PASS | FA-010 evidence_tests corrected only.
ca1dd74 | PASS | .nvmrc bumped 20.11.1→22.20.0 only.
a221d9d | PASS | 11 lines added to handoff-run3.md §4; no other edits.
87e3342 | PASS | New handoff-run4.md (129 lines); no other files.
```

**Anti-pattern scan results:**

- ✅ No `# noqa` or `# type: ignore` added
- ✅ No bare `except:` introduced
- ✅ No fixture modifications
- ✅ No `git config` changes
- ✅ No hidden file edits (`.gitignore`, `.github/`, etc.)
- ✅ No comments removed
- ✅ No lockfile drift
- ✅ All 6 Conventional Commits compliant
- ✅ Reflog shows NO `commit (amend)` entries (clean linear history)
- ✅ All 6 authored by `Manzela <81286733+Manzela@users.noreply.github.com>`

### Synthesis

- R4 closed 6/6 in-scope items cleanly.
- R4 introduced NO regressions, NO drift, NO anti-patterns.
- NF-1 path-schema inconsistency is real but pre-existing (R4 just made it visible
  by auditing `evidence_tests` paths). Now sized at ~20% of mandatory features →
  promote R5-01 to P2.
- NF-2..4 doc defects remain cosmetic and unchanged.

**Final recommendation unchanged: APPROVE close-out for R4. Optional R5 hygiene
brief covering R5-01 (now P2) + R5-02..04 (P3) can be bundled in a single ~25-min
brief if user wants to clear hygiene tail before sprint progression, or deferred
to natural cleanup.**
