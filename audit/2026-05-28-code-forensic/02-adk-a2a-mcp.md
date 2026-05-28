# Forensic Audit — ADK / A2A / MCP / Gemini Enterprise Agent Platform

**Auditor:** Opus 4.7
**Date:** 2026-05-28
**Scope:** Phase 2 consensus-agent worktree
**Method:** Code-only; documentation and comments ignored
**Hard cap:** 25 findings

---

## P0 (must-fix — these will lose the Build pillar evaluation)

### P0-1 — A2A agent card is not served by the FastAPI app at `/.well-known/agent.json`

**File:** `atelier-core/src/atelier/api/app.py:162-289`
**Issue:** The A2A spec requires the agent card to be discoverable at `GET /.well-known/agent.json` on the agent's URL. The agent card file `agent_card.json` (worktree root) declares `"url": "https://atelier.dev"` but `app.py` only registers `/health`, `/v1/account/usage`, `/auth/signin`, `/v1/generate`, `/v1/replay/{session_id}`, `/v1/dream`, `/v1/dream/promote`. No `/.well-known/agent.json` route. `grep -rn "well-known\|StaticFiles\|FileResponse" atelier-core` returns zero hits.
**Evidence:** `grep "def \|@router\|app\.get" app.py` → only 7 route definitions, none for `.well-known`. `grep -rn "agent_card" atelier-core/src` returns 0 hits — Python code never references the JSON file.
**Why P0:** A judge running A2A protocol discovery against the Cloud Run service will get a 404. The agent is not discoverable by other A2A agents. This is the core A2A contract.
**Fix:** Add to `app.py`:
```python
@application.get("/.well-known/agent.json", include_in_schema=False)
async def agent_card() -> dict[str, Any]:
    from pathlib import Path
    import json
    return json.loads((Path(__file__).resolve().parents[5] / "agent_card.json").read_text())
```
Or mount `StaticFiles` for `.well-known/`. The Firebase static-hosting rewrite at `firebase.json:44-53` only proxies `/api/**` to Cloud Run — `/.well-known/agent.json` on Firebase Hosting (`docs/dashboards/.well-known/agent.json`) serves a *different, conflicting* file (P0-2).

### P0-2 — Two divergent A2A agent cards declare conflicting capabilities

**File 1:** `agent_card.json:1-67` (claimed primary; never served)
**File 2:** `docs/dashboards/.well-known/agent.json:1-46` (served by Firebase Hosting)
**Issue:** The two cards declare different versions (`0.1.1-alpha` vs `0.2.0-beta`), different skills (4 skills incl. `campaign-orchestrate` and `design-system-infer` vs 3 skills incl. `optimize-design`), different stream/multiTurn capabilities (`streaming: true / multiTurn: true` vs `streaming: false / multiTurn` absent), and different evaluation axes (5 D-O-R-A-V axes vs 9 axes). Neither matches what the code implements (5 axes per `nodes/consensus.py:497 _AXIS_SCORERS`).
**Evidence:**
- `agent_card.json:42-43` declares `"protocols": {"a2a": "1.0", "adk": "2.0-beta"}` — non-standard fields not in the A2A spec.
- `docs/dashboards/.well-known/agent.json:25` claims 9 axes ("brand, originality, relevance, accessibility, visual clarity, copy, motion, token efficiency, coherence"); code implements only `{brand, originality, relevance, accessibility, visual_clarity}` per `consensus.py:497`.
- `optimize-design` skill claims DPO promotion via `/v1/dream/promote` but `api/dream.py:227-238` returns HTTP 501 unless `ATELIER_ENV=development` and uses a fake md5-based scorer at line 246-250.
**Why P0:** A judge reading the card will form expectations the code cannot meet. Misleading capability declaration violates A2A interoperability contract.
**Fix:** Single source of truth; serve it from one place; only declare what's implemented. The `motion / copy / token_efficiency / coherence` axes are vaporware.

### P0-3 — No `ConsensusAgent` (or any ADK BaseAgent subclass) for N3d

**File:** `atelier-core/src/atelier/nodes/consensus.py` (entire 30K-line module)
**Issue:** The PRD §6.3 and agent card describe N3d as a `ConsensusAgent` — judges should run inside an ADK agent, not a plain Python `evaluate_candidate(...)` function. `consensus.py` defines a `ConsensusEvaluation` dataclass (line 202) and an `evaluate_candidate()` function (line 624), but never imports `from google.adk.agents.*` and never subclasses `BaseAgent`. The N3d "agent" is just an in-process function call.
**Evidence:** `grep -rn "from google.adk.agents" atelier-core/src` returns only 4 hits: `brief_parser.py:6`, `generator_ensemble.py:16-17,30`. `nodes/consensus.py` has zero ADK agent imports. `runner.py:226` calls `evaluate_candidate(candidate, weights, judge_client=self._judge_client)` synchronously inside a Python loop, bypassing ADK orchestration.
**Why P0:** Judges who score "use of ADK BaseAgent / Workflow primitives" will see only 2 real LlmAgents (`BriefParserAgent` + the 3 generators in `GeneratorEnsemble`). Five "judges" run as Python heuristics in the default config (P0-4).
**Fix:** Wrap each per-axis judge as an `LlmAgent` and compose them under `ParallelAgent` or the new `Workflow` primitive. Use `SequentialAgent` for N3c→N3d→N4.

### P0-4 — D-O-R-A-V judges default to deterministic heuristics, not Gemini

**File:** `atelier-core/src/atelier/nodes/llm_judge.py:98-105`, `orchestrator/runner.py:144-151`
**Issue:** `DEFAULT_JUDGE_MODE = JUDGE_MODE_HEURISTIC` (line 105 of llm_judge.py). In `runner.py:144`, `effective_mode = os.environ.get(ATELIER_JUDGE_MODE_ENV, JUDGE_MODE_HEURISTIC)` — so unless `ATELIER_JUDGE_MODE` is explicitly set to `"llm"` or `"hybrid"` in the environment, `_judge_client` stays `None` (runner.py:151) and `evaluate_candidate` falls through to the Phase-1 regex/TF-IDF scorers in `consensus.py:263-` (e.g., `_score_brand` counts CSS custom-property declarations).
**Evidence:**
- `consensus.py:497` `_AXIS_SCORERS` maps each axis to a `_score_*` heuristic function.
- `llm_judge.py:731-734`: heuristic mode returns those heuristic callables verbatim.
- `cloud_run` deployment in `examples/agents-cli-scaffold/agent.yaml:36-39` env section sets `ENVIRONMENT`, `BQ_DATASET`, `OTEL_SERVICE_NAME`, `ATELIER_DASHBOARD_ORIGIN` — **no `ATELIER_JUDGE_MODE`**. Therefore production defaults to heuristic.
**Why P0:** "Multi-judge Bayesian consensus" advertised in the agent card is, by default, five regex passes over the CSS. Judges scoring "actual use of Gemini for evaluation" will mark this as misleading.
**Fix:** Default `ATELIER_JUDGE_MODE=llm` in production; document the heuristic fallback as a degradation mode, not the default.

### P0-5 — `_call_llm` for `BriefParserAgent` raises `NotImplementedError` — N1 cannot run

**File:** `atelier-core/src/atelier/intake/brief_parser.py:87-99`
**Issue:** `BriefParserAgent.parse()` (line 74) calls `await self._call_llm(brief_text)` (line 76), and `_call_llm` unconditionally raises `NotImplementedError` with the message "stub must be replaced by a real ADK integration or mocked in tests" (line 96). The agent never actually calls Gemini. The pipeline cannot get past N1 in any environment.
**Evidence:** `runner.py:284` `brief = await n1_agent.parse(brief_text)` will raise. The constructor at brief_parser.py:65 instantiates a real `LlmAgent` with `output_schema=BriefSpec`, but nothing ever invokes `self._llm.run_async(...)` — `_call_llm` doesn't reference `self._llm`.
**Why P0:** The advertised "Brief Parsing" capability is non-functional. Any judge that runs `POST /v1/generate` will get an unhandled exception.
**Fix:** Wire `_call_llm` to `self._llm.run_async(...)` or a `Runner(agent=self._llm)`; until then the pipeline has no N1.

### P0-6 — Memory Bank backends are in-process dicts; `raise NotImplementedError` outside `ATELIER_ENV=development`

**File:** `atelier-core/src/atelier/memory/backends/vertex_semantic.py:58-63`, `vertex_procedural.py:68-73`
**Issue:** Both `VertexSemanticMemoryBackend` and `VertexProceduralMemoryBackend` are in-memory dicts (`self._store: dict[str, ...]`). The constructor refuses to instantiate unless `ATELIER_ENV=development` (vertex_semantic.py:58, vertex_procedural.py:68). The classes never import `vertexai`, `google.cloud.aiplatform`, or `MemoryBank`. `query_semantic` (line 139) uses a stdlib TF-IDF function (line 100 `_tfidf_similarity`) — no embeddings, no `text-embedding-005` call.
**Evidence:** `grep -rn "VertexAiMemoryBankService\|aiplatform.MemoryBank" atelier-core/src` → only docstring mentions in `source_resolver.py:136,145`. Never imported.
**Why P0:** The Build pillar's RAG component (Vertex AI Memory Bank / RAG Engine) is zero. The agent card and PRD claim "Memory Bank priors" but `intake/source_resolver.py:147-153` returns 5 hardcoded English strings.
**Fix:** Wire the real `vertexai.preview.rag` or `MemoryBank` API; until then drop the claim.

---

## P1 (should-fix)

### P1-1 — Gemini model pins are 2024 previews, not current models

**File:** `atelier-core/src/atelier/models/model_registry.py:84,94,105,115,125,135,145,155`
**Issue:** Every judge, generator, copy-editor, and fixer pins `model_id="gemini-2.5-flash-preview-05-20"` or `"gemini-2.5-pro-preview-05-06"`. Those are May 2024 preview names. Current model in `intake/brief_parser.py:62` is `"gemini-3-flash"`; `examples/agents-cli-scaffold/agent.py:34` uses `"gemini-3-pro"`; `intake/web_research.py:308` uses `"gemini-2.5-flash"` (the GA name, different from the preview alias).
**Why P1:** Inconsistent model pinning across modules; judges won't recognize "we used Gemini 3" if every actual N3d call hits a 2024 preview alias. Likely some calls will 404 because preview aliases are decommissioned.
**Fix:** Single `Final[str] DEFAULT_MODEL = "gemini-3.1-pro"` (or `gemini-3-flash`) at the registry top; reference everywhere; bump after verifying with context7.

### P1-2 — `app.py` has no router for an A2A `POST /` (or `/messages`) JSON-RPC endpoint

**File:** `atelier-core/src/atelier/api/app.py:244-251`
**Issue:** A2A protocol clients POST a JSON-RPC envelope to the agent's URL (typically `POST /` or `POST /messages`). Atelier exposes `POST /v1/generate` with a bespoke Pydantic request schema (`api/generate.py:48-68`). There is no A2A JSON-RPC handler that accepts `tasks/send`, `tasks/get`, `tasks/cancel`, or `tasks/sendSubscribe` per the A2A spec.
**Why P1:** Even if the agent card were served, an A2A client cannot actually call the agent over the protocol — only over Atelier's bespoke REST.
**Fix:** Add a minimal `POST /` A2A endpoint that translates `tasks/send` → `_run_pipeline()`. Use `python-a2a` or hand-roll per the spec.

### P1-3 — Stitch MCP toolset is wired correctly but degrades silently in tests/CI

**File:** `atelier-core/src/atelier/integrations/stitch_mcp.py:294,318-326`
**Issue:** Real MCP via ADK's `McpToolset(SseConnectionParams(url=..., headers=...))` (line 326) — this *does* speak the real MCP protocol over SSE, good. However: the URL `https://stitch.googleapis.com/mcp` (line 323) is the speculative GA endpoint; the secret `projects/atelier-build-2026/secrets/atelier-geap-api-key/versions/latest` (line 294) is project-scoped to `atelier-build-2026`. In any environment without that secret + correct project context, `try_get_stitch_mcp_toolset()` (line 329) catches the exception and returns `(None, degradation_info)` — generators continue with no Stitch tools. `generator_ensemble.py:44-45` then passes empty `toolsets` to the `LlmAgent` instances, so all three generators degrade to raw Gemini HTML generation with no design-system tokens.
**Why P1:** In CI / sandbox / cold-start, this is the *normal* code path. The agent card's `generate-ui` skill claims "production-grade HTML/CSS/JS … brand alignment" but the brand alignment via Stitch design tokens is gated on a single GCP secret. Should at minimum surface this prominently in the response, which `runner.py:390-396` does — credit for that.
**Fix:** Make the Stitch MCP URL configurable; provide a public sandbox endpoint; document the fallback contract.

### P1-4 — `GitHubMCPClient` is HTTP, not MCP — name is misleading

**File:** `atelier-core/src/atelier/integrations/github_mcp.py:104-356`
**Issue:** `GitHubMCPClient` (line 104) is a plain `httpx.AsyncClient` wrapper around the GitHub REST API v3 (line 131: `"Accept": "application/vnd.github.v3+json"`). It does not import `mcp`, does not use `McpToolset`, does not connect to GitHub's MCP server (which exists at `https://api.githubcopilot.com/mcp/` and speaks MCP over stdio/HTTP). The "MCP" in the class name refers to nothing protocol-related — the docstring on line 28 even says "Wraps GitHub's REST API v3."
**Evidence:** `grep -rn "GitHubMCPClient" atelier-core/src` returns only its definition + a logger string — **no consumer in src/**. The class is dead code at runtime.
**Why P1:** Calling it "MCP" while it bypasses MCP and isn't called from anywhere will be flagged by any auditor who opens the file.
**Fix:** Rename to `GitHubRestClient`, or replace with `McpToolset(StdioConnectionParams(...))` pointing at the official GitHub MCP server.

### P1-5 — N14 WRAI calls `client.models.generate_content` synchronously from `asyncio.to_thread`; the GoogleSearch tool *is* wired correctly

**File:** `atelier-core/src/atelier/intake/web_research.py:339-431`
**Issue:** The wiring of `genai_types.Tool(google_search=genai_types.GoogleSearch())` (line 373) is correct — this is the canonical way to enable Gemini's Google Search grounding via the `google.genai` Vertex AI client (line 335 `genai.Client(vertexai=True, project=project, location=location)`). Good. However the call uses `asyncio.to_thread(client.models.generate_content, ...)` (line 368) — the synchronous `generate_content` blocks a thread pool worker per query, and 5-8 parallel queries (default 5 per `DEFAULT_QUERY_COUNT:40`) will exhaust the default thread pool quickly. The async variant `client.aio.models.generate_content` exists in google-genai 1.75.0 and should be used.
**Why P1:** Performance + correctness — currently this is the *only* place real Gemini Grounding lives in the codebase, and it serializes through the threadpool.
**Fix:** `await client.aio.models.generate_content(...)` directly; drop `asyncio.to_thread`.

### P1-6 — `a2ui_payload` field exists on `CandidateUI` but is never populated

**File:** `atelier-core/src/atelier/models/data_contracts.py:184`, `atelier-core/src/atelier/nodes/generator.py:279`
**Issue:** `CandidateUI.a2ui_payload: dict[str, object] | None = None` (data_contracts.py:184). The only writer in `src/` is `generator.py:279` which hardcodes `a2ui_payload=None`. The orchestrator never reads or sets it. No `from a2ui import ...` anywhere. The runner returns raw HTML strings (runner.py:404 → `best_candidate` is a `str`); no A2UI structured render hints are emitted.
**Why P1:** A2UI is one of the Build pillar's flagship surfaces (structured agent output that any host UI can render). Claiming the field while never populating it is the textbook "card lists capabilities the code doesn't implement" anti-pattern.
**Fix:** Either populate `a2ui_payload` with a real A2UI render-tree (use the `a2ui` package if it exists in 1.75.0 google-genai, or hand-build the JSON), or remove the field.

### P1-7 — `Agent Skills` (ADK ≥ 2.0 native concept) declared nowhere

**File:** Cross-cutting; `atelier-core/src/atelier/orchestrator/generator_ensemble.py:49-61`, all `LlmAgent` constructors
**Issue:** No `LlmAgent` in the codebase declares `skills=[...]` or imports `from google.adk.agents.skill import Skill` or registers an `AgentSkill`. `grep -rn "Skills\|skill_id\|agent_skill" atelier-core/src` returns 0 hits. The four "skills" in `agent_card.json:11-39` are A2A-protocol skills (declarative manifest) — distinct from ADK Agent Skills (composable runtime capabilities).
**Why P1:** Judges scoring "uses new ADK Agent Skills surface" will mark 0. Agent Skills landed in `google-adk` 2.0 (per Cloud Next 2026); the dependency is pinned at `google-adk==2.0.0`.
**Fix:** Declare each generator capability as an `AgentSkill` and register on the root `LlmAgent`. Mirror the agent card's 4 skills (`generate-ui`, `review-ui`, `campaign-orchestrate`, `design-system-infer`).

### P1-8 — `agents-cli-scaffold` exists but uses a model name not in `model_registry`

**File:** `examples/agents-cli-scaffold/agent.py:34`, `agent.yaml:1-41`
**Issue:** `AtelierRootAgent = LlmAgent(name="atelier-root", model="gemini-3-pro", ...)` (agent.py:34). `gemini-3-pro` is not in `model_registry.ALL_MODEL_IDS` (line 183), which lists only `gemini-2.5-flash-preview-05-20` and `gemini-2.5-pro-preview-05-06`. The `agent.yaml:14-16` entry maps to `AtelierRootAgent` (a single LlmAgent with no tools, no sub-agents, no skills) — running `agents-cli` against this YAML produces a vanilla Gemini chat session, not the Atelier pipeline.
**Why P1:** The CLI scaffold is a separate, isolated agent definition that doesn't exercise the production pipeline. Judges who run `agents-cli serve agent.yaml` see a one-shot Gemini, not Atelier.
**Fix:** Either make `agents-cli-scaffold/agent.py` import `AtelierRunner` and wrap it, or pick a model from the registry. Add tools so the CLI demo actually demonstrates Atelier.

### P1-9 — BigQuery session backend silently falls back to in-memory on every BQ error

**File:** `atelier-core/src/atelier/memory/bigquery_session.py:141-149, 219-223, 281-285, 320-324, 358-362`
**Issue:** Every BQ operation (`create_session`, `get_session`, `list_sessions`, `delete_session`, `append_event`) is wrapped in `try/except Exception` that downgrades to `self._fallback_store` (in-process dict) on any failure. There is no fail-loud path, no retry, no metric on degradation rate. `runner.py:89-99` further wraps the *constructor* call in `try/except ImportError` falling back to `InMemorySessionService`.
**Why P1:** On a Cloud Run cold start where `google-cloud-bigquery` is installed but the project/dataset isn't reachable (e.g., wrong service account), every session silently uses in-memory storage. Cloud Run scales to zero, so all session state is lost on every cold start — silently. The agent card claims `"stateTransitionHistory": true`.
**Fix:** Fail-loud on BQ errors in production (gated on `ATELIER_ENV!="development"`). Emit a metric. Distinguish "BQ unavailable" from "BQ row not found".

---

## P2 (nice-to-fix)

### P2-1 — `ATELIER_JUDGE_MODE` env var read at construction time, not per request

**File:** `atelier-core/src/atelier/orchestrator/runner.py:144-151`
**Issue:** The judge mode is decided once in `AtelierRunner.__init__`. Tests that set the env var after construction get the wrong client. Per-request judge mode switching (useful for ablations) is impossible.
**Fix:** Move the resolution into `_run_n3c_n3d_n4` and read the env var per call.

### P2-2 — `Runner(...)` is created and discarded per request inside `_run_ensemble`

**File:** `atelier-core/src/atelier/orchestrator/runner.py:337-359`
**Issue:** `adk_runner = Runner(agent=ensemble, session_service=self._session_service, app_name=_APP_NAME)` is built inside `_run_ensemble` for every request. The `ParallelAgent` + 3 `LlmAgent` instances are also rebuilt every request via `create_generator_ensemble()`. This bypasses ADK's runner warm-up and any internal connection pooling.
**Fix:** Construct the ensemble + runner once in `AtelierRunner.__init__`. Inject the session per call.

### P2-3 — `ParallelAgent` is deprecation-flagged in the source but still used

**File:** `atelier-core/src/atelier/orchestrator/generator_ensemble.py:17-18`
**Issue:** The import comment `Deprecation(adk-3.0): migrate -> Workflow` (line 18) and module-level `.. deprecated:: ADK 2.1.0` (line 7) acknowledge that `ParallelAgent` will be removed in ADK 3.0. Judges who check live ADK best-practice surfaces will see this. `requirements.lock` pins `google-adk==2.0.0`, so the migration is not blocked by anything external.
**Fix:** Migrate to `google.adk.agents.workflow.Workflow` (or the current preferred parallel primitive) before submission.

### P2-4 — Generator instructions mention a tool name without checking it exists

**File:** `atelier-core/src/atelier/orchestrator/generator_ensemble.py:52-57`
**Issue:** The instruction string tells the LLM: "Attempt to generate the requested screen using the `stitch_generate_screen_from_text` tool." When `try_get_stitch_mcp_toolset()` returns `None` (degraded mode), the generator is told to call a tool that isn't bound. Gemini may hallucinate the tool call. Should branch the instruction on degradation status.
**Fix:** Pass `stitch_degradation.is_degraded` into the instruction template; use a fallback instruction when degraded.

### P2-5 — `app.py` has no Identity-Aware-Proxy / GEAP-native auth path

**File:** `atelier-core/src/atelier/auth/firebase.py`, `app.py:30,34`
**Issue:** Auth uses Firebase ID tokens (Identity Platform), which is fine, but the Build pillar's preferred path for agent-to-agent or service-to-service auth is Workload Identity Federation / GEAP service accounts. The agent card declares both `bearer` and `apiKey` schemes — the apiKey path (`X-Atelier-API-Key`) is declared on `agent_card.json:54-56` but no code path checks for that header.
**Fix:** Add the `X-Atelier-API-Key` header check, or drop the scheme from the card.

### P2-6 — `dream.py` production scorer is a hash of the brief

**File:** `atelier-core/src/atelier/api/dream.py:246-250`
**Issue:** `_staging_generate_fn` computes `0.78 + (digest % 100) / 1000` — guaranteed to always pass the κ ≥ 0.70 gate. The endpoint at line 227 raises HTTP 501 in non-development to prevent this from being used in prod, good. But the fact that the only scorer in the file is a fake means the DPO promote pipeline is non-functional even in development beyond a smoke test.
**Fix:** Wire a real scorer that invokes the tuned endpoint and runs the calibration seed.

### P2-7 — Trajectory recorder fakes per-candidate `surface_id` on every record

**File:** `atelier-core/src/atelier/api/generate.py:200`
**Issue:** `surface_id=uuid4()` is generated *inside* the per-candidate loop, so every candidate gets a unique random surface_id. The DPO pair miner groups by `surface_id` to find "different candidates for the same surface" (per `nodes/trajectory.py:237 by_surface`). With unique IDs per candidate, the miner can never group same-surface alternatives → DPO pair extraction yields zero pairs.
**Fix:** Hoist `surface_id = uuid4()` outside the loop; pass through from the BriefSpec/Surface model.

### P2-8 — `vertex_semantic.py` self-implements TF-IDF instead of using `text-embedding-005`

**File:** `atelier-core/src/atelier/memory/backends/vertex_semantic.py:100-137`
**Issue:** The "Vertex AI Memory Bank semantic backend" implements its own TF-IDF over a two-document corpus (lines 100-137). The constructor docstring (line 8) says "embedding via text-embedding-005" but no embedding API is called.
**Fix:** Either call Vertex `text-embedding-005` or drop the "semantic" naming.

### P2-9 — `agent_card.json` declares `"protocols": {"a2a": "1.0", "adk": "2.0-beta"}` — non-standard A2A field

**File:** `agent_card.json:41-44`
**Issue:** The A2A spec's `AgentCard` schema does not define a top-level `"protocols"` object. Clients that strict-validate against the spec will reject the card. The schema reference URL on line 2 (`https://raw.githubusercontent.com/anthropics/a2a-protocol/main/schema/agent_card.json`) is *not* the canonical Google A2A schema — A2A originated at Google (April 2025) and the schema repo is `github.com/google/A2A`, not `anthropics/a2a-protocol`. The schema $ref is broken.
**Fix:** Use the canonical schema URL; remove `protocols`; declare ADK version in a non-spec extension field if needed.

### P2-10 — `bigquery_session.append_event` uses `UPDATE` instead of streaming insert

**File:** `atelier-core/src/atelier/memory/bigquery_session.py:344-360`
**Issue:** Persisting an event uses `UPDATE` against a partitioned table. BigQuery `UPDATE` on streamed rows is subject to a 90-min streaming buffer; the update can fail with `Cannot mutate rows in the streaming buffer`. ADK 2.0 emits events at ~1Hz during a generation; the pattern will silently degrade frequently.
**Fix:** Append to an `events` table (one row per event), join on read; or use BigQuery's storage write API.

---

## Coverage Matrix — Files audited (10 of 10 from scope)

| File                                                         | Read | Imports verified | Key claim verified |
| ------------------------------------------------------------ | ---- | ---------------- | ------------------ |
| `agent_card.json`                                            | ✓    | n/a              | served? **no**     |
| `docs/dashboards/.well-known/agent.json`                     | ✓    | n/a              | divergent (P0-2)   |
| `atelier-core/src/atelier/orchestrator/runner.py`            | ✓    | ✓ ADK Runner real | uses Runner (line 338) |
| `atelier-core/src/atelier/orchestrator/generator_ensemble.py`| ✓    | ✓ ParallelAgent + LlmAgent real | uses real ADK |
| `atelier-core/src/atelier/orchestrator/governor.py`          | ✓    | ✓ stdlib + asyncio | no ADK use; pure Python MAPE-K |
| `atelier-core/src/atelier/intake/brief_parser.py`            | ✓    | ✓ LlmAgent imported | **never invoked** (P0-5) |
| `atelier-core/src/atelier/intake/source_resolver.py`         | ✓    | ✓ no ADK use     | hardcoded priors at line 147-153 |
| `atelier-core/src/atelier/intake/web_research.py`            | ✓    | ✓ google.genai + GoogleSearch real | grounding wired correctly |
| `atelier-core/src/atelier/integrations/stitch_mcp.py`        | ✓    | ✓ McpToolset + SseConnectionParams real | real MCP via ADK |
| `atelier-core/src/atelier/integrations/github_mcp.py`        | ✓    | ✓ httpx only     | **not MCP** (P1-4) |
| `atelier-core/src/atelier/memory/bigquery_session.py`        | ✓    | ✓ BaseSessionService real | subclasses ADK base; falls back to dict |
| `atelier-core/src/atelier/memory/backends/vertex_semantic.py`| ✓    | ✓ stdlib only    | **dict + TF-IDF**, NotImplementedError prod |
| `atelier-core/src/atelier/memory/backends/vertex_procedural.py`| ✓  | ✓ stdlib only    | **dict only**, NotImplementedError prod |
| `atelier-core/src/atelier/nodes/llm_judge.py`                | ✓    | ✓ vertexai lazy import | real client when mode=llm |
| `atelier-core/src/atelier/nodes/consensus.py`                | ✓    | ✓ no ADK         | function, not Agent (P0-3) |
| `atelier-core/src/atelier/nodes/trajectory.py`               | ✓    | ✓ stdlib + uuid  | dataclass only, no ADK |
| `atelier-core/src/atelier/models/model_registry.py`          | ✓    | ✓ stdlib only    | preview-05 model pins (P1-1) |
| `atelier-core/src/atelier/api/app.py`                        | ✓    | ✓ FastAPI only   | **no /.well-known route** (P0-1) |
| `atelier-core/src/atelier/api/generate.py`                   | ✓    | ✓ BQ + AtelierRunner real | bespoke REST, not A2A |
| `atelier-core/src/atelier/api/replay.py`                     | ✓    | ✓ BQ real        | reads trajectory_records |
| `atelier-core/src/atelier/api/dream.py`                      | ✓    | ✓ dreaming_module real | **fake scorer** (P2-6) |
| `examples/agents-cli-scaffold/agent.py`                      | ✓    | ✓ LlmAgent real  | isolated; model not in registry (P1-8) |
| `examples/agents-cli-scaffold/agent.yaml`                    | ✓    | n/a              | single-agent scaffold; no tools |

---

## Gaps (things I could not verify with code alone)

1. **Does `https://stitch.googleapis.com/mcp` exist as a publicly addressable MCP endpoint?** The URL is hardcoded but Google has not GA-announced a Stitch MCP server at that path as of 2026-05-28. The `mcp__stitch` MCP server in the auditor's own toolchain proxies to a different (internal) endpoint. Needs verification via curl with a valid service-account token.
2. **Is `google-adk==2.0.0` actually published?** `requirements.lock:20` pins it; I did not run `pip index versions google-adk`. If the lockfile resolved against a private mirror, the dep may not resolve in a clean Cloud Build.
3. **Does the agent actually deploy to Cloud Run?** `examples/agents-cli-scaffold/agent.yaml:25-33` declares `target: cloud_run, service: atelier-api-staging` but no deploy script was in scope; I cannot confirm a running endpoint exists.
4. **Is `gemini-3-flash` / `gemini-3-pro` GA on Vertex AI?** Per the audit constraints (no speculation), I cannot answer this — context7 would.

---

## Build-pillar coverage matrix

| Build component                                   | Status | Evidence (file:line)                                                                                                  |
| ------------------------------------------------- | ------ | --------------------------------------------------------------------------------------------------------------------- |
| **ADK Runner**                                    | ✅     | `runner.py:33,338-356` — real `from google.adk.runners import Runner`, called via `run_async`                          |
| **ADK LlmAgent**                                  | ✅     | `generator_ensemble.py:16,49-62`, `brief_parser.py:6,65-72`                                                            |
| **ADK ParallelAgent (deprecated)**                | ⚠️     | `generator_ensemble.py:17-18,64-67` — used but deprecation-flagged for ADK 3.0                                         |
| **ADK BaseSessionService**                        | ⚠️     | `bigquery_session.py:30,39` — real subclass, but falls back to in-memory on any BQ error; production never tested      |
| **ADK BaseAgent for N3d (ConsensusAgent)**        | ❌     | `consensus.py` — plain function `evaluate_candidate` (line 624); no `BaseAgent` subclass (P0-3)                        |
| **Agent Skills (new ADK 2.0 feature)**            | ❌     | `grep "AgentSkill\|skill_id" src` → 0 hits (P1-7)                                                                       |
| **Agent Studio**                                  | N/A    | No Agent Studio config / blueprint files in scope; out of code surface                                                  |
| **Agent Garden**                                  | N/A    | No Agent Garden publishing manifest in scope                                                                            |
| **A2A protocol — agent card discovery**           | ❌     | `app.py` has no `/.well-known/agent.json` route (P0-1); Firebase serves a divergent dashboard card (P0-2)               |
| **A2A protocol — task JSON-RPC endpoint**         | ❌     | No `POST /` or `POST /messages` JSON-RPC handler in `app.py` (P1-2)                                                    |
| **MCP — Stitch (Google design system)**           | ✅     | `stitch_mcp.py:29,326` — real `McpToolset(SseConnectionParams(url, headers))` via ADK MCP integration                  |
| **MCP — GitHub**                                  | ❌     | `github_mcp.py:104,131` — raw `httpx` REST v3 wrapper named "MCP" (P1-4); never instantiated from src                  |
| **Vertex AI Search Grounding (GoogleSearch)**     | ✅     | `web_research.py:373` — real `genai_types.Tool(google_search=genai_types.GoogleSearch())` via Vertex client            |
| **RAG / Vertex AI Memory Bank**                   | ❌     | `memory/backends/*.py` — in-memory dicts + stdlib TF-IDF; `NotImplementedError` in non-dev (P0-6)                       |
| **Gemini Models via Vertex AI**                   | ⚠️     | `llm_judge.py:776-779,851-906` — real `vertexai.init` + `GenerativeModel.generate_content`, **only if** env opts in (P0-4); preview-05 model pins (P1-1) |
| **A2UI**                                          | ❌     | `data_contracts.py:184` field exists but always `None` (P1-6); no `a2ui` package import anywhere                       |
| **AP2 / UCP (Universal Context Protocol)**        | ❌     | `grep "AP2\|ap2\|UCP" src` → 0 hits                                                                                     |
| **Cloud Marketplace integration**                 | ❌     | No marketplace metadata, manifest, or BillingAccount linkage in scope                                                   |
| **Agents CLI**                                    | ⚠️     | `examples/agents-cli-scaffold/agent.{py,yaml}` exists but uses non-registry model `gemini-3-pro`; runs an isolated bare LlmAgent, not the Atelier pipeline (P1-8) |

**Score (12 Build components, weighted 1.0 each):**
- ✅ used: **3** (ADK Runner, ADK LlmAgent, Vertex Grounding, Stitch MCP) — actually 4
- ⚠️ stub/partial: **4** (ParallelAgent deprecated, BaseSessionService fallback, Gemini Vertex opt-in, Agents CLI scaffold-only)
- ❌ missing: **7** (ConsensusAgent, Agent Skills, A2A discovery, A2A JSON-RPC, GitHub MCP, RAG, A2UI, AP2, Marketplace) — actually 9
- N/A: **2** (Agent Studio, Agent Garden)

**Net Build-pillar coverage estimate: ~25-30% real implementation, ~30% partial, ~40% missing.** The single largest scoring loss is the A2A discovery endpoint (P0-1) — a one-line fix that gates most of the A2A column.
