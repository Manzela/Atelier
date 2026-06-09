"""Per-agent A2A 0.3.0 AgentCard generation — single source, zero drift.

Exports one pure function:

    build_agent_cards(registry) -> dict[str, dict]

that converts a list of :class:`~atelier.orchestrator.agent_registry.AgentDescriptor`
objects into a mapping of ``agent_id -> A2A 0.3.0 AgentCard dict``.  The cards
are generated from the same live registry that drives ``/v1/platform/agents``,
so they can never drift from the code.

Card schema mirrors ``agent_card.json`` (the top-level Atelier card):

    name, description, version, protocolVersion, url, provider,
    skills, protocols, authentication, capabilities,
    defaultInputModes, defaultOutputModes

The ``url`` is the per-agent well-known path:
``https://atelier.autonomous-agent.dev/.well-known/agents/{id}/agent-card.json``

A ``generate_committed_cards`` helper regenerates and writes all cards under
``atelier-core/agent_cards/{id}.agent-card.json`` so a CI drift-guard test can
compare the committed artifacts against a fresh generation.

Design constraints (audit-derived):
- Pure function: no network, no GCP credentials, no side effects.
- Hermetic: safe to call in tests and CI without any live services.
- Fail-soft: individual card build errors log and yield a minimal card rather
  than halting the entire generation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — shared across all generated cards
# ---------------------------------------------------------------------------

_PROTOCOL_VERSION: str = "0.3.0"
_ADK_VERSION: str = "2.1"
_PROVIDER: dict[str, str] = {
    "organization": "Manzela",
    "url": "https://manzela.com",
}
_BASE_URL: str = "https://atelier.autonomous-agent.dev"
_AUTHENTICATION: dict[str, Any] = {
    "schemes": [
        {
            "type": "bearer",
            "description": "Firebase ID token from Identity Platform",
        },
        {
            "type": "apiKey",
            "description": "API key for service-to-service communication",
            "in": "header",
            "name": "X-Atelier-API-Key",
        },
    ]
}
_DEFAULT_CAPABILITIES: dict[str, Any] = {
    "streaming": False,
    "pushNotifications": False,
    "stateTransitionHistory": True,
    "multiTurn": False,
}

# Skills table: maps agent kind (and specific agent ids) to the skill records
# they advertise.  Specialists and judges expose a single, focused skill.
# The planner, intake parser, fixer, and critics expose an introspection skill.
_KIND_SKILLS: dict[str, list[dict[str, Any]]] = {
    "planner": [
        {
            "id": "plan-generation",
            "name": "Plan Generation",
            "description": (
                "Analyzes a design brief and emits a PlanStep that drives downstream "
                "DAG routing (WRAI, ensemble_k, axis weights, constitution, surfaces)."
            ),
            "inputModes": ["text"],
            "outputModes": ["text"],
            "tags": ["planning", "dag-routing", "orchestration"],
        }
    ],
    "intake": [
        {
            "id": "brief-parsing",
            "name": "Brief Parsing",
            "description": (
                "Extracts a structured BriefSpec from raw brief text; "
                "schema-constrained (output_schema=BriefSpec)."
            ),
            "inputModes": ["text"],
            "outputModes": ["text"],
            "tags": ["intake", "brief", "schema-extraction"],
        }
    ],
    "fixer": [
        {
            "id": "fix-directive",
            "name": "Fix Directive",
            "description": (
                "Analyzes gate failures and low axis scores; proposes a "
                "FixerDirective (mutations + prompt amendments) for the next iteration."
            ),
            "inputModes": ["text"],
            "outputModes": ["text"],
            "tags": ["fixer", "iteration", "gate-failure"],
        }
    ],
}

# Per-specialist skill tags derived from the output_key / role
_SPECIALIST_SKILL_TAGS: dict[str, list[str]] = {
    "ux_research": ["ux-research", "jobs-to-be-done", "user-needs"],
    "ia_flows": ["information-architecture", "user-flows", "navigation"],
    "wireframe": ["wireframing", "layout", "structural-design"],
    "ui_design": ["ui-generation", "html", "css", "stitch-mcp", "wcag-aa"],
    "interaction_spec": ["interaction-design", "animation", "aria", "keyboard"],
    "tokens": ["design-tokens", "dtcg", "token-extraction"],
}

_JUDGE_SKILL_TAGS: dict[str, list[str]] = {
    "brand": ["dorav-brand", "brand-alignment", "evaluation"],
    "originality": ["dorav-originality", "novelty", "evaluation"],
    "relevance": ["dorav-relevance", "brief-alignment", "evaluation"],
    "accessibility": ["dorav-accessibility", "wcag", "axe-core", "evaluation"],
    "visual_clarity": ["dorav-visual", "visual-quality", "evaluation"],
}

_CRITIC_SKILL_TAGS: dict[str, list[str]] = {
    "accessibilitycritic": ["qa", "accessibility", "wcag-aa"],
    "nielsenheuristiccritic": ["qa", "usability", "heuristics"],
    "visualqacritic": ["qa", "visual", "design-quality"],
    "brandcoherencecritic": ["qa", "brand", "coherence"],
}


# ---------------------------------------------------------------------------
# Skill builders
# ---------------------------------------------------------------------------


def _skills_for_descriptor(descriptor: Any) -> list[dict[str, Any]]:
    """Derive the skills list for one AgentDescriptor.

    Specialist agents expose a single skill named after their DDLC role.
    Judge agents expose a single D-O-R-A-V evaluation skill.
    Critic agents expose a single QA skill.
    All others fall back to ``_KIND_SKILLS``.
    """
    kind: str = descriptor.kind

    if kind == "specialist":
        output_key: str = descriptor.output_key or ""
        tags = _SPECIALIST_SKILL_TAGS.get(output_key, ["ddlc", "specialist"])
        return [
            {
                "id": f"ddlc-{output_key.replace('_', '-')}",
                "name": descriptor.name,
                "description": descriptor.description,
                "inputModes": ["text"],
                "outputModes": ["text"],
                "tags": tags,
            }
        ]

    if kind == "judge":
        axis = descriptor.id.removeprefix("judge_")
        tags = _JUDGE_SKILL_TAGS.get(axis, ["evaluation", "dorav"])
        return [
            {
                "id": f"judge-{axis}",
                "name": f"D-O-R-A-V {axis.replace('_', ' ').title()} Judge",
                "description": descriptor.description,
                "inputModes": ["text"],
                "outputModes": ["text"],
                "tags": tags,
            }
        ]

    if kind == "critic":
        critic_key = descriptor.id.removeprefix("critic_")
        tags = _CRITIC_SKILL_TAGS.get(critic_key, ["qa"])
        return [
            {
                "id": f"critic-{critic_key}",
                "name": descriptor.name,
                "description": descriptor.description,
                "inputModes": ["text"],
                "outputModes": ["text"],
                "tags": tags,
            }
        ]

    # planner / intake / fixer — use static table, fallback to generic
    return _KIND_SKILLS.get(
        kind,
        [
            {
                "id": f"{kind}-task",
                "name": descriptor.name,
                "description": descriptor.description,
                "inputModes": ["text"],
                "outputModes": ["text"],
                "tags": [kind],
            }
        ],
    )


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------


def build_agent_cards(registry: list[Any]) -> dict[str, dict[str, Any]]:
    """Build one A2A 0.3.0 AgentCard per AgentDescriptor in *registry*.

    This is a **pure function**: it reads only the descriptors it is given,
    performs no network calls, and has no side effects.  It is safe to call
    in tests, CI pipelines, and the FastAPI lifespan without live credentials.

    Args:
        registry: A list of
            :class:`~atelier.orchestrator.agent_registry.AgentDescriptor`
            objects (as returned by
            :func:`~atelier.orchestrator.agent_registry.get_agent_registry`).

    Returns:
        A ``dict[agent_id, card_dict]`` mapping.  Each card is a plain
        ``dict`` conforming to the A2A 0.3.0 agent-card JSON schema.
        Agents whose card generation raises are logged and yield a minimal
        fallback card (fail-soft).
    """
    from atelier.__version__ import __version__  # noqa: PLC0415 — late import avoids circular

    cards: dict[str, dict[str, Any]] = {}
    for descriptor in registry:
        try:
            agent_id: str = descriptor.id
            card: dict[str, Any] = {
                "name": descriptor.name,
                "description": descriptor.description,
                "version": __version__,
                "protocolVersion": _PROTOCOL_VERSION,
                "url": (f"{_BASE_URL}/.well-known/agents/{agent_id}/agent-card.json"),
                "provider": _PROVIDER,
                "skills": _skills_for_descriptor(descriptor),
                "protocols": {
                    "a2a": _PROTOCOL_VERSION,
                    "adk": _ADK_VERSION,
                },
                "authentication": _AUTHENTICATION,
                "capabilities": {
                    **_DEFAULT_CAPABILITIES,
                    # Specialists + judges + critics run inside the pipeline
                    # and support multi-turn via the SequentialAgent context.
                    "multiTurn": descriptor.kind in ("specialist", "judge", "critic"),
                },
                "defaultInputModes": ["text"],
                "defaultOutputModes": ["text"],
            }
            cards[agent_id] = card
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "atelier.agent_cards.build_failed",
                extra={"agent_id": getattr(descriptor, "id", "?"), "error": type(exc).__name__},
            )
            # Minimal fallback card so the registry does not disappear entirely
            _aid = getattr(descriptor, "id", "unknown")
            cards[_aid] = {
                "name": getattr(descriptor, "name", _aid),
                "description": "Card generation failed — see server logs.",
                "version": "0.0.0",
                "protocolVersion": _PROTOCOL_VERSION,
                "url": f"{_BASE_URL}/.well-known/agents/{_aid}/agent-card.json",
                "provider": _PROVIDER,
                "skills": [],
                "protocols": {"a2a": _PROTOCOL_VERSION, "adk": _ADK_VERSION},
                "authentication": _AUTHENTICATION,
                "capabilities": _DEFAULT_CAPABILITIES,
                "defaultInputModes": ["text"],
                "defaultOutputModes": ["text"],
            }
    return cards


# ---------------------------------------------------------------------------
# Committed-artifact helpers (used by the drift-guard test + CI script)
# ---------------------------------------------------------------------------

# Path to the ``agent_cards/`` directory that holds the committed JSON artifacts.
# Resolve relative to this module's location:
#   src/atelier/orchestrator/agent_cards.py
#   -> src/atelier/orchestrator/
#   -> src/atelier/
#   -> src/
#   -> atelier-core/
#   -> atelier-core/agent_cards/
_COMMITTED_CARDS_DIR: Path = Path(__file__).resolve().parents[3] / "agent_cards"


def committed_card_path(agent_id: str) -> Path:
    """Return the expected filesystem path for the committed card artifact."""
    return _COMMITTED_CARDS_DIR / f"{agent_id}.agent-card.json"


def generate_committed_cards(registry: list[Any] | None = None) -> dict[str, Path]:
    """Regenerate and write all agent-card JSON artifacts to ``agent_cards/``.

    Idempotent and hermetic: reads the live registry (or the supplied one),
    generates cards, serialises to JSON, and writes each file.  Existing files
    are overwritten.  Called by the ``scripts/generate_agent_cards.py`` helper
    and by the drift-guard test during its self-consistency check.

    Args:
        registry: Optional pre-built registry list.  Defaults to the live
            :func:`~atelier.orchestrator.agent_registry.get_agent_registry`
            result.

    Returns:
        A ``dict[agent_id, Path]`` of written file paths.
    """
    import json  # noqa: PLC0415

    if registry is None:
        from atelier.orchestrator.agent_registry import get_agent_registry  # noqa: PLC0415

        registry = get_agent_registry()

    _COMMITTED_CARDS_DIR.mkdir(parents=True, exist_ok=True)

    cards = build_agent_cards(registry)
    written: dict[str, Path] = {}
    for agent_id, card in cards.items():
        path = committed_card_path(agent_id)
        path.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written[agent_id] = path
    return written
