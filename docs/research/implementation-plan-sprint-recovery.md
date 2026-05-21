# Implementation Plan: Atelier Sprint Execution

> **Goal**: Execute the Atelier 21-day sprint to WIN the Google for Startups AI Agent Hackathon (Track 1: Build)
> **Deadline**: June 3, 2026 noon (submission target); June 5 official cutoff
> **Current State**: 1/205 features complete (F0001 scaffold only). **0 lines of application code.**
> **Days Remaining**: ~14 days (May 21 → Jun 3)
> **Budget Remaining**: ~$4,950 of $5,000
> **Audit Source**: [Autonomous Agent Audit & Checklist](file:///Users/danielmanzela/.gemini/antigravity-ide/brain/e9962ddd-ddea-4979-a1d2-fa00102a9019/autonomous_agent_audit_and_checklist.md)

---

## Situation Assessment

> [!CAUTION]
> **We are 6 days behind the original sprint plan.** The sprint was designed for May 15 → Jun 4 (21 days). Today is May 21 — Day 7 equivalent. Zero application code exists. The original D1-D7 (Phase 1 Foundation) was supposed to be COMPLETE by today. We must compress Phase 1 aggressively while maintaining quality standards from CLAUDE.md.

### What EXISTS vs What's NEEDED

| Layer                 | EXISTS                                                                                           | NEEDED (PRD + Audit)                                                                                              |
| --------------------- | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| **Project scaffold**  | ✅ Repo, CI, pre-commit, features.json, CLAUDE.md, PRD, sprint plan, ADRs 0001-0013, REJECTED.md | —                                                                                                                 |
| **atelier-core**      | `__init__.py` + `__version__.py` only                                                            | 11 Pydantic data contracts, 8-node DAG, PIP, 5 judges, 6 det gates, EvoDesign, Governor, task-aware model routing |
| **atelier-deploy**    | README only                                                                                      | Terraform, Dockerfiles, Cloud Run, OTel, model registry, sandbox configs, scrubber patterns                       |
| **atelier-eval**      | README only                                                                                      | WebGen-Bench harness, calibration golden set, `agents-cli eval`, DPO dataset builder                              |
| **atelier-dashboard** | README + package.json                                                                            | React+Vite calibration dashboard, project management UI                                                           |
| **atelier-action**    | action.yml stub                                                                                  | GitHub Action for CI integration                                                                                  |
| **Infrastructure**    | GCP project `i-for-ai` exists                                                                    | Terraform apply, Cloud Run services, Artifact Registry, BigQuery, KMS, Identity Platform                          |

### Critical Path Analysis

The features.json dependency chain means we MUST build in this order:

```
F0001a (worktree) → F0001b (init.sh) → F0002 (model registry) + F0003 (deps)
  → F0004 (BriefSpec) → F0009 (all data contracts)
  → F0010 (FastAPI skeleton) → F0011 (Docker + Cloud Run)
  → F0013-F0022 (8-node DAG: GateAgents + JudgeAgents)
  → F0023-F0030 (EvoDesign + ConsensusAgent)
  → F0031+ (Campaign Orchestrator, PIP, WRAI, etc.)
```

**Everything is serialized through F0001a → F0001b → F0003.** Until the worktree + venv + deps are in place, nothing else can start.

---

## Audit-Sourced Features (FA-series)

> [!IMPORTANT]
> The following **28 features** are derived from the [Autonomous Agent Audit & Checklist](file:///Users/danielmanzela/.gemini/antigravity-ide/brain/e9962ddd-ddea-4979-a1d2-fa00102a9019/autonomous_agent_audit_and_checklist.md) and supplement the existing 205 features in `features.json`. Each traces back to a specific audit section. These MUST be added to `features.json` as part of the sprint recovery.

### Phase 0 / Phase 1 Audit Features

| ID         | Name                                                                                                                                                                                              | Audit Source                 | Depends On | Phase |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- | ---------- | ----- |
| **FA-001** | Create `docker network create --internal sandbox_isolated_net` + `deploy/docker-compose.dev.yml` with shell-sandbox (cap_drop=ALL, read_only, no-new-privileges) and browser-sandbox (Playwright) | Audit §1 (C9, ADR 0003)      | F0001b     | P1    |
| **FA-002** | Create `config/scrubber-patterns.yaml` — 6 regex patterns (Google API Key, GitHub Token, SA Key, Generic Secret, JWT, Vertex Endpoint)                                                            | Audit §1 (PRD §15)           | F0001b     | P1    |
| **FA-003** | Stitch MCP integration via `MCPToolset(server_uri, auth_config=google_default)`                                                                                                                   | Audit §2 (C8, ADR 0010)      | F0003      | P1    |
| **FA-004** | GitHub MCP integration via `MCPToolset(server_uri=localhost:8003, bearer token)`                                                                                                                  | Audit §2 (C8)                | F0003      | P1    |
| **FA-005** | Create `agent_card.json` — A2A Agent Card with skills, protocols, auth spec                                                                                                                       | Audit §2 (C8, A2A)           | F0010      | P1    |
| **FA-006** | Create `config/otel-collector-config.yaml` — OTLP receivers (gRPC + HTTP), batch processor, Phoenix dev exporter + Google Cloud prod exporter, `gen_ai.system=atelier` attribute                  | Audit §3 (C10, ADR 0006)     | F0001b     | P1    |
| **FA-007** | OTel span attribute schema implementation — `ATELIER_SPAN_ATTRS` dict with 15 mandatory attributes per PRD §7.3                                                                                   | Audit §3 (C10, PRD §7.3)     | F0009      | P1    |
| **FA-008** | Create `consensus/` directory — `DESIGN_PRINCIPLES_APPLE.md`, `constitution-apple-grade/index.json`, `axis_weights_heuristic.yaml`, `research-trust.yaml`                                         | Audit §4 (C6 + C3, N6 CSC-D) | F0001b     | P1    |
| **FA-009** | Docker volume enforcement — consensus files mounted `read_only: true`, workspace mounted `read_only: false`                                                                                       | Audit §4 (C6)                | FA-001     | P1    |
| **FA-010** | Per-project workspace structure — `./workspace/.atelier/{checkpoints,trajectories}`                                                                                                               | Audit §4 (PRD §6.2)          | F0001b     | P1    |

### Phase 2 Audit Features (DPO Pipeline + Governor + Judges)

| ID         | Name                                                                                                                                                                                                                                                                                                           | Audit Source                        | Depends On   | Phase |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------- | ------------ | ----- |
| **FA-011** | `TrajectoryRecorder` class — records JSONL per PRD `TrajectoryRecord` schema; fields: trajectory_id, tenant/project/session/surface IDs, node_name, iteration, candidate_id, prompt, response, gate_outcomes, judge_votes, composite_score, cost_usd, user_signal                                              | Audit §5 (C4+C10)                   | F0009, F0050 | P2    |
| **FA-012** | `prepare_dpo_dataset.py` — groups by (surface_id, node_name, iteration), T2 chosen (≥0.7), T3 rejected (<0.5), MIN_MARGIN=0.15; outputs JSONL preference pairs                                                                                                                                                 | Audit §5 (C4+C10, G10 fix)          | FA-011       | P2    |
| **FA-013** | `submit_vertex_training.py` — **Path A**: `TuningJob.create()` for Gemini 2.5 Flash (DPO, managed). **Path B reference**: `CustomJob` for Gemma 4 with TRL+PEFT container (Phase 2 only)                                                                                                                       | Audit §5 + Part 6 (G2 fix, G3 fix)  | FA-012       | P2    |
| **FA-014** | DPO Training Container — `deploy/training/Dockerfile.dpo` with pytorch + transformers + peft + trl + accelerate + bitsandbytes                                                                                                                                                                                 | Audit §5 (Path B reference)         | FA-013       | P2    |
| **FA-015** | `MetacognitiveGovernor` class — MAPE-K loop with PRD §21 Failure Trichotomy: `FailureMode.FAIL_LOUD` (budget/security), `FAIL_SOFT` (tool errors/stall/loop), `SELF_HEAL` (429/503, max 3 retries). Methods: `_check_budget`, `_check_step_budget`, `_check_infinite_loop`, `_check_stall`, `should_self_heal` | Audit §6 (C7, G12 fix)              | F0009        | P2    |
| **FA-016** | `JUDGE_MODEL_CONFIG` — task-aware model routing dict: brand→Flash(vision), originality→2.5Pro(thinking), relevance→Flash+Grounding, accessibility→DetGate+FlashLite, visual_clarity→Flash+Embedding2                                                                                                           | Audit §7 (N3d, 2026 best practices) | F0029        | P2    |
| **FA-017** | Judge anti-bias rules implementation: (1) No family-self-preference guard, (2) CoT-before-score enforcement in JudgeVote, (3) Position swap for pairwise comparisons, (4) Gold set calibration pipeline (200-500 labels, Cohen's κ ≥ 0.7)                                                                      | Audit §7 (2026 best practices)      | FA-016       | P2    |
| **FA-018** | `AxisWeights` data contract + `compute_axis_weights()` — BriefSpec-conditional weighting per N15 MJG                                                                                                                                                                                                           | Audit §7, F0209-F0210               | F0009        | P2    |
| **FA-019** | `axis_weights_heuristic.yaml` — default weight presets per `visual_register × compliance_level × convergence_bar` matrix                                                                                                                                                                                       | Audit §7, F0209                     | FA-018       | P2    |
| **FA-020** | WRAI sub-stack — Vertex AI Search Grounding integration + domain trust scorer + 8 query templates + Findings Synthesizer (Gemini 3 Flash) + per-tenant 7-day cache + Model Armor                                                                                                                               | Audit Part 1 (C3, N14), F0203-F0208 | F0053        | P2    |
| **FA-021** | CSC-D constitution registry — `apple-grade.md` + `brutalist.md` + selection logic by `BriefSpec.visual_register`                                                                                                                                                                                               | Audit Part 1 (C6, N6), F0213-F0214  | FA-008       | P2    |
| **FA-022** | Hook `REJECTED.md` into N3e Fixer — when mutation pattern is in REJECTED.md, inject as negative constraint in Hebbian mutator; auto-populate from low-scoring trajectory steps                                                                                                                                 | Audit Part 1 (C5 alignment)         | F0041        | P2    |

### Phase 3 Audit Features (Competition + Polish)

| ID         | Name                                                                                                                                                                                                                                                       | Audit Source                            | Depends On         | Phase |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------- | ------------------ | ----- |
| **FA-023** | `agents-cli eval` integration — wire `atelier-eval/` to `uvx google-agents-cli eval run`                                                                                                                                                                   | Audit Part 2 (G7 fix)                   | F0180              | P3    |
| **FA-024** | `agents-cli deploy` integration — wire `atelier-deploy/` to `uvx google-agents-cli deploy`                                                                                                                                                                 | Audit Part 2 (G7 fix)                   | F0180              | P3    |
| **FA-025** | Agent Studio compatibility demo — import ADK code into Agent Studio for visual debugging; record 30-second clip for demo                                                                                                                                   | Audit Part 2 (Platform Features)        | FA-005             | P3    |
| **FA-026** | DevPost for Teams project page — text, screenshots, links, repo access instructions for internal Googler judges                                                                                                                                            | Audit Q&A (video transcript L264, L260) | —                  | P3    |
| **FA-027** | End-to-end pipeline verification script — automated test matching Audit §8: (1) Docker sandbox non-root + no-network, (2) OTel collector accepts traces, (3) Consensus read-only, (4) Trajectory recorder, (5) DPO dataset builder, (6) agents-cli version | Audit §8                                | FA-001 thru FA-012 | P3    |
| **FA-028** | Cost ceiling enforcement — Apigee AI Gateway per-tenant budget cap + Redis token-bucket surge protection per PRD §7.2                                                                                                                                      | Audit G17 fix                           | F0080              | P3    |

---

## Proposed Changes

### Phase 0: Sprint Recovery (Day 1 of execution — TODAY)

> Priority: **Unblock all downstream features** by completing the D1+D2 foundation in one session.

#### [NEW] Execute Sprint Plan Tasks 1.1-1.7 (features F0001a → F0005)

Follow the exact steps in [sprint plan](file:///Users/danielmanzela/Professional%20Profile/Atelier/docs/superpowers/plans/2026-05-14-atelier-sprint-plan.md) Tasks 1.1-1.7:

1. **Create phase/1 worktree** (F0001a) — Task 1.1
2. **Run init.sh** (F0001b) — Task 1.2
3. **Verify Vertex AI models** (F0002) — Task 1.3
4. **Pin dependencies** (F0003) — Task 1.4-1.5
5. **BriefSpec data contract** (F0004) — Task 1.6 (TDD)
6. **D1 checkpoint** (F0005) — Task 1.7

#### [NEW] Execute Sprint Plan Tasks 2.1-2.8 (features F0006 → F0012) + Audit FA-001 thru FA-010

Follow Tasks 2.1-2.8 for D2 PLUS the audit's Phase 1 items:

1. **Terraform skeleton** (F0006) — Task 2.1
1. **Cloud Run service** (F0007) — Task 2.1 continued
1. **terraform apply** (F0008) — Task 2.2
1. **All Pydantic data contracts** (F0009) — Task 2.3
1. **FastAPI skeleton + /health** (F0010) — Task 2.4
1. **Docker + Artifact Registry** (F0011) — Task 2.5
1. **ADK dispatch wrapper** (F0199) — audit addendum
1. **Sandbox + Docker Compose** (FA-001) — Audit §1
1. **Secret scrubber patterns** (FA-002) — Audit §1
1. **Stitch MCP integration** (FA-003) — Audit §2
1. **GitHub MCP integration** (FA-004) — Audit §2
1. **A2A Agent Card** (FA-005) — Audit §2
1. **OTel Collector config** (FA-006) — Audit §3
1. **OTel span attributes** (FA-007) — Audit §3
1. **Consensus directory** (FA-008) — Audit §4
1. **Docker volume enforcement** (FA-009) — Audit §4
1. **Per-project workspace** (FA-010) — Audit §4
1. **D2 checkpoint** (F0012) — Task 2.8

**Gate**: FastAPI `/health` responds on Cloud Run staging + Docker sandbox passes isolation checks + OTel collector accepts traces.

---

### Phase 1: Foundation Completion (Days 2-4 — D3-D7 compressed)

> Priority: **1-surface end-to-end pipeline working** by end of Day 4.

#### [NEW] 8-Node DAG Implementation (F0013 → F0052)

The 8-node atomic DAG is the core engine. Build in TDD order per sprint plan D3-D5:

| Node                          | Feature IDs | PRD Section | Audit Feature                                      | Test Count |
| ----------------------------- | ----------- | ----------- | -------------------------------------------------- | ---------- |
| N3a Generator                 | F0023-F0025 | §6.3 N3a    | —                                                  | 3          |
| N3b Copy Editor               | F0026-F0028 | §6.3 N3b    | —                                                  | 3          |
| N3c Det Gates (6)             | F0013-F0022 | §6.3 N3c    | —                                                  | 12         |
| N3d ConsensusAgent (5 judges) | F0029-F0040 | §6.3 N3d    | **FA-016** (model routing), **FA-017** (anti-bias) | 10         |
| N3e Fixer (Hebbian mutator)   | F0041-F0043 | §6.3 N3e    | **FA-022** (REJECTED.md hook)                      | 3          |
| N3f Convergence Oracle        | F0044-F0046 | §6.3 N3f    | —                                                  | 3          |
| N3g Side-Effect Executor      | F0047-F0049 | §6.3 N3g    | —                                                  | 3          |
| N3h Trajectory Recorder       | F0050-F0052 | §6.3 N3h    | **FA-011** (full schema)                           | 3          |

**Key correction from audit**: ConsensusAgent (N3d) uses **task-aware model routing** per Audit §7:

| Judge Axis         | Model                               | Mode             | Anti-Bias Rule                            |
| ------------------ | ----------------------------------- | ---------------- | ----------------------------------------- |
| Brand (D)          | Gemini 3 Flash                      | vision           | CoT before score; position swap           |
| Originality (O)    | Gemini 2.5 Pro                      | thinking         | CoT before score; 200+ gold labels        |
| Relevance (R)      | Gemini 3 Flash + Grounding          | grounded         | CoT before score; BriefSpec fact-check    |
| Accessibility (A)  | Det gate + Flash-Lite               | supplementary    | Det gate authoritative; model adds nuance |
| Visual-clarity (V) | Gemini 3 Flash + Gemini Embedding 2 | vision+embedding | CoT + cosine similarity threshold         |

#### [NEW] PIP (Pre-Generation Intake Protocol) (F0053 → F0065)

- Intent classifier
- 12 intake questions (adaptive)
- BriefSpec builder
- User approval flow
- PADI (Project-Agnostic Descriptor Inference) — **N4, Atelier-original**

#### [NEW] OTel + Cloud Trace Integration (F0070 → F0078 + FA-006, FA-007)

- OTel Collector config with 15 mandatory span attributes (FA-006, FA-007)
- Cloud Trace exporter (production)
- Phoenix exporter (dev-only, per ADR 0006, Audit G8 correction)
- BigQuery trajectory sink

**Phase 1 Gate**: 1 surface end-to-end (brief → generate → judge → converge → output) on `pipeline-observatory/index.html` test brief.

---

### Phase 2: 10× Mechanisms (Days 5-9 — W2 compressed)

> Priority: **Multi-surface campaigns + EvoDesign + DPO pipeline proof**.

#### [NEW] Campaign Orchestrator (F0080 → F0095)

- RLRD outer loop (N12)
- Multi-surface dispatching
- Budget enforcement — **FA-028**: Apigee AI Gateway per-tenant cap + Redis token-bucket (Audit G17)
- Panic/resume primitives (PRD §22)

#### [NEW] Metacognitive Governor (FA-015 — Audit §6)

- `MetacognitiveGovernor` class with PRD §21 Failure Trichotomy (Audit G12 fix)
- MAPE-K loop: Monitor → Analyze → Plan → Execute → Knowledge
- `_check_budget` (fail-loud), `_check_step_budget` (fail-soft), `_check_infinite_loop` (fail-soft), `_check_stall` (fail-soft), `should_self_heal` (bounded retries)
- Governor config: `max_consecutive_identical_calls=3`, `max_total_steps=50`, `max_cost_usd=5.0`, `self_heal_max_retries=3`

#### [NEW] EvoDesign (N5) (F0096 → F0110)

- K=6 parallel candidate generation via `ADK CoordinatorAgent + ParallelAgent` (Audit C2 alignment)
- Selection + Crossover + Mutation
- Hebbian mutator via `adk optimize`/GEPA (Audit G13 fix)
- **FA-022**: Hook `REJECTED.md` into Fixer as negative constraints

#### [NEW] WRAI (N14) — Web-Research-Augmented Intake (FA-020, F0203 → F0208)

- Vertex AI Search Grounding integration (Audit G15 fix)
- Domain trust scorer + `research-trust.yaml` whitelist/denylist
- 8 query templates
- Findings Synthesizer (Gemini 3 Flash)
- Per-tenant 7-day cache
- Model Armor integration

#### [NEW] DPO Flywheel Proof (FA-011 → FA-014, F0120 → F0130)

- **FA-011**: Trajectory recorder with full PRD schema (BigQuery sink)
- **FA-012**: DPO dataset builder with corrected logic (Audit G10 fix): group by (surface_id, node_name, iteration), T2 chosen (≥0.7), T3 rejected (<0.5), MIN_MARGIN=0.15
- **FA-013**: **Path A** (MVP): Managed `TuningJob.create()` for Gemini 2.5 Flash (Audit Part 6 recommendation). **Path B** (reference): `CustomJob` for Gemma 4 with TRL+PEFT
- **FA-014**: DPO Training Container (`Dockerfile.dpo`) — pytorch + transformers + peft + trl + accelerate
- A/B eval against baseline before LoRA promotion — auto-register only if eval improves ≥2%

#### [NEW] Axis Weighting (N15) + Constitution (N6) (FA-018 → FA-021, F0209 → F0214)

- **FA-018**: `AxisWeights` data contract + `compute_axis_weights()` — BriefSpec-conditional
- **FA-019**: `axis_weights_heuristic.yaml` — presets per `visual_register × compliance_level × convergence_bar`
- **FA-021**: CSC-D constitution registry — `apple-grade.md` + `brutalist.md` + selection logic
- 20 calibration runs across visual_register × convergence_bar matrix (F0211-F0212)

#### [NEW] Memory Namespace Isolation (Audit C3 alignment)

- Enforce `tenant_id` + `project_id` partition keys at Memory Bank + Firestore + Vector Search
- IAM Conditions for session-level access control
- Vertex Memory Bank for cross-session memory; Firestore for hot state

**Phase 2 Gate**: 12-surface autonomous campaign. WebGen-Bench ≥51 on 50-task subset. Governor handles at least 1 fail-soft + 1 self-heal scenario in test suite.

---

### Phase 3: Production Polish + Submission (Days 10-14 — W3)

> Priority: **All 15 Novel Contributions evidenced. Submission package complete.**

#### [NEW] Calibration Dashboard (N8) (F0140 → F0150)

- React+Vite dashboard at `calibration.atelier.dev`
- Public judge calibration transparency — gold set agreement scores per axis
- Golden set refresh pipeline (200-500 human-labeled examples, Cohen's κ ≥ 0.7 target)

#### [NEW] Submission Package (F0160 → F0175 + FA-026)

- 4-min demo video (vertical + horizontal)
- 2-min backup + 60-sec elevator pitch
- Pre-recorded segments for Stitch MCP rate-limit resilience (Audit Risk: "Stitch MCP rate-limited")
- **FA-026**: DevPost for Teams project page — text, screenshots, repo access for **internal Googler judges** (Audit Q&A)
- README polish with all 15 N-contributions linked to code/demo evidence
- arXiv preprint draft
- Twitter thread (12 tweets)

#### [NEW] `agents-cli` Integration (FA-023, FA-024, F0180 → F0185)

- **FA-023**: `agents-cli eval` wired to `atelier-eval/`
- **FA-024**: `agents-cli deploy` wired to Cloud Run
- **FA-025**: Agent Studio compatibility demo — import into Agent Studio visual debugger; 30-second recording for demo
- A2A Agent Card deployed

#### [NEW] Security Hardening (F0190 → F0198 + FA-001, FA-002, FA-009)

- FA-001: Docker sandbox verified (cap_drop=ALL, network=none, non-root, no-new-privileges)
- FA-002: Secret scrubber patterns active
- FA-009: Consensus files verified read-only in container
- Identity Platform tenant configuration (Audit C6 alignment)
- **Audit G4 correction**: macOS uses Docker built-in isolation; Cloud Run (Linux) gets gVisor automatically

#### [NEW] End-to-End Pipeline Verification (FA-027 — Audit §8)

Automated verification script matching Audit §8 exactly:

```bash
# 1. Verify Docker sandbox
docker compose -f deploy/docker-compose.dev.yml up -d
docker exec shell-sandbox whoami  # Should NOT be root
docker exec shell-sandbox ping google.com  # Should FAIL (no network)

# 2. Verify OTel collector
curl -s http://localhost:4318/v1/traces  # Should accept POST

# 3. Verify consensus file is read-only
docker exec shell-sandbox touch /consensus/test.txt  # Should FAIL

# 4. Run trajectory recorder test
python -c "from atelier.flywheel.trajectory_recorder import TrajectoryRecorder; ..."

# 5. Run DPO dataset builder test
python scripts/prepare_dpo_dataset.py

# 6. Verify agents-cli setup
uvx google-agents-cli --version
```

#### [NEW] Cost Ceiling Enforcement (FA-028 — Audit G17)

- Apigee AI Gateway per-tenant budget cap
- Redis token-bucket surge protection (PRD §7.2)
- Daily cost ledger monitoring (target cache-hit-rate ≥85%)

**Phase 3 Gate**: All 15 N-contributions evidenced. E2E verification script passes. G4S submission filed Jun 3 noon.

---

## 17 Audit Gap Resolutions — Implementation Mapping

Every gap from the audit preamble is now mapped to a concrete implementation step:

| Gap                              | Resolution                                                                              | Feature ID                |
| -------------------------------- | --------------------------------------------------------------------------------------- | ------------------------- |
| G1 (Wrong base model)            | Use `google/gemma-4-26b-a4b-it` in Path B; Gemini 2.5 Flash in Path A                   | FA-013                    |
| G2 (Wrong Tuning API)            | Path A: `TuningJob.create()` (Gemini). Path B: `CustomJob` (Gemma 4)                    | FA-013                    |
| G3 (LoRA blocked)                | Mitigated: MVP uses managed Gemini 2.5 Flash tuning; Forensic Runbook is reference-only | FA-013, Part 6            |
| G4 (gVisor on macOS)             | Docker built-in isolation locally; Cloud Run gVisor automatically                       | FA-001                    |
| G5 (Missing judging criteria)    | All 4 criteria (Tech 30%, Biz 30%, Innovation 20%, Demo 20%) mapped to features         | Competition Scoring table |
| G6 (Missing competition tracks)  | Track 1: Build confirmed. One track only per video L264                                 | Q&A section               |
| G7 (Missing agents-cli)          | FA-023 + FA-024: `eval` + `deploy` integration                                          | FA-023, FA-024            |
| G8 (Phoenix in prod)             | Phoenix dev-only; Cloud Trace + Vertex AI Studio Tracing in production                  | FA-006                    |
| G9 (Wrong GCP project)           | Use Atelier's own project (NOT `n26-adk-demo`)                                          | Open Question Q1          |
| G10 (DPO logic flawed)           | Corrected: group by decision point, compare DIFFERENT candidates, margin ≥0.15          | FA-012                    |
| G11 (Missing N1-N15 coverage)    | 5 unmapped Novel Contributions (N4, N7, N8, N10, N11) documented as Atelier-original    | Audit Part 1              |
| G12 (Missing Failure Trichotomy) | `MetacognitiveGovernor` with fail-loud/fail-soft/self-heal                              | FA-015                    |
| G13 (Missing `adk optimize`)     | N3e Fixer uses `adk optimize`/GEPA for prompt mutation                                  | F0041-F0043               |
| G14 (Missing D-O-R-A-V)          | Full 5-axis rubric with task-aware model routing                                        | FA-016, FA-017            |
| G15 (Missing WRAI)               | Full WRAI sub-stack with Vertex AI Search Grounding                                     | FA-020                    |
| G16 (Location mismatch)          | Configurable region via model-registry.yaml                                             | F0002                     |
| G17 (Missing cost ceiling)       | Apigee AI Gateway + Redis token-bucket                                                  | FA-028                    |

---

## Execution Protocol for Long-Running Session

> [!IMPORTANT]
> The coding agent executing this plan MUST follow these protocols from [CLAUDE.md](file:///Users/danielmanzela/Professional%20Profile/Atelier/CLAUDE.md):

### 1. Session Start Ritual (90 seconds)

```bash
cd "/Users/danielmanzela/Professional Profile/Atelier"
cat docs/sprint/STATUS.md
cat docs/sprint/BLOCKERS.md
tail -50 docs/sprint/CHECKPOINTS.md
tail -20 REJECTED.md
tail -7 docs/sprint/COST_LEDGER.md
cat features.json | python3 -c "import json,sys; d=json.load(sys.stdin); print([f['id'] for f in d['features'] if not f.get('passes')][:5])"
git log --oneline -10
git status
```

### 2. Feature Execution Loop

For EACH feature:

1. Read the feature spec from `features.json` (or FA-series from this plan)
2. Read the corresponding task in the sprint plan (or audit checklist)
3. Write FAILING test first (TDD)
4. Implement until test passes
5. Run `mypy --strict` + `pytest -x` + `python -c "import ..."`
6. Mark feature as `passes: true` in `features.json`
7. Commit with Conventional Commits format

### 3. Checkpoint Cadence

After every ~5 features or ~2 hours:

- Update `docs/sprint/CHECKPOINTS.md`
- Update `docs/sprint/COST_LEDGER.md`
- Push to `phase/1` branch
- Verify CI status

### 4. Invariants (NEVER violate)

From CLAUDE.md + Audit corrections:

- No `--no-verify`
- No silent `except` blocks (Audit: every error → fail-loud/fail-soft/self-heal)
- No undocumented commits
- No new deps without lockfile pin (no slopsquatting)
- No spec changes without ADR
- No Phoenix in production (ADR 0006, Audit G8)
- No `n26-adk-demo` project ID (Audit G9)
- No single-model-for-all-judges (Audit §7: task-aware routing)
- No DPO pairs from same-step comparison (Audit G10: different candidates required)
- No gVisor commands on macOS (Audit G4)

---

## Competition Scoring Optimization

Map every implementation decision to the 4 judging criteria:

| Criterion                    | Weight  | What to demonstrate                                                                                                                                   | Key Audit Features                                         |
| ---------------------------- | ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| **Technical Implementation** | **30%** | 8-node DAG, task-aware model routing (FA-016), OTel + Cloud Trace (FA-006/007), DPO flywheel (FA-011-014), ADK 2.0 graph workflows, Governor (FA-015) | FA-001 thru FA-022                                         |
| **Business Case**            | **30%** | $20/mo Pro tier, <$0.50 per session, 10× thesis with 7 axes, cost ceiling enforcement (FA-028), live demo with real output                            | FA-028, competition scoring                                |
| **Innovation & Creativity**  | **20%** | 15 Novel Contributions, task-aware model routing (2026 best practice), first A2UI-native agent, public calibration dashboard, Convergence Spec RFC    | FA-016/017 (model routing is novel in competition context) |
| **Demo & Presentation**      | **20%** | Pre-recorded 4-min demo, Agent Studio compatibility (FA-025), DevPost page (FA-026), agents-cli integration (FA-023/024)                              | FA-023 thru FA-027                                         |

---

## Verification Plan

### Automated Tests

```bash
# Phase 1 gate
pytest tests/unit/ -v --tb=short
pytest tests/integration/ -v --tb=short -k "single_surface"

# Phase 2 gate
pytest tests/eval/ --baseline=HEAD~1
python -m atelier.eval.webgen_bench --tasks=50 --threshold=51

# Phase 3 gate (includes Audit §8 E2E verification)
pytest tests/ -v  # Full suite
bash scripts/verify_pipeline_e2e.sh  # FA-027
agents-cli eval run  # FA-023
```

### Manual Verification

- [ ] 1-surface end-to-end on test brief (Phase 1)
- [ ] Docker sandbox isolation verified: non-root, no-network, read-only consensus (Phase 1)
- [ ] OTel traces visible in Cloud Trace (Phase 1) and Phoenix (dev only)
- [ ] 12-surface campaign completes autonomously (Phase 2)
- [ ] Governor handles fail-soft (stall) + self-heal (429) in test suite (Phase 2)
- [ ] DPO dataset builder produces valid preference pairs from trajectories (Phase 2)
- [ ] Demo video records without issues (Phase 3)
- [ ] DevPost submission page complete with repo access instructions (Phase 3)
- [ ] All 15 N-contributions have code evidence linked in README (Phase 3)

---

## Open Questions

> [!IMPORTANT]
> **Q1**: The GCP project is `i-for-ai`. Is this the correct project for Atelier's production deployment, or should we create a dedicated `atelier-*` project? The competition credits are for GCP only. **(Audit G9 flags this — `n26-adk-demo` is wrong; what IS right?)**

> [!IMPORTANT]
> **Q2**: The sprint plan references `agent-dag-pipeline` as a lockfile-pinned dependency. Is this package published on PyPI, or do we need to install from the GitHub VCS reference (`git+https://github.com/Manzela/agent-dag-pipeline.git@v3.0.0`)?

> [!WARNING]
> **Q3**: Given we are 6 days behind, should we skip Terraform (F0006-F0008) and deploy directly via `gcloud run deploy` / `agents-cli deploy` to save time? Terraform is valuable but may not be worth the setup cost for a competition deadline.

> [!NOTE]
> **Q4**: The audit recommends Gemini 2.5 Pro for the Originality judge (FA-016). Gemini 2.5 Pro is listed as "Legacy/Retiring" with deprecation no earlier than Oct 16, 2026. Should we use Gemini 3 Pro instead if available, or stick with 2.5 Pro since it's still accessible and has the deepest reasoning?
