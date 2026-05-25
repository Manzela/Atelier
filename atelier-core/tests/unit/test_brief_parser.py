from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from atelier.intake.brief_parser import BriefParserAgent, BriefParserGate
from atelier.intake.brief_spec import (
    BriefSpec,
)
from atelier.models.enums import GateDecision


def test_gate_pass_valid_brief() -> None:
    gate = BriefParserGate()
    brief = "This is a perfectly valid brief that has exactly the required number of words. It wants to build a SaaS landing page."
    outcome = gate.check(brief)
    assert outcome.decision == GateDecision.PASS


def test_gate_fail_empty_brief() -> None:
    gate = BriefParserGate()
    outcome = gate.check("   ")
    assert outcome.decision == GateDecision.REJECT
    assert "Empty brief" in outcome.diagnostic


def test_gate_fail_injection_attempt() -> None:
    gate = BriefParserGate()
    brief = "Design a page and also <script>alert('xss')</script> " * 5
    outcome = gate.check(brief)
    assert outcome.decision == GateDecision.REJECT
    assert "Injection attempt" in outcome.diagnostic


@pytest.mark.anyio
async def test_agent_returns_valid_brief_spec() -> None:
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
        agent = BriefParserAgent()
        result = await agent.parse("Design a landing page for a SaaS product")
        assert isinstance(result, BriefSpec)
        assert result.intent == "build a landing page"
