# Executor Brief — Round 5 (Hygiene)

**Source:** `audit/findings-run4.md` + `audit/audit-plan-run4.md`
**Target executor:** Antigravity IDE (Gemini 2.5 Pro)
**SLA:** 20-30 min wall-clock
**Commit policy:** **Per-item commits required** (4 commits expected). No bulk commits.
**Prior round:** R4 closed 6/6 items clean. R5 is opportunistic hygiene — no material defects.

---

## Context

R4 closed all P1+P2 material defects. The auditor's Pass-2 enrichment surfaced
4 hygiene-grade items that are worth fixing in a single bundled brief before
sprint progression resumes. None block anything. Estimated wall-clock 20-30 min.

**Why now:** Pass-2 spot-check found that ~20% of mandatory `.passes==true`
features in `features.json` carry inconsistent `evidence_tests` path schema
(root-relative `tests/...` vs repo-relative `atelier-core/tests/...`). Both
resolve in CI because pytest runs from `atelier-core/`, but mechanical
path-validation scripts fail. R5-01 normalizes the schema.

---

## Items (1 P2 + 3 P3)

### R5-01 (P2, hygiene) — Normalize `features.json` evidence_tests path schema

**Where:** `features.json` — every entry's `evidence_tests` array.

**Problem:** Two competing styles coexist:

- Style A (minority, ~20%): `tests/unit/test_X.py` — relative to `atelier-core/`
- Style B (majority, ~80%): `atelier-core/tests/unit/test_X.py` — relative to repo root

**Decision: standardize on Style B** (`atelier-core/tests/...`). Rationale:

1. Style B is unambiguous from any CWD (validation scripts can run from repo root).
2. Style B is already the majority of entries.
3. Style B matches the actual filesystem path from repo root.

**Fix:**

1. Identify all Style A entries:

   ```bash
   jq -r '.features[] | select(.passes==true) | .evidence_tests[]?' features.json \
     | grep -v "^atelier-core/" | sort -u
   ```

   (Lists every path that does NOT start with `atelier-core/`. Expected ≥1.)

2. For each Style A path, verify the corresponding file exists at
   `atelier-core/<path>`:

   ```bash
   for p in $(jq -r '.features[].evidence_tests[]?' features.json | grep -v "^atelier-core/"); do
     [[ -f "atelier-core/$p" ]] && echo "OK: $p" || echo "MISS: $p"
   done | sort -u
   ```

   **If any MISS:** stop and investigate (would be a separate finding). Do NOT
   proceed to step 3 until all MISS results are explained.

3. Use `jq` to rewrite features.json in place, prefixing every non-prefixed
   `evidence_tests` entry with `atelier-core/`:

   ```bash
   jq '
     .features = [
       .features[] | (
         if (.evidence_tests | type) == "array"
         then .evidence_tests = [.evidence_tests[] | if startswith("atelier-core/") then . else "atelier-core/" + . end]
         else .
         end
       )
     ]
   ' features.json > features.json.tmp && mv features.json.tmp features.json
   ```

4. Verify schema is now uniform:

   ```bash
   jq -r '.features[].evidence_tests[]?' features.json | grep -v "^atelier-core/" | head
   ```

   Expected: empty output.

5. Re-run the mandatory gate (must remain empty):

   ```bash
   jq '.features[] | select(.passes==true and (.evidence_tests | length)==0)' features.json
   ```

**Acceptance:** Every `evidence_tests` entry in `features.json` starts with
`atelier-core/`. Mandatory gate still empty. Every cited path resolves to an
existing file from repo root.

**Commit:** `fix(features): normalize evidence_tests path schema to atelier-core/ prefix (R5-01)`

---

### R5-02 (P3, doc) — Fix handoff-run4 §3 + §6 mypy file paths

**Where:** `audit/executor-handoff-run4.md` §3 and §6.

**Problem:** Both sections refer to mypy files as bare basenames
(`github_mcp.py, trajectory_recorder.py, observability/__init__.py`). The
actual paths are:

- `atelier-core/src/atelier/integrations/github_mcp.py`
- `atelier-core/src/atelier/recorders/trajectory_recorder.py`
- `atelier-core/src/atelier/observability/__init__.py`

This is stale wording carried over from R3 handoff (where the same mistake
appeared). Cosmetic; no behavioral impact, but readers grep for the wrong path.

**Fix:** Replace bare basenames with the full repo-relative paths in both §3
and §6.

**Acceptance:** `grep "nodes/github_mcp" audit/executor-handoff-run4.md` returns
nothing. The strings `integrations/github_mcp.py`, `recorders/trajectory_recorder.py`,
and `observability/__init__.py` appear in §3 and §6.

**Commit:** `docs(audit): correct mypy file paths in run4 handoff §3+§6 (R5-02)`

---

### R5-03 (P3, doc) — Backfill R4-handoff SHA in handoff-run4 §2

**Where:** `audit/executor-handoff-run4.md` §2, "R4-handoff" row of the per-item table.

**Problem:** Row reads `| R4-handoff | This document | ✅ | TBD | — |`.
The actual SHA is `87e3342` (recoverable via `git log --grep="R4-handoff"`).
Pre-existing chicken-and-egg from self-referential handoffs.

**Fix:** Replace `TBD` with `87e3342`. Note: the new commit modifying this
line will itself have a different SHA, but that's fine — the table row
documents the handoff commit's SHA, not the SHA-backfill commit's SHA.

**Acceptance:** `grep "87e3342" audit/executor-handoff-run4.md` returns the
table row.

**Commit:** `docs(audit): backfill R4-handoff commit SHA in run4 handoff §2 (R5-03)`

---

### R5-04 (P3, doc — skippable) — Clarify "3-source alignment" convention

**Where:** New ADR file under `docs/decisions/` (next ADR number in sequence).

**Problem:** `ca1dd74`'s commit message says "3-source alignment: .nvmrc,
.pre-commit-config.yaml, and package.json all now reference node 22.20.0",
but `package.json.engines.node` is `>=20.11.0` (semver range, not exact pin).
The honest version lives in handoff-run4 §8.1, but there's no central
project-policy doc explaining why the asymmetry is intentional.

**Fix:** Author a short ADR (~20 lines) titled "Node version pinning
convention" documenting:

- `.nvmrc` and `.pre-commit-config.yaml` use exact pin (developer + CI determinism)
- `package.json.engines.node` uses semver minimum (downstream consumer flexibility)
- Both styles agree on the target version; "alignment" refers to compatibility, not byte-identical strings
- Update procedure: bump exact pins first, then update semver minimum if needed

**Acceptance:** New ADR file exists under `docs/decisions/` with the next
ADR number. `DECISIONS.md` at repo root references it (if `DECISIONS.md`
maintains an index).

**Commit:** `docs(adr): add node version pinning convention ADR (R5-04)`

**Skip condition:** If time is tight at the 25-min budget, skip R5-04 entirely.
The §8.1 disclosure is sufficient for the audit trail; the ADR is "nice to have."

---

## Per-Item Commit Plan (3 required, 4 with R5-04)

| #   | Subject                                                                               | Items        |
| --- | ------------------------------------------------------------------------------------- | ------------ |
| 1   | `fix(features): normalize evidence_tests path schema to atelier-core/ prefix (R5-01)` | R5-01        |
| 2   | `docs(audit): correct mypy file paths in run4 handoff §3+§6 (R5-02)`                  | R5-02        |
| 3   | `docs(audit): backfill R4-handoff commit SHA in run4 handoff §2 (R5-03)`              | R5-03        |
| 4   | `docs(adr): add node version pinning convention ADR (R5-04)` (optional)               | R5-04        |
| 5   | `docs(audit): R5 handoff (R5-handoff)`                                                | handoff file |

**Bulk-commit drift in R5 = automatic REJECT** (same rule as R4).

---

## Out of R5 Scope (Do Not Touch)

- Anything in `atelier-core/src/atelier/` source code (no feature work this round)
- Anything in `atelier-core/tests/` (no test changes this round — only path strings in features.json reference them)
- `4d2bec1`, `261fcbf`, `cb9abd3`, `129a7d4`, `ca1dd74`, `a221d9d`, `87e3342` — do NOT amend any R3/R4 commit
- ADR 0007 worktree relocation for Phase 2 work — governor task R4-09, separate
- Force-push, history rewrite, `git reset --hard`, `--no-verify`, `SKIP=hook` — all forbidden
- Re-litigation of R4 verdict (verdict: APPROVE close-out, no material defects)

---

## Acceptance Gates (must all pass before R5 handoff)

1. `pytest tests/` → 300+ passed (no regression from R4)
2. `mypy --strict atelier-core/src/atelier/integrations/github_mcp.py atelier-core/src/atelier/recorders/trajectory_recorder.py atelier-core/src/atelier/observability/__init__.py` → exit 0
3. `jq '.features[] | select(.passes==true and (.evidence_tests | length)==0)' features.json` → empty
4. `jq -r '.features[].evidence_tests[]?' features.json | grep -v "^atelier-core/" | head` → empty (proves R5-01 success)
5. Every `evidence_tests` path resolves from repo root:

   ```bash
   for p in $(jq -r '.features[].evidence_tests[]?' features.json); do [[ -f "$p" ]] || echo "MISS: $p"; done
   ```

   → no MISS output

6. `grep "TBD" audit/executor-handoff-run4.md` → empty (proves R5-03 success)
7. `grep "nodes/github_mcp" audit/executor-handoff-run4.md` → empty (proves R5-02 success)
8. `pre-commit run --all-files` → exit 0
9. `READY-FOR-AUDIT-RUN-5:` trailer present in handoff

---

## R5-handoff — Write `audit/executor-handoff-run5.md`

After all R5-01..04 commits land:

1. Author `audit/executor-handoff-run5.md` with the same structure as
   `executor-handoff-run4.md` (§§1-8).
2. **Important:** §2 R5-handoff row should include the commit SHA after the
   commit is made — do NOT leave "TBD". If self-referential, use the SHA of
   the _previous_ commit (R5-04 or whichever is most recent before the handoff
   commit) as a checkpoint, OR amend with the actual SHA in a second pass.
   (R5-03 specifically targets this pattern; you have a chance to avoid
   reintroducing it.)
3. Emit trailer: `READY-FOR-AUDIT-RUN-5: <ISO-8601 UTC>`

---

## Submission

Emit `READY-FOR-AUDIT-RUN-5: <ISO-8601 UTC>` and link to all 4-5 commit SHAs in chat.
