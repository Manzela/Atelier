# Atelier Days 11–21 Parallel Execution Design

**Status:** Approved (2026-05-25)
**Author:** Daniel Manzela + Claude (Opus 4.7 MAX)
**Date:** 2026-05-25
**Scope window:** 2026-05-25 (D11) → 2026-06-04 (D21, submission 2026-06-03 noon)
**Supersedes:** nothing (additive — extends Post-R4 Strategic Roadmap `2026-05-21-design.md`)
**Audience:** future-Daniel, future-Claude, future-Antigravity, internal Google judges (indirectly)

---

## §0. Context

Today is Day 11 of 21. Eleven days remain before submission target (noon 2026-06-03).

**Verified state at session start (2026-05-25):**

| Surface            | State                                                                                         |
| ------------------ | --------------------------------------------------------------------------------------------- |
| `phase/1`          | Merged → `main` (PR #25). T1–T5 SOTA Protocols landed. CI fully green.                        |
| `phase/2` tip      | `0e1c3b1` — ConsensusAgent + Post-R4 roadmap design. Zero implementation commits since D7.    |
| `main`             | 2 commits behind `origin/main` — needs `git pull`.                                            |
| Post-R4 schedule   | D9–D11 tasks (Brief Parser, OTel, TrajectoryRecorder, Governor, agents-cli deploy) unstarted. |
| Budget             | ~$200 of $5,000 (4%).                                                                         |
| Days to submission | **11** (target 2026-06-03 noon).                                                              |

**Competition rubric (from locked decision L3, ADR 0018):**

| Criterion                | Weight |
| ------------------------ | ------ |
| Technical Implementation | 30%    |
| Business Impact          | 30%    |
| Innovation               | 20%    |
| Demo Quality             | 20%    |

The design below maximizes all four simultaneously by running two independent execution lanes in parallel.

---

## §1. Core principle: strict domain split

Claude and Antigravity execute concurrently in `.worktrees/phase2-consensus-agent` on branch `phase/2`. File-level ownership boundaries make merge conflicts structurally impossible.

### §1.1 Antigravity R9 owns (pipeline + infrastructure)

```
atelier-core/src/atelier/api/
atelier-core/src/atelier/gates/
atelier-core/src/atelier/intake/
atelier-core/src/atelier/orchestrator/
atelier-core/src/atelier/recorders/
atelier-core/src/atelier/observability/
atelier-core/src/atelier/integrations/
atelier-core/src/atelier/durability/
infra/terraform/
deploy/
atelier-eval/src/atelier_eval/metrics/  [except visual_similarity.py — already done]
config/
scripts/migration/
scripts/governance/
```

### §1.2 Claude owns (SOTA Protocol surfaces)

```
atelier-core/src/atelier/router/
atelier-core/src/atelier/reward/
atelier-core/src/atelier/memory/
atelier-core/src/atelier/optimize/
atelier-core/src/atelier/nodes/_types.py  [shared types, already locked]
```

### §1.3 Shared (read-only for both, write by explicit coordination)

```
features.json           — batch-end update only; never concurrent writes
docs/sprint/CHECKPOINTS.md  — append-only; Antigravity commits first, then Claude
DECISIONS.md            — ADR additions only; coordinate before committing
pyproject.toml          — dependency additions: notify the other agent before committing
```

---

## §2. Antigravity R9 executor brief

### §2.1 R9 goals

1. Deliver a working 3-node pipeline (N1 Brief Parser → N2 Source Resolver → N3a Generator) by R9-C end.
2. Deliver observability infrastructure (OTel), DPO pipeline (TrajectoryRecorder + dataset builder), and MetacognitiveGovernor.
3. Produce a Daniel-action checklist for all GCP-gated steps (not blocking).
4. Tag `v0.1.0-phase-1-gate` after Phase 1 Gate criteria pass.

### §2.2 R9-A batch (D11–D12, 2026-05-25 → 2026-05-26)

**Goal:** Core observability + Brief Parser end-to-end.

| Feature | File(s)                                                                                                                                                                 | Acceptance                                                                                   |
| ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| FA-006  | `config/otel-collector-config.yaml` — OTLP gRPC + HTTP receivers, batch processor, Phoenix dev exporter + Google Cloud prod exporter, `gen_ai.system=atelier` attribute | `pytest tests/integration/test_otel_export.py` passes                                        |
| FA-007  | `atelier-core/src/atelier/observability/spans.py` — `ATELIER_SPAN_ATTRS` dict, 15 mandatory attributes per PRD §7.3                                                     | `pytest tests/unit/test_otel_spans.py` passes                                                |
| F0013   | `atelier-core/src/atelier/intake/brief_parser.py` — N1 BriefParserGate (deterministic JSON schema validator) + BriefParserAgent (Gemini 3 Flash via Vertex AI ADK)      | 3 unit tests: gate pass, gate reject empty, agent returns valid BriefSpec                    |
| F0014   | `atelier-core/tests/unit/test_brief_parser.py`                                                                                                                          | All 3 tests pass under `pytest -x`                                                           |
| F0015   | `atelier-core/src/atelier/orchestrator/runner.py` — ADK SequentialAgent containing N1                                                                                   | Import resolves; `python -c "from atelier.orchestrator.runner import AtelierRunner"` exits 0 |
| F0016   | `atelier-core/tests/integration/test_pipeline_n1.py`                                                                                                                    | End-to-end: brief text → BriefSpec via ADK Runner with mocked Gemini                         |
| FA-002  | `config/scrubber-patterns.yaml` — 6 regex patterns (Google API Key, GitHub Token, SA Key, Generic Secret, JWT, Vertex Endpoint)                                         | `pytest tests/security/test_scrubber.py` passes                                              |
| FA-001  | `deploy/docker-compose.dev.yml` — shell-sandbox (cap_drop=ALL, read_only=true, no-new-privileges=true) + browser-sandbox (Playwright)                                   | `docker compose -f deploy/docker-compose.dev.yml config` exits 0                             |

**R9-A definition of done:** `pytest tests/unit/test_brief_parser.py tests/integration/test_pipeline_n1.py tests/unit/test_otel_spans.py tests/security/test_scrubber.py` all pass. Pre-commit hooks pass on all changed files. Commit with `feat(intake): N1 Brief Parser + FA-006/007 OTel + FA-001/002 security`.

### §2.3 R9-B batch (D12–D13, 2026-05-26 → 2026-05-27)

**Goal:** Governor + DPO pipeline + task-aware routing.

| Feature | File(s)                                                                                                                                                                                                                                                                                                                 | Acceptance                                                                                 |
| ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| FA-015  | `atelier-core/src/atelier/orchestrator/governor.py` — `MetacognitiveGovernor` with MAPE-K loop, `FailureMode.{FAIL_LOUD,FAIL_SOFT,SELF_HEAL}`, `_check_budget`, `_check_step_budget`, `_check_infinite_loop`, `_check_stall`, `should_self_heal` (max 3 retries)                                                        | `pytest tests/unit/test_governor.py` ≥ 20 cases                                            |
| FA-011  | `atelier-core/src/atelier/recorders/trajectory_recorder.py` — `TrajectoryRecorder` writing JSONL per PRD `TrajectoryRecord` schema; fields: trajectory_id, tenant/project/session/surface IDs, node_name, iteration, candidate_id, prompt, response, gate_outcomes, judge_votes, composite_score, cost_usd, user_signal | `pytest tests/integration/test_trajectory_recorder.py` passes                              |
| FA-012  | `atelier-core/src/atelier/recorders/dpo_builder.py` — `prepare_dpo_dataset()` groups by (surface_id, node_name, iteration), T2 chosen (≥0.7), T3 rejected (<0.5), MIN_MARGIN=0.15, outputs JSONL preference pairs. G10 fix: compare DIFFERENT candidates at the same decision point, not consecutive iterations.        | `pytest tests/unit/test_dpo_builder.py` ≥ 10 cases including G10 regression                |
| FA-016  | `atelier-core/src/atelier/nodes/model_registry.py` — `JUDGE_MODEL_CONFIG` routing dict: `brand → gemini-3-flash(vision)`, `originality → gemini-2.5-pro(thinking)`, `relevance → gemini-3-flash+grounding`, `accessibility → det_gate+gemini-3.1-flash-lite`, `visual_clarity → gemini-3-flash+embedding2`              | Import resolves; `python -c "from atelier.nodes.model_registry import JUDGE_MODEL_CONFIG"` |
| FA-017  | `atelier-core/src/atelier/nodes/judge_harness.py` — anti-bias rules: (1) no family-self-preference guard, (2) CoT-before-score in JudgeVote, (3) position swap for pairwise, (4) gold set calibration pipeline stub (200–500 labels, Cohen's κ ≥ 0.7)                                                                   | `pytest tests/unit/test_judge_harness.py` ≥ 8 cases                                        |

**R9-B definition of done:** `pytest tests/unit/test_governor.py tests/unit/test_dpo_builder.py tests/unit/test_judge_harness.py tests/integration/test_trajectory_recorder.py` all pass. Commit with `feat(orchestrator,recorders): MetacognitiveGovernor + DPO pipeline + task-aware judge routing`.

### §2.4 R9-C batch (D13–D14, 2026-05-27 → 2026-05-28)

**Goal:** N2 Source Resolver + N3a Generator + Phase 1 Gate validation.

| Feature      | File(s)                                                                                                                                                                                               | Acceptance                           |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| F0021        | `atelier-core/src/atelier/intake/source_resolver.py` — N2 GateAgent: descriptor exists OR brief contains path → resolve to project context                                                            | 3 unit tests                         |
| F0022        | N2 agent: pull DESIGN.md tokens via `dmd lint` subprocess, pull principles, pull Memory Bank prior preferences                                                                                        | 3 unit tests                         |
| F0027        | `atelier-core/src/atelier/integrations/stitch_mcp.py` — Stitch MCP via ADK `MCPToolset(server_uri, auth_config=google_default)`; auth via Secret Manager `atelier-geap-api-key`                       | Import resolves                      |
| F0028–F0030  | `atelier-core/src/atelier/orchestrator/generator_ensemble.py` — N3a Generator: K=3 candidates via `ParallelAgent`; each sub-generator calls Stitch `generate_screen_from_text` OR Gemini 3 Pro direct | Integration test with mocked Stitch  |
| F0016+       | `atelier-core/tests/integration/test_pipeline_n1_n2_n3a.py` — pipeline integration: brief + descriptor → BriefSpec + ProjectContext + 3 candidates                                                    | Passes                               |
| Phase 1 Gate | Validate all 7 Phase 1 Gate criteria (see PRD §11)                                                                                                                                                    | All green; tag `v0.1.0-phase-1-gate` |

**R9-C definition of done:** Full pipeline integration test passes. All 7 Phase 1 Gate criteria verified. Tag `v0.1.0-phase-1-gate` created. `agents-cli deploy --dry-run` plan committed.

### §2.5 R9 Daniel-action checklist (output at R9 end, non-blocking)

Antigravity produces this checklist as the final R9 artifact. Daniel runs these interactively:

1. `gcloud iam service-accounts create atelier-runtime --project=atelier-build-2026 --display-name="Atelier Runtime SA"`
2. `cd infra/terraform && terraform apply -var-file=staging.tfvars` (review plan output first)
3. `bash scripts/migration/07_migrate_geap_secret.sh --wet`
4. `bash scripts/governance/protect_phase_1.sh --apply`
5. `agents-cli deploy --project=atelier-build-2026 --target=cloud_run --service=atelier-staging` (live credentials)
6. Submit Atelier to UIBench (2h session; generates DPO labels + leaderboard ranking)

### §2.6 R9 protected paths (DO NOT MODIFY — Claude-owned)

```
atelier-core/src/atelier/router/
atelier-core/src/atelier/reward/
atelier-core/src/atelier/memory/
atelier-core/src/atelier/optimize/
atelier-core/src/atelier/nodes/_types.py
```

---

## §3. Claude T6–T14 implementation plan

Concurrent with R9. Executes in `phase/2` worktree, SOTA Protocol subpackages only.

### §3.1 Task ordering and contracts

| Task | File                                                            | PRD   | Key implementation detail                                                                                                                                                                                              | Acceptance                         |
| ---- | --------------------------------------------------------------- | ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| T6   | `atelier-core/src/atelier/optimize/dpo_tuning_job.py`           | §9.2  | Replace deprecated `vertexai.tuning.sft` with `google.genai TuningMethod.PREFERENCE_TUNING`; β=0.1, epochCount=3, adapterSize=4 per ADR 0028. Verify API via `context7` before writing any import.                     | mypy strict + 12 unit tests        |
| T7   | `atelier-core/src/atelier/optimize/generator_tuner.py`          | §9.3  | GeneratorTuner Protocol + `mine_pairs()` pulling from BigQuery `atelier_trajectories.dpo_pairs`; returns `list[PreferencePair]`                                                                                        | mypy strict + 8 unit tests         |
| T8   | `atelier-core/src/atelier/memory/bigquery_backend.py`           | §20   | BigQuery episodic memory backend implementing `MemoryBackend` Protocol (T1); §20.5 virtual context isolation leak test — ensure `tenant_id` predicate is always present in every query                                 | mypy strict + §20.5 isolation test |
| T13  | `atelier-core/src/atelier/router/bandit.py`                     | §18.2 | Router v1 ε-Greedy Bandit: UCB1 selection, `EPSILON_START=0.10`, `EPSILON_FLOOR=0.02`, 7-day decay, `UCB1_EXPLORATION_CONSTANT=sqrt(2.0)`, BigQuery-backed arm counts. Implements `PhaseAwareMoERouter` Protocol (T3). | mypy strict + 15 unit tests        |
| T14  | `atelier-core/src/atelier/optimize/generator_tuner.py` (extend) | §9.4  | Full `tune()` + `evaluate_and_promote()` against BigQuery golden set; `evaluate_and_promote()` gates promotion on κ ≥ 0.7                                                                                              | 10 unit tests + eval-delta clean   |

### §3.2 Sequence rationale

T6 → T7 → T8 → T13 → T14 is the dependency order:

- T6 (DPO tuning client) is a prerequisite for T7 (`mine_pairs` feeds T6)
- T8 (BQ memory backend) is independent of T6/T7; can start in parallel if context allows
- T13 (router bandit) depends on T3 Protocol (already done) and BQ backend (T8)
- T14 extends T7, so T7 must be complete

### §3.3 Claude protected paths (DO NOT MODIFY — Antigravity-owned)

```
atelier-core/src/atelier/api/
atelier-core/src/atelier/gates/
atelier-core/src/atelier/intake/
atelier-core/src/atelier/orchestrator/
atelier-core/src/atelier/recorders/
atelier-core/src/atelier/observability/
atelier-core/src/atelier/integrations/
atelier-core/src/atelier/durability/
infra/terraform/
deploy/
config/
scripts/
```

---

## §4. Coordination protocol

### §4.1 Commit discipline

- Both agents follow `<conventional_commits_required>` (scope-prefixed, no `--no-verify`)
- Both agents run `git pull --rebase origin phase/2` before every push
- Shared files (`features.json`, `CHECKPOINTS.md`, `DECISIONS.md`, `pyproject.toml`, `requirements.lock`) are written at batch end only; no concurrent writes
- If a shared file needs updating mid-batch, commit it as a standalone commit with scope `chore(state):` and leave a comment in `CHECKPOINTS.md` so the other agent knows not to touch it until the next pull
- `pyproject.toml` additions: Antigravity adds to `[project.dependencies]` only; Claude adds to `[tool.mypy.overrides]` only. If either needs the other section, open a GitHub Issue first.

### §4.2 Verification before any completion claim

Per `<compile_then_commit>` and the Iron Law:

1. `mypy --strict <path>` exit 0
2. `python -c "import <module.path>"` exit 0
3. `pytest -x --no-header <test_file>` exit 0
4. `pre-commit run --all-files` exit 0

No DONE token without all four passing.

### §4.3 Checkpoint cadence

- End of each batch (R9-A, R9-B, R9-C, and each T-series task): append to `docs/sprint/CHECKPOINTS.md`
- Format: date, batch ID, what shipped, test count, cost estimate, next task
- Antigravity commits first (pipeline features), Claude commits second (SOTA Protocol)

---

## §5. Phase 2 → Phase 3 gate (D14–D21)

After R9-C closes and T6–T14 complete, the remaining 7 days (D15–D21) deliver:

- **Phase 2 gate** (D14): 12-surface autonomous campaign + WebGen-Bench ≥ 51 + 5 beta tenants
- **D15–D16**: WRAI sub-stack (FA-020), Campaign Orchestrator, EvoDesign (N3b–N3f)
- **D17–D18**: WebGen-Bench eval harness + `agents-cli eval` + DPO warm-start ingestion
- **D19**: Phase 2 gate validation; tag `v0.2.0-phase-2-gate`
- **D20**: DevPost project page (FA-026), demo video script, Agent Studio compatibility clip (FA-025)
- **D21**: Final submission to Google for Startups AI Agents Challenge DevPost by noon 2026-06-03

A new design spec will be written at D15 to capture Phase 2 → Phase 3 details, scoped to the state verified at that point.

---

## §6. Definition of success for this design

This design is successful when all of the following are true:

1. All T6–T14 unit tests pass (`pytest atelier-core/tests/unit/` ≥ 60 new tests)
2. R9-A, R9-B, R9-C all pass their stated acceptance criteria
3. Phase 1 Gate tag `v0.1.0-phase-1-gate` exists on `phase/2`
4. CI green on `phase/2` (CI + CodeQL + features.json schema)
5. Daniel-action checklist issued with clear instructions
6. `docs/sprint/CHECKPOINTS.md` updated with D11–D14 entries
