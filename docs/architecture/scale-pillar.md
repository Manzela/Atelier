# Scale Pillar — Model Catalog · Session Backend · Memory · Agent Engine

> How Atelier routes work to the right model tier, persists session state, and deploys to managed serverless infrastructure.

## Overview

The **Scale** pillar governs Atelier's operational envelope: which Gemini model tier handles each pipeline task, how session state and semantic memory are persisted across turns, and how the planner agent is deployed to Vertex AI Agent Engine for managed, serverless scaling. The platform surface (`/v1/platform/scale`) exposes a live snapshot of all three concerns — model routing catalog, backend mode, and deploy configuration — as an authenticated, read-only projection.

```
┌─────────────────────────────────────────────────────────────────────┐
│                          SCALE STACK                                │
├──────────────┬──────────────┬──────────────┬────────────────────────┤
│ Model        │ Session      │ Semantic     │ Agent Engine           │
│ Catalog      │ Backend      │ Memory       │ Deployment             │
│              │              │              │                        │
│ 3-tier       │ Vertex AI    │ Vertex AI    │ AdkApp wraps           │
│ Gemini       │ sessions or  │ Memory Bank  │ PlannerAgent;          │
│ routing      │ BigQuery     │ (scope-keyed)│ operator-deployed      │
│ table        │ or in-memory │              │ to us-central1         │
└──────────────┴──────────────┴──────────────┴────────────────────────┘
```

---

## 1. Model Catalog — Task-Aware Routing

`model_registry.py` is the single source of truth for every model assignment in the pipeline. Every task that touches a Gemini model has an explicit entry in `TASK_MODEL_ROUTING` — there are no implicit defaults and no task falls through to an unaudited model.

### Three-tier routing

| Tier           | Model ID                | Input price | Output price | Lifetime cap (per user) |
| -------------- | ----------------------- | ----------- | ------------ | ----------------------- |
| **Pro**        | `gemini-2.5-pro`        | $1.25/M tok | $10.00/M tok | 5,000,000 tokens        |
| **Flash**      | `gemini-2.5-flash`      | $0.30/M tok | $2.50/M tok  | 15,000,000 tokens       |
| **Flash-Lite** | `gemini-2.5-flash-lite` | $0.10/M tok | $0.40/M tok  | 60,000,000 tokens       |

### Routing table (from `TASK_MODEL_ROUTING`)

```python
# From atelier-core/src/atelier/models/model_registry.py

TASK_MODEL_ROUTING: dict[TaskType, str] = {
    # Pro — deep reasoning; quality gap vs Flash is measurable
    TaskType.PLANNER:             "gemini-2.5-pro",
    TaskType.JUDGE_ORIGINALITY:   "gemini-2.5-pro",
    TaskType.CLARIFY:             "gemini-2.5-pro",
    # Flash — generation volume; 6 candidates × 6 specialists per run
    TaskType.WEB_RESEARCH:        "gemini-2.5-flash",
    TaskType.UX_RESEARCH:         "gemini-2.5-flash",
    TaskType.IA_FLOW:             "gemini-2.5-flash",
    TaskType.WIREFRAME:           "gemini-2.5-flash",
    TaskType.UI_DESIGN:           "gemini-2.5-flash",
    TaskType.INTERACTION:         "gemini-2.5-flash",
    TaskType.FIXER:               "gemini-2.5-flash",
    TaskType.JUDGE_DESIGN:        "gemini-2.5-flash",
    TaskType.JUDGE_RELEVANCE:     "gemini-2.5-flash",
    TaskType.JUDGE_VISUAL:        "gemini-2.5-flash",
    # Flash-Lite — structured short outputs; 12.5× cheaper than Pro
    TaskType.BRIEF_PARSE:         "gemini-2.5-flash-lite",
    TaskType.TOKEN_GEN:           "gemini-2.5-flash-lite",
    TaskType.COPY_EDITOR:         "gemini-2.5-flash-lite",
    TaskType.JUDGE_ACCESSIBILITY: "gemini-2.5-flash-lite",
}
```

`calibrate_model(task_type)` resolves the model for a given task. Resolution order:

1. `GEMINI_MODEL_ID` env var override (hermetic test environments only — overrides all tasks).
2. Firebase Remote Config lookup (`model_routing_{task_type}` parameter) — fail-soft to step 3.
3. Static `TASK_MODEL_ROUTING` table.

`get_model_catalog()` returns a `ModelCatalogEntry` list for the platform surface, one entry per distinct model with its tier, token cap, and all task types it serves.

**Key files:**

- [`model_registry.py`](../../atelier-core/src/atelier/models/model_registry.py) — `TASK_MODEL_ROUTING`, `calibrate_model()`, `get_model_catalog()`
- [`platform.py`](../../atelier-core/src/atelier/api/platform.py) — `/scale` endpoint + `_model_catalog_payload()`

---

## 2. Session Backend — Multi-Implementation Protocol

`session_protocol.py` defines a `@runtime_checkable` `SessionBackend` Protocol with two async methods: `create_session` and `get_session`. Any conforming class can be injected into `AtelierRunner` without modifying the runner.

```python
# From atelier-core/src/atelier/memory/session_protocol.py

@runtime_checkable
class SessionBackend(Protocol):
    async def create_session(self, *, app_name, user_id, state, session_id) -> Session: ...
    async def get_session(self, *, app_name, user_id, session_id, config) -> Session | None: ...
```

Three implementations satisfy the Protocol:

| Implementation                 | When used                   | Durability       |
| ------------------------------ | --------------------------- | ---------------- |
| `VertexAiSessionService` (ADK) | `SESSION_BACKEND=vertex`    | Managed (Vertex) |
| `BigQuerySessionBackend`       | `SESSION_BACKEND=bigquery`  | Durable (BQ)     |
| `InMemorySessionService` (ADK) | Default / local dev / tests | Ephemeral        |

`_session_backend_mode()` in `platform.py` reads `SESSION_BACKEND` and surfaces the active tier at `/v1/platform/scale`.

---

## 3. Semantic Memory — Vertex AI Memory Bank Backend

`VertexSemanticMemoryBackend` (`memory/backends/vertex_semantic.py`) implements the `SemanticMemoryBackend` Protocol: scope-keyed reads and writes, TF-IDF similarity scoring (stdlib-only, no external ML dependency), and periodic consolidation.

```python
# From atelier-core/src/atelier/memory/backends/vertex_semantic.py

class VertexSemanticMemoryBackend:
    async def write_semantic(self, scope: MemoryScopeKey, content: str, ...) -> str:
        """Write one semantic memory; returns the Vertex resource name."""

    async def query_semantic(self, scope: MemoryScopeKey, query_text: str,
                             *, top_k: int = 5, min_similarity: float = 0.0) -> list[SemanticHit]:
        """Top-k TF-IDF vector search within scope."""

    async def consolidate(self, scope: MemoryScopeKey, *, dry_run: bool = True) -> ConsolidationReport:
        """Periodic dedup + cluster-summarize."""
```

**Scope isolation.** Memories are keyed by `MemoryScopeKey.encode()` — tenant, session, and surface are encoded into the key so queries never cross tenant boundaries.

**Production wiring.** `SESSION_BACKEND=vertex` routes the managed `VertexAiMemoryBankService` (via `orchestrator.backend_factory`); the `VertexSemanticMemoryBackend` class remains the offline/dev semantic store and the Protocol shim for type checking.

**Durability.** The per-tenant design-system record is owned separately by `atelier.durability.design_system_persister` (Firestore online; JSON on-disk offline). This backend is the semantic similarity substrate; design-system ownership does not overlap.

**Key files:**

- [`vertex_semantic.py`](../../atelier-core/src/atelier/memory/backends/vertex_semantic.py) — `VertexSemanticMemoryBackend`
- [`session_protocol.py`](../../atelier-core/src/atelier/memory/session_protocol.py) — `SessionBackend` Protocol
- [`bigquery_session.py`](../../atelier-core/src/atelier/memory/bigquery_session.py) — BQ session implementation
- [`scope.py`](../../atelier-core/src/atelier/memory/scope.py) — `MemoryScopeKey` encoding

---

## 4. Agent Engine Deployment

`agent_engine_deploy.py` packages the Atelier planner agent as a `vertexai.agent_engines.AdkApp` and deploys it to Vertex AI Agent Engine — a managed, serverless ADK runtime. The deploy is operator-gated: it requires Application Default Credentials for the `atelier-build-2026` project and the Agent Engine API enabled.

```python
# From atelier-core/src/atelier/agent_engine_deploy.py

def deploy_agent_engine() -> str:
    """Deploy the Atelier planner to Vertex AI Agent Engine.

    Returns the deployed resource name. Fails loud on any error —
    deploy failures are never swallowed.
    """
    adk_version = validate_adk_pin()  # enforces AT-002: google-adk==2.1.x
    config = resolve_config()         # project, location, staging_bucket

    vertexai.init(project=config["project"], location=config["location"],
                  staging_bucket=config["staging_bucket"])
    app = AdkApp(agent=PlannerAgent().llm, enable_tracing=True)
    remote_app = create(app, display_name=config["display_name"],
                        requirements=deployment_requirements(), extra_packages=["."])
    return str(remote_app.resource_name)
```

**ADK pin enforcement.** `validate_adk_pin()` reads `importlib.metadata.version("google-adk")` and raises `AgentEngineDeployError` if the installed version does not start with `2.1`. A drift from the AT-002 pin is a hard failure — the deploy never ships an unverified ADK version.

### Deploy configuration

| Parameter      | Env var                  | Default                                 |
| -------------- | ------------------------ | --------------------------------------- |
| GCP project    | `GOOGLE_CLOUD_PROJECT`   | `atelier-build-2026`                    |
| Region         | `GOOGLE_CLOUD_LOCATION`  | `us-central1`                           |
| Display name   | `ATELIER_AGENT_NAME`     | `atelier-planner-engine`                |
| Staging bucket | `ATELIER_STAGING_BUCKET` | `gs://atelier-build-2026-agent-staging` |

### Pinned sandbox requirements

```python
_DEPLOY_REQUIREMENTS = (
    "google-adk>=2.1.0,<3",
    "google-genai>=1.0,<3",
    "google-cloud-aiplatform>=1.71,<2",
    "pydantic>=2.6,<3",
)
```

These are kept in lockstep with the AT-002 pins in `pyproject.toml` so the served runtime resolves the same major versions as the verified build.

`resolve_config()` is exercised by `/v1/platform/scale → deploy_config` at request time (fail-soft: `{"available": false}` if the import fails).

**Key files:**

- [`agent_engine_deploy.py`](../../atelier-core/src/atelier/agent_engine_deploy.py) — `deploy_agent_engine()`, `validate_adk_pin()`, `resolve_config()`
- [`platform.py`](../../atelier-core/src/atelier/api/platform.py) — `/scale` endpoint + `_deploy_config_payload()`

---

## `/v1/platform/scale` Response Shape

```
GET /v1/platform/scale
{
  "available": true,
  "model_catalog": {
    "available": true,
    "models": [
      { "model_id": "gemini-2.5-pro",        "tier": "pro",        "token_cap": 5000000,  "task_types": ["planner", ...] },
      { "model_id": "gemini-2.5-flash",       "tier": "flash",      "token_cap": 15000000, "task_types": ["ux_research", ...] },
      { "model_id": "gemini-2.5-flash-lite",  "tier": "flash_lite", "token_cap": 60000000, "task_types": ["brief_parse", ...] }
    ]
  },
  "session_backend": "vertex",
  "usage_backend": "firestore",
  "deploy_config": {
    "available": true,
    "project": "atelier-build-2026",
    "location": "us-central1",
    "display_name": "atelier-planner-engine",
    "staging_bucket": "gs://atelier-build-2026-agent-staging"
  },
  "health": { "available": true, "status": "healthy", "service": "atelier-api" }
}
```

---

## Related Files

- [`model_registry.py`](../../atelier-core/src/atelier/models/model_registry.py) — model routing table + catalog
- [`agent_engine_deploy.py`](../../atelier-core/src/atelier/agent_engine_deploy.py) — Agent Engine deploy + ADK pin enforcement
- [`session_protocol.py`](../../atelier-core/src/atelier/memory/session_protocol.py) — `SessionBackend` Protocol
- [`vertex_semantic.py`](../../atelier-core/src/atelier/memory/backends/vertex_semantic.py) — semantic memory backend
- [`bigquery_session.py`](../../atelier-core/src/atelier/memory/bigquery_session.py) — BQ session implementation
- [`platform.py`](../../atelier-core/src/atelier/api/platform.py) — `/scale` endpoint
