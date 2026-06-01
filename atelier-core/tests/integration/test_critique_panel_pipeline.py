"""AT-021 integration test — hermetic ADK ParallelAgent critique panel.

PRD v2.2 §3.2 / §12 E2 (AT-021).

The test is hermetic: a :class:`_FakeLlm` (a ``BaseLlm`` that yields a single
non-empty response per call, no network) replaces the served Gemini model, so the
real ADK ``ParallelAgent`` executes offline. ``_FakeLlm.calls`` proves all four
critics were served by the fake — i.e. zero live model calls.

Acceptance condition: after a single run, every key in ``CRITIQUE_OUTPUT_KEYS``
is present in session state and non-empty, and ``fake.calls == 4``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import pytest
from atelier.nodes.critique_panel import CRITIQUE_OUTPUT_KEYS, create_critique_panel
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types as genai_types

if TYPE_CHECKING:
    from google.adk.models.llm_request import LlmRequest

_APP = "atelier"
_USER = "user-at021"
_SID = "session-at021"
_MESSAGE = "Critique the UI design."

#: The pre-seeded ui_design value injected into session state so the critics
#: have something to critique (mirrors the production flow where the Designer
#: writes to the ui_design key in AT-020 before the panel runs in AT-021).
_DESIGN_VALUE = "<main><h1>Co-working Studio</h1><p>Quiet desks, fast fibre.</p></main>"


class _FakeLlm(BaseLlm):
    """Hermetic stand-in for the served Gemini model.

    Yields one non-empty text response per call with no network I/O, so the real
    ADK ``ParallelAgent`` runs offline and each critic's ``output_key`` is
    populated. ``calls`` records how many critics the fake served (proving no
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
                parts=[genai_types.Part(text=f"FAKE_CRITIC_OUTPUT_{self.calls}")],
            )
        )


@pytest.mark.anyio
async def test_critique_panel_writes_all_output_keys() -> None:
    """AT-021 acceptance: all four CRITIQUE_OUTPUT_KEYS are written to session state,
    each non-empty, after a single parallel panel run with a hermetic fake model."""
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=_APP,
        user_id=_USER,
        session_id=_SID,
        state={"ui_design": _DESIGN_VALUE},
    )

    fake = _FakeLlm(model="fake-hermetic")
    panel = create_critique_panel(model=fake)

    runner = Runner(agent=panel, session_service=session_service, app_name=_APP)
    async for _event in runner.run_async(
        user_id=_USER,
        session_id=_SID,
        new_message=genai_types.Content(role="user", parts=[genai_types.Part(text=_MESSAGE)]),
    ):
        pass

    refreshed = await session_service.get_session(app_name=_APP, user_id=_USER, session_id=_SID)
    assert refreshed is not None, "Session must exist after run"

    state = dict(refreshed.state)

    for key in CRITIQUE_OUTPUT_KEYS:
        assert key in state, (
            f"output_key '{key}' missing from session state after panel run; "
            f"state keys present: {sorted(state.keys())}"
        )
        assert str(state[key]).strip(), f"output_key '{key}' produced empty value in session state"


@pytest.mark.anyio
async def test_critique_panel_all_critics_served_by_fake() -> None:
    """Hermeticity: all four critics ran through the fake model (one call each),
    proving zero live model surfaces were reached."""
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=_APP,
        user_id=_USER,
        session_id="session-at021-calls",
        state={"ui_design": _DESIGN_VALUE},
    )

    fake = _FakeLlm(model="fake-hermetic")
    panel = create_critique_panel(model=fake)

    runner = Runner(agent=panel, session_service=session_service, app_name=_APP)
    async for _event in runner.run_async(
        user_id=_USER,
        session_id="session-at021-calls",
        new_message=genai_types.Content(role="user", parts=[genai_types.Part(text=_MESSAGE)]),
    ):
        pass

    assert fake.calls == len(CRITIQUE_OUTPUT_KEYS), (
        f"expected one fake-model call per critic ({len(CRITIQUE_OUTPUT_KEYS)}); got {fake.calls}"
    )
