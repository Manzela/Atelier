# Competition Alignment Forensic Audit
**Scope**: Atelier code vs. Gemini Enterprise Agent Platform (16+ services)
**Date**: 2026-05-28
**Worktree**: `phase2-consensus-agent`
**Method**: Code-only — `agent_card.json`, `agent.json`, READMEs, and ADRs are evidence of *intent*, not of *implementation*. Status columns below grade what the Python and Terraform actually do.

---

## Service Coverage Matrix

| Pillar | Service | Status | Evidence (file:line) | Effort to Lift |
|---|---|---|---|---|
| **Build** | **ADK 2.0** | ✅ | `orchestrator/runner.py:33` (Runner), `orchestrator/generator_ensemble.py:16-18` (LlmAgent + ParallelAgent), `intake/brief_parser.py:6` (LlmAgent), `memory/bigquery_session.py:29-34` (BaseSessionService subclass), `examples/agents-cli-scaffold/agent.py:8` | — |
| **Build** | **Gemini API** (via google-genai client) | ✅ | `intake/web_research.py:331-335` (`genai.Client(vertexai=True, ...)`), `optimize/dpo_tuning_job.py:25-26,59`, `nodes/llm_judge.py:776-779` (`vertexai.generative_models`), `nodes/llm_judge.py:874` (`model.generate_content`) | — |
| **Build** | **Model Garden** | ⚠️ | `models/model_registry.py:84,93,104,125,134,145,155` — 7 ModelSpec entries hard-code public Gemini IDs (`gemini-2.5-flash-preview-05-20`, `gemini-2.5-pro-preview-05-06`); no `publishers/google/models/...` resource references or Model Garden deploy. Only one indirect reference in `tests/unit/test_router_protocol.py:105`. | 1d (replace bare IDs with full publisher paths + Model Garden deploy step) |
| **Build** | **MCP** | ✅ | `integrations/stitch_mcp.py:29-30,322-326` (real `McpToolset` + `SseConnectionParams` to `stitch.googleapis.com/mcp`), `integrations/github_mcp.py` (hand-rolled httpx — see Competing Implementations below) | — |
| **Build** | **A2A** | ⚠️ | `agent_card.json` declares `"a2a": "1.0"` and points to `anthropics/a2a-protocol` schema (line 2). `docs/dashboards/.well-known/agent.json` is served. **But no A2A server endpoint exists** — `api/app.py:244-247` only mounts generate/replay/dream routers; no `/.well-known/agent.json` route, no A2A `tasks.send`/`tasks.get` handlers, no remote-agent invocation code. | 2d (add A2A task-server endpoints + register the agent card from the API itself) |
| **Build** | **A2UI** | ⚠️ | `models/data_contracts.py:184` defines `a2ui_payload: dict[str, object] \| None`, `nodes/generator.py:279` always passes `a2ui_payload=None`. Field is structurally present, never populated. | 1.5d (emit a real A2UI widget tree from N3a candidates) |
| **Build** | **AP2 / UCP** (Agent Payments / User Consent) | ❌ | Zero references in code. No payment/consent envelopes anywhere. | N/A (not in scope for a design agent; safe to skip) |
| **Build** | **Grounding** / Vertex AI Search | ✅ | `intake/web_research.py:373` (`Tool(google_search=GoogleSearch())` enabled on `gemini-2.5-flash` calls), `web_research.py:381-411` (parses `grounding_metadata.grounding_chunks`). Real and wired. | — |
| **Build** | **RAG** / RAG Engine | ❌ | No `rag.create`, no `RagCorpus`, no `discoveryengine.googleapis.com`. The "Memory Bank priors" path (`intake/source_resolver.py:132-153`) returns a hardcoded 5-element list — *literally* `["Scope: tenant:..", "Design preference: Material Design 3 dark theme...", ...]`. | 2d (wire a real `vertexai.preview.rag` corpus seeded with the calibration dataset) |
| **Build** | **Cloud Marketplace** | ❌ | No marketplace listing config; not surfaced. | 0.5d (marketing — submission-only) |
| **Build** | **Agents CLI** (new) | ❌ | `examples/agents-cli-scaffold/agent.py` + `agent.yaml` are a *scaffold* (a static demo), not invoked anywhere in the actual pipeline. The agent it exports (`AtelierRootAgent`) is a single LlmAgent — entirely disconnected from `AtelierRunner`. `pyproject.toml` does not declare `google-agents-cli`. No `agents-cli eval`, no `agents-cli deploy` call anywhere. | 1d (a real `agents-cli deploy` wiring + replace scaffold agent with `AtelierRunner` export) |
| **Build** | **Agent Studio** | ❌ | Zero references. The deployed Agent Card lives at `docs/dashboards/.well-known/agent.json` (static) but nothing publishes it to Agent Studio. | 1d (publish agent + agent card to Agent Studio for in-Console preview) |
| **Build** | **Agent Garden** | ❌ | Zero references. Atelier is not registered as a Garden template. | 0.5d (submission-only) |
| **Scale** | **Agent Runtime** | ⚠️ | `infra/terraform/cloud_run.tf:11-45` deploys a `google_cloud_run_v2_service` (atelier-api-staging) with min=0 max=3 instances. This is **Cloud Run**, NOT the new managed **Agent Runtime**. `agent.yaml` declares `target: cloud_run`. No `agents-cli deploy`, no `reasoning_engine`, no `agent_engine` calls. | 1.5d (deploy via Agent Runtime — provides session/sandbox/memory bank IAM out of the box) |
| **Scale** | **Agent Sessions** | ✅ | `memory/bigquery_session.py:39` subclasses `google.adk.sessions.BaseSessionService`. The default in `orchestrator/runner.py:80-99` is `BigQuerySessionBackend` with `InMemorySessionService` fallback. Sessions persist to BQ table `atelier-build-2026.atelier_trajectories.sessions` with create/get/list/delete/append. **Custom backend, not managed Sessions** — but it conforms to the ADK Session API. | 0.5d (swap default to `VertexAiSessionService` per the comment at `memory/session_protocol.py:11`) |
| **Scale** | **Agent Sandbox** | ❌ | No sandbox API call. `deploy/Dockerfile.api:21-22,74` ships non-root container with read-only-fs compatible build — that's container hygiene, not Agent Sandbox (which is the managed sandboxed code-execution service for generated artifacts). Generated HTML/CSS is never executed inside a sandbox before scoring. | 1.5d (wrap `_run_n3c_n3d_n4` candidate rendering in Agent Sandbox before SSIM/Lighthouse) |
| **Scale** | **Agent Memory Bank** | ❌ | `memory/backends/vertex_semantic.py:46-66` and `memory/backends/vertex_procedural.py:56-79` self-declare as in-process stubs that **raise `NotImplementedError`** when `ATELIER_ENV != "development"`. No `vertexai.preview.memorybank` calls. The "memory bank priors" returned by `intake/source_resolver.py:147-153` are 5 hardcoded strings. IAM Conditions in `memory/scope.py:67-68` reference `aiplatform.googleapis.com/memoryScope` but nothing writes to that resource. | 2d (wire real Vertex AI Memory Bank — semantic + procedural — and remove the stubs) |
| **Govern** | **Agent Gateway** | ❌ | Traffic enters via `api/app.py` (FastAPI on Cloud Run) → `INGRESS_TRAFFIC_ALL` (`cloud_run.tf:18`). No Apigee, no gateway in front. Comment at `cloud_run.tf:16-17` admits prod should use INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER. | 1d (front Cloud Run with Agent Gateway) |
| **Govern** | **Agent Identity** | ⚠️ | `auth/firebase.py` does **caller identity** (Firebase Authentication for end-users). `iam.tf:1-17` creates two service accounts (`atelier-runtime`, `atelier-api-sa`) and grants `roles/aiplatform.user` + `roles/bigquery.dataEditor`. This is GCP IAM identity, not the new **Agent Identity** service (which provides agent-to-agent identity assertions for A2A). | 1d (issue an Agent Identity for Atelier when called as a remote A2A agent) |
| **Govern** | **Agent Registry** | ❌ | Two agent cards exist on disk (`agent_card.json`, `docs/dashboards/.well-known/agent.json`) with **inconsistent versions** (0.1.1-alpha vs 0.2.0-beta) and inconsistent skill counts (4 vs 3). Neither is registered with a registry. | 0.5d (publish a single canonical card to Agent Registry) |
| **Govern** | **Agent Anomaly Detection** | ❌ | `orchestrator/governor.py` + `durability/governor.py` are *custom* MAPE-K governors implementing the failure trichotomy (FAIL_LOUD on budget breach, SELF_HEAL on 429/503, FAIL_SOFT on tool errors). Loop detection at `governor.py:65-70`, stall detection at `:72-73`. Zero references to the managed Agent Anomaly Detection service. | 1.5d (route MetacognitiveGovernor events into Agent Anomaly Detection for fleet-wide signals) |
| **Govern** | **Model Armor** | ❌ | `models/safety.py` declares 4 GEAP `HarmCategory` safety settings at `BLOCK_MEDIUM_AND_ABOVE`. That's **Vertex AI safety_settings**, not Model Armor (which is the new prompt-injection / jailbreak / data-loss-prevention shield layered in front of the model). `intake/brief_parser.py:28-34` does have an in-process injection regex (`<script`, `javascript:`, `__import__`, etc.) — homegrown PIA defence, not Model Armor. | 1.5d (wrap LlmAgent calls with Model Armor — the named injection-shield service judges want to see) |
| **Govern** | **Agent Policy** | ⚠️ | "Constitution" framework exists (`consensus/constitutions/apple-grade.yaml`, `consensus/constitution-apple-grade/*.md`, applied via `nodes/consensus.py:577-617` as a soft penalty multiplier). This is a **policy-as-data** layer but it's a custom YAML schema, not OPA/Agent Policy. | 1d (re-express constitutions as Agent Policy rules + enforce at gateway) |
| **Govern** | **Agent Security** | ❌ | Security artifacts: `observability/scrubber.py:160-167` (PII regex scrubber for emails/E.164), `utils/log_sanitizer.py` (used everywhere), `secret_manager.SecretManagerServiceClient()` at `integrations/stitch_mcp.py:303`. All custom. No Agent Security service binding. | 1d |
| **Govern** | **Agent Compliance** | ❌ | Zero references. Tenant isolation is enforced by hand in `recorders/trajectory_recorder.py:183-185` (`tenant_id` required), `optimize/generator_tuner.py:133-138` (admin opt-in for cross-tenant), `memory/bigquery_backend.py:67-69` (empty tenant blocks write). | 1d |
| **Optimize** | **Agent Evaluation** | ⚠️ | `atelier-eval/src/atelier_eval/runner.py:18-67` is a **20-line skeleton** that delegates to `design2code` and `webgen_bench` adapters. The adapters depend on a `chromium-browser` subprocess (`metrics/visual_similarity.py:40-53`) and `lighthouse` CLI (`metrics/lighthouse.py:137-152`) — both shell-out, neither is the managed Agent Evaluation service. `atelier-eval/datasets/calibration-seed-v0.jsonl` is the only seed dataset present. **WebGen-Bench dataset is NOT present**: `adapters/webgen_bench.py:42-47` raises `FileNotFoundError` if manifest is absent — and `datasets/` only contains `calibration-seed-v0.jsonl`. | 1.5d (wire `gen_ai.evaluation` SDK + push results to managed Agent Evaluation) |
| **Optimize** | **Agent Simulation** | ❌ | Zero references. Evaluator subagent tier mentioned in `CLAUDE.md` but not in code. | 1d |
| **Optimize** | **Agent Observability** | ⚠️ | `observability/spans.py` defines a 15-attribute mandatory OTel schema (real). `config/otel-collector-config.yaml:22-27` exports to `googlecloud` (Cloud Trace + Cloud Monitoring + Cloud Logging). But `observability/__init__.py:3-5` admits "ATELIER_OBSERVABILITY_MODE is READ but NOT BRANCHED ON" — the conditional routing is a phase-2 TODO (F0223). PII scrubbing via `PiiScrubSpanProcessor` (`observability/scrubber.py:175-217`) is real. Telemetry lands in Cloud Trace; it's *not* using the new managed Agent Observability surface. | 1d (subscribe to Agent Observability for AI-specific dashboards) |
| **Optimize** | **Agent Optimizer** | ⚠️ | `optimize/dpo_tuning_job.py` submits Vertex AI `PREFERENCE_TUNING` jobs (real `genai.Client.tunings.tune` calls, ADR-0028 verified API). `optimize/generator_tuner.py:191-346` is full pipeline: mine pairs → upload JSONL to GCS → submit tune → κ gate (≥0.70) → promote. `optimize/dreaming_module.py:115-203` is real mid-flight pair extraction. **But the κ scorer in the promote endpoint is a deterministic mock**: `api/dream.py:246-250` returns `0.78 + (hash % 100)/1000` — always 0.780-0.879 — guaranteed to pass the 0.70 gate regardless of model quality. Production gate is hardcoded to reject (`api/dream.py:227-238`: returns 501). | 1.5d (replace mock scorer with a real pipeline invocation against the tuned endpoint) |

**Summary scorecard**: ✅ 5 / ⚠️ 9 / ❌ 12 (out of 26 surfaces graded; AP2 marked N/A).

---

## Top 5 highest-leverage gaps (sorted by lift/cost ratio)

### G1: **Agent Runtime + Agents CLI deploy** (the single biggest unforced error)
- **Current state**: `infra/terraform/cloud_run.tf:11-45` provisions plain Cloud Run (`google_cloud_run_v2_service`). `examples/agents-cli-scaffold/agent.yaml` declares `target: cloud_run` (not `agent_runtime`). The `AtelierRootAgent` in `examples/agents-cli-scaffold/agent.py:32-48` is a single LlmAgent disconnected from the actual 8-node DAG in `orchestrator/runner.py`. No `agents-cli deploy` invocation exists anywhere.
- **Gap**: Two of the three highest-visibility "Build" pillar services (Agent Runtime + Agents CLI) are missing. The entire Track 1 thesis (*"net new agents built from scratch with the new Agent Platform services"*) expects these.
- **Lift**: Judges open the kickoff demo and see `agents-cli deploy && agents-cli eval run` as the canonical hello-world. Atelier's submission landing on Cloud Run + custom FastAPI is exactly the *old* way the new platform replaces. Single highest perception delta.
- **Cost (days)**: 1.5–2 days.
- **Plan**:
  1. Rewrite `examples/agents-cli-scaffold/agent.py` to export `AtelierRunner.run` as the entry point (not a placeholder LlmAgent).
  2. Add `uvx google-agents-cli` to dev deps; add `make deploy` calling `agents-cli deploy`.
  3. Switch `infra/terraform/cloud_run.tf` over to `google_aiplatform_reasoning_engine` (or equivalent) once Agent Runtime is Terraform-able; otherwise drive deploys exclusively via `agents-cli deploy`.
  4. Update `agent.yaml:28` `target: cloud_run` → `target: agent_runtime`.
  5. In demo: open Console → Agent Runtime → see Atelier listed.

### G2: **Agent Memory Bank — replace the in-process stubs**
- **Current state**: `memory/backends/vertex_semantic.py:46` is a TF-IDF in-process dict (`memory/backends/vertex_semantic.py:101-137`) that **raises `NotImplementedError` outside `ATELIER_ENV=development`** (lines 58-63). The "memory bank priors" returned by `intake/source_resolver.py:147-153` are 5 hardcoded strings. IAM Conditions at `memory/scope.py:67-68` reference `aiplatform.googleapis.com/memoryScope` but nothing writes to that resource.
- **Gap**: One of the four "Scale" pillar services is entirely missing. The replay UI (`api/replay.py:99-114`) declares a `MemoryRecall` schema that is never populated — `_assemble_payload` at `:289-342` sets `memory_recalls=[]`.
- **Lift**: Memory Bank is the one new GA service judges will explicitly look for. With the IAM scope already designed (`memory/scope.py`), it's also the *easiest* one to wire — the scaffolding is there.
- **Cost (days)**: 2 days.
- **Plan**:
  1. Replace `_store: dict[...]` in `vertex_semantic.py:66` with `vertexai.preview.memorybank.MemoryBank` calls (semantic + procedural).
  2. Replace `pull_memory_bank_priors` in `intake/source_resolver.py:132-153` with a real Memory Bank query keyed by tenant_id.
  3. Populate `memory_recalls` in `api/replay.py:_assemble_payload` from Memory Bank queries scoped to the session.
  4. Demo: show two runs back-to-back — second uses prior from first.

### G3: **Model Armor + safety_settings narrative**
- **Current state**: `models/safety.py:33-50` declares 4 `HarmCategory` settings (Vertex `safety_settings`). `intake/brief_parser.py:28-54` runs a homegrown injection-pattern regex on briefs (custom PIA defence).
- **Gap**: No Model Armor — the named injection/jailbreak/DLP shield that judges will explicitly ask about during the "Govern" pillar slide.
- **Lift**: Govern pillar today has zero ✅ marks. Adding Model Armor flips at least one box without rebuilding anything — the existing safety_settings stay, Model Armor wraps the boundary.
- **Cost (days)**: 1–1.5 days.
- **Plan**:
  1. Add `google-cloud-modelarmor` to lock.
  2. Wrap every `LlmAgent` call site (`intake/brief_parser.py:65-72`, `orchestrator/generator_ensemble.py:48-62`) with a Model Armor pre/post pass.
  3. Replace the regex in `intake/brief_parser.py:28-34` with Model Armor's PIA classifier (kept as fallback).
  4. Pipe Model Armor detections into Agent Anomaly Detection.

### G4: **Agent Evaluation — wire managed eval instead of CLI subprocess**
- **Current state**: `atelier-eval/src/atelier_eval/runner.py:18-67` is a 50-line skeleton. Evaluation requires a shell `chromium-browser` (`metrics/visual_similarity.py:40-53`) and a shell `lighthouse` CLI (`metrics/lighthouse.py:137-152`). Neither runs in Cloud Run by default; both are absent from `deploy/Dockerfile.api`. The WebGen-Bench dataset is NOT in the repo (`adapters/webgen_bench.py:42-47` raises FileNotFoundError) — the only seed file present is `atelier-eval/datasets/calibration-seed-v0.jsonl`. The κ scorer in the promote endpoint is a **mock**: `api/dream.py:246-250`.
- **Gap**: The "Optimize" pillar has 0 ✅ services. Agent Evaluation is the most demoable.
- **Lift**: A `bench.atelier.dev` page showing the agent passing/failing the Google-managed eval suite is judge-bait. Today `atelier-eval/scoreboard.py:38-60` (`publish_to_scoreboard`) explicitly `raise NotImplementedError`.
- **Cost (days)**: 1.5 days.
- **Plan**:
  1. Replace `subprocess.run(["chromium-browser", ...])` with `gen_ai.evaluation` SDK or Vertex AI Evaluation Service.
  2. Replace the κ mock at `api/dream.py:246-250` with an Agent Evaluation managed run against the tuned endpoint.
  3. Submit results to managed Agent Evaluation; render the live scoreboard in `docs/dashboards/bench/index.html`.

### G5: **Resolve the Agent Card schism + register the canonical card**
- **Current state**: Two cards exist on disk with conflicting metadata:
  - `agent_card.json` — version `0.1.1-alpha`, 4 skills (incl. `campaign-orchestrate`, `design-system-infer`), schema points to `anthropics/a2a-protocol` (line 2 — wrong vendor for a Google submission)
  - `docs/dashboards/.well-known/agent.json` — version `0.2.0-beta`, 3 skills (different set: `generate-design`, `evaluate-design`, `optimize-design`), declares 9 axes (vs. 5 in code), declares `streaming: false`
  - Neither is registered with Agent Registry; neither is served by `api/app.py` (which has no `/.well-known/agent.json` route).
- **Gap**: A judge running `curl https://atelier.autonomous-agent.dev/.well-known/agent.json` gets 404. A judge looking at the GitHub repo sees two contradictory cards.
- **Lift**: Two competing cards is a credibility-killer; a single registered card is a checkbox.
- **Cost (days)**: 0.5 day.
- **Plan**:
  1. Pick one canonical card. Recommend a *new* one built from code: emit it from `api/app.py` at `/.well-known/agent.json` driven by `__version__` + the actual `_AXIS_NAME_TO_ENUM` (5 axes, not 9).
  2. Replace `agent_card.json` schema reference (line 2) — drop `anthropics/a2a-protocol`, use the canonical A2A schema URL.
  3. Delete the static `docs/dashboards/.well-known/agent.json` and `agent_card.json` root file; have one source of truth.
  4. Register with Agent Registry (Garden + Studio if accessible).

---

## Top 3 competing implementations (Atelier rolled its own)

### CI-1: **MetacognitiveGovernor vs. Agent Anomaly Detection**
- **Where**: Two governors, both custom — `orchestrator/governor.py:82-183` and `durability/governor.py:95-247`. Both implement MAPE-K loop detection, stall detection, budget enforcement, retry trichotomy. `governor.py:65-70` is real loop detection; `governor.py:72-73` is real stall detection; `governor.py:170-176` is the $5K hard cap.
- **Why it competes**: Agent Anomaly Detection is the new managed service for exactly these signals — loop, runaway-cost, drift, anomaly. Atelier doing this in-process is fine for correctness, but it costs the agent the "Govern" pillar Anomaly Detection checkbox AND fleet-wide visibility.
- **Recommendation**: **Hybridize**. Keep `MetacognitiveGovernor` as the in-process enforcement layer (it's tight, well-tested, sub-50ms). Add an `_emit_anomaly_event()` hook in `governor.py:_classify_failure` (line 88) and `_check_budget` (line 170) that publishes to Agent Anomaly Detection. Best of both: instant local kill + fleet observability.

### CI-2: **EpsilonGreedyBandit vs. Agent Optimizer / managed routing**
- **Where**: `router/v1_bandit.py:116-237` — full hand-rolled ε-greedy + UCB1 multi-armed bandit. Phase preferences in `_PHASE_PREFERENCE` (line 69-78). Real implementation with proper math (UCB1 with `c=√2`, 7-day epsilon decay).
- **Why it competes**: The Agent Optimizer surface is exactly "the system picks the right expert per task." Atelier rolled a respectable bandit; the managed service is what judges expect.
- **Recommendation**: **Keep custom + document**. This is genuinely a feature, not a gap — the bandit is novel research-grade work (cites Auer 2002, Sutton & Barto). Frame it as "we built our own router on top of Agent Optimizer's primitives" rather than ignoring Agent Optimizer entirely. Add a one-paragraph ADR explaining the choice; cite the regret bound; show the math. **Add** a thin Agent Optimizer wrapper for *generator selection* (not the bandit) so the service appears in the call graph.

### CI-3: **BigQuerySessionBackend vs. VertexAiSessionService**
- **Where**: `memory/bigquery_session.py:39-364` — full ADK `BaseSessionService` subclass writing to BigQuery `atelier-build-2026.atelier_trajectories.sessions`. Real create/get/list/delete/append_event. Code at `memory/session_protocol.py:11` literally says "`VertexAiSessionService` satisfies this protocol" — meaning the swap was deliberately deferred.
- **Why it competes**: VertexAiSessionService is the managed Agent Sessions service. Sessions is one of the 4 GA "Scale" services. Today Atelier ✅ on Sessions only because it implements the ADK Protocol — not because it uses the managed service.
- **Recommendation**: **Migrate** for the demo path (one-line change at `orchestrator/runner.py:80-99` — return `VertexAiSessionService` from `_default_session_service`). **Keep custom** for prod (BigQuery gives cost accounting + cross-tenant query + DPO mining via the `trajectory_records` join). Add `ATELIER_SESSION_BACKEND=managed|bigquery` env switch. Default to `managed` so the demo lights up.

---

## `agent_card.json` claims vs reality

> Code grades against `agent_card.json` (the root file). The second card at `docs/dashboards/.well-known/agent.json` is graded separately at the end.

| Claim | Backed by code? | Evidence |
|---|---|---|
| `"name": "Atelier"` | ✅ | `__version__.py` + uniform usage |
| `"description": "8-node DAG ... D-O-R-A-V consensus judges"` | ⚠️ Partial | The runner is documented as **8-node DAG** but `orchestrator/runner.py:1-23` enumerates **N1, N14, N2, N3a, N3c, N3d, N4** = 7 nodes. There is no N5/N6/N7/N8 wired into `runner.run()`. Generator file `nodes/generator.py` exists but is not called from runner (it's a separate `generate_candidate` helper). |
| skill `"generate-ui"` | ✅ | `api/generate.py:290-358` `POST /v1/generate` is real |
| skill `"review-ui"` (review existing UI vs D-O-R-A-V) | ⚠️ Partial | The CLI exposes it (`cli.py:113-163` `cmd_evaluate`) but the API does NOT — no `POST /v1/review` route in `api/app.py:244-251` |
| skill `"campaign-orchestrate"` (multi-surface, 12+ pages, cross-surface coherence) | ❌ | No multi-surface code path. `models/data_contracts.py` has `campaign_id` field but `runner.run()` operates on a single brief; no orchestration over multiple surfaces, no cross-surface coherence verification anywhere |
| skill `"design-system-infer"` via PADI | ❌ | No "PADI" code, no Project-Agnostic Descriptor Inference module exists. The closest is `intake/source_resolver.py:39-86` `_parse_design_md_tokens` which reads DESIGN.md with regex — that's "parse-if-present", not "infer from codebase" |
| `"protocols": {"a2a": "1.0"}` | ❌ | No A2A endpoint code. The card cites the schema, but the API doesn't serve the card and doesn't accept A2A `tasks.send` |
| `"protocols": {"adk": "2.0-beta"}` | ✅ | ADK 2.0 imports are real and pinned |
| `"authentication.bearer": "Firebase ID token"` | ✅ | `auth/firebase.py:260-284` `require_auth` is wired |
| `"authentication.apiKey: X-Atelier-API-Key"` | ❌ | No API key middleware in `api/app.py`. CORS at `app.py:113` allows `Authorization` and `X-Request-ID` headers; **`X-Atelier-API-Key` is not parsed anywhere** |
| `"capabilities.streaming": true` | ❌ | `api/app.py` has zero `StreamingResponse` / `EventSourceResponse` / SSE endpoints. The other card (`agent.json`) honestly declares `"streaming": false` |
| `"capabilities.pushNotifications": false` | ✅ | True — no push code |
| `"capabilities.stateTransitionHistory": true` | ⚠️ Partial | Trajectory records ARE stored (`recorders/trajectory_recorder.py`) and replayable (`api/replay.py`), but state *transitions* (the events emitted by ADK Runner) aren't surfaced — `api/replay.py:139-152` builds spans with `duration_ms=0.0`, comment at `:144` notes "duration is not pre-computed; UI computes it from timestamps" |
| `"capabilities.multiTurn": true` | ❌ | `api/generate.py` `POST /v1/generate` accepts only `brief` + `budget_usd` + `design_system_source`. No prior `session_id` accepted; each call creates a fresh session via `runner.py:327-333`. There is no multi-turn affordance |
| `"defaultOutputModes": ["text", "file"]` | ⚠️ | API returns `text/html` in `best_candidate` field; no file/attachment endpoint |

**Demo-time embarrassments (likely to be hit by a judge in 5 minutes)**:
1. **Streaming claim**: a judge with `curl --no-buffer` sees a complete JSON, not a stream. Either flip the claim to `false` (matches the other card) or add SSE.
2. **API key auth**: hitting `/v1/generate` with `X-Atelier-API-Key: foo` is silently ignored — 401 fires only because Firebase is required. Card promises a working API key flow.
3. **Two cards**: a judge comparing the repo card (4 skills, 0.1.1-alpha) to the deployed card (3 skills, 0.2.0-beta) flags this as version drift.
4. **`campaign-orchestrate` skill**: there is no multi-surface code anywhere. Asking the agent to "design the whole onboarding flow" produces a single surface.
5. **`design-system-infer` (PADI)**: no module exists. The README story doesn't have a backing implementation.
6. **8-node DAG**: 7 are wired (N1, N14, N2, N3a, N3c, N3d, N4). N3b (Copy Editor) and N3e (Fixer) have ModelSpec entries in `model_registry.py:144-161` but no orchestration call.

`docs/dashboards/.well-known/agent.json` claims (separate evaluation):
- "9 quality axes": code defines **5** axes (`nodes/consensus.py:165-171`). Adding `copy, motion, token efficiency, coherence` would require 4 new judges + prompts + scorers — none exist.
- "Multi-judge Bayesian consensus": there are 5 LLM judges (`nodes/llm_judge.py`), but **Bayesian** is overstating it — the CI is symmetric ±0.10 fixed (`nodes/consensus.py:116`) or derived from `avg_logprob` when available (`nodes/llm_judge.py:893-898`). No prior, no posterior update, no Beta/Dirichlet.

---

## Recommended winning narrative

> "Atelier is a **net-new agent built on the Gemini Enterprise Agent Platform**: a 7-node ADK 2.0 DAG that takes a design brief, dispatches parallel Gemini 2.5 generators through an MCP toolchain (Stitch + GitHub), evaluates each candidate through 6 deterministic gates and 5 LLM-judges (D-O-R-A-V) shipped as Vertex AI calls, and closes a **DPO data flywheel** that mines preference pairs from BigQuery and submits Vertex AI `PREFERENCE_TUNING` jobs — gated at κ ≥ 0.70 before promotion. The entire pipeline runs under a metacognitive **MAPE-K governor** with a $5K hard budget cap, with PII-scrubbed OpenTelemetry traces routed through the Google Cloud OTel collector to Cloud Trace, Logging, and Monitoring. **Built with ADK, Gemini API, MCP, Grounding (Vertex AI Search), Cloud Run, BigQuery, Cloud Trace, and Firebase Identity**; demos in 60 seconds via `atelier generate`."

**Three sentences this narrative is true given today's code**:
1. *"ADK 2.0 DAG with MCP-driven generators and a 5-axis LLM judge consensus"* — ✅ verifiable in `orchestrator/runner.py`, `integrations/stitch_mcp.py`, `nodes/llm_judge.py`.
2. *"DPO flywheel writing preference pairs to BigQuery and submitting Vertex AI `PREFERENCE_TUNING` jobs"* — ✅ verifiable in `optimize/dpo_tuning_job.py`, `optimize/dreaming_module.py`, `optimize/generator_tuner.py`.
3. *"Cost-bounded metacognitive governor with PII-scrubbed OTel telemetry"* — ✅ verifiable in `orchestrator/governor.py`, `observability/scrubber.py`, `config/otel-collector-config.yaml`.

**5 code deltas that would make a meaningfully stronger narrative true within 7 days**:

| Delta | Files touched | Net gain |
|---|---|---|
| **D1**: Deploy via `agents-cli deploy` to Agent Runtime; remove the standalone `examples/agents-cli-scaffold` agent and re-export `AtelierRunner` as the canonical agent. | `examples/agents-cli-scaffold/agent.py`, `examples/agents-cli-scaffold/agent.yaml`, new `Makefile` target, `infra/terraform/cloud_run.tf` (delete) | Adds **Agent Runtime + Agents CLI** services to the call graph (2 named services) |
| **D2**: Replace `VertexSemanticMemoryBackend` stub with real `vertexai.preview.memorybank` calls; populate `memory_recalls` in `api/replay.py:_assemble_payload`. | `memory/backends/vertex_semantic.py`, `memory/backends/vertex_procedural.py`, `intake/source_resolver.py:132-153`, `api/replay.py:289-342` | Adds **Agent Memory Bank** (+1 GA Scale service); makes replay UI show memory hits |
| **D3**: Wrap every `LlmAgent` call with Model Armor pre/post; replace `intake/brief_parser.py:28-34` injection regex with Model Armor PIA classifier. | `models/safety.py` (extend), `intake/brief_parser.py:65-72`, `orchestrator/generator_ensemble.py:48-62`, new `integrations/model_armor.py` | Adds **Model Armor** (+1 Govern service); makes Govern pillar non-zero |
| **D4**: Add `POST /v1/review` (wraps the existing `cmd_evaluate` flow) and emit a real A2A endpoint at `/.well-known/agent.json` from `api/app.py`; collapse the two static cards. | `api/app.py:244-251`, new `api/review.py`, delete `agent_card.json`, delete `docs/dashboards/.well-known/agent.json` | Backs `agent_card.json:"review-ui"` skill claim; adds **A2A** + **Agent Registry** (+2 services); resolves the agent-card schism |
| **D5**: Replace the κ scorer mock at `api/dream.py:246-250` with a real Agent Evaluation managed run against the tuned endpoint; download the WebGen-Bench manifest into `atelier-eval/datasets/`. | `api/dream.py:226-255`, `atelier-eval/src/atelier_eval/runner.py`, `atelier-eval/datasets/` | Adds **Agent Evaluation** (+1 Optimize service); converts WebGen-Bench from "Phase 2 stub" to runnable; closes the flywheel honesty gap |

**After 5 deltas**: scorecard improves from 5 ✅ / 9 ⚠️ / 12 ❌ to approximately **11 ✅ / 8 ⚠️ / 7 ❌**, and **every pillar gets at least one ✅**. Total dev cost: ~7 days, fits inside the remaining sprint window.

---

## Gaps in this audit

- Did not read every test file — focused on production code surfaces. Tests might reveal additional API stubs not exercised by the runner.
- Did not audit `atelier-dashboard`, `atelier-chrome-extension`, `atelier-figma-plugin`, `atelier-deploy` — out of stated scope (`atelier-core` and `atelier-eval` only).
- Did not exhaust `atelier-core/src/atelier/router/v0_managed.py`, `nodes/trajectory.py`, `intake/brief_spec.py`, `models/axis_weights.py`, `models/data_contracts.py` line-by-line; reviewed them indirectly through their callers.
- Did not verify whether the deployed Cloud Run service actually serves any of these routes (DNS `atelier.autonomous-agent.dev` was not probed) — strictly a static code audit per the brief.
- Did not investigate `consensus/*.yaml` constitution rules in depth — confirmed they exist and are wired as soft penalties; depth of the rule set was not graded.
- Phoenix vs Cloud Trace conditional routing (F0223) is marked as an open issue in `observability/__init__.py:3-5`; did not investigate the live routing config.
- The full LLM judge module (`nodes/llm_judge.py`) is 900+ lines; spot-checked imports, `VertexAIJudgeClient`, `_resolve_axis_scorers`, and `JUDGE_PROMPTS`. Did not read every helper.
- `agents-cli` availability: assumed it exists as `google-agents-cli` per `docs/research/`; did not verify against PyPI or `npm view`.
- Agent Anomaly Detection / Agent Identity / Agent Gateway product surfaces (newly announced) — graded on **mention in code**, not on whether the SDK exists yet at submission deadline. If any are still preview-only with no public SDK, the corresponding effort estimates above will grow.
