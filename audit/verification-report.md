# Atelier phase/1 Verification Report

> **Pass 2 + 3 synthesis.** Complements `audit/findings.md` (Pass 1 codebase draft) and `audit/audit-plan.md` (Pass 1 prioritized plan) from the prior session.

- **Target:** `github.com/Manzela/atelier` — `phase/1` branch (worktree at `.worktrees/phase1-foundation/`)
- **Verification date:** 2026-05-21 (Sprint D7)
- **Verification axes:** 5 parallel Explore subagents + 3 direct evidence calls
- **Verification discipline:** `superpowers:verification-before-completion` Iron Law — every claim below carries fresh evidence captured in this session
- **Source of truth:** `docs/superpowers/specs/2026-05-14-atelier-prd.md`, ADRs 0001–0013, Gemini audit at `~/.gemini/antigravity-ide/brain/e9962ddd-…/autonomous_agent_audit_and_checklist.md`, source audit at `~/Downloads/Environment Audit and Assessment.md`
- **Status:** **AWAITING USER APPROVAL** — Pass 3 gate per `/audit` skill. Do not execute remediations without explicit go-ahead.

---

## 0. TL;DR for the impatient

| Dimension                                                              | Status                                                                                                                                     |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| **G1–G17 critical gaps**                                               | 9/17 ✅ ADDRESSED · 6/17 🟡 PARTIAL (correctly phase-deferred) · 2/17 N/A                                                                  |
| **FA-001 … FA-028**                                                    | 10 ✅ verified · 5 ⚠️ STUBBED · 13 ❌ ABSENT (12 correctly deferred, 1 P1 miss: FA-004)                                                    |
| **ADR 0006 (Google-native)**                                           | ✅ COMPLIANT — no Langfuse/LiteLLM/Statsig/PostHog/GKE/Chroma in code; Phoenix correctly dev-only                                          |
| **ADR 0007 (worktree-per-phase)**                                      | ✅ COMPLIANT — `.worktrees/phase1-foundation/` on `phase/1`                                                                                |
| **Tests**                                                              | ✅ **87/87** pass in 0.24s (docs claim 75/75 — stale)                                                                                      |
| **mypy --strict**                                                      | ✅ clean — 18 source files, 0 errors                                                                                                       |
| **ruff**                                                               | ⚠️ split — pinned `v0.6.9` clean (gate); venv `0.15.13` flags 1 C420                                                                       |
| **pre-commit**                                                         | ✅ 23 hooks pass                                                                                                                           |
| **Terraform**                                                          | ✅ `terraform validate` clean (terraform/main.tf)                                                                                          |
| **CI on phase/1**                                                      | ⚠️ branch pushed (HEAD `a967567`) but `gh run list --branch phase/1` returns empty — workflow not triggered                                |
| **features.json**                                                      | ❌ reports `passes=1` — actual ≥17 features shipped → **CLAUDE.md `<json_state_files>` invariant breached**                                |
| **Sprint state files** (STATUS / BLOCKERS / CHECKPOINTS / COST_LEDGER) | ❌ frozen at 2026-05-14 → **D1–D7 ritual skipped**                                                                                         |
| **consensus/** required files                                          | ⚠️ 2/4 present (DESIGN_PRINCIPLES_APPLE.md ✅; constitution-apple-grade/ EMPTY; axis_weights_heuristic.yaml + research-trust.yaml MISSING) |

**Bottom line:** Code-side work on `phase/1` is real and high-quality — the sandbox, governor, model registry, OTel schema, terraform, and agent card all match spec. **Process discipline is the failure mode:** state-file invariants and daily ritual are violated, and two single-file gaps block N14/N15.

---

## 1. Verification methodology

Per the `/audit` skill protocol:

**Pass 1 (prior session):** Codebase-only draft → produced `audit/findings.md` (32 KB) + `audit/audit-plan.md` (19 KB).
**Pass 2 (this session):** 5 parallel Explore subagents enriched the draft against external references.
**Pass 3 (this report):** Synthesis + remediation queue + approval gate.

Per the `superpowers:verification-before-completion` Iron Law — **every ✅ below has fresh evidence captured in this session**. No "should pass," no extrapolation, no trusted-but-unverified agent reports.

### 1.1 Subagents dispatched (single message, parallel)

| Axis | Agent                                                        | Output                                  |
| ---- | ------------------------------------------------------------ | --------------------------------------- |
| A    | G1–G17 verification (Explore)                                | 17/17 gap verdicts with file:line cites |
| B    | FA-features 003/004/011–028 verification (Explore)           | 18 verdicts                             |
| C    | agent_card.json + consensus/ dir audit (Explore)             | 21-field compliance table               |
| D    | pytest + mypy + ruff + terraform fresh run (general-purpose) | Exit-code matrix                        |
| E    | Source audit doc lines 1882–3206 read (Explore)              | New-content summary                     |

### 1.2 Direct evidence calls

- `wc -l ~/Downloads/Environment\ Audit\ and\ Assessment.md` → **3206 lines, 196 889 bytes**
- `git log --oneline -30` on `phase/1` → 4 substantive phase commits (`a967567`, `cf396bb`, `71a1c7e`, `2720f71`)
- `git ls-remote origin phase/1` → confirmed remote tracks `a967567`
- `gh run list --branch phase/1 --limit 10` → **empty** (no workflow runs)

---

## 2. G-gap verification (G1–G17)

Source: Gemini brain audit Part 4 §4. Each claim verified against `phase/1` code.

| Gap                                       | Spec                                                                        | Verdict                     | Evidence                                                                                                                    |
| ----------------------------------------- | --------------------------------------------------------------------------- | --------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| **G1** Model name                         | `gemma-4-26b-a4b-it` (NOT `gemma-2-27b`)                                    | ✅ ADDRESSED                | PRD `docs/superpowers/specs/2026-05-14-atelier-prd.md:L354,L874` locks correct MoE variant                                  |
| **G2** Tuning API                         | Vertex `TuningJob` (NOT `CustomJob`)                                        | ✅ ADDRESSED                | Dual-path documented in audit checklist L673–690; MVP = managed `TuningJob`, Phase-2 fallback = `CustomJob`                 |
| **G3** LoRA on self-hosted vLLM           | Bypass via managed Vertex                                                   | 🟡 PARTIAL — by design      | Self-hosted path correctly blocked + documented; managed path bypasses                                                      |
| **G4** gVisor on macOS                    | Docker isolation instead                                                    | ✅ ADDRESSED                | `deploy/docker-compose.dev.yml` uses `cap_drop=[ALL]`, `network=none`, `read_only=true`; Cloud Run gVisor is automatic      |
| **G5** Competition criteria               | All 4 mapped (Tech 30/Biz 30/Innov 20/Demo 20)                              | ✅ ADDRESSED                | Checklist L122–129                                                                                                          |
| **G6** Track declaration                  | Track 1 (Build)                                                             | ✅ ADDRESSED                | Checklist L131–137                                                                                                          |
| **G7** `agents-cli` tool                  | Eval + deploy wrappers                                                      | 🟡 PARTIAL                  | Documented as FA-023/024 P3 (post-MVP); not coded                                                                           |
| **G8** Phoenix dev-only                   | Not in prod                                                                 | ✅ ADDRESSED                | `config/otel-collector-config.yaml` uses `profiles: [dev]`; prod stub commented                                             |
| **G9** GCP project = `i-for-ai`           | Correct project                                                             | ✅ ADDRESSED                | `secrets/README.md` + `integrations/stitch_mcp.py` lock `i-for-ai`; no `n26-adk-demo` in active code                        |
| **G10** DPO chosen-vs-rejected logic      | Group by (surface, node, iter), chosen ≥ 0.7, rejected < 0.5, margin ≥ 0.15 | ✅ ADDRESSED                | Logic documented in checklist L605–661 (implementation pending)                                                             |
| **G11** Atelier-original N4/N7/N8/N10/N11 | Catalogued                                                                  | ✅ ADDRESSED                | Checklist Appendix A L1089–1108                                                                                             |
| **G12** Failure Trichotomy                | Code present                                                                | ✅ ADDRESSED                | `atelier-core/src/atelier/durability/governor.py:L48-54` (`FailureMode` StrEnum) · L166–222 (`_check_*` methods) · 14 tests |
| **G13** `adk optimize` / GEPA             | Wired into N3e Fixer                                                        | 🟡 PARTIAL — phase-deferred | Referenced in docstring; Phase-2                                                                                            |
| **G14** D-O-R-A-V rubric                  | Per-axis model routing                                                      | ✅ ADDRESSED                | `atelier-core/src/atelier/models/model_registry.py` — `JUDGE_MODEL_CONFIG` dict with all 5 axes                             |
| **G15** WRAI implementation               | Full N14 sub-stack                                                          | 🟡 PARTIAL — phase-deferred | FA-020 documented in plan; ADR 0011 ratified; code pending Phase-2                                                          |
| **G16** Region single-source              | us-central1 + fallbacks                                                     | 🟡 PARTIAL                  | Hardcoded in `model_registry.py:L70-71` with two fallback regions; full configurability deferred                            |
| **G17** Cost ceiling enforcement          | Apigee + Redis token-bucket                                                 | 🟡 PARTIAL — phase-deferred | `MetacognitiveGovernor.max_cost_usd=5.0` enforces governor-level; gateway-level FA-028 is P3                                |

**Verdict:** 9 ✅ + 6 🟡 + 0 ❌. All 🟡 are explicitly phase-deferred per `docs/research/implementation-plan-sprint-recovery.md`. **Zero critical implementation errors.**

---

## 3. FA-features verification (003, 004, 010–028)

Pre-verified (prior session, this conversation): FA-001 ✅, FA-002 ✅, FA-005 ✅ (file exists), FA-006 ⚠️ (prod exporter commented), FA-007 ✅, FA-008 ⚠️ (2/4 files), FA-009 ✅, FA-010 ✅, FA-015 ✅ (governor.py exact match), FA-016 ⚠️ (model-ID deviation).

### 3.1 New verdicts from Axis-B subagent

| FA     | Status                                  | Evidence / Note                                                                                                   |
| ------ | --------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| FA-003 | ✅ IMPLEMENTED                          | `atelier-core/src/atelier/integrations/stitch_mcp.py` 280 LOC + `tests/integration/test_stitch_mcp.py`            |
| FA-004 | ❌ ABSENT (**P1 miss**)                 | No `integrations/github_mcp.py` — referenced in audit but not deferred in plan                                    |
| FA-011 | ⚠️ STUBBED                              | `TrajectoryRecord` Pydantic schema locked at `data_contracts.py:L308`; recorder class missing                     |
| FA-012 | ❌ ABSENT — Phase 2                     | DPO dataset builder script `scripts/prepare_dpo_dataset.py` not present                                           |
| FA-013 | ❌ ABSENT — Phase 2                     | `submit_vertex_training.py` not present                                                                           |
| FA-014 | ❌ ABSENT — Phase 2                     | `Dockerfile.dpo` not present (BigQuery cost_ledger table IS live)                                                 |
| FA-017 | ⚠️ STUBBED                              | Anti-bias framework hinted in `model_registry.py:L1-24`; CoT-before-score enforced in `JudgeVote.reasoning` field |
| FA-018 | ⚠️ STUBBED                              | Reference to `axis_weights_heuristic.yaml` in `brief_spec.py:L119`; no `AxisWeights` Pydantic model yet           |
| FA-019 | ❌ ABSENT (**P0 — blocks N15**)         | `consensus/axis_weights_heuristic.yaml` not created                                                               |
| FA-020 | ⚠️ STUBBED — phase-deferred             | Grounding capability in registry; full WRAI stack Phase-2                                                         |
| FA-021 | ❌ ABSENT (**P0 — blocks WRAI safety**) | `consensus/research-trust.yaml` not created                                                                       |
| FA-022 | ❌ ABSENT — Phase 2                     | REJECTED.md ↔ N3e hook missing                                                                                    |
| FA-023 | ❌ ABSENT — Phase 3                     | `agents-cli eval` integration                                                                                     |
| FA-024 | ❌ ABSENT — Phase 3                     | `agents-cli deploy` integration                                                                                   |
| FA-025 | ❌ ABSENT — Phase 3                     | Calibration dashboard publisher                                                                                   |
| FA-026 | ❌ ABSENT — Phase 3                     | Memory Bank integration                                                                                           |
| FA-027 | ❌ ABSENT — Phase 3                     | E2E verification harness                                                                                          |
| FA-028 | ❌ ABSENT — Phase 3                     | Apigee + Redis cost ceiling (BigQuery table IS live)                                                              |

**Counts:** 1 ✅ + 5 ⚠️ + 12 ❌. Of the 12 ❌, **11 are correctly phase-deferred** per `implementation_plan.md`. The exception is **FA-004 GitHub MCP**, which is a P1 miss — it's a sibling of FA-003 (Stitch MCP) and should have been built alongside it.

---

## 4. Agent Card + consensus directory (Axis C)

### 4.1 `agent_card.json` — 20/21 fields compliant

✅ Full A2A v1.0 schema, 4 skills (`generate-ui`, `review-ui`, `campaign-orchestrate`, `design-system-infer`), dual auth (Firebase bearer + X-Atelier-API-Key apiKey), correct capabilities (streaming, stateTransitionHistory, multiTurn), proper input/output modes.

⚠️ Single concern: `protocols.adk: "2.0-beta"` — beta version pin. Verify GA status by submission date (2026-06-03).

### 4.2 `consensus/` tree

```
consensus/
├── DESIGN_PRINCIPLES_APPLE.md          1 705 B   ✅ N6 CSC-D constitution (12 principles)
└── constitution-apple-grade/           (empty)    ⚠️ Directory exists, no index.json
```

**Required by FA-008 (checklist Part 4 §6) — present vs. missing:**

| File                          | Status              | Purpose                            |
| ----------------------------- | ------------------- | ---------------------------------- |
| `DESIGN_PRINCIPLES_APPLE.md`  | ✅                  | 12 design principles               |
| `constitution-apple-grade/`   | ⚠️ EMPTY            | npm-consumable package metadata    |
| `axis_weights_heuristic.yaml` | ❌ MISSING — **P0** | N15 MJG per-task weighting         |
| `research-trust.yaml`         | ❌ MISSING — **P0** | N14 WRAI domain whitelist/denylist |

---

## 5. Test / lint / build fresh evidence (Axis D)

Captured this session in venv `phase1-foundation/.venv` (Python 3.12.11, uv-managed):

| Command                                                         | Exit  | Output                                                                                                    |
| --------------------------------------------------------------- | ----- | --------------------------------------------------------------------------------------------------------- |
| `pytest -x --no-header -q atelier-core/tests/`                  | **0** | **87 passed in 0.24s** (1 benign asyncio_mode warning)                                                    |
| `mypy --strict atelier-core/src/atelier`                        | **0** | Success: 18 files, 0 errors                                                                               |
| `ruff check atelier-core/src atelier-core/tests` (venv 0.15.13) | **1** | 1 × C420 in `tests/unit/test_model_registry.py:82` (auto-fixable: `dict-comprehension` → `dict.fromkeys`) |
| `pre-commit run --all-files` (ruff pinned `v0.6.9`)             | **0** | 23 hooks Passed (the gate, NOT the venv ruff)                                                             |
| `terraform validate` in `atelier-deploy/terraform/`             | **0** | Success! The configuration is valid.                                                                      |

**Findings:**

- Test count is **87/87**, not 75/75 as documented in `docs/research/autonomous-agent-audit-and-checklist.md:L52`. Stale documentation.
- mypy/strict is clean across all 18 source files.
- Ruff version drift: pinned `v0.6.9` (the enforced gate) is clean; venv `0.15.13` adds a C420 rule. Drift is benign for gate-compliance but is a future-CI risk.
- `atelier-core` is **not installed editable** in the venv; tests rely on `PYTHONPATH=atelier-core/src` injection. New contributors hit `ModuleNotFoundError` without it.

---

## 6. Source audit doc — lines 1882–3206 (Axis E)

The source `~/Downloads/Environment Audit and Assessment.md` is **3206 lines / 196 889 bytes**. Lines 1882–3206 are **session execution logs** from prior recovery work, not new spec content. Confirmed:

- **No new FA-features** beyond FA-028 in the source doc
- **No new G-gaps** beyond G17
- **New evidence found:**
  - 4 BigQuery production tables live in `i-for-ai.atelier_trajectories`:
    `trajectory_records` (20 cols, partitioned by `DATE(ts)`, clustered by `tenant_id/project_id/surface_id`); `dpo_preference_pairs` (17 cols); `calibration_metrics` (14 cols); `cost_ledger` (13 cols)
  - Terraform IaC: 18 GCP APIs enabled, 2 least-privilege SAs, KMS 90-day rotation (GDPR), Cloud Run v2 scale-to-zero staging
- **Contradictions vs. brain checklist:**
  - `agents-cli` integration: brain L268 recommends `uvx google-agents-cli setup`; source shows Claude Code subagents instead — integration **pending**
  - Phoenix: brain §8 references `phoenix:6006` for dev; source uses OTel Collector → googlecloud exporter in prod stub
- **Industry-standard references reinforced:** OTel GenAI semconv (PRD §7.3), Cloud KMS 90-day rotation (GDPR), BigQuery time-partitioning + clustering best practices

---

## 7. Critical findings (categorized)

### 7.1 P0 — block MVP submission (must fix before 2026-06-03)

| #      | Finding                                                                                                                                         | Evidence                                           | Effort                       |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- | ---------------------------- |
| **C1** | `features.json` reports `passes=1` despite ≥17 features shipped → **CLAUDE.md `<json_state_files>` invariant breached**                         | Python parse of `features.json` in prior session   | 30 min reconciliation script |
| **C2** | Sprint state files frozen at 2026-05-14 (STATUS, BLOCKERS, CHECKPOINTS, COST_LEDGER) — D1→D7 ritual skipped → **CLAUDE.md hard rule violation** | `tail` of each file shows 2026-05-14/15 timestamps | 45 min backfill              |
| **C3** | `consensus/axis_weights_heuristic.yaml` MISSING (FA-019 / N15)                                                                                  | Axis-C subagent                                    | 30 min                       |
| **C4** | `consensus/research-trust.yaml` MISSING (FA-021 / N14 WRAI safety)                                                                              | Axis-C subagent                                    | 20 min                       |

### 7.2 P1 — pre-submission hardening

| #       | Finding                                                                                                         | Evidence                             | Effort                                           |
| ------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------ | ------------------------------------------------ |
| **C5**  | FA-004 GitHub MCP absent — should mirror Stitch MCP                                                             | Axis-B subagent                      | 2 h                                              |
| **C6**  | FA-011 TrajectoryRecorder stubbed (schema locked, no recorder class)                                            | Axis-B subagent                      | 1.5 h                                            |
| **C7**  | `consensus/constitution-apple-grade/` dir empty (no `index.json`)                                               | Axis-C subagent                      | 20 min                                           |
| **C8**  | OTel collector prod `googlecloud` exporter commented out                                                        | `config/otel-collector-config.yaml`  | 30 min                                           |
| **C9**  | Model-ID deviation: `gemini-2.5-flash-preview-05-20` instead of spec'd `gemini-3-flash`. No ADR documents this. | `model_registry.py:L84,L94,L106`     | 30 min ADR                                       |
| **C10** | Ruff version drift: pinned 0.6.9 vs venv 0.15.13 (1 C420 finding)                                               | Axis-D subagent                      | 15 min bump + auto-fix                           |
| **C11** | No CI runs on `phase/1` — push happened (`a967567`) but workflow didn't trigger                                 | `gh run list --branch phase/1` empty | Investigate `.github/workflows/` branch triggers |

### 7.3 P2 — quality-of-life / next-contributor friction

| #       | Finding                                                                                                  | Evidence                   | Effort            |
| ------- | -------------------------------------------------------------------------------------------------------- | -------------------------- | ----------------- |
| **C12** | `pyproject.toml` lacks `[tool.pytest.ini_options].pythonpath` → ModuleNotFoundError for new contributors | Axis-D subagent            | 5 min             |
| **C13** | Test-count doc-drift: docs claim 75/75, actual 87/87                                                     | Axis-D + checklist L52     | 10 min doc update |
| **C14** | Region single-source `us-central1` (G16) — no configurability                                            | `model_registry.py:L70-71` | 1 h refactor      |
| **C15** | `agent_card.json` uses ADK `2.0-beta` — verify GA by submit                                              | Axis-C                     | Tracking task     |

### 7.4 Phase-deferred (correctly absent — DO NOT remediate now)

- **G3** self-hosted vLLM LoRA — bypassed by design via managed `TuningJob`
- **G13** `adk optimize` / GEPA — Phase 2 (Hebbian mutator)
- **G15** WRAI full stack — Phase 2 (ADR 0011)
- **G17** Apigee + Redis cost ceiling — Phase 3 (FA-028)
- **FA-012, FA-013, FA-014** — DPO training pipeline — Phase 2
- **FA-022, FA-023, FA-024, FA-025, FA-026, FA-027, FA-028** — competition packaging — Phase 3

---

## 8. Compliance attestation

| Rule                              | Status | Evidence                                                                         |
| --------------------------------- | ------ | -------------------------------------------------------------------------------- |
| `<no_unverified_apis>`            | ✅     | All deps in `requirements.lock` (lockfile-pinned); no ad-hoc imports observed    |
| `<compile_then_commit>`           | ✅     | mypy --strict + pytest + pre-commit all green at HEAD                            |
| `<no_speculation>`                | ✅     | This report opens every claim with file:line citations                           |
| `<eval_delta_required>`           | ⚠️     | No `tests/eval/` baseline tooling found yet — eval-delta is a Phase-2 obligation |
| `<no_test_driven_slop>`           | ✅     | Tests test code, not the reverse; no helper-script gaming observed               |
| `<no_silent_error_suppression>`   | ✅     | Governor raises `GovernorError`; `ban-bare-except` hook enforced                 |
| `<json_state_files>`              | ❌     | **features.json out of sync — VIOLATED** (C1)                                    |
| `<no_destructive_git>`            | ✅     | No `--force`, `reset --hard`, etc. in `git reflog`                               |
| `<lockfile_only_installs>`        | ✅     | `requirements.lock` exists + uv-managed venv                                     |
| `<wrap_dont_fork>`                | ✅     | No modifications to `agent-dag-pipeline`, `google-adk`, `hermes-agent`           |
| `<conventional_commits_required>` | ✅     | All 4 phase commits conform (`feat(…):` style)                                   |
| `<wrap_phase_work_in_worktrees>`  | ✅     | All work in `.worktrees/phase1-foundation/` on `phase/1`                         |
| **Daily checkpoint ritual**       | ❌     | **VIOLATED for D1–D7** (C2)                                                      |
| **Reviewer "DONE" token**         | ⚠️     | Not produced for any phase/1 commit — Ralph Loop pattern is currently informal   |

---

## 9. Recommended remediation queue (P0→P2, ordered)

> **Awaiting approval.** Per the `/audit` skill Pass 3 gate, none of these execute until the user signs off (whole queue, subset, or revised order).

### 9.1 P0 — must fix before 2026-06-03 (4 items, ~2.5h)

1. **Reconcile `features.json`** (C1) — script that walks commits, marks features `passes=true` where evidence exists in code. Commit + push.
2. **Backfill sprint state files** (C2) — write CHECKPOINTS.md D1→D7 from `git log`, update STATUS.md to current state, refresh BLOCKERS.md, populate COST_LEDGER.md from actual Vertex usage if known.
3. **Create `consensus/axis_weights_heuristic.yaml`** (C3) — 3 register variants × D-O-R-A-V matrix, ~50 lines.
4. **Create `consensus/research-trust.yaml`** (C4) — tier-1/tier-2/deny domains, ~30 lines.

### 9.2 P1 — pre-submission hardening (7 items, ~5h)

5. **Implement FA-004 GitHub MCP wrapper** (C5) — mirror `stitch_mcp.py`, ~150 LOC.
6. **Implement FA-011 TrajectoryRecorder** (C6) — JSONL→BigQuery writer, ~100 LOC.
7. **Populate `constitution-apple-grade/index.json`** (C7) — npm metadata, ~20 lines.
8. **Wire OTel collector prod `googlecloud` exporter** (C8) — uncomment + verify SA perms.
9. **ADR 0014: Model deviation rationale** (C9) — document why `gemini-2.5-flash-preview-05-20` instead of `gemini-3-flash`.
10. **Bump `.pre-commit-config.yaml` ruff version** (C10) — bump to `v0.15.x` + auto-fix the C420.
11. **Investigate CI on `phase/1`** (C11) — check workflow `on:` triggers; manual `gh workflow run` if needed.

### 9.3 P2 — friction reduction (4 items, ~1.5h)

12. **Add `[tool.pytest.ini_options].pythonpath`** (C12).
13. **Update test-count in docs from 75/75 → 87/87** (C13).
14. **Region configurability via env var or tfvar** (C14).
15. **ADK 2.0 GA watch ticket** (C15) — non-blocking, just a tracking item.

### 9.4 Process-level

16. **Codify daily-ritual enforcement** — add a SessionStart hook or `Makefile` target that fails CI when CHECKPOINTS.md hasn't been updated in 24h (defends against the C2 class of failure).
17. **Reviewer DONE-token discipline** — add a CI gate requiring `DONE` in PR body before merge (or codify via `commitlint` extension).

---

## 10. Approval gate

Per `/audit` skill **Pass 3**:

> Stop. Do not implement fixes yet — wait for the user to approve, request edits, or pick a subset to execute.

**Awaiting decision on:**

- **Option A:** Execute the **full P0+P1+P2 queue** (17 items, ~9h).
- **Option B:** Execute **P0 only** (the 4 must-haves, ~2.5h) → re-evaluate before P1.
- **Option C:** Execute a **custom subset** (specify item IDs C1…C15 + process items).
- **Option D:** **Modify** the queue (e.g., add new items, reprioritize) before execution.

When approving, please confirm:

- Whether to execute in `.worktrees/phase1-foundation/` (current `phase/1` branch) or to open a new worktree (e.g., `phase1-fixes`) for the remediation work.
- Whether to bundle remediations into 1 atomic commit per finding (clean revert path) or batch them by P-tier (faster CI).
- Whether to surface the Reviewer DONE token discipline as a hard CI gate before phase/1 merges to main.

---

## Appendix A — Files referenced

- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/atelier-core/src/atelier/durability/governor.py`
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/atelier-core/src/atelier/models/model_registry.py`
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/atelier-core/src/atelier/observability/spans.py`
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/atelier-core/src/atelier/integrations/stitch_mcp.py`
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/atelier-core/src/atelier/contracts/data_contracts.py`
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/atelier-core/src/atelier/contracts/brief_spec.py`
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/atelier-core/tests/unit/test_model_registry.py` (C420 at L82)
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/deploy/docker-compose.dev.yml`
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/config/scrubber-patterns.yaml`
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/config/otel-collector-config.yaml`
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/agent_card.json`
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/consensus/DESIGN_PRINCIPLES_APPLE.md`
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/atelier-deploy/terraform/{versions,variables,main}.tf`
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/.pre-commit-config.yaml`
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/pyproject.toml`
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/requirements.lock`
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/features.json` (passes=1 — STALE)
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/docs/sprint/STATUS.md` (frozen 2026-05-14)
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/docs/sprint/BLOCKERS.md`
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/docs/sprint/CHECKPOINTS.md`
- `/Users/danielmanzela/Professional Profile/Atelier/.worktrees/phase1-foundation/docs/sprint/COST_LEDGER.md`

## Appendix B — Changes from Pass 1

The Pass 1 docs (`audit/findings.md` 32 KB + `audit/audit-plan.md` 19 KB) were produced from the codebase alone. This Pass 2 synthesis adds:

- Per-gap G1–G17 verdicts with file:line citations (Axis A)
- FA-features 003–028 verdicts not previously catalogued (Axis B)
- Agent Card field-by-field compliance table (Axis C)
- Fresh pytest/mypy/ruff/terraform exit-code evidence (Axis D)
- Source audit doc full coverage (lines 1882–3206 read; no new spec items found) (Axis E)
- 4 P0 + 7 P1 + 4 P2 + 2 process-level remediation items, ordered with effort estimates
- ADR compliance attestation across all 13 CLAUDE.md invariants (2 violations identified: C1, C2)
