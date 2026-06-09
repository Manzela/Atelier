"""GET /v1/platform/* — read-only platform introspection API (Phase B, Step 2).

A thin, authenticated, **read-only** projection over Atelier's already-defined
internals: the agent registry, the model catalog, the system DAG topology, the
usage/governance snapshot, the deploy config, and recent runs. It exposes what
the system *is* — it invents no agent logic and writes nothing.

Hard invariants (audit-derived, non-negotiable — see the Phase A P0 fixes):

* **GET-only.** There are no write endpoints. Writes through a platform/MCP
  surface are exactly the anti-pattern the audit flagged; the only mutation
  paths remain the governed ``/v1/generate`` / ``/v1/a2a`` entry points.
* **Always authenticated.** Every handler takes ``Depends(require_auth)``.
* **Tenant from the verified JWT, never the client.** Tenant-scoped data
  (recent runs, identity) is keyed off ``FirebaseUser.tenant_id`` — a value
  derived from the verified token (``firebase.py``: ``atelier_tenant`` claim or
  uid). No endpoint accepts a client-supplied tenant.
* **Fail-soft everywhere.** A source that is unavailable (BigQuery offline, a
  deploy-config lookup that raises) returns ``{"available": false, "reason":
  ...}`` with HTTP 200 — never a 500, never a raw exception string. Error text
  mirrors ``a2a.py``: only ``type(exc).__name__`` is surfaced (the audit
  flagged ``generate.py``'s raw ``str(e)`` echo as an info leak).

Two honesty constraints carried from the audit, stated in the payloads:

* Replay spans are **flat** — the backend does not populate
  ``parent_span_id`` / ``duration_ms`` — so ``/topology`` describes the static
  pipeline DAG (from the specialist hand-off contract), not a per-run span tree.
* ``/optimize`` reports observed spend as **telemetry**, and explicitly does
  NOT claim per-run/aggregate spend caps are *enforced* (RR-05 is open).

PRD Reference: §7.1 (API surface). Mirrors ``api/replay.py`` for the
auth + tenant + fail-soft pattern.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from atelier.auth.firebase import FirebaseUser, require_auth
from atelier.models.model_registry import (
    TIER_TOKEN_CAPS,
    get_model_catalog,
)
from atelier.orchestrator.agent_registry import AgentDescriptor, get_agent_registry
from atelier.orchestrator.specialists import SPECIALIST_OUTPUT_KEYS, get_specialist_specs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/platform", tags=["platform"])


# ---------------------------------------------------------------------------
# Fail-soft helper
# ---------------------------------------------------------------------------


def _unavailable(reason_exc: Exception, *, context: str) -> dict[str, Any]:
    """Build a fail-soft ``{"available": false, ...}`` body (HTTP 200).

    Mirrors the ``a2a.py`` error shape: only ``type(exc).__name__`` is exposed —
    never the raw ``str(exc)`` (the audit flagged that as an info leak). The full
    detail is logged server-side for operators.
    """
    logger.warning(
        "atelier.platform.source_unavailable",
        extra={"context": context, "error": type(reason_exc).__name__},
    )
    return {"available": False, "reason": type(reason_exc).__name__}


# ---------------------------------------------------------------------------
# Descriptor serialization
# ---------------------------------------------------------------------------


def _descriptor_summary(d: AgentDescriptor) -> dict[str, Any]:
    """Compact agent row for the list endpoint (no prompt body)."""
    return {
        "id": d.id,
        "name": d.name,
        "kind": d.kind,
        "adk_type": d.adk_type,
        "description": d.description,
        "model_id": d.model_id,
        "task_type": d.task_type.value if d.task_type is not None else None,
        "tools": list(d.tools),
        "prompt_source": d.prompt_source,
        "subagent_of": d.subagent_of,
    }


def _descriptor_full(d: AgentDescriptor) -> dict[str, Any]:
    """Full agent descriptor including the prompt body and hand-off contract."""
    return {
        **_descriptor_summary(d),
        "prompt": d.prompt,
        "upstream_keys": list(d.upstream_keys),
        "output_key": d.output_key,
    }


# ---------------------------------------------------------------------------
# GET /agents — roster summary
# ---------------------------------------------------------------------------


@router.get("/agents", summary="List every Atelier agent (summary).")
async def list_agents(
    user: Annotated[FirebaseUser, Depends(require_auth)],  # noqa: ARG001 — auth-gated read
) -> dict[str, Any]:
    """Return the full agent roster as summary rows (no prompt bodies)."""
    registry = get_agent_registry()
    counts: dict[str, int] = {}
    for d in registry:
        counts[d.kind] = counts.get(d.kind, 0) + 1
    return {
        "available": True,
        "count": len(registry),
        "counts_by_kind": counts,
        "agents": [_descriptor_summary(d) for d in registry],
    }


# ---------------------------------------------------------------------------
# GET /agents/{agent_id} — full descriptor
# ---------------------------------------------------------------------------


@router.get("/agents/{agent_id}", summary="Full descriptor for one agent.")
async def get_agent(
    agent_id: str,
    user: Annotated[FirebaseUser, Depends(require_auth)],  # noqa: ARG001 — auth-gated read
) -> dict[str, Any]:
    """Return one agent's full descriptor (prompt + config), or available:false.

    A missing id is fail-soft (``available: false``) rather than a 404 — the
    registry is a fixed roster, so an unknown id is a client mistake, not a
    server fault, and the dashboard renders the soft body uniformly.
    """
    for d in get_agent_registry():
        if d.id == agent_id:
            return {"available": True, "agent": _descriptor_full(d)}
    return {"available": False, "reason": "agent_not_found"}


# ---------------------------------------------------------------------------
# GET /build — registry summary + agent-card skills + MCP toolsets + counts
# ---------------------------------------------------------------------------


def _load_agent_card() -> dict[str, Any] | None:
    """Read the repo-root ``agent_card.json`` the same way ``app.py`` serves it.

    Returns the parsed card, or ``None`` if it is absent/unparseable (fail-soft).
    """
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    # Mirror app.py: agent_card.json sits at parents[3] of this module
    # (src/atelier/api/platform.py -> atelier-core/agent_card.json).
    card_path = Path(__file__).resolve().parents[3] / "agent_card.json"
    if not card_path.exists():
        return None
    try:
        parsed: dict[str, Any] = json.loads(card_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning(
            "atelier.platform.agent_card_unreadable",
            extra={"error": type(exc).__name__},
        )
        return None
    return parsed


@router.get("/build", summary="Build surface: agents, skills, MCP toolsets, counts.")
async def get_build(
    user: Annotated[FirebaseUser, Depends(require_auth)],  # noqa: ARG001 — auth-gated read
) -> dict[str, Any]:
    """Summarize what Atelier ships: agent roster, A2A skills, MCP toolsets."""
    registry = get_agent_registry()
    counts_by_kind: dict[str, int] = {}
    for d in registry:
        counts_by_kind[d.kind] = counts_by_kind.get(d.kind, 0) + 1

    # MCP toolsets: derived from the registry's tool labels (the single
    # Stitch-carrying UI Designer is the only MCP-wired agent today).
    toolset_to_agents: dict[str, list[str]] = {}
    for d in registry:
        for tool in d.tools:
            toolset_to_agents.setdefault(tool, []).append(d.id)
    mcp_toolsets = [
        {"toolset": name, "agents": sorted(agents)}
        for name, agents in sorted(toolset_to_agents.items())
    ]

    card = _load_agent_card()
    skills: list[dict[str, Any]] = []
    card_meta: dict[str, Any] = {"available": False}
    if card is not None:
        raw_skills = card.get("skills", [])
        if isinstance(raw_skills, list):
            for s in raw_skills:
                if isinstance(s, dict):
                    skills.append(
                        {
                            "id": s.get("id"),
                            "name": s.get("name"),
                            "description": s.get("description"),
                            "tags": s.get("tags", []),
                        }
                    )
        protocols = card.get("protocols", {})
        card_meta = {
            "available": True,
            "name": card.get("name"),
            "version": card.get("version"),
            "protocolVersion": card.get("protocolVersion"),
            "protocols": protocols if isinstance(protocols, dict) else {},
        }

    return {
        "available": True,
        "agent_card": card_meta,
        "skills": skills,
        "mcp_toolsets": mcp_toolsets,
        "counts": {
            "agents_total": len(registry),
            "by_kind": counts_by_kind,
            "skills": len(skills),
            "mcp_toolsets": len(mcp_toolsets),
        },
    }


# ---------------------------------------------------------------------------
# GET /topology — the static pipeline DAG
# ---------------------------------------------------------------------------


@router.get("/topology", summary="System DAG: specialist nodes + hand-off edges.")
async def get_topology(
    user: Annotated[FirebaseUser, Depends(require_auth)],  # noqa: ARG001 — auth-gated read
) -> dict[str, Any]:
    """Return the DDLC specialist DAG built from the hand-off contract.

    Nodes are the 6 DDLC specialists (keyed by ``output_key``); edges are drawn
    from each spec's ``upstream_keys`` to its own ``output_key`` — i.e. the
    genuine state hand-offs that make the sequence a pipeline rather than six
    independent prompts. Only edges whose source is itself a specialist output
    are drawn (WRAI ``research_findings`` is an external input, not a node here).

    NOTE: this is the **static** pipeline DAG. It is NOT a per-run span tree —
    replay spans are flat (the backend does not populate ``parent_span_id`` /
    ``duration_ms``), so no real parent/child timing graph exists to surface.
    """
    specs = get_specialist_specs()
    output_keys = set(SPECIALIST_OUTPUT_KEYS)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for spec in specs:
        nodes.append(
            {
                "id": spec.output_key,
                "label": spec.name,
                "kind": "specialist",
                "model": spec.task_type.value if spec.task_type is not None else None,
            }
        )
        for upstream in spec.upstream_keys:
            # Only draw edges between specialist nodes; external inputs
            # (e.g. WRAI research_findings) are not nodes in this DAG.
            if upstream in output_keys:
                edges.append({"from": upstream, "to": spec.output_key})

    return {
        "available": True,
        "kind": "static_pipeline_dag",
        "note": (
            "Static DDLC hand-off DAG (from specialist upstream_keys). "
            "Not a per-run span tree: replay spans are flat."
        ),
        "nodes": nodes,
        "edges": edges,
    }


# ---------------------------------------------------------------------------
# GET /scale — model catalog + backend mode + deploy config + health rollup
# ---------------------------------------------------------------------------


def _session_backend_mode() -> str:
    """Resolve the session/memory backend mode (mirrors the durability helpers).

    ``SESSION_BACKEND`` selects the persistence tier: ``vertex`` in production
    (Agent Engine sessions / Vertex semantic memory), ``memory`` otherwise.
    """
    return os.getenv("SESSION_BACKEND", "memory").strip().lower() or "memory"


def _model_catalog_payload() -> dict[str, Any]:
    """Serialize the model catalog, fail-soft."""
    try:
        catalog = get_model_catalog()
    except Exception as exc:  # noqa: BLE001
        return _unavailable(exc, context="model_catalog")
    return {
        "available": True,
        "models": [
            {
                "model_id": e.model_id,
                "display_name": e.display_name,
                "tier": e.tier,
                "token_cap": e.token_cap,
                "task_types": [t.value for t in e.task_types],
            }
            for e in catalog
        ],
    }


def _deploy_config_payload() -> dict[str, Any]:
    """Resolve the Agent Engine deploy config, fail-soft."""
    try:
        from atelier.agent_engine_deploy import resolve_config  # noqa: PLC0415

        config = resolve_config()
    except Exception as exc:  # noqa: BLE001
        return _unavailable(exc, context="deploy_config")
    return {"available": True, **config}


@router.get("/scale", summary="Scale surface: model catalog, backends, deploy config.")
async def get_scale(
    user: Annotated[FirebaseUser, Depends(require_auth)],  # noqa: ARG001 — auth-gated read
) -> dict[str, Any]:
    """Return the scaling envelope: model routing catalog + backend modes.

    Each sub-source is independently fail-soft so a single offline dependency
    degrades only its own block (``available: false``) — never the whole call.
    """
    return {
        "available": True,
        "model_catalog": _model_catalog_payload(),
        "session_backend": _session_backend_mode(),
        "usage_backend": _usage_backend_mode(),
        "deploy_config": _deploy_config_payload(),
        "health": {"available": True, "status": "healthy", "service": "atelier-api"},
    }


# ---------------------------------------------------------------------------
# GET /govern — per-tier usage + identity + safety categories + thresholds
# ---------------------------------------------------------------------------


def _usage_backend_mode() -> str:
    """Return the configured usage-counter backend ("memory" | "firestore")."""
    try:
        from atelier.durability.usage_counter import get_usage_store  # noqa: PLC0415

        return get_usage_store().backend
    except Exception:  # noqa: BLE001
        return "unknown"


def _per_tier_usage(user: FirebaseUser) -> dict[str, Any]:
    """Read the authed user's per-tier usage snapshot against the tier caps.

    Tenant/identity scoping: the snapshot is keyed off ``user.uid`` (the
    verified Firebase uid), never a client value. Fail-soft: any store error
    (e.g. fail-closed Firestore read) degrades to ``available: false`` rather
    than propagating a 503/500 through this read-only surface.
    """
    try:
        from atelier.durability.usage_counter import get_usage_store  # noqa: PLC0415

        store = get_usage_store()
        snapshot = store.snapshot(user.uid)
    except Exception as exc:  # noqa: BLE001
        return _unavailable(exc, context="usage_snapshot")

    used = snapshot.per_tier()
    tiers: dict[str, dict[str, int]] = {}
    for tier, cap in TIER_TOKEN_CAPS.items():
        tier_used = int(used.get(tier, 0))
        tiers[tier] = {
            "used": tier_used,
            "cap": cap,
            "remaining": max(0, cap - tier_used),
        }
    return {
        "available": True,
        "tiers": tiers,
        "total_tokens": snapshot.total_tokens,
    }


def _rate_and_breaker_thresholds() -> dict[str, Any]:
    """Surface the operator-set rate-limit + circuit-breaker thresholds.

    Read from the live usage store instance so the dashboard shows the values
    actually in force (env-overridable). Fail-soft to ``available: false``.
    """
    try:
        from atelier.durability.usage_counter import get_usage_store  # noqa: PLC0415

        store = get_usage_store()
        # Read the in-force thresholds the store was constructed with (env-
        # overridable). These are plain config values, surfaced read-only.
        rate_limit = {
            "max_requests": store._rl_max,
            "window_seconds": store._rl_window,
        }
        circuit_breaker = {
            "global_token_budget_per_window": store._global_budget,
            "window_seconds": store._global_window,
            "cooldown_seconds": store._breaker_cooldown,
            "enabled": store._global_budget > 0,
        }
    except Exception as exc:  # noqa: BLE001
        return _unavailable(exc, context="thresholds")
    return {
        "available": True,
        "rate_limit": rate_limit,
        "circuit_breaker": circuit_breaker,
    }


def _model_armor_categories() -> dict[str, Any]:
    """Surface the always-on Model Armor injection-marker categories.

    The deterministic input guard (``model_armor_callbacks``) blocks a
    high-confidence set of natural-language prompt-injection markers. We expose
    the marker count and whether the Vertex Model Armor template is enabled —
    not the raw regexes (which are a detection surface).
    """
    try:
        from atelier.models.model_armor_callbacks import (  # noqa: PLC0415
            _INJECTION_PATTERNS,
        )

        marker_count = len(_INJECTION_PATTERNS)
    except Exception as exc:  # noqa: BLE001
        return _unavailable(exc, context="model_armor")
    template_enabled = os.getenv("ATELIER_MODEL_ARMOR_ENABLED", "").lower() in (
        "1",
        "true",
        "yes",
    )
    return {
        "available": True,
        "deterministic_injection_guard": {
            "always_on": True,
            "marker_count": marker_count,
        },
        "vertex_model_armor_template": {"enabled": template_enabled},
    }


@router.get("/govern", summary="Governance: per-tier usage, identity, safety, thresholds.")
async def get_govern(
    user: Annotated[FirebaseUser, Depends(require_auth)],
) -> dict[str, Any]:
    """Return the governance snapshot for the authed identity.

    Usage is the per-tier lifetime token meter for *this* user (used + remaining
    == cap, per :data:`TIER_TOKEN_CAPS`); identity echoes only the verified,
    non-sensitive claims; safety lists the Model Armor categories; thresholds
    surface the in-force rate-limit + circuit-breaker settings. Every sub-source
    is fail-soft.
    """
    return {
        "available": True,
        "identity": {
            "uid": user.uid,
            "tenant_id": user.tenant_id,
            "email_verified": user.email_verified,
        },
        "usage": _per_tier_usage(user),
        "usage_backend": _usage_backend_mode(),
        "model_armor": _model_armor_categories(),
        "thresholds": _rate_and_breaker_thresholds(),
    }


# ---------------------------------------------------------------------------
# GET /optimize — recent runs (tenant-scoped), each deep-linking to replay
# ---------------------------------------------------------------------------


@router.get("/optimize", summary="Optimize surface: recent runs (tenant-scoped).")
async def get_optimize(
    user: Annotated[FirebaseUser, Depends(require_auth)],
    limit: int = 20,
) -> dict[str, Any]:
    """Return the tenant's recent runs as telemetry, each linking to replay.

    Tenant-scoped: the run list is queried with ``user.tenant_id`` (verified
    JWT), never a client value. Fail-soft: when BigQuery is unavailable the
    body is ``{"available": false, ...}`` with HTTP 200 — never a 500.

    HONESTY (RR-05 open): the cost figures are **observed telemetry**, not an
    enforced spend cap. This surface does not, and must not, claim per-run or
    aggregate spend caps are enforced.
    """
    from atelier.api.replay import list_recent_runs  # noqa: PLC0415

    try:
        runs = await list_recent_runs(user.tenant_id, limit=limit)
    except Exception as exc:  # noqa: BLE001 — read-only surface must never 500
        return _unavailable(exc, context="recent_runs")

    if runs is None:
        return {
            "available": False,
            "reason": "bigquery_unavailable",
            "spend_caps_enforced": False,
        }

    return {
        "available": True,
        "spend_caps_enforced": False,
        "note": (
            "Cost figures are observed telemetry, not an enforced spend cap "
            "(RR-05 open). Each run deep-links to /v1/replay/{session_id}."
        ),
        "count": len(runs),
        "runs": [r.model_dump() for r in runs],
    }
