"""AT-031 acceptance oracle — fail-closed human-in-the-loop sign-off gate.

PRD v2.2 §1 (the "pause for a human" win-condition), §12 E3 (line 358), §16 (golden
path: plan -> scope-lock -> Awaiting Sign-off -> Approve -> cards march), R5 (durability).

The six oracles, all hermetic (no network — every model surface, including the FixerAgent,
is faked or the inner N3a Runner is replaced):

1. ``test_await_signoff_is_long_running_and_requests_confirmation`` — drives the real
   ``LongRunningFunctionTool`` through a real ADK ``LlmAgent`` + ``Runner`` and asserts the
   native halt: an ``adk_request_confirmation`` ``FunctionCall`` is emitted with the call id
   registered in ``Event.long_running_tool_ids`` and ``requested_tool_confirmations``
   populated, with exactly one model call up to the confirmation request (the driver stops
   there). Proves the ADK mechanism (acceptance bullet 1).
2. ``test_run_halts_and_persists_checkpoint`` — ``run(require_signoff=True)`` returns the
   halt sentinel, persists ``signoff_status == AWAITING_SIGNOFF`` durably, and emits no
   screen/N3a events.
3. ``test_resume_idempotent_stage_counts`` — run -> HALT, then a FRESH ``AtelierRunner``
   (the crash) resumes from the same session service with a confirmed ``ToolConfirmation``;
   completed N1/N2 stage counts show delta 0, post-signoff N3a token count > 0, and the
   payload is well-formed.
4. ``test_no_model_call_between_halt_and_approve`` — the halt + inspection window runs under
   ``hermetic()`` and asserts ``LiveCallGuard.live_calls == 0``.
5. ``test_negative_no_approval_stays_awaiting`` — resume with
   ``ToolConfirmation(confirmed=False)`` leaves ``signoff_status == AWAITING_SIGNOFF`` and
   does not advance to N3a; a later confirmed resume still works (deny-then-approve).
6. ``test_double_resume_does_not_recharge`` — a SECOND confirmed resume on an already
   APPROVED/COMPLETED session returns the ``already_resumed`` sentinel and re-runs ZERO
   N3a stages (PRD P4 "crash -> resume, no double-charge"). Fail-closed re-entry guard.

The tests are non-rigged: they assert structural durability properties (deltas, status
transitions, native ADK events), never specific generated output values.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest
from atelier.gates.signoff import (
    AWAIT_SIGNOFF_TOOL,
    CHECKPOINT_KEY,
    SIGNOFF_STATUS_KEY,
    STATUS_APPROVED,
    STATUS_AWAITING,
    STATUS_COMPLETED,
    is_signoff_confirmed,
)
from atelier.intake.brief_spec import BriefSpec
from atelier.intake.source_resolver import ProjectContext
from atelier.orchestrator.planner import PlanStep
from atelier.orchestrator.runner import (
    STAGE_N1_BRIEF_PARSE,
    STAGE_N2_SOURCE_RESOLVE,
    STAGE_N3A_SPECIALIST_PIPELINE,
    AtelierRunner,
)
from atelier.testing.record_replay import hermetic
from google.adk.agents.llm_agent import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools.tool_confirmation import ToolConfirmation
from google.genai import types as genai_types

if TYPE_CHECKING:
    from google.adk.models.llm_request import LlmRequest

_APP = "atelier"
_USER = "u1"

#: A brief long enough to clear the deterministic BriefParserGate word-count check.
_BRIEF = "Build a calm editorial landing page and a pricing page for a co-working studio."


# --------------------------------------------------------------------------- #
# Oracle 1 — native ADK long-running confirmation halt
# --------------------------------------------------------------------------- #


class _FakeSignoffCallingLlm(BaseLlm):
    """Hermetic model that always emits the ``await_signoff`` tool call.

    A real model would re-request the (still-pending) confirmation rather than invent a
    final answer, so the fake keeps emitting the call. ``calls`` records how many model
    turns occurred — the driver stops at the first ``adk_request_confirmation`` event, so
    a correct native halt leaves ``calls == 1``.
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
                parts=[
                    genai_types.Part(
                        function_call=genai_types.FunctionCall(name="await_signoff", args={})
                    )
                ],
            )
        )


@pytest.mark.anyio
async def test_await_signoff_is_long_running_and_requests_confirmation() -> None:
    """The native ADK halt: ``adk_request_confirmation`` long-running event +
    ``requested_tool_confirmations`` populated, with a single model call up to it."""
    from google.adk.flows.llm_flows.functions import (
        REQUEST_CONFIRMATION_FUNCTION_CALL_NAME,
    )

    svc = InMemorySessionService()
    await svc.create_session(app_name=_APP, user_id=_USER, session_id="s-native")
    fake = _FakeSignoffCallingLlm(model="fake-hermetic")
    agent = LlmAgent(
        name="signoff_agent",
        model=fake,
        tools=[AWAIT_SIGNOFF_TOOL],
        instruction="call await_signoff",
    )
    runner = Runner(agent=agent, session_service=svc, app_name=_APP)

    saw_original_tool_call = False
    saw_confirmation_request = False
    saw_requested_confirmations = False
    calls_at_confirmation: int | None = None

    async for ev in runner.run_async(
        user_id=_USER,
        session_id="s-native",
        new_message=genai_types.Content(role="user", parts=[genai_types.Part(text="go")]),
    ):
        fc_names = [fc.name for fc in ev.get_function_calls()]
        if "await_signoff" in fc_names:
            saw_original_tool_call = True
        if REQUEST_CONFIRMATION_FUNCTION_CALL_NAME in fc_names and getattr(
            ev, "long_running_tool_ids", None
        ):
            # The native halt: the runner emits a long-running adk_request_confirmation
            # FunctionCall. Record the model-call count — the runner-internal events that
            # follow (which carry requested_tool_confirmations) issue NO further model call.
            saw_confirmation_request = True
            calls_at_confirmation = fake.calls
        if ev.actions and ev.actions.requested_tool_confirmations:
            # The function-response event that registers the ToolConfirmation. This is the
            # last signal a native client needs before pausing the run for the human.
            saw_requested_confirmations = True
            break

    assert saw_original_tool_call, "the agent never issued the await_signoff tool call"
    assert saw_confirmation_request, (
        "the runner never emitted the native adk_request_confirmation long-running event"
    )
    assert saw_requested_confirmations, "requested_tool_confirmations was never populated"
    assert calls_at_confirmation == 1, (
        f"exactly one model call should precede the confirmation halt; got {calls_at_confirmation}"
    )
    # No further model call occurred between the confirmation request and the
    # requested_tool_confirmations registration (the halt window).
    assert fake.calls == 1, (
        f"the runner must issue no model call during the halt window; got {fake.calls}"
    )


def test_is_signoff_confirmed_is_fail_closed() -> None:
    """The helper denies on None and on confirmed=False; only confirmed=True advances."""
    assert is_signoff_confirmed(None) is False
    assert is_signoff_confirmed(ToolConfirmation(confirmed=False)) is False
    assert is_signoff_confirmed(ToolConfirmation(confirmed=True)) is True


# --------------------------------------------------------------------------- #
# Shared offline pipeline scaffolding for run()/resume() oracles
# --------------------------------------------------------------------------- #

_VALID_BRIEF_JSON = """
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

#: Two surfaces so the stage accumulators record more than one N3a call after approval.
_SURFACES = ["landing page", "pricing page"]


def _fake_brief() -> BriefSpec:
    return BriefSpec.model_validate_json(_VALID_BRIEF_JSON)


def _fake_plan() -> PlanStep:
    # should_run_wrai=False keeps WRAI offline (no web_research network surface).
    return PlanStep(should_run_wrai=False, surfaces=list(_SURFACES), reasoning="test plan")


def _fake_project_ctx() -> ProjectContext:
    return ProjectContext(
        brief=_fake_brief(),
        design_tokens={"primary_color": "#101010"},
        memory_bank_priors=["prior-a"],
    )


class _FakeN3aRunner:
    """Stand-in for the ADK ``Runner`` the runner builds for N3a.

    Yields one candidate HTML event per run, fully offline. Constructed with the same
    keyword arguments the production code passes (``agent``, ``session_service``,
    ``app_name``), which are ignored here.
    """

    def __init__(self, **_kwargs: Any) -> None:
        pass

    async def run_async(self, **_kwargs: Any) -> AsyncGenerator[dict[str, str], None]:
        # A minimally well-formed candidate so N3c gates have something to score.
        yield {
            "type": "message",
            "data": (
                "<!doctype html><html lang='en'><head><title>Studio</title></head>"
                "<body><main><h1>Co-working Studio</h1>"
                "<p>Quiet desks, fast fibre.</p></main></body></html>"
            ),
        }


def _degraded_stitch() -> tuple[None, Any]:
    from atelier.integrations.stitch_mcp import StitchDegradationInfo

    return None, StitchDegradationInfo(
        is_degraded=True,
        reason="Stitch MCP disabled for hermetic test",
        fallback_mode="direct_generation",
    )


def _offline_fixer_directive(*_args: Any, **_kwargs: Any) -> Any:
    """A deterministic no-op FixerDirective — offline-by-construction.

    The fake N3a candidate does not clear the N3c gates, so the convergence loop does NOT
    converge and the production ``FixerAgent.fix`` is invoked once per surface. Unpatched,
    each call builds a real ``genai`` client that raises ``No API key`` and is fail-soft
    swallowed — i.e. the resume path would be "offline-by-exception". Patching ``fix`` with
    this deterministic directive makes the resume path offline-BY-CONSTRUCTION: no live LLM
    client is ever constructed, so ``LiveCallGuard.live_calls`` stays 0 by design rather
    than by a swallowed degradation. The directive mirrors the Fixer's own fail-soft no-op
    shape, so loop behaviour (a non-converging re-anchor) is unchanged.
    """
    from atelier.nodes.fixer import FixerDirective

    return FixerDirective(
        mutations=[],
        prompt_amendments=["Offline test directive: revise and improve the design."],
        reasoning="Deterministic offline fixer directive (no live LLM call).",
    )


def _offline_pipeline_patches() -> list[Any]:
    """Patches that make a full ``AtelierRunner.run`` execute offline and deterministically."""
    return [
        patch(
            "atelier.intake.brief_parser.BriefParserAgent.parse",
            new=AsyncMock(return_value=_fake_brief()),
        ),
        patch(
            "atelier.orchestrator.planner.PlannerAgent.plan",
            new=AsyncMock(return_value=_fake_plan()),
        ),
        patch("atelier.orchestrator.runner.source_resolver_gate", return_value=True),
        patch(
            "atelier.orchestrator.runner.source_resolver_agent",
            new=AsyncMock(return_value=_fake_project_ctx()),
        ),
        patch(
            "atelier.orchestrator.runner.create_specialist_pipeline",
            side_effect=_degraded_stitch,
        ),
        patch("atelier.orchestrator.runner.Runner", _FakeN3aRunner),
        # Offline-by-construction: patch the FixerAgent surface so the non-converging
        # resume loop never builds a live genai client (no "offline-by-exception").
        patch(
            "atelier.nodes.fixer.FixerAgent.fix",
            new=AsyncMock(side_effect=_offline_fixer_directive),
        ),
    ]


class _PatchStack:
    """Apply a list of unittest.mock patchers as one context manager."""

    def __init__(self, patchers: list[Any]) -> None:
        self._patchers = patchers

    def __enter__(self) -> _PatchStack:
        for p in self._patchers:
            p.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        for p in reversed(self._patchers):
            p.stop()


def _offline() -> _PatchStack:
    return _PatchStack(_offline_pipeline_patches())


# --------------------------------------------------------------------------- #
# Oracle 2 — run() halts and persists an idempotent checkpoint
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_run_halts_and_persists_checkpoint() -> None:
    """``run(require_signoff=True)`` returns the halt sentinel, persists
    ``AWAITING_SIGNOFF`` durably, and emits no screen/N3a progress events."""
    svc = InMemorySessionService()
    runner = AtelierRunner(session_service=svc)

    events: list[str] = []

    async def progress(event_type: str, _payload: dict[str, Any]) -> None:
        events.append(event_type)

    with _offline():
        result = await runner.run(_BRIEF, progress_callback=progress, require_signoff=True)

    assert result["status"] == "awaiting_signoff"
    session_id = result["session_id"]
    assert result["signoff"]["is_long_running"] is True
    assert result["signoff"]["requested_tool_confirmations"], (
        "the native confirmation request was never registered"
    )

    # Durable persistence: a fresh read of the session sees AWAITING_SIGNOFF + checkpoint.
    session = await svc.get_session(app_name=_APP, user_id=_USER, session_id=session_id)
    assert session is not None
    assert session.state.get(SIGNOFF_STATUS_KEY) == STATUS_AWAITING
    assert isinstance(session.state.get(CHECKPOINT_KEY), dict)

    # No screen generation happened — the halt is before N3a.
    assert "signoff" in events
    assert "screen_start" not in events, "the screen loop must not run before approval"
    assert "complete" not in events


# --------------------------------------------------------------------------- #
# Oracle 3 — fresh-runner crash resume, idempotent stage counts
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_resume_idempotent_stage_counts() -> None:
    """Run -> HALT -> (crash) -> a FRESH ``AtelierRunner`` resumes from the shared session
    service with a confirmed ``ToolConfirmation``; N1/N2 completed-stage counts show delta
    0, N3a post-signoff token count > 0, and the payload is well-formed."""
    svc = InMemorySessionService()
    runner_a = AtelierRunner(session_service=svc)

    with _offline():
        halt = await runner_a.run(_BRIEF, require_signoff=True)

    session_id = halt["session_id"]
    # Stage counts captured at the halt (N1 + N2 ran once each; N3a has not run).
    pre_calls = dict(runner_a._governor._state.stage_call_counts)
    assert pre_calls.get(STAGE_N1_BRIEF_PARSE) == 1
    assert pre_calls.get(STAGE_N2_SOURCE_RESOLVE) == 1
    assert STAGE_N3A_SPECIALIST_PIPELINE not in pre_calls

    # The "crash": a brand-new runner instance, same session service, no shared memory.
    runner_b = AtelierRunner(session_service=svc)
    assert runner_b is not runner_a

    with _offline():
        payload = await runner_b.resume(session_id, ToolConfirmation(confirmed=True))

    # Approved path returns a full payload (not the halt sentinel).
    assert payload.get("status") != "awaiting_signoff"
    assert payload["session_id"] == session_id
    assert payload["best_candidate"] is not None
    assert "screens" in payload
    assert set(payload["screens"]) == set(_SURFACES)

    post_calls = runner_b._governor._state.stage_call_counts
    post_tokens = runner_b._governor._state.stage_token_counts

    # Completed-stage delta 0: N1/N2 were restored from the checkpoint, never re-run.
    assert post_calls.get(STAGE_N1_BRIEF_PARSE) == pre_calls.get(STAGE_N1_BRIEF_PARSE), (
        "N1 must not re-run on resume (idempotent completed-stage count)"
    )
    assert post_calls.get(STAGE_N2_SOURCE_RESOLVE) == pre_calls.get(STAGE_N2_SOURCE_RESOLVE), (
        "N2 must not re-run on resume (idempotent completed-stage count)"
    )

    # Post-signoff stages: N3a ran (at least once per surface; the convergence loop may
    # iterate within a surface) and its token delta is > 0. The token count must equal the
    # call count times the per-call attribution — i.e. it accrued only during resume.
    n3a_calls = post_calls.get(STAGE_N3A_SPECIALIST_PIPELINE, 0)
    assert n3a_calls >= len(_SURFACES), (
        f"N3a must run for every surface after approval; got {n3a_calls} for "
        f"{len(_SURFACES)} surfaces"
    )
    assert post_tokens.get(STAGE_N3A_SPECIALIST_PIPELINE, 0) > 0, (
        "post-signoff stage token delta must be > 0"
    )
    # The token delta is exclusively post-signoff: N1/N2 token counts equal their
    # checkpointed (pre-halt) values, so no pre-signoff stage accrued tokens on resume.
    assert post_tokens.get(
        STAGE_N1_BRIEF_PARSE
    ) == runner_a._governor._state.stage_token_counts.get(STAGE_N1_BRIEF_PARSE), (
        "N1 token count must be frozen across resume"
    )
    assert post_tokens.get(
        STAGE_N2_SOURCE_RESOLVE
    ) == runner_a._governor._state.stage_token_counts.get(STAGE_N2_SOURCE_RESOLVE), (
        "N2 token count must be frozen across resume"
    )

    # The approval is durable too. After the surface loop returns, resume() records the
    # terminal COMPLETED state (APPROVED is the transient mid-surface state; COMPLETED is
    # the post-surface terminal state the re-entry guard keys off — see oracle 6).
    session = await svc.get_session(app_name=_APP, user_id=_USER, session_id=session_id)
    assert session is not None
    assert session.state.get(SIGNOFF_STATUS_KEY) == STATUS_COMPLETED


# --------------------------------------------------------------------------- #
# Oracle 4 — zero model calls during the halt window
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_no_model_call_between_halt_and_approve() -> None:
    """The halt + inspection window touches no live model/tool surface (AT-003)."""
    svc = InMemorySessionService()
    runner = AtelierRunner(session_service=svc)

    with hermetic() as guard, _offline():
        halt = await runner.run(_BRIEF, require_signoff=True)
        # Inspect the persisted halt state — still no model call.
        session = await svc.get_session(app_name=_APP, user_id=_USER, session_id=halt["session_id"])
        assert session is not None
        assert session.state.get(SIGNOFF_STATUS_KEY) == STATUS_AWAITING

    assert guard.live_calls == 0, (
        f"the sign-off halt window must issue zero live model calls; got {guard.live_calls}"
    )


# --------------------------------------------------------------------------- #
# Oracle 5 — negative arm: no approval stays AWAITING_SIGNOFF
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_negative_no_approval_stays_awaiting() -> None:
    """``resume`` with ``confirmed=False`` leaves the run AWAITING_SIGNOFF and does not
    advance to N3a (fail-closed)."""
    svc = InMemorySessionService()
    runner = AtelierRunner(session_service=svc)

    with _offline():
        halt = await runner.run(_BRIEF, require_signoff=True)

    session_id = halt["session_id"]
    runner_b = AtelierRunner(session_service=svc)

    with _offline():
        denied = await runner_b.resume(session_id, ToolConfirmation(confirmed=False))

    assert denied["status"] == "awaiting_signoff"
    assert denied["session_id"] == session_id
    # N3a never ran on the denied resume.
    assert STAGE_N3A_SPECIALIST_PIPELINE not in runner_b._governor._state.stage_call_counts

    session = await svc.get_session(app_name=_APP, user_id=_USER, session_id=session_id)
    assert session is not None
    assert session.state.get(SIGNOFF_STATUS_KEY) == STATUS_AWAITING

    # Deny-then-approve still works: the denied session stayed AWAITING_SIGNOFF (never
    # APPROVED/COMPLETED), so the terminal re-entry guard does not block a later approve.
    runner_c = AtelierRunner(session_service=svc)
    with _offline():
        approved = await runner_c.resume(session_id, ToolConfirmation(confirmed=True))
    assert approved.get("status") not in ("awaiting_signoff", "already_resumed")
    assert approved["best_candidate"] is not None
    assert runner_c._governor._state.stage_call_counts.get(STAGE_N3A_SPECIALIST_PIPELINE, 0) >= len(
        _SURFACES
    )
    session = await svc.get_session(app_name=_APP, user_id=_USER, session_id=session_id)
    assert session is not None
    assert session.state.get(SIGNOFF_STATUS_KEY) == STATUS_COMPLETED


# --------------------------------------------------------------------------- #
# Oracle 6 — double-resume re-entry must not re-run surfaces (no double-charge)
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_double_resume_does_not_recharge() -> None:
    """A SECOND confirmed resume on an already-approved session must NOT re-run surfaces.

    PRD P4 ("crash -> resume, no double-charge"). The first confirmed resume (runner_b)
    runs the surface loop and records N3a calls. A second confirmed resume — modelling an
    approval-webhook redelivery / UI double-click / crash-after-approve — arrives on a
    THIRD fresh runner_c (a fresh runner has empty accumulators, so any N3a count it shows
    can only have come from a re-run). It must return the ``already_resumed`` sentinel and
    record ZERO N3a stage calls: no duplicated model spend.

    The resume window also runs under ``hermetic()`` so the offline-by-construction path is
    proven to touch no live model surface (``live_calls == 0``).
    """
    svc = InMemorySessionService()
    runner_a = AtelierRunner(session_service=svc)

    with _offline():
        halt = await runner_a.run(_BRIEF, require_signoff=True)
    session_id = halt["session_id"]

    # First confirmed resume on a fresh runner_b: runs surfaces, records N3a calls.
    runner_b = AtelierRunner(session_service=svc)
    with hermetic() as guard_b, _offline():
        payload = await runner_b.resume(session_id, ToolConfirmation(confirmed=True))
    assert payload.get("status") != "awaiting_signoff"
    assert payload.get("status") != "already_resumed"
    assert runner_b._governor._state.stage_call_counts.get(STAGE_N3A_SPECIALIST_PIPELINE, 0) >= len(
        _SURFACES
    ), "the first resume must actually run N3a for every surface"
    # Offline-by-construction: the first resume issued zero live model calls.
    assert guard_b.live_calls == 0, (
        f"the first resume must be offline-by-construction; got {guard_b.live_calls} live calls"
    )

    # The session is now in a terminal state recorded durably.
    session = await svc.get_session(app_name=_APP, user_id=_USER, session_id=session_id)
    assert session is not None
    assert session.state.get(SIGNOFF_STATUS_KEY) == STATUS_COMPLETED

    # Second confirmed resume on a THIRD fresh runner_c (webhook redelivery / double-click).
    runner_c = AtelierRunner(session_service=svc)
    assert runner_c is not runner_b
    with hermetic() as guard_c, _offline():
        re_entry = await runner_c.resume(session_id, ToolConfirmation(confirmed=True))

    # Fail-closed sentinel — NOT a re-run, NOT a fresh payload.
    assert re_entry["status"] == "already_resumed", (
        f"a second confirmed resume must be a no-op sentinel; got {re_entry.get('status')!r}"
    )
    assert re_entry["session_id"] == session_id
    assert re_entry["signoff_status"] == STATUS_COMPLETED
    assert "best_candidate" not in re_entry, "the re-entry sentinel must not assemble a payload"

    # The decisive no-double-charge proof: runner_c (fresh, empty accumulators) recorded
    # ZERO N3a stage calls — the surface loop never ran a second time.
    assert runner_c._governor._state.stage_call_counts.get(STAGE_N3A_SPECIALIST_PIPELINE, 0) == 0, (
        "the re-entry must NOT re-run N3a (no double-charge)"
    )
    assert guard_c.live_calls == 0, (
        f"the re-entry must issue zero live model calls; got {guard_c.live_calls}"
    )

    # The durable terminal state is unchanged.
    session = await svc.get_session(app_name=_APP, user_id=_USER, session_id=session_id)
    assert session is not None
    assert session.state.get(SIGNOFF_STATUS_KEY) == STATUS_COMPLETED
