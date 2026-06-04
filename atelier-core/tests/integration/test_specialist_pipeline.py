"""AT-020 acceptance oracle — the DDLC role-specialist ``SequentialAgent``.

PRD v2.2 §3.2 / §12 E2 (AT-020): the N3a node is a ``SequentialAgent`` of six
DDLC specialists, each writing a unique ``output_key`` into shared session state,
in production order. Acceptance: *an integration test asserts the session state
contains the exact ordered ``output_key`` set*
``["ux_research","ia_flows","wireframe","ui_design","interaction_spec","tokens"]``
*after a run, each non-empty, in that production order.*

The test is hermetic: a :class:`_FakeLlm` (a ``BaseLlm`` that yields a single
non-empty response per call, no network) replaces the served Gemini model, so the
**real** ADK ``SequentialAgent`` executes offline. ``_FakeLlm.calls`` proves every
specialist was served by the fake — i.e. zero live model calls. The Stitch MCP
toolset is forced into its degraded (fallback) mode so the run touches no external
process, which also exercises the AG-06 "produce a design even without Stitch" path.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from atelier.integrations.stitch_mcp import StitchDegradationInfo
from atelier.orchestrator.specialists import (
    SPECIALIST_OUTPUT_KEYS,
    create_specialist_pipeline,
)
from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types as genai_types

if TYPE_CHECKING:
    from google.adk.models.llm_request import LlmRequest

_APP = "atelier"
_USER = "user-at020"
_SID = "session-at020"
_BRIEF = "Build a landing page for a quiet co-working space, editorial register."

#: Patch target — the name `specialists` binds at import (FIX-3 / AG-06 fallback).
_STITCH_TARGET = "atelier.orchestrator.specialists.try_get_stitch_mcp_toolset"

#: The exact contract AT-020 locks (kept literal here so the test fails loudly if
#: the production constant ever drifts).
_EXPECTED_ORDER = (
    "ux_research",
    "ia_flows",
    "wireframe",
    "ui_design",
    "interaction_spec",
    "tokens",
)


class _FakeLlm(BaseLlm):
    """Hermetic stand-in for the served Gemini model.

    Yields one non-empty text response per call with no network I/O, so the real
    ADK ``SequentialAgent`` runs offline and each specialist's ``output_key`` is
    populated. ``calls`` records how many specialists the fake served (proving no
    live model surface was reached).
    """

    calls: int = 0

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,  # noqa: FBT001, FBT002 — must match BaseLlm override signature
    ) -> AsyncGenerator[LlmResponse, None]:
        self.calls += 1
        yield LlmResponse(
            content=genai_types.Content(
                role="model",
                parts=[genai_types.Part(text=f"FAKE_SPECIALIST_OUTPUT_{self.calls}")],
            )
        )


def _degraded_stitch(*args: Any, **kwargs: Any) -> tuple[None, StitchDegradationInfo]:
    """Force the Stitch-unavailable fallback: no toolset, degradation acknowledged."""
    return None, StitchDegradationInfo(
        is_degraded=True,
        reason="Stitch MCP disabled for hermetic test",
        fallback_mode="direct_generation",
    )


async def _run_specialist_pipeline() -> tuple[dict[str, Any], int, StitchDegradationInfo]:
    """Run the production specialist pipeline offline; return (state, fake.calls, degradation)."""
    session_service = InMemorySessionService()
    await session_service.create_session(app_name=_APP, user_id=_USER, session_id=_SID)

    fake = _FakeLlm(model="fake-hermetic")
    with patch(_STITCH_TARGET, side_effect=_degraded_stitch):
        pipeline, degradation = create_specialist_pipeline(model=fake)

    runner = Runner(agent=pipeline, session_service=session_service, app_name=_APP)
    async for _event in runner.run_async(
        user_id=_USER,
        session_id=_SID,
        new_message=genai_types.Content(role="user", parts=[genai_types.Part(text=_BRIEF)]),
    ):
        pass

    refreshed = await session_service.get_session(app_name=_APP, user_id=_USER, session_id=_SID)
    assert refreshed is not None
    return dict(refreshed.state), fake.calls, degradation


@pytest.mark.anyio
async def test_pipeline_writes_exact_ordered_output_keys() -> None:
    """AT-020 acceptance: the six DDLC ``output_key``s appear in production order,
    each non-empty, after a single pipeline run."""
    state, _calls, _deg = await _run_specialist_pipeline()

    produced_in_order = [key for key in state if key in set(SPECIALIST_OUTPUT_KEYS)]
    assert produced_in_order == list(SPECIALIST_OUTPUT_KEYS), (
        f"session state must contain the exact ordered DDLC output_key set; got {produced_in_order}"
    )
    for key in SPECIALIST_OUTPUT_KEYS:
        assert key in state, f"missing output_key: {key}"
        assert str(state[key]).strip(), f"output_key produced empty value: {key}"


@pytest.mark.anyio
async def test_every_specialist_served_by_fake_no_live_call() -> None:
    """Hermeticity: every specialist ran through the fake model (one call each),
    so zero live model surfaces were reached."""
    _state, calls, degradation = await _run_specialist_pipeline()
    assert calls == len(SPECIALIST_OUTPUT_KEYS), (
        f"expected one fake-model call per specialist ({len(SPECIALIST_OUTPUT_KEYS)}); got {calls}"
    )
    # AG-06: the pipeline still produced a full design with Stitch degraded.
    assert degradation.is_degraded is True


def test_published_output_key_contract_is_locked() -> None:
    """The production constant matches the AT-020-locked contract: six unique keys, in order."""
    assert SPECIALIST_OUTPUT_KEYS == _EXPECTED_ORDER
    assert len(set(SPECIALIST_OUTPUT_KEYS)) == len(_EXPECTED_ORDER) == 6


@pytest.mark.anyio
async def test_sequential_order_is_observable_and_directional() -> None:
    """Methodology control: a ``SequentialAgent`` writes ``output_key``s into state
    in *construction* order — so the ordered-set assertion above is non-vacuous and
    genuinely detects mis-ordering (reversing the agents reverses the produced order)."""

    async def _produced_order(order: list[tuple[str, str]]) -> list[str]:
        # Fresh agents per run: ADK binds each sub-agent to a single parent, so the
        # instances cannot be reused across two SequentialAgents.
        fake = _FakeLlm(model="fake-hermetic")
        sub_agents = [
            LlmAgent(name=name, model=fake, output_key=key, instruction="produce output")
            for name, key in order
        ]
        svc = InMemorySessionService()
        await svc.create_session(app_name=_APP, user_id=_USER, session_id="ctrl")
        runner = Runner(
            agent=SequentialAgent(name="Ctrl", sub_agents=sub_agents),
            session_service=svc,
            app_name=_APP,
        )
        async for _e in runner.run_async(
            user_id=_USER,
            session_id="ctrl",
            new_message=genai_types.Content(role="user", parts=[genai_types.Part(text="go")]),
        ):
            pass
        session = await svc.get_session(app_name=_APP, user_id=_USER, session_id="ctrl")
        assert session is not None
        return [k for k in session.state if k in {"alpha", "beta"}]

    forward = [("First", "alpha"), ("Second", "beta")]
    assert await _produced_order(forward) == ["alpha", "beta"]
    assert await _produced_order(list(reversed(forward))) == ["beta", "alpha"]
