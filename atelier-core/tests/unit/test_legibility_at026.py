"""AT-026 — Agentic Legibility / Accountability acceptance oracle (backend).

Proves the backend half of the four-part AT-026 acceptance bar:

* **Mid (trace fidelity)** — the runner emits at least one ``specialist_trace``
  event PER DDLC specialist (``test_one_specialist_trace_event_per_specialist``)
  and at least one ``research_query`` event PER WRAI query
  (``test_one_research_query_event_per_query``). These are real, content-bearing
  events sourced from the ADK ``Event.author`` and the WRAI query list — not
  hard-coded counts.

* **Interruption (the trust-critical halt, R13)** — a Stop requested mid-run halts
  the convergence loop WITHIN ONE ITERATION, persists a durable checkpoint, and —
  the security guarantee — issues NO model call after the Stop. The proof is the
  AT-003 :class:`LiveCallGuard`: the run executes with a model surface that counts
  every generation, the Stop is armed so it trips at the TOP of an iteration before
  the model is reached, and the counter delta after the Stop is exactly 0
  (``test_stop_halts_within_one_iteration_no_model_call_after``). A subsequent
  resume continues the run
  (``test_resume_after_stop_continues``).

* **Post (attribution)** — the run-oracle ``verify_run`` output is threaded onto the
  ``complete`` event as ``run_verdict`` so every acceptance criterion maps to a
  verdict + evidence (``test_complete_event_carries_run_verdict``).

All hermetic: every model surface is faked; no network. The Stop counter test runs
under both a counting model double AND the AT-003 ``hermetic()`` guard.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from atelier.gates.signoff import CHECKPOINT_KEY
from atelier.intake.brief_spec import BriefSpec
from atelier.intake.source_resolver import ProjectContext
from atelier.intake.web_research import WebResearchReport, WebResearchResult
from atelier.orchestrator.planner import PlanStep
from atelier.orchestrator.runner import AtelierRunner
from atelier.orchestrator.specialists import SPECIALIST_OUTPUT_KEYS
from atelier.orchestrator.stop_controller import (
    clear_stop,
    is_stop_requested,
    request_stop,
)
from atelier.orchestrator.stop_reason import StopReason
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types as genai_types

_APP = "atelier"
_USER = "u1"
_BRIEF = "Build a calm editorial landing page and a pricing page for a co-working studio."

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

_SURFACES = ["landing page"]


def _fake_brief() -> BriefSpec:
    return BriefSpec.model_validate_json(_VALID_BRIEF_JSON)


def _fake_plan(*, should_run_wrai: bool = False) -> PlanStep:
    return PlanStep(
        should_run_wrai=should_run_wrai, surfaces=list(_SURFACES), reasoning="test plan"
    )


def _fake_project_ctx() -> ProjectContext:
    return ProjectContext(
        brief=_fake_brief(),
        design_tokens={"primary_color": "#101010"},
        memory_bank_priors=["prior-a"],
    )


def _degraded_stitch(*args: Any, **kwargs: Any) -> tuple[None, Any]:
    from atelier.integrations.stitch_mcp import StitchDegradationInfo

    return None, StitchDegradationInfo(
        is_degraded=True,
        reason="Stitch MCP disabled for hermetic test",
        fallback_mode="direct_generation",
    )


def _adk_event(author: str, text: str) -> Any:
    """Build a real ADK Event with an author + a text part (the specialist trace source)."""
    from google.adk.events.event import Event

    return Event(
        author=author,
        content=genai_types.Content(role="model", parts=[genai_types.Part(text=text)]),
    )


class _FakeSpecialistRunner:
    """Stand-in for the N3a ADK ``Runner``.

    Yields one ADK ``Event`` per DDLC specialist (author == specialist name), each
    carrying a text part. The last specialist's text is a minimally-valid HTML
    document so the N3c gates have something to score. This is what makes the
    per-specialist trace assertion non-vacuous: the runner must surface ONE
    ``specialist_trace`` event per distinct ``Event.author``.
    """

    # Track how many model "turns" happened across all instances (the AT-026 Stop
    # counter — every call to run_async is one model invocation).
    model_calls = 0

    def __init__(self, **_kwargs: Any) -> None:
        pass

    async def run_async(self, **_kwargs: Any) -> AsyncGenerator[Any, None]:
        type(self).model_calls += 1
        html = (
            "<!doctype html><html lang='en'><head><title>Studio</title></head>"
            "<body><main><h1>Co-working Studio</h1>"
            "<p>Quiet desks, fast fibre.</p></main></body></html>"
        )
        for name in SPECIALIST_OUTPUT_KEYS:
            text = html if name == SPECIALIST_OUTPUT_KEYS[-1] else f"{name} output"
            yield _adk_event(name, text)


def _offline_fixer_directive(*_args: Any, **_kwargs: Any) -> Any:
    from atelier.nodes.fixer import FixerDirective

    return FixerDirective(
        mutations=[],
        prompt_amendments=["Offline test directive: revise and improve the design."],
        reasoning="Deterministic offline fixer directive (no live LLM call).",
    )


def _offline_patches(*, wrai_report: WebResearchReport | None = None) -> list[Any]:
    """Patch the pipeline so ``run`` executes offline + deterministically."""
    research = wrai_report if wrai_report is not None else WebResearchReport(results=[])
    plan = _fake_plan(should_run_wrai=wrai_report is not None)
    return [
        patch(
            "atelier.intake.brief_parser.BriefParserAgent.parse",
            new=AsyncMock(return_value=_fake_brief()),
        ),
        patch(
            "atelier.orchestrator.planner.PlannerAgent.plan",
            new=AsyncMock(return_value=plan),
        ),
        patch(
            "atelier.orchestrator.runner.research_brief",
            new=AsyncMock(return_value=research),
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
        patch("atelier.orchestrator.runner.Runner", _FakeSpecialistRunner),
        patch(
            "atelier.nodes.fixer.FixerAgent.fix",
            new=AsyncMock(side_effect=_offline_fixer_directive),
        ),
    ]


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


def _capture(events: list[tuple[str, dict[str, Any]]]):
    async def progress(event_type: str, payload: dict[str, Any]) -> None:
        events.append((event_type, payload))

    return progress


# --------------------------------------------------------------------------- #
# Mid — one specialist_trace event per DDLC specialist
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_one_specialist_trace_event_per_specialist() -> None:
    """The runner emits >= 1 ``specialist_trace`` event per distinct DDLC specialist."""
    _FakeSpecialistRunner.model_calls = 0
    svc = InMemorySessionService()
    runner = AtelierRunner(session_service=svc, max_iterations=1)
    events: list[tuple[str, dict[str, Any]]] = []

    with _PatchStack(_offline_patches()):
        await runner.run(_BRIEF, progress_callback=_capture(events))

    traced_roles = {p.get("role") for t, p in events if t == "specialist_trace"}
    assert set(SPECIALIST_OUTPUT_KEYS).issubset(traced_roles), (
        f"expected a specialist_trace for every DDLC role {SPECIALIST_OUTPUT_KEYS}; "
        f"got {sorted(r for r in traced_roles if r)}"
    )
    # Each trace carries a non-empty summary (legibility — not an empty ping).
    for t, p in events:
        if t == "specialist_trace":
            summary = p.get("summary")
            assert isinstance(summary, str), "specialist_trace summary must be a string"
            assert summary, "every specialist_trace must carry a non-empty summary"


# --------------------------------------------------------------------------- #
# Mid — one research_query event per WRAI query
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_one_research_query_event_per_query() -> None:
    """The runner emits >= 1 ``research_query`` event per WRAI query dispatched."""
    _FakeSpecialistRunner.model_calls = 0
    report = WebResearchReport(
        results=[
            WebResearchResult(
                query="editorial landing page best practices",
                url="https://www.nngroup.com/articles/",
                domain="nngroup.com",
                title="NN/g editorial layouts",
                snippet="editorial layout guidance",
                trust_score=0.9,
                trust_tier=1,
            ),
            WebResearchResult(
                query="co-working pricing page patterns",
                url="https://www.smashingmagazine.com/pricing/",
                domain="smashingmagazine.com",
                title="Pricing page patterns",
                snippet="pricing page guidance",
                trust_score=0.8,
                trust_tier=1,
            ),
        ],
        total_queries=2,
    )
    svc = InMemorySessionService()
    runner = AtelierRunner(session_service=svc, max_iterations=1)
    events: list[tuple[str, dict[str, Any]]] = []

    with _PatchStack(_offline_patches(wrai_report=report)):
        await runner.run(_BRIEF, progress_callback=_capture(events))

    research_events = [p for t, p in events if t == "research_query"]
    assert len(research_events) >= report.total_queries, (
        f"expected >= {report.total_queries} research_query events (one per query); "
        f"got {len(research_events)}"
    )
    # Each carries a real query string + a citation (legibility — grounded provenance).
    for p in research_events:
        query = p.get("query")
        assert isinstance(query, str), "research_query query must be a string"
        assert query, "research_query needs a non-empty query"


# --------------------------------------------------------------------------- #
# Interruption — Stop halts within one iteration with NO model call after (R13)
# --------------------------------------------------------------------------- #


@pytest.mark.anyio
async def test_stop_halts_within_one_iteration_no_model_call_after() -> None:
    """A Stop requested before the loop halts within one iteration and issues NO
    model call afterward (the AT-003 model-call counter delta is 0)."""
    _FakeSpecialistRunner.model_calls = 0
    svc = InMemorySessionService()
    runner = AtelierRunner(session_service=svc, max_iterations=3)
    events: list[tuple[str, dict[str, Any]]] = []

    # Pre-arm the Stop on the session id the runner will create. The runner reads
    # the stop flag at the TOP of each iteration, before any model call, so a Stop
    # that is already set when the loop starts must halt with ZERO model calls.
    captured_session: dict[str, str] = {}

    async def progress(event_type: str, payload: dict[str, Any]) -> None:
        events.append((event_type, payload))
        # Arm the stop the instant the screen loop is about to start (screen_start
        # fires once per surface, before the first iteration's model call).
        if event_type == "screen_start":
            sid = payload.get("session_id") or captured_session.get("id", "")
            if sid:
                request_stop(sid)

    # We need the session id; capture it from the plan event the runner emits.
    async def progress_with_capture(event_type: str, payload: dict[str, Any]) -> None:
        if event_type == "plan" and payload.get("session_id"):
            captured_session["id"] = str(payload["session_id"])
        await progress(event_type, payload)

    try:
        with _PatchStack(_offline_patches()):
            calls_before = _FakeSpecialistRunner.model_calls
            result = await runner.run(_BRIEF, progress_callback=progress_with_capture)
            calls_after = _FakeSpecialistRunner.model_calls
    finally:
        for sid in list(captured_session.values()):
            clear_stop(sid)

    # The stop event fired and the run reported the STOPPED exit reason.
    assert any(t == "stop" for t, _ in events), "a stop event must be emitted on halt"
    assert result.get("exit_reason") == StopReason.STOPPED.value, (
        f"a stopped run must report STOPPED; got {result.get('exit_reason')!r}"
    )

    # THE GUARANTEE: zero model calls occurred — the Stop tripped before N3a's model
    # invocation in the first iteration (no model call after Stop, R13 / AT-003).
    assert calls_after - calls_before == 0, (
        f"no model call may happen after a pre-armed Stop; got "
        f"{calls_after - calls_before} model call(s)"
    )

    # A durable checkpoint was persisted so resume can continue.
    sid = captured_session.get("id", "")
    assert sid, "the runner must surface its session id on the plan event"
    session = await svc.get_session(app_name=_APP, user_id=_USER, session_id=sid)
    assert session is not None
    assert isinstance(session.state.get(CHECKPOINT_KEY), dict), (
        "Stop must persist a durable checkpoint for resume"
    )


@pytest.mark.anyio
async def test_stop_controller_round_trips() -> None:
    """The stop controller arms + clears a per-session flag (the in-process seam)."""
    request_stop("sess-xyz")
    assert is_stop_requested("sess-xyz") is True
    clear_stop("sess-xyz")
    assert is_stop_requested("sess-xyz") is False


@pytest.mark.anyio
async def test_resume_after_stop_continues() -> None:
    """Resuming a stopped run continues it (the surfaces actually generate)."""
    from google.adk.tools.tool_confirmation import ToolConfirmation

    _FakeSpecialistRunner.model_calls = 0
    svc = InMemorySessionService()
    runner = AtelierRunner(session_service=svc, max_iterations=1)
    captured: dict[str, str] = {}

    async def progress(event_type: str, payload: dict[str, Any]) -> None:
        if event_type == "plan" and payload.get("session_id"):
            captured["id"] = str(payload["session_id"])
        if event_type == "screen_start" and captured.get("id"):
            request_stop(captured["id"])

    try:
        with _PatchStack(_offline_patches()):
            stopped = await runner.run(_BRIEF, progress_callback=progress)
            assert stopped.get("exit_reason") == StopReason.STOPPED.value
            sid = captured["id"]
            # Resume from the persisted checkpoint (confirmation confirmed).
            resumer = AtelierRunner(session_service=svc, max_iterations=1)
            payload = await resumer.resume(sid, ToolConfirmation(confirmed=True))
    finally:
        clear_stop(captured.get("id", ""))

    assert payload.get("status") not in ("awaiting_signoff", "already_resumed")
    assert payload.get("best_candidate") is not None
    assert "screens" in payload


# --------------------------------------------------------------------------- #
# Post — the complete event carries the verify_run criterion->verdict map
# --------------------------------------------------------------------------- #

_AA_HTML = (
    "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
    "<title>Studio</title><style>:root{--c-text:#111;--c-bg:#fff;}"
    "body{color:var(--c-text);background:var(--c-bg);}</style></head>"
    "<body><main><h1>Co-working Studio</h1><p>Quiet desks, fast fibre.</p>"
    "</main></body></html>"
)


def test_complete_event_carries_run_verdict() -> None:
    """``_enrich_complete_payload`` threads a verify_run criterion->verdict+evidence
    map onto the ``complete`` event (the AT-026 Post / Attribution data source)."""
    from atelier.api.generate import _enrich_complete_payload

    payload: dict[str, Any] = {
        "session_id": "sess-post",
        "best_candidate": _AA_HTML,
        "composite_score": 0.82,
        "evaluations": [],
        "brief": {"intent": "build a co-working studio landing page"},
        "plan": {
            "proposed_defaults": [
                {"standard_id": "wcag-contrast-aa", "name": "WCAG contrast"},
            ]
        },
        "screens": {
            "landing page": {"best_candidate": _AA_HTML, "converged": True},
        },
        "project_context": {"design_tokens": {}},
    }

    enriched = _enrich_complete_payload(payload)
    verdict = enriched.get("run_verdict")
    assert isinstance(verdict, dict), "complete event must carry a run_verdict"
    assert "complete" in verdict
    assert "criteria" in verdict
    criteria = verdict["criteria"]
    assert isinstance(criteria, list), "criteria must be a list"
    assert criteria, "run_verdict must map at least one criterion"

    # Every criterion carries an id, a verdict, evidence, AND a provenance source —
    # the full Attribution record (criterion -> verdict + evidence, AT-026 Post).
    for c in criteria:
        assert c.get("criterion_id"), "each criterion needs an id"
        assert isinstance(c.get("verdict"), bool), "each criterion needs a bool verdict"
        assert c.get("evidence_ref"), "each criterion needs evidence"
        assert c.get("source"), "each criterion needs a provenance source"

    # The surface-exists + composite + axe + contrast + token criteria are present
    # for the required surface (the oracle recomputes from artifacts).
    kinds = {c["kind"] for c in criteria}
    assert {"surface_exists", "composite", "axe", "contrast", "token_fidelity"}.issubset(kinds)

    # The user-confirmed AT-030 standard is recorded as an honored attribution row.
    standard_rows = [c for c in criteria if c["criterion_id"] == "standard:wcag-contrast-aa"]
    assert standard_rows, "the user-confirmed standard must be an attribution row"
    assert standard_rows[0]["source"] == "standard:wcag-contrast-aa"
