"""Integration test for N1 -> N2 -> N3a pipeline flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from atelier.intake.brief_parser import BriefParserAgent
from atelier.intake.source_resolver import ProjectContext
from atelier.models.design_system import DesignSystemRecord
from atelier.orchestrator.runner import AtelierRunner


@pytest.mark.anyio
async def test_end_to_end_pipeline_n1_n2_n3a() -> None:
    """End-to-end: N1 -> N2 -> N3a using mocked components."""
    valid_json = """
    {
        "spec_id": "123e4567-e89b-12d3-a456-426614174000",
        "tenant_id": "t1",
        "project_id": "p1",
        "intent": "build a landing page",
        "visual_register": "editorial",
        "stack": "vanilla-html",
        "design_system_source": "infer",
        "compliance_level": "wcag-aa",
        "convergence_bar": "ship-it",
        "reference_artifacts": [],
        "campaign_scope": null,
        "intake_transcript": [],
        "schema_version": 1,
        "approved_at": "2026-05-25T12:00:00Z",
        "approved_by_user_id": "user1"
    }
    """

    # Mock session service that satisfies the Protocol
    mock_session_service = MagicMock()
    mock_session = MagicMock()
    mock_session.id = "test-session-id"
    mock_session_service.create_session = AsyncMock(return_value=mock_session)

    runner = AtelierRunner(session_service=mock_session_service)

    with (
        patch.object(BriefParserAgent, "_call_llm", new_callable=AsyncMock) as mock_n1,
        # NOTE: the N2 gate is deliberately NOT mocked here. The brief above uses
        # design_system_source="infer", which the real source_resolver_gate must
        # admit (PADI auto-discovery). This is the integration guard that the unit
        # suite's gate mocks would otherwise hide — see test_source_resolver_gate.
        patch(
            "atelier.intake.source_resolver.pull_design_tokens", new_callable=AsyncMock
        ) as mock_tokens,
        # AT-053 (c8b49ce) rewrote source_resolver_agent: memory-bank priors are
        # now derived from the tenant's PERSISTED design system via
        # load_tenant_design_system + serialize_priors, NOT the old standalone
        # pull_memory_bank_priors (which the agent no longer calls). We patch the
        # seam the agent actually reaches today and return a real DesignSystemRecord
        # so the genuine auto-apply path (serialize_priors) runs end-to-end.
        patch(
            "atelier.intake.source_resolver.load_tenant_design_system",
            new_callable=AsyncMock,
        ) as mock_persisted_system,
        patch("atelier.orchestrator.runner.Runner") as mock_runner_cls,
    ):
        # N1 mock
        mock_n1.return_value = valid_json

        # N2 mock
        mock_tokens.return_value = {"primary_color": "#ffffff"}
        mock_persisted_system.return_value = DesignSystemRecord(
            tenant_id="t1",
            run_id="prior-run",
            tokens={"primary_color": "#ffffff"},
        )

        # N3a mock — Runner instance with run_async
        mock_runner_instance = mock_runner_cls.return_value

        async def mock_events(*args, **kwargs):
            yield {"type": "message", "data": "candidate1"}
            yield {"type": "message", "data": "candidate2"}
            yield {"type": "message", "data": "candidate3"}

        mock_runner_instance.run_async.side_effect = mock_events

        brief_text = "This is a brief text that needs to have more than ten words to pass the deterministic gate check."

        result = await runner.run(brief_text)

        assert isinstance(result, dict)

        # N1 Validation
        assert result["brief"].intent == "build a landing page"

        # N2 Validation
        assert isinstance(result["project_context"], ProjectContext)
        assert result["project_context"].design_tokens["primary_color"] == "#ffffff"
        # AT-053 auto-apply: the persisted system is serialized into priors, the
        # first of which is the tenant-scoped provenance marker.
        priors = result["project_context"].memory_bank_priors
        assert any("Persisted design system for tenant t1" in p for p in priors)
        # The persisted authorized token set is also threaded for the AT-012 gate.
        assert result["project_context"].persisted_design_tokens == {"primary_color": "#ffffff"}

        # N3a Validation
        assert len(result["candidates"]) == 3
        assert result["candidates"][0] == "candidate1"

        # B4 Validation — session service was called
        mock_session_service.create_session.assert_called_once()

        # AG-06 Validation — stitch_degraded is surfaced
        assert "stitch_degraded" in result
        assert isinstance(result["stitch_degraded"], bool)

        # AG-07 Validation — session_id is returned
        assert result["session_id"] == "test-session-id"

        # AG-09 Validation — WRAI report is returned
        assert "web_research" in result
