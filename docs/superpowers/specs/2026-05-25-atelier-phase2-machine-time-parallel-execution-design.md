# Atelier Phase 2 — Machine-Time Parallel Execution Design

**Date**: 2026-05-25
**Author**: Claude (orchestrator) with Daniel (decision authority)
**Status**: Proposed — awaiting Daniel sign-off
**Supersedes (partial)**: [`2026-05-25-atelier-days-11-21-parallel-execution-design.md`](2026-05-25-atelier-days-11-21-parallel-execution-design.md) §3 day-by-day cadence (replaces calendar-day plan with machine-time fan-out)
**Inputs (4 audits + kickoff)**:

- Phase 2 Architecture Synthesis (subagent `af5de1056046a6475`)
- Reliability Audit (subagent `a9b9cb61fa2aa22f5`)
- GEAP Compliance Audit (subagent `a30170af91de8163b`)
- Competition Strategy Audit (subagent `a7fce5962e7213016`)
- Kickoff transcript (`docs/research/kickoff-video-transcript.txt`) + PDF (`docs/research/kickoff-pdf-transcript.txt`)

---

## 1. Goal (one sentence)

Ship a judge-hittable demo at `atelier.autonomous-agent.dev` that replays a real trajectory (Cloud Trace + Memory Bank recall + AND-Gate scorecard) backed by `bench.atelier.autonomous-agent.dev` showing ADK's 11 first-class eval criteria on a held-out set — within ~24 wall-clock hours of plan acceptance, via maximum-parallel Antigravity delegation.

## 2. Architecture (2-3 sentences)

Claude (Opus 4.7 MAX) writes three Protocol/contract files first (~30 min sequential work), then runs in parallel with Antigravity (Opus 4.6 Thinking + Gemini 3.1 Pro) which fans out to 13 mechanical-scaffolding tasks behind those contracts. Claude simultaneously executes the 3 novel SOTA items it owns (B7, DPO end-to-end, B6 router) and reviews each Antigravity PR as it lands (notification-driven, no polling). All work converges on `phase/2` after individual PR review; `v0.2.0-phase-2-gate` tag triggers when 13/13 Antigravity PRs + 3/3 Claude PRs are merged + full eval-delta is clean.

## 3. Tech Stack

- **Models**: Claude Opus 4.7 MAX (orchestrator + novel SOTA), Opus 4.6 Thinking (Antigravity high-judgment tasks), Gemini 3.1 Pro Preview (Antigravity mechanical tasks)
- **Platform**: Google Cloud (`atelier-build-2026` project), Cloud Run staging, BigQuery sessions, Vertex AI Memory Bank, Cloud Trace + OTel
- **Languages**: Python 3.11 strict-typed, Terraform, HTML/JS (dashboards, pipeline-observatory pattern)
- **CI/CD**: GitHub Actions, pre-commit hooks, `mypy --strict`, `pytest -x`, conventional commits, branch protection on `phase/2`

## 4. Three Protocol contracts (Claude writes FIRST, ~30 min sequential)

These three files must exist on `phase/2` before any Antigravity sub-agent starts. They lock the interface so 13 parallel tasks cannot architecturally drift.

### 4.1 `atelier-core/src/atelier/models/safety.py` — `SafetyDefaults`

Frozen dataclass + helper function: `default_safety_settings() → list[google.genai.types.SafetySetting]`. Applied at every `LlmAgent(...)` call-site to close GEAP **B5** (no `safety_settings` on any `LlmAgent`). Categories: HARASSMENT, HATE_SPEECH, SEXUALLY_EXPLICIT, DANGEROUS_CONTENT all at `BLOCK_MEDIUM_AND_ABOVE`. Frozen via `Final[...]`; change requires ADR amendment.

### 4.2 `atelier-core/src/atelier/memory/session_protocol.py` — `SessionBackend` Protocol

Replaces `InMemoryRunner` (GEAP **B4**). Two async methods: `create_session(user_id, session_id) → Session` and `resume_session(user_id, session_id) → Session | None`. BigQuery-backed implementation goes in `atelier-core/src/atelier/memory/bigquery_session.py` (Antigravity-implemented on D15 PM). Critically: Protocol must accept ADK 2.x `Session` type so the `VertexAiSessionService` (recommended by GEAP audit) drops in without runner changes.

### 4.3 `docs/dashboards/bench-schema.json` — `BenchDashboardSchema`

JSON shape for `bench.atelier.autonomous-agent.dev` eval dashboard. Keys: `run_id, timestamp, calibration_pass_rate, adversarial_pass_rate, adk_criteria_scores: {tool_trajectory_avg_score, multi_turn_trajectory_quality_v1, rubric_based_*}, per_judge_calibration: {brand, copy, motion, token, coherence}, dpo_promotion_events[]`. Schema versioned (`schema_version: "1.0"`); dashboard renderer + bench publisher both validate against this file.

## 5. Antigravity fan-out (13 tasks, parallel, ~3-5 hours wall clock)

Antigravity orchestrates these across 2-3 concurrent sub-agents (concurrency choice belongs to Daniel + Antigravity's runtime). Each task ships as one PR into `phase/2-antigravity-<task-id>` branch, then merges to `phase/2` after Claude review-and-DONE-token.

| Task ID | Title                                                                                                                                                                                                                                                                                                                                                                                   | Surface                                                                                                                                                           | Model             | Est. machine-time |
| ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- | ----------------- |
| AG-01   | **B1** project_id → `GOOGLE_CLOUD_PROJECT` env var, drop `i-for-ai` defaults                                                                                                                                                                                                                                                                                                            | `atelier-deploy/terraform/main.tf`, `cloud_run.tf`                                                                                                                | Gemini 3.1 Pro    | 30m               |
| AG-02   | **B2** TF `containers{}` block dedup (validate via `terraform plan` clean)                                                                                                                                                                                                                                                                                                              | `atelier-deploy/terraform/cloud_run.tf`                                                                                                                           | Gemini 3.1 Pro    | 20m               |
| AG-03   | **B3** drop `allUsers` IAM binding → IAP-protected ingress                                                                                                                                                                                                                                                                                                                              | `atelier-deploy/terraform/cloud_run_iam.tf`, new `iap.tf`                                                                                                         | Opus 4.6 Thinking | 1h                |
| AG-04   | **B5 sweep**: apply `default_safety_settings()` to every `LlmAgent(...)` site                                                                                                                                                                                                                                                                                                           | `intake/brief_parser.py`, `orchestrator/generator_ensemble.py`, `nodes/llm_judge.py`, `nodes/consensus.py`, `nodes/anti_bias.py`, `nodes/trajectory.py` (6 sites) | Gemini 3.1 Pro    | 45m               |
| AG-05   | **FIX-1** wire `CostGovernor.check_budget()` into `AtelierRunner.run()` pre/post N3a + fail-loud at $5K MAX cap                                                                                                                                                                                                                                                                         | `orchestrator/runner.py`, `orchestrator/governor.py`                                                                                                              | Opus 4.6 Thinking | 1.5h              |
| AG-06   | **FIX-3** Stitch acknowledged-degradation: surface degraded mode in `BriefSpec.metadata`, emit `structlog.warning` with redacted error, propagate to UI via session metadata                                                                                                                                                                                                            | `integrations/stitch_mcp.py`, `orchestrator/generator_ensemble.py`                                                                                                | Opus 4.6 Thinking | 1h                |
| AG-07   | **B4** `bigquery_session.py` implements `SessionBackend` Protocol; swap `InMemoryRunner` → `VertexAiSessionService` in `runner.py`                                                                                                                                                                                                                                                      | `memory/bigquery_session.py` (new), `orchestrator/runner.py`                                                                                                      | Opus 4.6 Thinking | 2h                |
| AG-08   | **B8** rewrite `runner.py` event loop to use ADK 2.0 `Event` API (`event.is_final_response()`, `event.content.parts`) — drop dead-code `event.type == "message"` filter                                                                                                                                                                                                                 | `orchestrator/runner.py`                                                                                                                                          | Opus 4.6 Thinking | 1h                |
| AG-09   | **N14 WRAI scaffold**: `intake/web_research.py` fetches top-N web refs scored by domain trust lattice per ADR 0011                                                                                                                                                                                                                                                                      | `intake/web_research.py` (new), `intake/brief_parser.py`                                                                                                          | Opus 4.6 Thinking | 2h                |
| AG-10   | **FIX-2** PII scrubber runtime path verified on every span export                                                                                                                                                                                                                                                                                                                       | `observability/scrubber.py` (new or expand), `observability/spans.py`                                                                                             | Opus 4.6 Thinking | 1.5h              |
| AG-11   | DNS + wildcard cert for `*.atelier.autonomous-agent.dev` (Cloud DNS or Cloudflare)                                                                                                                                                                                                                                                                                                      | `atelier-deploy/terraform/dns.tf` (new)                                                                                                                           | Gemini 3.1 Pro    | 30m               |
| AG-12   | `bench.atelier.autonomous-agent.dev` static dashboard (pipeline-observatory pattern) reading from `bench-schema.json`                                                                                                                                                                                                                                                                   | `docs/dashboards/bench/` (new dir)                                                                                                                                | Gemini 3.1 Pro    | 2h                |
| AG-13   | `atelier.autonomous-agent.dev` trajectory replay UI: reads BQ session by `session_id` → renders Cloud Trace span graph + Memory Bank recalls + AND-Gate scorecard. New endpoint `GET /v1/replay/{session_id} → SessionReplayPayload` in `api/replay.py`; new fastapi router registered in `api/app.py`. Static frontend in `docs/dashboards/replay/index.html` consuming this endpoint. | `docs/dashboards/replay/` (new dir) + `api/replay.py` (new) + `api/app.py` (modify)                                                                               | Opus 4.6 Thinking | 3h                |

**Antigravity total wall-clock (with 3-way concurrency)**: ~5h (longest task AG-13 sits on critical path after AG-07 finishes BQ session backend).

## 6. Claude parallel work (3 novel SOTA items + reviews + polish, ~3-5h)

Claude runs concurrently with Antigravity. Items here are exclusively Claude-owned surfaces or judge-facing polish that needs Opus 4.7 MAX taste.

| Task ID         | Title                                                                                                                                                                                                                                                                                                                                              | Surface                                                                               | Est. machine-time                                   |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | --------------------------------------------------- |
| CL-01           | **Protocol contracts** (§4 above) — written FIRST, blocks AG-04/AG-07/AG-12                                                                                                                                                                                                                                                                        | `models/safety.py`, `memory/session_protocol.py`, `docs/dashboards/bench-schema.json` | 30m                                                 |
| CL-02           | **B7** real `_call_llm` in DPO pair miner (replace stub with `google.genai.Client.models.generate_content`)                                                                                                                                                                                                                                        | `optimize/dpo_tuning_job.py`, `optimize/generator_tuner.py`                           | 1.5h                                                |
| CL-03           | **DPO κ-promotion end-to-end run** on whatever calibration seed exists (see CL-08) → produces real promoted adapter + before/after artifact for demo. **Blocked by CL-08.**                                                                                                                                                                        | `optimize/`, calibration data                                                         | 2h (mostly wall-clock waiting on Vertex tuning job) |
| CL-08           | **Calibration seed dataset** (small, honest, shippable): ~20-30 tasks derived from PRD §22 examples + ~10 hand-curated adversarial cases, written to `atelier-eval/datasets/calibration-seed-v0.jsonl`. **NOT a full 100-task golden set** — that is post-submission work tracked as CL-09 stretch. The spec is explicit about this limited scope. | `atelier-eval/datasets/` (new)                                                        | 1.5h                                                |
| CL-09 (stretch) | Expand calibration to full 100-task golden set + 50-task adversarial held-out                                                                                                                                                                                                                                                                      | `atelier-eval/datasets/`                                                              | 4h+ (likely post-submission)                        |
| CL-04           | **B6** ModelRegistry routing wired into `router/v1_bandit.py` (router consults registry per ADR 0014)                                                                                                                                                                                                                                              | `router/v1_bandit.py`, `router/protocol.py`                                           | 1h                                                  |
| CL-05           | **Optimize-pillar README framing**: position DPO flywheel as concrete "Observe → Simulate → Verify" loop per Addy's kickoff language                                                                                                                                                                                                               | `README.md` + `docs/architecture/optimize-pillar.md` (new)                            | 30m                                                 |
| CL-06           | **Govern-pillar README mapping**: explicit cite of Registry / Identity / Gateway / Policy / Security / Audit surfaces with config snippets                                                                                                                                                                                                         | `README.md` + `docs/architecture/govern-pillar.md` (new)                              | 30m                                                 |
| CL-07           | **PR review pass** for each Antigravity PR as it lands (notification-driven; budget ~15min/PR × 13 = ~3h interleaved with other work)                                                                                                                                                                                                              | All AG-\* PRs                                                                         | 3h interleaved                                      |

**Claude total wall-clock**: ~6h interleaved, ~4h on critical path (CL-01 → CL-02 → CL-03 + reviews fan in).

## 7. Stretch items (executed if main fan completes < 8h wall-clock)

| Task ID | Title                                                                                                                      | Surface                                                    | Model                           | Est.                         |
| ------- | -------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- | ------------------------------- | ---------------------------- |
| ST-01   | `agents-cli scaffold` round-trip — verify Atelier-shaped project scaffolds cleanly from `agents-cli` alpha; cite in README | `agents-cli` install + new `examples/agents-cli-scaffold/` | Gemini 3.1 Pro (Antigravity)    | 1h                           |
| ST-02   | Agent Studio export round-trip demo — confirm our ADK DAG round-trips through Agent Studio import (screenshot for DevPost) | `examples/agent-studio-export/`                            | Opus 4.6 Thinking (Antigravity) | 1h                           |
| ST-03   | Designer testimonial recording outreach automation                                                                         | Manual (Daniel)                                            | —                               | 30m + async wait             |
| CL-09   | Expand calibration to full 100-task golden + 50-task adversarial (deferred from CL-08 scope)                               | `atelier-eval/datasets/`                                   | Opus 4.7 MAX (Claude)           | 4h+ (likely post-submission) |

## 8. Convergence point — `v0.2.0-phase-2-gate`

Tag triggers when:

1. **All 13 AG-\* PRs** merged to `phase/2` with Claude review-and-DONE-token
2. **All 4 CL-02 through CL-06 surfaces** committed
3. **CL-03** produces ≥1 real DPO promotion event recorded in BigQuery **OR** a documented attempted Vertex tuning run with reproducible failure mode + §9 fallback artifact (synthetic-but-realistic before/after using D11 trial data + transparent disclosure in demo)
4. **`atelier.autonomous-agent.dev`** + **`bench.atelier.autonomous-agent.dev`** serving HTTP 200 on golden seed brief
5. **Full eval-delta** (`pytest tests/eval/ --baseline=HEAD~1`) clean — no regression
6. **`mypy --strict`**, **`pytest -x`**, **pre-commit** all green
7. **CHECKPOINTS.md** updated; **STATUS.md** updated; **COST_LEDGER.md** updated (verify cache-hit-rate ≥85%)

## 9. Failure handling

Per CLAUDE.md trichotomy:

- **AG-\* PR fails Claude review** → REJECT comment with specific findings; Antigravity rev-and-resubmit (max 3 rejection cycles per ADR Anti-Premature-Completion); 3rd rejection escalates to Daniel
- **CL-03 DPO tuning job fails on Vertex** → fail-soft: capture failure mode, record in `BLOCKERS.md`, ship demo with synthetic-but-realistic before/after artifact + transparent disclosure ("DPO promotion event from D11 trial run, full Vertex production run completed post-submission")
- **DNS + cert (AG-11) blocked by registrar latency** → fall back to `atelier-staging.run.app` direct URL + redirect plan recorded as TODO

## 10. What this design does NOT cover

- The 4-min demo video itself (Daniel produces outside Claude Code scope per prior directive)
- DevPost final submission UI walkthrough (Daniel does at D24-D25)
- Cloud Marketplace listing (out-of-scope; cited in README as "stretch post-submission")
- Phase 3 production polish (separate spec post-v0.2.0-phase-2-gate)

## 11. Open trade-offs requiring no further input (decided)

| Trade-off                              | Decision                                                              | Authority               |
| -------------------------------------- | --------------------------------------------------------------------- | ----------------------- |
| Strategy A vs B vs C parallelization   | **Hybrid C+B**: max delegation + Protocol-first contracts             | Daniel 2026-05-25       |
| Cadence: per-day vs per-task PR merges | **Per-task** in machine-time (notification-driven Claude review)      | Daniel 2026-05-25       |
| Domain                                 | `atelier.autonomous-agent.dev` + `bench.` + `calibration.` subdomains | Daniel 2026-05-25       |
| Single-track submission                | **Build track only** (kickoff L264 enforces)                          | Kickoff                 |
| Submission target                      | D21 noon internal (Wed 2026-06-03), Jun 5 absolute backstop           | Phase 2 Synthesis audit |

## 12. Acceptance criteria (Reviewer DONE-token requirements)

For Reviewer subagent to emit DONE on the full Phase 2 gate:

- [ ] All §4 Protocol contracts exist, are `mypy --strict` clean, and are imported by their consumers
- [ ] All §5 AG-\* PRs merged and tagged with Claude `Reviewed-by: claude-orchestrator-opus-4-7 DONE`
- [ ] All §6 CL-\* tasks complete with eval-delta clean
- [ ] §8 convergence-point checklist 7/7 green
- [ ] No new entries in `BLOCKERS.md` since plan acceptance
- [ ] `CHANGELOG.md` entry for `v0.2.0-phase-2-gate` published

---

**Approval gate**: Daniel must explicitly approve this spec before Claude invokes `writing-plans` skill to produce the executable implementation plan.
