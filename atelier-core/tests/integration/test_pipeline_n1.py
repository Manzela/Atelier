from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from atelier.intake.brief_parser import BriefParserAgent
from atelier.integrations.stitch_mcp import StitchDegradationInfo
from atelier.orchestrator.runner import AtelierRunner
from atelier.orchestrator.specialists import SPECIALIST_OUTPUT_KEYS, create_specialist_pipeline
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types as genai_types

if TYPE_CHECKING:
    from google.adk.models.llm_request import LlmRequest

_N3A_APP = "atelier-n1-n3a"
_N3A_USER = "user-n1-n3a"
_N3A_SID = "session-n1-n3a"
_N3A_BRIEF = "Design a landing page for a quiet editorial co-working space with muted tones."
_STITCH_TARGET = "atelier.orchestrator.specialists.try_get_stitch_mcp_toolset"


class _FakeLlm(BaseLlm):
    """Hermetic stand-in for the served Gemini model used by N3a specialists.

    Each call yields one non-empty text response with no network I/O so the real
    ADK ``SequentialAgent`` runs the N3a specialists offline.
    """

    calls: int = 0

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,  # noqa: FBT001, FBT002
    ) -> AsyncGenerator[LlmResponse, None]:
        self.calls += 1
        yield LlmResponse(
            content=genai_types.Content(
                role="model",
                parts=[genai_types.Part(text=f"FAKE_N3A_OUTPUT_{self.calls}")],
            )
        )


def _degraded_stitch(*args: Any, **kwargs: Any) -> tuple[None, StitchDegradationInfo]:
    return None, StitchDegradationInfo(
        is_degraded=True,
        reason="Stitch MCP disabled for hermetic N1 integration test",
        fallback_mode="direct_generation",
    )


@pytest.mark.anyio
async def test_brief_text_to_brief_spec_via_runner() -> None:
    """End-to-end: brief text -> BriefSpec via AtelierRunner with mocked Gemini."""
    # Mock session service
    mock_session_service = MagicMock()
    mock_session = MagicMock()
    mock_session.id = "test-session-id"
    mock_session_service.create_session = AsyncMock(return_value=mock_session)

    runner = AtelierRunner(session_service=mock_session_service)

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

        with (
            patch("atelier.orchestrator.runner.source_resolver_gate", return_value=True),
            patch(
                "atelier.orchestrator.runner.source_resolver_agent", new_callable=AsyncMock
            ) as mock_resolver,
            patch("atelier.orchestrator.runner.Runner") as mock_runner_cls,
        ):
            mock_resolver.return_value = "fake_project_ctx"

            # Mock runner instance and run_async
            mock_runner_instance = mock_runner_cls.return_value

            async def mock_events(*args, **kwargs):
                yield {"type": "message", "data": "candidate1"}

            mock_runner_instance.run_async.side_effect = mock_events

            result = await runner.run(brief_text)

            assert isinstance(result, dict)
            assert "brief" in result
            assert result["brief"].intent == "build a landing page"


@pytest.mark.anyio
async def test_n3a_specialist_pipeline_executes_real_adk_agent() -> None:
    """N3a node executes the real ADK SequentialAgent with a hermetic fake model.

    Verifies that all six DDLC specialist ``output_key``s are written to session
    state by the actual production SequentialAgent (not a mock of the ADK Runner).
    The fake BaseLlm yields one response per call with no network I/O.
    """
    session_service = InMemorySessionService()
    await session_service.create_session(app_name=_N3A_APP, user_id=_N3A_USER, session_id=_N3A_SID)

    fake = _FakeLlm(model="fake-n1-n3a")
    with patch(_STITCH_TARGET, side_effect=_degraded_stitch):
        pipeline, degradation = create_specialist_pipeline(model=fake)

    runner = Runner(agent=pipeline, session_service=session_service, app_name=_N3A_APP)
    async for _event in runner.run_async(
        user_id=_N3A_USER,
        session_id=_N3A_SID,
        new_message=genai_types.Content(role="user", parts=[genai_types.Part(text=_N3A_BRIEF)]),
    ):
        pass

    refreshed = await session_service.get_session(
        app_name=_N3A_APP, user_id=_N3A_USER, session_id=_N3A_SID
    )
    assert refreshed is not None
    state = dict(refreshed.state)

    # All six specialist output_keys must be present and non-empty.
    for key in SPECIALIST_OUTPUT_KEYS:
        assert key in state, f"N3a specialist output_key missing: {key}"
        assert str(state[key]).strip(), f"N3a specialist output_key is empty: {key}"

    # Confirm the real SequentialAgent served all specialists through the fake
    # (one call per specialist) — no live model calls.
    assert fake.calls == len(SPECIALIST_OUTPUT_KEYS), (
        f"expected {len(SPECIALIST_OUTPUT_KEYS)} fake-model calls; got {fake.calls}"
    )

    # AG-06: pipeline produced a full design with Stitch degraded.
    assert degradation.is_degraded is True
