"""AT-082 unit oracle — Agent Engine deploy + registration (no live deploy).

Exercises the pure / hermetic surface, with no network and no GCP credentials:

- the pinned requirement list, the google-adk version-pin validation gate, and
  environment-driven config resolution;
- ``build_root_agent`` / ``build_agent_engine_app`` — the offline construction of
  the full Atelier ROOT graph (planner coordinator + brief parser + DDLC
  specialist pipeline + QA critique panel + fixer) and its ``AdkApp`` wrapper,
  asserted *without* calling ``vertexai.agent_engines.create()``;
- the Agent Gallery registration payloads built from the 18 committed A2A cards,
  asserting 1:1 coverage and the offline-derivable card-backed definition.

The live ``create()`` call and the Discovery Engine POST are operator-gated and
are not unit-tested.

PRD Reference: §12 E8 (AT-082)
"""

from __future__ import annotations

import json

import pytest
from atelier.agent_engine_deploy import (
    AgentEngineApp,
    AgentEngineDeployError,
    build_agent_engine_app,
    build_root_agent,
    deployment_requirements,
    resolve_config,
    validate_adk_pin,
)
from atelier.orchestrator.agent_registration import (
    build_registration_payloads,
    load_committed_cards,
)

# The 18 committed A2A cards (the discovery artifacts) — the registration
# payloads must cover exactly this set.
_EXPECTED_CARD_COUNT = 18

# The root coordinator's direct sub_agents (the deployed graph members).
_EXPECTED_SUB_AGENTS = {
    "brief_parser_llm",
    "DDLCSpecialistPipeline",
    "QACritiquePanel",
    "atelier_fixer",
}


@pytest.fixture
def _offline_vertex_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let ``AdkApp`` construct offline, without Application Default Credentials.

    Wrapping the root agent in ``AdkApp`` lazily resolves Vertex credentials via
    ``google.auth.default()``; CI has no ADC, so the real call raises
    ``GoogleAuthError``. Inject anonymous credentials plus a fake project — no
    network call happens at construction (no ``create()``), so this keeps the
    AdkApp-wrapping assertions running in CI instead of skipping them.
    """
    import google.auth
    from google.auth.credentials import AnonymousCredentials

    monkeypatch.setattr(
        google.auth,
        "default",
        lambda *_args, **_kwargs: (AnonymousCredentials(), "atelier-test"),
    )


def test_deployment_requirements_match_at002_pins() -> None:
    # Exact constraint strings — must stay in lockstep with pyproject.toml so a
    # dependency bump that drifts the deploy sandbox is caught here.
    reqs = deployment_requirements()
    assert "google-adk>=2.1.0,<3" in reqs
    assert "google-genai>=1.0,<3" in reqs
    assert "google-cloud-aiplatform>=1.71,<2" in reqs
    assert "pydantic>=2.6,<3" in reqs


def test_validate_adk_pin_accepts_installed_version() -> None:
    # The build venv pins google-adk==2.1.x (AT-002).
    assert validate_adk_pin().startswith("2.1")


def test_validate_adk_pin_rejects_version_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("importlib.metadata.version", lambda _name: "1.0.0")
    with pytest.raises(AgentEngineDeployError, match="drifts from the AT-002 pin"):
        validate_adk_pin()


def test_resolve_config_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-proj")
    monkeypatch.setenv("ATELIER_AGENT_NAME", "my-engine")
    config = resolve_config()
    assert config["project"] == "my-proj"
    assert config["display_name"] == "my-engine"


def test_resolve_config_defaults_to_serving_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("ATELIER_AGENT_NAME", raising=False)
    config = resolve_config()
    assert config["project"] == "atelier-build-2026"
    assert config["display_name"] == "atelier-root-engine"
    assert config["location"] == "us-central1"


# ---------------------------------------------------------------------------
# Root-graph construction (hermetic — no create(), no network, no GCP)
# ---------------------------------------------------------------------------


def test_build_root_agent_is_a_coordinator_not_a_leaf() -> None:
    # The deployed root is a coordinator: it must NOT set output_schema (which
    # would disable transfer to its sub_agents — ADK structured-output rule).
    root = build_root_agent()
    assert root.name == "atelier_root_coordinator"
    assert getattr(root, "output_schema", None) is None
    assert {child.name for child in root.sub_agents} == _EXPECTED_SUB_AGENTS


def test_build_root_agent_deploys_the_full_graph_not_just_the_planner() -> None:
    # AT-082 generalisation: the whole reachable graph is deployed, so the nested
    # DDLC specialist pipeline (6) and QA critique panel (4) must be present —
    # not just a bare planner leaf.
    root = build_root_agent()
    by_name = {child.name: child for child in root.sub_agents}

    specialists = {a.name for a in by_name["DDLCSpecialistPipeline"].sub_agents}
    assert specialists == {
        "UXResearcher",
        "IAFlowDesigner",
        "Wireframer",
        "UIDesigner",
        "InteractionDesigner",
        "TokenGenerator",
    }

    critics = {a.name for a in by_name["QACritiquePanel"].sub_agents}
    assert critics == {
        "AccessibilityCritic",
        "NielsenHeuristicCritic",
        "VisualQACritic",
        "BrandCoherenceCritic",
    }


def test_build_root_agent_leaves_keep_output_schema() -> None:
    # brief_parser + fixer are leaf structured-output agents — valid as leaves.
    root = build_root_agent()
    by_name = {child.name: child for child in root.sub_agents}
    assert by_name["brief_parser_llm"].output_schema is not None
    assert not by_name["brief_parser_llm"].sub_agents
    assert by_name["atelier_fixer"].output_schema is not None
    assert not by_name["atelier_fixer"].sub_agents


@pytest.mark.usefixtures("_offline_vertex_auth")
def test_build_agent_engine_app_returns_valid_offline_config() -> None:
    # The hermetic core: a frozen AgentEngineApp with the AdkApp wrapping the
    # exact root agent, the pinned requirements, and tracing — no create() call.
    spec = build_agent_engine_app()
    assert isinstance(spec, AgentEngineApp)
    assert spec.display_name == "atelier-root-engine"
    assert spec.requirements == deployment_requirements()
    assert spec.extra_packages == ["."]
    assert set(spec.sub_agent_names) == _EXPECTED_SUB_AGENTS
    # The AdkApp wraps the same root object the spec exposes.
    assert type(spec.app).__name__ == "AdkApp"
    tmpl = getattr(spec.app, "_tmpl_attrs", {})
    assert tmpl.get("agent") is spec.root_agent
    assert tmpl.get("enable_tracing") is True


@pytest.mark.usefixtures("_offline_vertex_auth")
def test_build_agent_engine_app_honours_supplied_config() -> None:
    spec = build_agent_engine_app(
        {
            "project": "p",
            "location": "us-central1",
            "display_name": "custom-engine",
            "description": "custom-desc",
            "staging_bucket": "gs://b",
        }
    )
    assert spec.display_name == "custom-engine"
    assert spec.description == "custom-desc"


# ---------------------------------------------------------------------------
# Agent Gallery registration payloads (pure — from the 18 committed cards)
# ---------------------------------------------------------------------------


def test_committed_cards_present() -> None:
    cards = load_committed_cards()
    assert len(cards) == _EXPECTED_CARD_COUNT


def test_registration_payloads_cover_all_18_cards() -> None:
    cards = load_committed_cards()
    payloads = build_registration_payloads(cards)
    # 1:1 coverage — every committed card yields exactly one registration.
    assert set(payloads) == set(cards)
    assert len(payloads) == _EXPECTED_CARD_COUNT


def test_registration_payload_is_card_backed_and_well_formed() -> None:
    cards = load_committed_cards()
    payloads = build_registration_payloads(cards)
    for agent_id, payload in payloads.items():
        card = cards[agent_id]
        # Human-facing identity is taken straight from the card.
        assert payload["displayName"] == card["name"]
        # The offline-derivable definition inlines the committed card verbatim.
        inlined = json.loads(payload["a2aAgentDefinition"]["jsonAgentCard"])
        assert inlined == card
        # The ADK-backed alternative is provided as an operator template only.
        assert "provisionedReasoningEngine" in payload["_adkAgentDefinitionTemplate"]
        # No live resource is hardcoded — every target value is a placeholder.
        assert payload["_target"]["parent"].startswith("projects/${GOOGLE_CLOUD_PROJECT}")
        assert payload["_provenance"]["sourceCard"] == f"agent_cards/{agent_id}.agent-card.json"


def test_committed_registration_artifacts_match_fresh_generation() -> None:
    # Drift guard: the on-disk artifacts under agent_cards/registration/ must
    # equal a fresh generation from the committed cards.
    from atelier.orchestrator.agent_registration import (
        build_registration_payload,
        registration_payload_path,
    )

    cards = load_committed_cards()
    for agent_id, card in cards.items():
        path = registration_payload_path(agent_id)
        assert path.exists(), f"missing committed registration artifact: {path}"
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk == build_registration_payload(agent_id, card)
