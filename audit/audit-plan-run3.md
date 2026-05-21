# Audit Plan — Round 3 → Round 4 (Remediation)

**Source:** `audit/findings-run3.md`
**Target:** `audit/executor-handoff-run3.md` (Antigravity / Gemini 2.5 Pro, 2026-05-21)
**Verdict (preliminary):** COMMENTS — revise & resubmit
**Round-4 estimated effort:** 45-60 min wall-clock

---

## Prioritized Fix List

### P1 — Material defects (block close-out)

| ID    | What                                     | Where                        | Why it matters                                                                                                                                                                         | Effort |
| ----- | ---------------------------------------- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| R4-01 | Fix F0006 fabricated evidence_tests path | `features.json` F0006 entry  | Cites `tests/unit/test_constitution.py` — **file does not exist**. F0006 is "Terraform skeleton + 18 GCP API enables" — needs Terraform-presence test or downgrade to `passes: false`. | 10 min |
| R4-02 | Fix FA-009 wrong attribution             | `features.json` FA-009 entry | "Consensus constitution YAML configs" pointing to `test_github_mcp.py` is incorrect. Find real loader test or downgrade.                                                               | 10 min |
| R4-03 | Fix FA-010 wrong attribution             | `features.json` FA-010 entry | "Axis weights heuristic YAML" pointing to `test_github_mcp.py` is incorrect. Find real loader test or downgrade.                                                                       | 10 min |

**Acceptance criterion (P1):** Each of F0006, FA-009, FA-010 either (a) cites
a test file that exists AND whose name/contents bear on the feature topic,
or (b) `passes: false` with explicit `evidence_gap_note`.

### P2 — Caveat ignored + disclosure gaps

| ID    | What                                              | Where                               | Why                                                                                                                                                                                  | Effort |
| ----- | ------------------------------------------------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------ |
| R4-04 | Update `.nvmrc` to `22.20.0`                      | `.nvmrc` (root)                     | R3-execution decision mandated 3-source alignment for node version. Only 1 of 3 sources updated. Causes nvm-vs-pre-commit drift.                                                     | 2 min  |
| R4-05 | Disclose bulk-commit drift in handoff §4          | `audit/executor-handoff-run3.md` §4 | Original brief required per-item commits. Executor delivered single commit `4d2bec1`. Drift is real and was acknowledged in chat but not in handoff §4. **Add a new §4 subsection.** | 5 min  |
| R4-06 | Reconcile push-state claim in user-facing summary | (user message channel)              | Handoff claims push blocked but `git ls-remote origin phase/1` confirms push succeeded at `a064c3b`. Either stale claim or post-summary push. Acknowledge in Round-4 handoff.        | 2 min  |

### P3 — Hygiene (defer to Round-5 if time-constrained)

| ID    | What                                             | Where                              | Why                                                                                                                                                      | Effort |
| ----- | ------------------------------------------------ | ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| R4-07 | Fix `CHANGELOG.md` prettier drift                | `CHANGELOG.md`                     | Pre-existing dirty file unrelated to R3, but flagged by whole-repo `prettier --check`. Will gate future commits if anyone runs `prettier --write .`.     | 1 min  |
| R4-08 | Audit remaining 10 mandatory IDs' evidence_tests | `features.json` (mandatory subset) | 3 of 13 sampled are wrong (23% defect rate). Statistical likelihood is high that more are wrong. Spot-check 5 more before declaring jq-gate trustworthy. | 15 min |

### P4 — Out of R3/R4 scope (governor task)

| ID    | What                                                 | Why                                                                                                                                                         |
| ----- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R4-09 | Move Phase-2 ConsensusAgent work to its own worktree | ADR 0007 violation: F0023 (Phase 2) currently in `phase1-foundation` worktree on `phase/1` branch. Needs `.worktrees/phase2-consensus-agent/` on `phase/2`. |

---

## Round-4 Executor Instructions (Suggested)

1. Read `audit/findings-run3.md` §3.R3-02 for evidence of fabricated paths.
2. For F0006: search for any Terraform-presence test under `tests/`. If none, downgrade to `passes: false` with `evidence_gap_note: "no Terraform skeleton test exists; F0006 acceptance was scaffold-only"`.
3. For FA-009 and FA-010: search for `test_consensus_constitution*.py`, `test_axis_weights*.py`, `test_yaml_configs*.py`. If found, update evidence_tests. If not, downgrade to `passes: false` with similar gap notes.
4. After downgrades, re-run jq mandatory gate: `jq '.features[] | select(.passes==true and (.evidence_tests | length)==0)' features.json` — must remain empty.
5. Update `.nvmrc` to `22.20.0`.
6. Append §4 subsection to `executor-handoff-run3.md`:

   ```markdown
   ### Bulk-commit drift (R3-10 §10)

   Brief required per-item commits (atomic rollback). Executor delivered all R3 work in single commit `4d2bec1`. Rationale: time pressure (~90min budget); per-item commits would have added ~15min for 11 separate stage/commit cycles. Trade-off accepted: rollback granularity sacrificed for execution speed.
   ```

7. Per-item commits **required** for R4 (5 commits expected: R4-01, R4-02, R4-03, R4-04, R4-05+R4-06).
8. Write `audit/executor-handoff-run4.md` with same structure as Run-3 handoff.
9. Emit `READY-FOR-AUDIT-RUN-4: <ISO-8601 UTC>` trailer.

---

## What Round-4 Must NOT Do

- Do not touch `llm_judge.py` or `test_llm_judge.py` (Opus's Phase-2 work, separately tracked).
- Do not move/rename Phase-2 work to a separate worktree (governor task R4-09, not executor task).
- Do not amend `4d2bec1` (force-push concern). Create new commits.
- Do not re-litigate R3-07 force-push disclosure (verdict: clean, no violation).
- No `--no-verify` / no `SKIP=hook`.

---

## Approval Gate

Per `/audit` Pass 3: **Stop. Do not implement R4 fixes yet — wait for user verdict on this plan.**

User decision required: APPROVE Round-4 brief / EDIT (specify changes) / REJECT (alternative path).

---

## Round-3 Verdict Summary

- ✅ **8 items clean**: R3-01, R3-03, R3-04, R3-05, R3-06, R3-07, R3-08, R3-11
- ⚠️ **2 items defective**: R3-02 (3 wrong evidence_tests), R3-09 (.nvmrc not updated)
- ⚠️ **1 item disclosure gap**: R3-10 (bulk-commit drift undisclosed)
- ✅ **0 invariant violations** by R3 executor
- ⚠️ **1 invariant violation** by adjacent Opus work (ADR 0007 — out of R3 scope)
- ✅ **No force-push** (formally cleared via GitHub Events API)

**Recommendation:** Issue Round-4 brief with the 6 P1+P2 items above. Estimated executor wall-clock: 30-45 min.
