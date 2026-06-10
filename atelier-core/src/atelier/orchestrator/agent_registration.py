"""Agent Gallery / Discovery Engine registration payloads — pure, offline (AT-082).

The 18 committed A2A 0.3.0 agent cards under ``atelier-core/agent_cards/`` are
Atelier's discovery artifacts. This module turns those cards into the
**registration payloads** an operator POSTs to register each Atelier agent in the
Gemini Enterprise Agent Gallery (Discovery Engine ``Agent`` resources), and
writes them as committed artifacts under
``atelier-core/agent_cards/registration/``.

It makes **no network call** and needs no GCP credentials — it is a pure
card-in → payload-out transform, safe in tests and CI.

Grounding (context7)
--------------------
Grounded on the Discovery Engine API (``/websites/cloud_google_java_reference_
google-cloud-discoveryengine``). The Gemini Enterprise Agent Gallery registers
an agent as an ``Agent`` resource *under an Assistant*:

    parent  = projects/{project}/locations/{location}/collections/{collection}
              /engines/{engine}/assistants/{assistant}
    POST {parent}/agents        (CreateAgent)

The ``Assistant`` resource and that parent hierarchy are confirmed in the indexed
docs (``Assistant`` resource name format
``projects/.../engines/{engine}/assistants/{assistant}``). The newer
``Agent.AgentDefinition`` discriminator — ``adk_agent_definition``
(``provisioned_reasoning_engine`` = an Agent-Engine reasoning-engine resource) vs
``a2a_agent_definition`` (``json_agent_card`` = an inline A2A card) — is newer
than the indexed snapshot. Per the AT-082 constraint we therefore emit the
**A2A-card-backed** payload (``a2a_agent_definition.json_agent_card``), which is
fully derivable offline from the committed cards, and document the operator step
for binding the deployed reasoning-engine resource where the ADK-backed variant
is preferred. See ``atelier-core/agent_cards/registration/README.md``.

Each emitted payload is the request **body** for ``CreateAgent``; the ``parent``,
``assistant``, ``engine``, and (for the ADK-backed variant) the deployed
``reasoning_engine`` resource name are operator-supplied at POST time and are
left as documented placeholders, never hardcoded.

PRD Reference: §12 E8 (AT-082)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths — the committed cards (input) and the registration artifacts (output)
# ---------------------------------------------------------------------------

# src/atelier/orchestrator/agent_registration.py
#   -> src/atelier/orchestrator/ -> src/atelier/ -> src/ -> atelier-core/
_ATELIER_CORE_DIR: Path = Path(__file__).resolve().parents[3]
_COMMITTED_CARDS_DIR: Path = _ATELIER_CORE_DIR / "agent_cards"
_REGISTRATION_DIR: Path = _COMMITTED_CARDS_DIR / "registration"

#: Operator-supplied placeholders. These are the parts of the Agent Gallery
#: target an operator fills in at POST time; we never hardcode a live engine /
#: assistant / project, so the artifact is environment-agnostic and reviewable.
_PARENT_PLACEHOLDER: str = (
    "projects/${GOOGLE_CLOUD_PROJECT}/locations/${LOCATION}"
    "/collections/default_collection/engines/${ENGINE_ID}"
    "/assistants/${ASSISTANT_ID}"
)
#: For the ADK-backed variant (preferred when the Agent Engine deploy has run),
#: the operator binds the deployed reasoning-engine resource name here.
_REASONING_ENGINE_PLACEHOLDER: str = (
    "projects/${GOOGLE_CLOUD_PROJECT}/locations/${LOCATION}/reasoningEngines/${REASONING_ENGINE_ID}"
)

#: Discovery Engine ``Agent`` resources require an authorization to call the
#: backing endpoint; the A2A cards already declare bearer + apiKey schemes, which
#: we surface here so the operator wires the matching authorization resource.
_AUTHORIZATIONS_PLACEHOLDER: list[str] = [
    "projects/${GOOGLE_CLOUD_PROJECT}/locations/${LOCATION}/authorizations/${AUTHORIZATION_ID}",
]


def _registration_id(agent_id: str) -> str:
    """Map a card's ``agent_id`` to a Discovery-Engine-safe registration id.

    Discovery Engine resource ids are constrained (lowercase, digits, hyphens);
    the Atelier card ids use underscores. We normalise underscores to hyphens so
    each registration has a deterministic, valid display id derived 1:1 from the
    source card.
    """
    return agent_id.replace("_", "-")


def build_registration_payload(agent_id: str, card: dict[str, Any]) -> dict[str, Any]:
    """Build one Agent Gallery registration payload from a single A2A card.

    The payload is the ``CreateAgent`` request body for the Gemini Enterprise
    Agent Gallery. It carries the human-facing identity (display name,
    description), the ``a2a_agent_definition`` (the source card inlined as
    ``json_agent_card``), and operator placeholders for the engine/assistant
    parent, the optional reasoning-engine binding (ADK-backed variant), and the
    authorization resource. No network call, no credentials.

    Args:
        agent_id: The card's stable id (e.g. ``"judge_originality"``).
        card: The A2A 0.3.0 agent-card dict (as committed under ``agent_cards/``).

    Returns:
        A registration payload dict ready to be serialised and POSTed by the
        operator (after substituting the ``${...}`` placeholders).
    """
    return {
        # Echoed for operator legibility / artifact diffing; not part of the
        # POST body (the operator supplies the real parent at request time).
        "_target": {
            "parent": _PARENT_PLACEHOLDER,
            "agentId": _registration_id(agent_id),
            "method": "CreateAgent (POST {parent}/agents)",
        },
        # --- CreateAgent request body (the Agent resource) ---
        "displayName": card["name"],
        "description": card.get("description", ""),
        "icon": {"uri": ""},
        # A2A-card-backed definition: the committed card IS the contract. This is
        # the offline-derivable variant (no deployed resource needed).
        "a2aAgentDefinition": {
            "jsonAgentCard": json.dumps(card, ensure_ascii=False, sort_keys=True),
        },
        # ADK-backed alternative (operator binds the deployed reasoning engine).
        # Mutually exclusive with a2aAgentDefinition at POST time — kept here,
        # under a clearly-namespaced operator block, as guidance not request body.
        "_adkAgentDefinitionTemplate": {
            "provisionedReasoningEngine": {
                "reasoningEngine": _REASONING_ENGINE_PLACEHOLDER,
            },
        },
        "authorizations": list(_AUTHORIZATIONS_PLACEHOLDER),
        # Provenance — ties the registration back to the source artifact so a CI
        # drift-guard can verify 1:1 coverage of the committed cards.
        "_provenance": {
            "sourceCard": f"agent_cards/{agent_id}.agent-card.json",
            "protocolVersion": card.get("protocolVersion", "0.3.0"),
            "skills": [s.get("id") for s in card.get("skills", [])],
        },
    }


def build_registration_payloads(
    cards: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build the Agent Gallery registration payload for every card.

    Pure function: ``{agent_id: card} -> {agent_id: registration_payload}``. The
    output covers exactly the input cards (1:1), so a CI test can assert all 18
    committed cards are represented.

    Args:
        cards: Mapping of ``agent_id -> A2A card dict`` (e.g. the output of
            :func:`~atelier.orchestrator.agent_cards.build_agent_cards`, or the
            committed cards loaded from disk via :func:`load_committed_cards`).

    Returns:
        A ``dict[agent_id, registration_payload]`` mapping.
    """
    return {
        agent_id: build_registration_payload(agent_id, card) for agent_id, card in cards.items()
    }


def load_committed_cards() -> dict[str, dict[str, Any]]:
    """Load every committed A2A card from ``agent_cards/*.agent-card.json``.

    Returns:
        A ``dict[agent_id, card_dict]`` keyed by the file stem's agent id
        (``"<agent_id>.agent-card.json"`` -> ``"<agent_id>"``).

    Raises:
        FileNotFoundError: If the committed cards directory is missing.
    """
    if not _COMMITTED_CARDS_DIR.is_dir():
        raise FileNotFoundError(
            f"Committed agent-cards directory not found: {_COMMITTED_CARDS_DIR}"
        )
    cards: dict[str, dict[str, Any]] = {}
    for path in sorted(_COMMITTED_CARDS_DIR.glob("*.agent-card.json")):
        agent_id = path.name.removesuffix(".agent-card.json")
        cards[agent_id] = json.loads(path.read_text(encoding="utf-8"))
    return cards


def registration_payload_path(agent_id: str) -> Path:
    """Return the committed artifact path for one agent's registration payload."""
    return _REGISTRATION_DIR / f"{agent_id}.registration.json"


def generate_committed_registrations(
    cards: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Path]:
    """Regenerate and write all registration-payload artifacts to ``registration/``.

    Idempotent and hermetic: loads the committed cards (or the supplied mapping),
    builds the registration payloads, and writes each as JSON under
    ``agent_cards/registration/``. Existing files are overwritten. Used by the
    ``scripts/generate_agent_registrations.py`` helper and the drift-guard test.

    Args:
        cards: Optional pre-loaded ``{agent_id: card}`` mapping. Defaults to the
            committed cards on disk (:func:`load_committed_cards`).

    Returns:
        A ``dict[agent_id, Path]`` of written artifact paths.
    """
    resolved_cards = cards if cards is not None else load_committed_cards()
    payloads = build_registration_payloads(resolved_cards)

    _REGISTRATION_DIR.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for agent_id, payload in payloads.items():
        path = registration_payload_path(agent_id)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written[agent_id] = path
    return written
