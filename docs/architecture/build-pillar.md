# Build Pillar — Registry · Topology · A2A · MCP · Garden

> How Atelier defines, wires, and publishes its agents for autonomous design work.

## Overview

The **Build** pillar is the structural definition of what Atelier is: the full roster of agents, the hand-off DAG they form, the A2A skills they advertise, the MCP toolsets they carry, and the operator-gated path for registering agents in Vertex AI Agent Garden. The platform surface (`/v1/platform/build` and `/v1/platform/topology`) exposes this definition as read-only, authenticated JSON — a live projection of the exact symbols that drive the pipeline, not a separately maintained catalogue.

```
┌────────────────────────────────────────────────────────────────────┐
│                          BUILD STACK                               │
├───────────┬──────────┬──────────┬──────────┬──────────┬───────────┤
│ Agent     │ DAG      │ A2A      │ MCP      │ Per-agent │ Garden   │
│ Registry  │ Topology │ Skills   │ Toolsets │ Cards     │ Reg.     │
│           │          │          │          │           │          │
│ 18 agents │ DDLC     │ agent_   │ stitch_  │ Full      │ Operator │
│ projected │ hand-off │ card.json│ mcp      │ descriptor│ gated    │
│ read-only │ edges    │ skills[] │ wiring   │ + prompt  │ (env)    │
└───────────┴──────────┴──────────┴──────────┴──────────┴───────────┘
```

---

## 1. Agent Registry — Single-Source Roster

`agent_registry.py` builds a read-only `AgentDescriptor` for every agent by reading already-instantiated, frozen module-level constants. No agent is constructed, no Vertex call is made. The registry is therefore fully hermetic and fail-soft-friendly.

```python
# From atelier-core/src/atelier/orchestrator/agent_registry.py

@dataclass(frozen=True)
class AgentDescriptor:
    """Read-only identity + wiring record for one Atelier agent."""
    id: str
    name: str
    kind: AgentKind          # planner | specialist | judge | critic | fixer | intake
    adk_type: str
    model_id: str
    task_type: TaskType | None
    tools: list[str]
    prompt: str
    prompt_source: str       # "static" | "vertex_agent_registry"
    upstream_keys: list[str]
    output_key: str | None
    subagent_of: str | None
```

The complete roster returned by `get_agent_registry()`, ordered by pipeline position:

| Kind         | Count | Source                                               |
| ------------ | ----- | ---------------------------------------------------- |
| `planner`    | 1     | `planner._PLANNER_SYSTEM_PROMPT` + `PlannerAgent`    |
| `intake`     | 1     | `brief_parser.BriefParserAgent` (schema-constrained) |
| `specialist` | 6     | `specialists.get_specialist_specs()` (DDLC N3a)      |
| `judge`      | 5     | `llm_judge.JUDGE_PROMPTS` + `JUDGE_MODEL_CONFIG`     |
| `critic`     | 4     | `critique_panel.get_critic_specs()`                  |
| `fixer`      | 1     | `fixer._FIXER_SYSTEM_PROMPT` + `FIXER_MODEL`         |

**Prompt provenance.** Specialists carry a runtime override hook (`_fetch_prompt_from_agent_registry`) gated by `ATELIER_AGENT_REGISTRY_ENABLED`. When the env var is truthy the hook may pull the prompt from Vertex AI Agent Registry (fail-soft to the static role); the descriptor records this as `prompt_source="vertex_agent_registry"`. All other agents are always `"static"`.

**Key files:**

- [`agent_registry.py`](../../atelier-core/src/atelier/orchestrator/agent_registry.py) — `AgentDescriptor` dataclass + `get_agent_registry()`
- [`specialists.py`](../../atelier-core/src/atelier/orchestrator/specialists.py) — DDLC specialist specs (the upstream source)
- [`llm_judge.py`](../../atelier-core/src/atelier/nodes/llm_judge.py) — `JUDGE_PROMPTS` + `JUDGE_MODEL_CONFIG`

---

## 2. DAG Topology — DDLC Hand-Off Contract

The six DDLC specialists execute in a directed order defined by their `upstream_keys` and `output_key` fields. `/v1/platform/topology` materialises this as nodes and edges from the hand-off contract — it is the **static** pipeline DAG, not a per-run span tree (replay spans are flat; `parent_span_id`/`duration_ms` are not populated).

```python
# From atelier-core/src/atelier/api/platform.py

@router.get("/topology")
async def get_topology(user: ...) -> dict:
    """Return the DDLC specialist DAG built from the hand-off contract."""
    nodes = [{"id": spec.output_key, "label": spec.name, ...} for spec in specs]
    edges = [
        {"from": upstream, "to": spec.output_key}
        for spec in specs
        for upstream in spec.upstream_keys
        if upstream in output_keys   # specialist-to-specialist edges only
    ]
```

The six specialist nodes (in execution order):

| Node            | Output key    | Upstream inputs                    |
| --------------- | ------------- | ---------------------------------- |
| UX Researcher   | `ux_research` | brief + `research_findings` (WRAI) |
| IA / Flow       | `ia_flow`     | `ux_research`                      |
| Wireframer      | `wireframe`   | `ia_flow`                          |
| UI Designer     | `ui_design`   | `wireframe` + Stitch MCP           |
| Interaction     | `interaction` | `ui_design`                        |
| Token Generator | `token_gen`   | `ui_design`                        |

---

## 3. A2A Skills — Agent Card

Atelier publishes a `agent_card.json` at the project root (A2A Protocol 0.3.0). Four skills are declared:

```json
// atelier-core/agent_card.json (excerpt)
{
  "protocolVersion": "0.3.0",
  "skills": [
    { "id": "generate-ui", "tags": ["ui-generation", "html", "css"] },
    { "id": "review-ui", "tags": ["dorav-scoring", "evaluation"] },
    { "id": "campaign-orchestrate", "tags": ["multi-surface", "planning"] },
    { "id": "design-system-infer", "tags": ["token-inference", "padi"] }
  ],
  "protocols": { "a2a": "0.3.0", "adk": "2.1" },
  "authentication": { "schemes": ["bearer", "apiKey"] }
}
```

`/v1/platform/build` reads the card at request time via `_load_agent_card()` (fail-soft: returns `{"available": false}` if absent) and surfaces skill metadata alongside the agent roster counts.

---

## 4. MCP Toolsets — Stitch Integration

The Stitch MCP toolset (`stitch_mcp`) is the sole externally-connected toolset in the current build. It is wired to the UI Designer specialist — the only DDLC node that writes production HTML/CSS from a component library. The registry derives toolset membership from the descriptor's `tools` field:

```python
# platform.py: /build endpoint
toolset_to_agents: dict[str, list[str]] = {}
for d in registry:
    for tool in d.tools:
        toolset_to_agents.setdefault(tool, []).append(d.id)
```

The `stitch_mcp` toolset is declared in `specialist.uses_stitch` in `specialists.py` and projected faithfully into `AgentDescriptor.tools` by the registry — there is no separate wiring table.

---

## 5. Per-Agent Cards — Full Descriptor Endpoint

`GET /v1/platform/agents/{agent_id}` returns the full `AgentDescriptor` for one agent, including the static system prompt, hand-off inputs (`upstream_keys`), and output key. This enables an A2A peer or operator toolchain to inspect an agent's prompt and wiring without reading source code.

```python
# platform.py
@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, user: ...) -> dict:
    for d in get_agent_registry():
        if d.id == agent_id:
            return {"available": True, "agent": _descriptor_full(d)}
    return {"available": False, "reason": "agent_not_found"}
```

A missing `agent_id` is fail-soft (`available: false`) rather than a 404 — the registry is a fixed roster, and an unknown id is a client error, not a server fault.

---

## 6. Agent Garden Registration — Operator-Gated

Specialists read their runtime prompt via `_fetch_prompt_from_agent_registry` in `specialists.py`, gated by `ATELIER_AGENT_REGISTRY_ENABLED`. When enabled, the hook attempts a Vertex AI Agent Registry lookup and fails soft to the static `spec.role` if the registry is unavailable. This is the extension point for registering and managing specialist prompts in Vertex AI Agent Garden without a code deploy.

The gate is env-var-only and off by default — no production traffic is affected until an operator explicitly sets the env var on the Cloud Run service.

---

## `/v1/platform/build` Response Shape

```
GET /v1/platform/build
{
  "available": true,
  "agent_card": { "available": true, "name": "Atelier", "version": "0.1.1-alpha", ... },
  "skills": [ { "id": "generate-ui", ... }, ... ],
  "mcp_toolsets": [ { "toolset": "stitch_mcp", "agents": ["specialist_uidesigner"] } ],
  "counts": {
    "agents_total": 18,
    "by_kind": { "planner": 1, "intake": 1, "specialist": 6, "judge": 5, "critic": 4, "fixer": 1 },
    "skills": 4,
    "mcp_toolsets": 1
  }
}
```

---

## Related Files

- [`agent_registry.py`](../../atelier-core/src/atelier/orchestrator/agent_registry.py) — full roster projection
- [`platform.py`](../../atelier-core/src/atelier/api/platform.py) — `/agents`, `/build`, `/topology` endpoints
- [`agent_card.json`](../../atelier-core/agent_card.json) — A2A skill declarations
- [`specialists.py`](../../atelier-core/src/atelier/orchestrator/specialists.py) — DDLC specialist specs + Stitch gate
