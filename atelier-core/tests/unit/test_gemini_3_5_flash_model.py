"""Gemini 3.5 Flash (High) as a selectable generation model.

gemini-3.5-flash is offered in the UI picker as "Gemini 3.5 Flash (High)" and
run by the N3a specialist pipeline at high thinking level. It is a selectable
OVERRIDE, not a production routing target — so the L05 GenerateRequest gate must
accept it without it appearing in the routing-derived catalog, and the high
thinking level must apply ONLY to it (never to the 2.5 family).
"""

from __future__ import annotations

import pytest
from atelier.models.model_registry import (
    GEMINI_3_5_FLASH_MODEL_ID,
    SELECTABLE_MODEL_OVERRIDES,
    get_model_catalog,
    model_tier_for_id,
)

pytestmark = pytest.mark.unit


def test_gemini_3_5_flash_is_a_selectable_override_not_a_routing_target() -> None:
    catalog_ids = {e.model_id for e in get_model_catalog()}
    # It is an explicit override ...
    assert GEMINI_3_5_FLASH_MODEL_ID in SELECTABLE_MODEL_OVERRIDES
    # ... and NOT a routing target (production task routing is unchanged).
    assert GEMINI_3_5_FLASH_MODEL_ID not in catalog_ids


def test_l05_gate_accepts_gemini_3_5_flash_and_still_rejects_garbage() -> None:
    from atelier.api.generate import GenerateRequest

    brief = "Build a clean B2B analytics landing page with a hero and three cards"
    assert GenerateRequest(brief=brief, model="gemini-3.5-flash").model == "gemini-3.5-flash"
    with pytest.raises(ValueError, match="operator-served catalog"):
        GenerateRequest(brief=brief, model="gpt-4o-ultra")


def test_gemini_3_5_flash_maps_to_flash_tier_for_token_caps() -> None:
    # Must resolve to a known tier so the per-user token cap never crashes/bypasses.
    assert model_tier_for_id(GEMINI_3_5_FLASH_MODEL_ID) == "flash"


def test_specialist_pipeline_runs_3_5_flash_at_high_thinking() -> None:
    from atelier.orchestrator.specialists import create_specialist_pipeline

    pipe, _ = create_specialist_pipeline(model="gemini-3.5-flash")
    for agent in pipe.sub_agents:
        cfg = agent.generate_content_config
        tc = cfg.thinking_config
        assert tc is not None, f"{agent.name} missing thinking_config"
        assert str(tc.thinking_level).upper().endswith("HIGH")
        # High thinking draws from the output budget; the ceiling must be raised so
        # the model can emit the full HTML after thinking (else MAX_TOKENS, no content).
        assert cfg.max_output_tokens is not None
        assert cfg.max_output_tokens >= 32768


def test_2_5_flash_does_not_get_high_thinking() -> None:
    # The thinking attach is scoped to the gemini-3 thinking model only.
    from atelier.orchestrator.specialists import create_specialist_pipeline

    pipe, _ = create_specialist_pipeline(model="gemini-2.5-flash")
    for agent in pipe.sub_agents:
        assert agent.generate_content_config.thinking_config is None


def test_global_only_model_pinned_to_global_endpoint_in_prod_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Production deploys to us-central1, where gemini-3.5-flash returns 404 on the
    # regional endpoint. The pipeline must pin it to the Vertex `global` endpoint
    # regardless of GOOGLE_CLOUD_LOCATION, so production works without changing the
    # deploy region or rerouting every other model. The genai Client is mocked so
    # the assertion is hermetic (no ADC, no network, no leaked global state).
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "atelier-build-2026")
    monkeypatch.setenv("ATELIER_STITCH_ENABLED", "false")

    captured: dict[str, object] = {}

    class _FakeClient:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)
            self.vertexai = kwargs.get("vertexai")

    monkeypatch.setattr("google.genai.Client", _FakeClient)
    from atelier.orchestrator.specialists import _GlobalEndpointGemini, create_specialist_pipeline

    pipe, _ = create_specialist_pipeline(model="gemini-3.5-flash")
    for agent in pipe.sub_agents:
        assert isinstance(agent.model, _GlobalEndpointGemini), agent.name
        _ = agent.model.api_client  # constructs the (mocked) Client
    # The pin is the whole point: location forced to global, Vertex backend on.
    assert captured.get("location") == "global"
    assert captured.get("vertexai") is True


def test_regional_model_stays_a_plain_id_using_ambient_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATELIER_STITCH_ENABLED", "false")
    from atelier.orchestrator.specialists import create_specialist_pipeline

    pipe, _ = create_specialist_pipeline(model="gemini-2.5-flash")
    for agent in pipe.sub_agents:
        # A regional model is left as a bare id so it uses the ambient
        # GOOGLE_CLOUD_LOCATION (no global pin, no per-agent client).
        assert agent.model == "gemini-2.5-flash"
