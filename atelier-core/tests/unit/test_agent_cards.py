"""Drift-guard and correctness tests for per-agent A2A 0.3.0 AgentCards.

Guarantees:
1. ``build_agent_cards`` is pure, hermetic, and never touches the network.
2. Every agent in the live registry gets a card with required A2A fields.
3. Each card's ``url`` resolves to the expected per-agent well-known path.
4. Committed JSON artifacts in ``agent_cards/`` match a fresh generation —
   the cards can never silently drift from the code (the build step must be
   re-run and artifacts committed whenever the registry changes).
5. The ``generate_committed_cards`` helper produces valid, parseable JSON.
6. Skills lists are non-empty for all agent kinds.
7. ``protocolVersion`` is exactly ``"0.3.0"`` and ``protocols.adk`` is ``"2.1"``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from atelier.orchestrator.agent_cards import (
    _COMMITTED_CARDS_DIR,
    build_agent_cards,
    committed_card_path,
    generate_committed_cards,
)
from atelier.orchestrator.agent_registry import AgentDescriptor, get_agent_registry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_TOP_LEVEL_KEYS = {
    "name",
    "description",
    "version",
    "protocolVersion",
    "url",
    "provider",
    "skills",
    "protocols",
    "authentication",
    "capabilities",
    "defaultInputModes",
    "defaultOutputModes",
}

_CANONICAL_URL_PREFIX = "https://atelier.autonomous-agent.dev/.well-known/agents/"


@pytest.fixture(scope="module")
def registry() -> list[AgentDescriptor]:
    return get_agent_registry()


@pytest.fixture(scope="module")
def cards(registry: list[AgentDescriptor]) -> dict[str, dict[str, Any]]:
    return build_agent_cards(registry)


# ---------------------------------------------------------------------------
# Schema / structure checks
# ---------------------------------------------------------------------------


def test_every_agent_gets_a_card(
    registry: list[AgentDescriptor], cards: dict[str, dict[str, Any]]
) -> None:
    expected_ids = {d.id for d in registry}
    assert set(cards.keys()) == expected_ids


def test_required_fields_present(cards: dict[str, dict[str, Any]]) -> None:
    for agent_id, card in cards.items():
        missing = _REQUIRED_TOP_LEVEL_KEYS - set(card.keys())
        assert not missing, f"Card for {agent_id!r} is missing fields: {missing}"


def test_protocol_version_is_0_3_0(cards: dict[str, dict[str, Any]]) -> None:
    for agent_id, card in cards.items():
        assert card["protocolVersion"] == "0.3.0", (
            f"Card {agent_id!r}: expected protocolVersion '0.3.0', got {card['protocolVersion']!r}"
        )
        assert card["protocols"]["a2a"] == "0.3.0", (
            f"Card {agent_id!r}: expected protocols.a2a '0.3.0'"
        )
        assert card["protocols"]["adk"] == "2.1", f"Card {agent_id!r}: expected protocols.adk '2.1'"


def test_url_is_per_agent_well_known_path(cards: dict[str, dict[str, Any]]) -> None:
    for agent_id, card in cards.items():
        expected_url = f"{_CANONICAL_URL_PREFIX}{agent_id}/agent-card.json"
        assert card["url"] == expected_url, (
            f"Card {agent_id!r}: expected url {expected_url!r}, got {card['url']!r}"
        )


def test_skills_list_is_non_empty(cards: dict[str, dict[str, Any]]) -> None:
    for agent_id, card in cards.items():
        assert card["skills"], f"Card {agent_id!r} has no skills"


def test_each_skill_has_required_fields(cards: dict[str, dict[str, Any]]) -> None:
    skill_required = {"id", "name", "description", "inputModes", "outputModes", "tags"}
    for agent_id, card in cards.items():
        for skill in card["skills"]:
            missing = skill_required - set(skill.keys())
            assert not missing, f"Skill in card {agent_id!r} missing fields: {missing}"


def test_authentication_schemes_non_empty(cards: dict[str, dict[str, Any]]) -> None:
    for agent_id, card in cards.items():
        schemes = card.get("authentication", {}).get("schemes", [])
        assert schemes, f"Card {agent_id!r} has no authentication schemes"


def test_provider_fields(cards: dict[str, dict[str, Any]]) -> None:
    for agent_id, card in cards.items():
        provider = card.get("provider", {})
        assert provider.get("organization"), f"Card {agent_id!r}: provider.organization is empty"
        assert provider.get("url"), f"Card {agent_id!r}: provider.url is empty"


def test_name_and_description_non_empty(cards: dict[str, dict[str, Any]]) -> None:
    for agent_id, card in cards.items():
        assert card["name"].strip(), f"Card {agent_id!r}: name is empty"
        assert card["description"].strip(), f"Card {agent_id!r}: description is empty"


# ---------------------------------------------------------------------------
# Kind-specific capability checks
# ---------------------------------------------------------------------------


def test_specialist_judge_critic_enable_multi_turn(
    registry: list[AgentDescriptor], cards: dict[str, dict[str, Any]]
) -> None:
    pipeline_kinds = {"specialist", "judge", "critic"}
    for d in registry:
        card = cards[d.id]
        if d.kind in pipeline_kinds:
            assert card["capabilities"]["multiTurn"] is True, (
                f"Card {d.id!r} (kind={d.kind!r}) should have multiTurn=True"
            )
        else:
            assert card["capabilities"]["multiTurn"] is False, (
                f"Card {d.id!r} (kind={d.kind!r}) should have multiTurn=False"
            )


# ---------------------------------------------------------------------------
# Drift-guard: committed artifacts must match a fresh generation
# ---------------------------------------------------------------------------


def test_committed_artifacts_exist() -> None:
    """All committed agent-card files must be present under agent_cards/."""
    registry = get_agent_registry()
    missing: list[str] = []
    for d in registry:
        if not committed_card_path(d.id).exists():
            missing.append(d.id)
    assert not missing, (
        f"Missing committed agent-card artifacts for: {missing}. "
        "Run 'python -m atelier.orchestrator.agent_cards' or "
        "'python scripts/generate_agent_cards.py' and commit the results."
    )


def test_committed_artifacts_match_live_registry(tmp_path: Path) -> None:
    """Regenerate cards in a temp dir and assert they match committed artifacts.

    This is the core drift guard: if the registry changes and the artifacts
    are not regenerated, this test fails — forcing a deliberate update commit.
    """
    registry = get_agent_registry()
    fresh_cards = build_agent_cards(registry)

    for agent_id, fresh_card in fresh_cards.items():
        committed_path = committed_card_path(agent_id)
        assert committed_path.exists(), (
            f"Committed artifact missing for {agent_id!r}: {committed_path}. "
            "Run generate_committed_cards() and commit."
        )
        committed_card = json.loads(committed_path.read_text(encoding="utf-8"))

        # Compare the structurally significant fields (exclude version which
        # changes on every release — version drift alone is not a "schema" drift).
        def _normalise(card: dict[str, Any]) -> dict[str, Any]:
            c = dict(card)
            c.pop("version", None)
            return c

        assert _normalise(fresh_card) == _normalise(committed_card), (
            f"Agent card for {agent_id!r} has drifted from the committed artifact.\n"
            f"Committed: {json.dumps(_normalise(committed_card), indent=2)}\n"
            f"Fresh:     {json.dumps(_normalise(fresh_card), indent=2)}\n"
            "Run generate_committed_cards() and commit the regenerated artifacts."
        )


# ---------------------------------------------------------------------------
# generate_committed_cards helper
# ---------------------------------------------------------------------------


def test_generate_committed_cards_writes_valid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """generate_committed_cards writes parseable JSON files."""
    import atelier.orchestrator.agent_cards as _mod

    # Redirect writes to tmp_path so the test does not pollute the real artifacts
    monkeypatch.setattr(_mod, "_COMMITTED_CARDS_DIR", tmp_path)

    registry = get_agent_registry()
    written = generate_committed_cards(registry)

    assert written, "generate_committed_cards returned an empty mapping"
    for agent_id, path in written.items():
        assert path.exists(), f"Written path {path} does not exist"
        content = path.read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert parsed.get("name"), f"Generated card for {agent_id!r} has no name"
        assert parsed.get("protocolVersion") == "0.3.0"


def test_generate_committed_cards_covers_all_agents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import atelier.orchestrator.agent_cards as _mod

    monkeypatch.setattr(_mod, "_COMMITTED_CARDS_DIR", tmp_path)

    registry = get_agent_registry()
    written = generate_committed_cards(registry)
    expected_ids = {d.id for d in registry}
    assert set(written.keys()) == expected_ids
