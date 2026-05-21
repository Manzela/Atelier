# Executor Brief — Round 4 (Audit Remediation)

**Source:** `audit/findings-run3.md` + `audit/audit-plan-run3.md`
**Target executor:** Antigravity IDE (Gemini 2.5 Pro)
**SLA:** 30-45 min wall-clock
**Commit policy:** **Per-item commits required** (5 commits expected). No bulk commits.
**Prior round:** R3 closed 8/11 items clean. R4 addresses the 3 defective + 3 disclosure-gap items.

---

## Items (P1 + P2)

### R4-01 (P1) — Fix F0006 fabricated evidence_tests path

**Where:** `features.json` → F0006 entry, `evidence_tests` field
**Problem:** Cites `tests/unit/test_constitution.py` — **file does not exist**. F0006 is "Terraform skeleton + 18 GCP API enables"; a constitution test bears no relation.
**Fix:**

1. Search for any Terraform-presence test:

   ```bash
   grep -rln "terraform\|tfstate\|main.tf" tests/
   find tests -name "test_*terraform*" -o -name "test_*infra*"
   ```

2. If found: replace `evidence_tests` with the real test path(s) AND verify the test actually exercises Terraform scaffold presence (not just imports it).
3. If not found: downgrade to `passes: false` with:

   ```json
   "evidence_gap_note": "no Terraform skeleton test exists; F0006 acceptance was scaffold-only and was not test-gated"
   ```

**Acceptance:** F0006 either cites a test file that exists AND bears on Terraform, or has `passes: false` + gap note.
**Commit:** `fix(features): correct F0006 evidence_tests (R4-01)`

---

### R4-02 (P1) — Fix FA-009 wrong attribution

**Where:** `features.json` → FA-009 entry, `evidence_tests` field
**Problem:** "Consensus constitution YAML configs" pointing to `tests/unit/test_github_mcp.py` is wrong (GitHub MCP test has nothing to do with consensus constitution YAML loaders).
**Fix:**

1. Search for real constitution YAML loader tests:

   ```bash
   grep -rln "consensus_constitution\|constitution.*yaml\|load_constitution" tests/
   find tests -name "test_*constitution*" -o -name "test_*yaml*config*"
   ```

2. If found: replace `evidence_tests` with the real path(s).
3. If not found: downgrade to `passes: false` with appropriate gap note.

**Acceptance:** FA-009 either cites a test that bears on consensus constitution YAML loading, or has `passes: false` + gap note.
**Commit:** `fix(features): correct FA-009 evidence_tests (R4-02)`

---

### R4-03 (P1) — Fix FA-010 wrong attribution

**Where:** `features.json` → FA-010 entry, `evidence_tests` field
**Problem:** "Axis weights heuristic YAML" pointing to `tests/unit/test_github_mcp.py` is wrong (same defect class as R4-02).
**Fix:**

1. Search for real axis_weights loader tests:

   ```bash
   grep -rln "axis_weights\|AXIS_WEIGHTS\|load_axis" tests/
   find tests -name "test_*axis*" -o -name "test_*weights*"
   ```

2. If found: replace `evidence_tests` with the real path(s).
3. If not found: downgrade to `passes: false` with appropriate gap note.

**Acceptance:** FA-010 either cites a test that bears on axis_weights YAML loading, or has `passes: false` + gap note.
**Commit:** `fix(features): correct FA-010 evidence_tests (R4-03)`

---

### R4-mandatory-gate (after R4-01..03) — Re-run jq mandatory gate

After downgrades, the mandatory-gate query MUST remain empty:

```bash
jq '.features[] | select(.passes==true and (.evidence_tests | length)==0)' features.json
```

If non-empty: stop and investigate before proceeding to R4-04.

---

### R4-04 (P2) — Update `.nvmrc` to 22.20.0

**Where:** `.nvmrc` at repo root
**Problem:** R3-09 mandated 3-source alignment for the Node version bump. `pre-commit-config.yaml` and `package.json` were updated; `.nvmrc` still reads `20.11.1`. This causes nvm-vs-pre-commit drift.
**Fix:** Replace contents of `.nvmrc` with `22.20.0` (single line, no trailing whitespace beyond newline).
**Acceptance:** `cat .nvmrc` returns `22.20.0`. Verify all three sources agree:

```bash
grep -h "^22" .nvmrc \
  && grep "node" package.json | grep "22.20.0" \
  && grep "language_version: 22.20.0" .pre-commit-config.yaml
```

**Commit:** `fix(deps): align .nvmrc with node 22.20.0 pin (R4-04)`

---

### R4-05 (P2) — Disclose bulk-commit drift in handoff §4

**Where:** `audit/executor-handoff-run3.md` §4 (Drift from the Brief)
**Problem:** Original R3 brief required per-item commits (atomic rollback granularity). Executor delivered all R3 work in single commit `4d2bec1`. Drift acknowledged in chat but **not** in handoff §4.
**Fix:** Append a new subsection to §4:

```markdown
### Bulk-commit drift (R3-10 §10)

Brief required per-item commits (atomic rollback granularity).
Executor delivered all R3 work in single commit `4d2bec1`.

**Rationale:** Time pressure (~90 min budget); per-item commits
would have added ~15 min for 11 separate stage/commit cycles.

**Trade-off accepted:** Rollback granularity sacrificed for
execution speed. R4 brief reinstates per-item commit requirement.
```

**Acceptance:** §4 contains the new subsection with title "Bulk-commit drift (R3-10 §10)".
**Commit:** `docs(audit): disclose R3 bulk-commit drift in handoff (R4-05)`

---

### R4-06 (P2) — Reconcile push-state claim

**Where:** R4 handoff document (`audit/executor-handoff-run4.md`, to be created in step R4-handoff below)
**Problem:** The R3 user-facing summary claimed "git push failed due to HTTPS auth", but `git ls-remote origin phase/1` confirms push succeeded at `a064c3b`. Either the push later succeeded after the summary, or the original claim was stale.
**Fix:** In the R4 handoff §4 (Drift from the Brief), add:

```markdown
### Push-state reconciliation (R4-06)

R3 user-facing summary stated push was blocked by HTTPS auth.
`git ls-remote origin phase/1` confirms `a064c3b` was pushed
successfully. Either (a) the post-summary retry succeeded
silently, or (b) the original "blocked" claim was incorrect.
Acknowledged here; no remediation action required (push state
is now consistent).
```

**Acceptance:** R4 handoff §4 contains the reconciliation subsection.
**Commit:** Bundled with R4-05 in `docs(audit): disclose R3 bulk-commit drift in handoff (R4-05, R4-06)` OR separate.

---

### R4-handoff — Write executor-handoff-run4.md

After all R4-01..06 commits land:

1. Author `audit/executor-handoff-run4.md` with the same structure as `executor-handoff-run3.md`:
   - §1 Executive Summary (one-paragraph close-out)
   - §2 Per-Item Table (R4-01..06, status, SHA, notes)
   - §3 Pre-commit Status (current gate state)
   - §4 Drift from the Brief (include R4-05 and R4-06 disclosures)
   - §5 Test Count Delta (should be unchanged: 300 → 300)
   - §6 Mypy Delta (should be unchanged)
   - §7 Gaps and Known Issues
   - §8 What I Would NOT Bet My Job On

2. Emit trailer: `READY-FOR-AUDIT-RUN-4: <ISO-8601 UTC>`

---

## Per-Item Commit Plan (5 commits expected)

| #   | Subject                                                                           | Items        |
| --- | --------------------------------------------------------------------------------- | ------------ |
| 1   | `fix(features): correct F0006 evidence_tests (R4-01)`                             | R4-01        |
| 2   | `fix(features): correct FA-009 evidence_tests (R4-02)`                            | R4-02        |
| 3   | `fix(features): correct FA-010 evidence_tests (R4-03)`                            | R4-03        |
| 4   | `fix(deps): align .nvmrc with node 22.20.0 pin (R4-04)`                           | R4-04        |
| 5   | `docs(audit): disclose R3 bulk-commit drift + push reconciliation (R4-05, R4-06)` | R4-05, R4-06 |
| 6   | `docs(audit): R4 handoff (R4-handoff)`                                            | handoff file |

Bulk-commit drift in R4 = automatic REJECT.

---

## Out of R4 Scope (Do Not Touch)

- `llm_judge.py`, `test_llm_judge.py`, `consensus.py` — Opus's ConsensusAgent Phase 2 work, separately committed.
- Worktree relocation for Phase 2 work — governor task **R4-09**, not executor task.
- Force-push, history rewrite, `git reset --hard`, `--no-verify`, `SKIP=hook`, `git commit --amend` of `4d2bec1` — all forbidden.
- Re-litigation of R3-07 force-push disclosure (verdict: clean).

---

## Acceptance Gates (must all pass before R4 handoff)

1. `pytest tests/` → 300+ passed (no regression from R3)
2. `mypy --strict atelier-core/src/atelier/nodes/github_mcp.py atelier-core/src/atelier/nodes/trajectory_recorder.py atelier-core/src/atelier/observability/__init__.py` → exit 0
3. `jq '.features[] | select(.passes==true and (.evidence_tests | length)==0)' features.json` → empty output
4. `cat .nvmrc` → `22.20.0`
5. `grep -A2 "Bulk-commit drift" audit/executor-handoff-run3.md` → non-empty match
6. `pre-commit run --all-files` → exit 0 (or non-R4 failures triaged explicitly)
7. `READY-FOR-AUDIT-RUN-4:` trailer present in handoff

---

## Submission

Emit `READY-FOR-AUDIT-RUN-4: <ISO-8601 UTC>` and link to all 6 commit SHAs in chat.
