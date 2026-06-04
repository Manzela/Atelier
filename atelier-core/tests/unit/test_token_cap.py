"""AT-095 acceptance oracle — per-user lifetime 5M-token hard cap enforcement.

PRD §13.2 / G14 / G16 / R5. Hermetic: the full ``AtelierRunner.run`` executes
offline (every model surface is faked; no network) and the token counter uses the
in-memory backend. Drives a signed-in user across multiple runs and asserts the
seven acceptance criteria:

    (a) zero cap-UI below the cap, all requests succeed + token_delta events emit;
    (b) the branded "Contact administrator…" message rendered exactly once at cap;
    (c) no Vertex call once at cap (run-start pre-flight rejects fail-loud);
    (d) the fail-loud breach carries uid / cap context for the alertable log;
    (e) the counter persists across runs (does not reset);
    (f) the request-rate limit blocks a rapid burn;
    (g) thinking tokens are counted.

The tests assert structural properties (cap fires, counter grows, message shown
once), never specific generated output — no test-driven slop.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from atelier.durability.usage_counter import (
    TOKEN_CAP_DEFAULT,
    UsageCounterStore,
    reset_global_breaker,
)
from atelier.intake.brief_spec import BriefSpec
from atelier.intake.source_resolver import ProjectContext
from atelier.models.data_contracts import TenantContext
from atelier.nodes.llm_judge import LLMJudgeResponse
from atelier.orchestrator.governor import (
    TOKEN_CAP_MESSAGE,
    GovernorCircuitBreakerOpen,
    GovernorRateLimitExceeded,
    GovernorTokenCapExceeded,
)
from atelier.orchestrator.planner import PlanStep
from atelier.orchestrator.runner import AtelierRunner
from google.adk.sessions.in_memory_session_service import InMemorySessionService


@pytest.fixture(autouse=True)
def _reset_global_breaker_after() -> Iterator[None]:
    # The fleet circuit-breaker is process-wide module state; the breaker
    # integration test trips it with a long cooldown. Reset after every test so a
    # tripped state never leaks into another test (spurious 503s).
    yield
    reset_global_breaker()


_BRIEF = "Build a calm editorial landing page for a co-working studio with pricing."
_UID = "cap-test-user"

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


def _fake_brief() -> BriefSpec:
    return BriefSpec.model_validate_json(_VALID_BRIEF_JSON)


def _fake_plan() -> PlanStep:
    # Single surface keeps the cap assertions unambiguous; WRAI offline (no network).
    return PlanStep(should_run_wrai=False, surfaces=["landing page"], reasoning="test plan")


def _fake_project_ctx() -> ProjectContext:
    return ProjectContext(
        brief=_fake_brief(),
        design_tokens={"primary_color": "#101010"},
        memory_bank_priors=["prior-a"],
    )


class _FakeN3aRunner:
    """Offline stand-in for the ADK Runner: yields one candidate, no usage_metadata."""

    def __init__(self, **_kwargs: Any) -> None:
        pass

    async def run_async(self, **_kwargs: Any) -> AsyncGenerator[dict[str, str], None]:
        yield {
            "type": "message",
            "data": (
                "<!doctype html><html lang='en'><head><title>Studio</title></head>"
                "<body><main><h1>Co-working Studio</h1>"
                "<p>Quiet desks, fast fibre.</p></main></body></html>"
            ),
        }


def _degraded_stitch(*args: Any, **kwargs: Any) -> tuple[None, Any]:
    from atelier.integrations.stitch_mcp import StitchDegradationInfo

    return None, StitchDegradationInfo(
        is_degraded=True,
        reason="Stitch MCP disabled for hermetic test",
        fallback_mode="direct_generation",
    )


def _offline_fixer_directive(*_args: Any, **_kwargs: Any) -> Any:
    from atelier.nodes.fixer import FixerDirective

    return FixerDirective(
        mutations=[],
        prompt_amendments=["Offline test directive: revise and improve the design."],
        reasoning="Deterministic offline fixer directive (no live LLM call).",
    )


class _PatchStack:
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
    return _PatchStack(
        [
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
            patch(
                "atelier.nodes.fixer.FixerAgent.fix",
                new=AsyncMock(side_effect=_offline_fixer_directive),
            ),
        ]
    )


def _tenant_ctx() -> TenantContext:
    return TenantContext(tenant_id="t1", user_id=_UID, project_id="p1")


def _fresh_store(**kwargs: Any) -> UsageCounterStore:
    s = UsageCounterStore(backend="memory", **kwargs)
    s.reset()  # clear the process-wide _MEMORY so each test is isolated
    return s


# --------------------------------------------------------------------------- #
# (a) Under the cap: requests succeed, token_delta events emit, no cap UI
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_under_cap_emits_token_deltas_and_no_cap_message() -> None:
    store = _fresh_store()
    runner = AtelierRunner(session_service=InMemorySessionService(), usage_store=store)

    events: list[tuple[str, dict[str, Any]]] = []

    async def progress(event_type: str, payload: dict[str, Any]) -> None:
        events.append((event_type, payload))

    with _offline():
        result = await runner.run(_BRIEF, _tenant_ctx(), progress_callback=progress)

    token_deltas = [p for (t, p) in events if t == "token_delta"]
    assert token_deltas, "at least one token_delta event must be emitted"
    # (b) payload shape: input / output / thinking / cumulative all present + non-negative.
    for p in token_deltas:
        assert {"input", "output", "thinking", "cumulative_user_tokens"} <= p.keys()
        assert p["input"] >= 0
        assert p["output"] >= 0
        assert p["thinking"] >= 0

    # cumulative is monotonically non-decreasing within the run.
    cumulatives = [p["cumulative_user_tokens"] for p in token_deltas]
    assert cumulatives == sorted(cumulatives)

    # (a) below the cap → NO branded cap message anywhere, and not a cap stop.
    assert result.get("user_message") != TOKEN_CAP_MESSAGE
    assert result["exit_reason"] != "token_cap_exhausted"
    assert result["tokens_used"] < TOKEN_CAP_DEFAULT
    # Persisted (the cross-run primitive).
    assert store.get_total(_UID) > 0
    assert store.get_total(_UID) == result["tokens_used"]


# --------------------------------------------------------------------------- #
# (e) The counter persists across runs (does not reset)
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_counter_persists_across_runs() -> None:
    store = _fresh_store()

    async def _run_once() -> int:
        runner = AtelierRunner(session_service=InMemorySessionService(), usage_store=store)
        with _offline():
            res = await runner.run(_BRIEF, _tenant_ctx())
        return int(res["tokens_used"])

    after_run_1 = await _run_once()
    after_run_2 = await _run_once()

    assert after_run_1 > 0
    # Run 2 starts where run 1 left off — strictly greater, never reset to a single-run total.
    assert after_run_2 > after_run_1
    assert store.get_total(_UID) == after_run_2


# --------------------------------------------------------------------------- #
# (c) + (d) Already at the cap: pre-flight rejects before any Vertex call
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_preflight_rejects_when_already_at_cap() -> None:
    store = _fresh_store()
    store.add(_UID, input_tokens=TOKEN_CAP_DEFAULT)  # simulate a user already at the cap

    runner = AtelierRunner(session_service=InMemorySessionService(), usage_store=store)
    events: list[str] = []

    async def progress(event_type: str, _payload: dict[str, Any]) -> None:
        events.append(event_type)

    with _offline(), pytest.raises(GovernorTokenCapExceeded) as exc_info:
        await runner.run(_BRIEF, _tenant_ctx(), progress_callback=progress)

    # (c) no Vertex spend once at cap — the loop never starts; no plan/screen events.
    assert "plan" not in events
    assert "screen_start" not in events
    assert "token_delta" not in events
    # (d) the breach carries the alertable context the 402 handler logs.
    exc = exc_info.value
    assert exc.uid == _UID
    assert exc.used_tokens >= TOKEN_CAP_DEFAULT
    assert exc.cap_tokens == TOKEN_CAP_DEFAULT


# --------------------------------------------------------------------------- #
# (b) Crossing the cap mid-run: graceful stop + the message exactly once
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_graceful_stop_at_cap_renders_message_once() -> None:
    store = _fresh_store()
    # One token under the cap: the first N3a generation crosses it.
    store.add(_UID, input_tokens=TOKEN_CAP_DEFAULT - 1)

    runner = AtelierRunner(session_service=InMemorySessionService(), usage_store=store)
    cap_messages: list[str] = []

    async def progress(event_type: str, payload: dict[str, Any]) -> None:
        if payload.get("user_message") == TOKEN_CAP_MESSAGE:
            cap_messages.append(event_type)

    with _offline():
        result = await runner.run(_BRIEF, _tenant_ctx(), progress_callback=progress)

    # Graceful stop — not a raise; the loop finishes the in-flight unit then halts.
    assert result["exit_reason"] == "token_cap_exhausted"
    # (b) the single branded, non-error message, rendered EXACTLY ONCE (the
    # terminal `complete` event) — never a duplicate banner or a raw quota error.
    assert result["user_message"] == TOKEN_CAP_MESSAGE
    assert cap_messages == ["complete"]
    assert store.get_total(_UID) >= TOKEN_CAP_DEFAULT


# --------------------------------------------------------------------------- #
# (b) Multi-surface: cap crossed on a LATER surface still surfaces the message
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_multi_surface_cap_crossed_on_later_surface_surfaces_message() -> None:
    # Regression for the audit finding: when surface 1 finishes UNDER the cap and
    # surface 2 crosses it, the top-level payload must still surface the cap
    # signal (it reads first_screen_res, so a naive impl would render the message
    # ZERO times). Deterministic via a fixed 100-token/generation estimate.
    store = _fresh_store()
    store.add(_UID, input_tokens=TOKEN_CAP_DEFAULT - 250)  # ~2 surfaces' worth under

    def _two_surface_plan() -> PlanStep:
        return PlanStep(
            should_run_wrai=False,
            surfaces=["landing page", "pricing page"],
            reasoning="two-surface test plan",
        )

    runner = AtelierRunner(session_service=InMemorySessionService(), usage_store=store)
    cap_messages: list[str] = []

    async def progress(event_type: str, payload: dict[str, Any]) -> None:
        if payload.get("user_message") == TOKEN_CAP_MESSAGE:
            cap_messages.append(event_type)

    patches = _PatchStack(
        [
            patch(
                "atelier.intake.brief_parser.BriefParserAgent.parse",
                new=AsyncMock(return_value=_fake_brief()),
            ),
            patch(
                "atelier.orchestrator.planner.PlannerAgent.plan",
                new=AsyncMock(return_value=_two_surface_plan()),
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
            patch(
                "atelier.nodes.fixer.FixerAgent.fix",
                new=AsyncMock(side_effect=_offline_fixer_directive),
            ),
            # Fixed per-generation token cost so the crossing point is deterministic.
            patch("atelier.orchestrator.runner._estimate_tokens", return_value=(0, 100, 0)),
        ]
    )
    with patches:
        result = await runner.run(_BRIEF, _tenant_ctx(), progress_callback=progress)

    # The cap was hit on surface 2; the top-level payload MUST surface it...
    assert result["exit_reason"] == "token_cap_exhausted"
    assert result["user_message"] == TOKEN_CAP_MESSAGE
    # ...rendered exactly once (the terminal complete event).
    assert cap_messages == ["complete"]
    # ...even though surface 1 (the first screen) stopped UNDER the cap.
    assert result["screens"]["landing page"]["exit_reason"] != "token_cap_exhausted"
    assert store.get_total(_UID) >= TOKEN_CAP_DEFAULT


# --------------------------------------------------------------------------- #
# (f) Rate limit blocks a rapid burn of runs
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_rate_limit_blocks_rapid_runs() -> None:
    store = _fresh_store(rate_limit_max_requests=1, rate_limit_window_seconds=300.0)

    async def _run() -> None:
        runner = AtelierRunner(session_service=InMemorySessionService(), usage_store=store)
        with _offline():
            await runner.run(_BRIEF, _tenant_ctx())

    await _run()  # 1st request — within the limit
    with pytest.raises(GovernorRateLimitExceeded):
        await _run()  # 2nd rapid request — blocked before any generation


# --------------------------------------------------------------------------- #
# AT-097: the fleet-wide (global) circuit-breaker is enforced at run pre-flight
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_circuit_breaker_blocks_run_after_global_budget_tripped() -> None:
    # AT-097 acceptance: "global circuit-breaker threshold enforced." With a tiny
    # fleet budget, the first run's token spend trips the breaker, and the NEXT
    # run is rejected at the pre-flight — before any Vertex call — the global
    # analogue of the per-user rate limit. Large window/cooldown so the trip
    # persists across the two back-to-back runs (no clock injection needed).
    store = _fresh_store(
        global_token_budget_per_window=1,
        global_window_seconds=3600.0,
        circuit_breaker_cooldown_seconds=3600.0,
    )

    async def _run() -> None:
        runner = AtelierRunner(session_service=InMemorySessionService(), usage_store=store)
        with _offline():
            await runner.run(_BRIEF, _tenant_ctx())

    await _run()  # 1st run consumes > 1 token → fleet window now over budget
    with pytest.raises(GovernorCircuitBreakerOpen):
        await _run()  # 2nd run rejected at pre-flight (fleet breaker open)


# --------------------------------------------------------------------------- #
# (g) Thinking tokens are captured on the judge response model
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_missing_user_id_fails_loud_not_shared_bucket() -> None:
    # AT-095 hardening: a context with no uid must NOT silently collapse into a
    # shared "anonymous" counter (cross-caller DoS). It fails loud instead.
    store = _fresh_store()
    runner = AtelierRunner(session_service=InMemorySessionService(), usage_store=store)
    ctx = TenantContext(tenant_id="t1", user_id="", project_id="p1")
    with _offline(), pytest.raises(ValueError, match="user_id is required"):
        await runner.run(_BRIEF, ctx)


def test_llm_judge_response_carries_thinking_tokens() -> None:
    # G15: thoughts_token_count flows into LLMJudgeResponse so it is counted.
    resp = LLMJudgeResponse(
        text="{}", model_id="m", input_tokens=10, output_tokens=20, thinking_tokens=7
    )
    assert resp.thinking_tokens == 7


def test_runner_usage_extraction_counts_thinking_tokens() -> None:
    # G15 at the runner layer: _usage_from_event must read thoughts_token_count
    # from a real Vertex-shaped event (the offline fake yields none, so the
    # estimate path always sets thinking=0 — this exercises the live path).
    from types import SimpleNamespace

    from atelier.orchestrator.runner import _usage_from_event

    event = SimpleNamespace(
        usage_metadata=SimpleNamespace(
            prompt_token_count=100,
            candidates_token_count=200,
            thoughts_token_count=50,
        )
    )
    assert _usage_from_event(event) == (100, 200, 50)
    # No usage_metadata → (0, 0, 0) so the caller falls back to the estimate.
    assert _usage_from_event(SimpleNamespace()) == (0, 0, 0)
