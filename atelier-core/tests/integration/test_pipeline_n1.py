from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from atelier.intake.brief_parser import BriefParserAgent
from atelier.intake.brief_spec import BriefSpec
from atelier.orchestrator.runner import AtelierRunner


@pytest.mark.anyio
async def test_brief_text_to_brief_spec_via_runner() -> None:
    """End-to-end: brief text → BriefSpec via AtelierRunner with mocked Gemini."""
    runner = AtelierRunner()

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
    with patch.object(BriefParserAgent, "_call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = valid_json

        # Valid brief text (10+ tokens)
        brief_text = "This is a brief text that needs to have more than ten words to pass the deterministic gate check."

        result = await runner.run(brief_text)
        assert isinstance(result, BriefSpec)
        assert result.intent == "build a landing page"
