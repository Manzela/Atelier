"""POST /v1/generate — Pipeline trigger endpoint.

Accepts a design brief, runs the full N1→N2→N3a→N3c→N3d→N4 pipeline,
persists the trajectory to BigQuery via TrajectoryRecorder, and returns
the best candidate with full convergence metadata.

This endpoint closes the self-improving flywheel:
  Request  → Runner → N3a candidates → N3c gates → N3d consensus → N4 best
           ↓
  TrajectoryRecorder → BigQuery trajectory_records
           ↓
  DPO builder reads pairs → BigQueryPairMiner.mine_pairs()
           ↓
  GeneratorTuner.tune() → DpoTuningJob → Vertex AI → promoted adapter

PRD Reference: §7.1 (API surface), §6.3 (N1-N4 pipeline)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from atelier.auth.firebase import FirebaseUser, require_auth
from atelier.orchestrator.governor import TOKEN_CAP_DEFAULT
from atelier.utils.log_sanitizer import sanitize

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/v1/generate", tags=["pipeline"])

_PROJECT: str = os.environ.get("GOOGLE_CLOUD_PROJECT", "atelier-build-2026")
# Upper bound on per-run candidate trajectory records emitted for the DPO data
# flywheel. The N3a node is now the DDLC specialist SequentialAgent (AT-020), not
# a K-candidate ensemble; this cap is independent of the specialist count.
_MAX_CANDIDATE_RECORDS: int = 3


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    """Request body for POST /v1/generate."""

    model_config = ConfigDict(frozen=True)

    brief: str = Field(
        description="Design brief text. The agent will interpret this and generate UI candidates.",
        min_length=10,
        max_length=4000,
        examples=["Build a SaaS analytics dashboard with a dark theme and KPI cards."],
    )
    design_system_source: str | None = Field(
        default=None,
        description="Path to DESIGN.md or 'infer'. If omitted, tokens are auto-parsed.",
    )
    # AT-095: the per-request USD budget knob is removed. Usage is governed solely
    # by the per-user lifetime 5M-token cap (server-side); there is no dollar budget.


class GateOutcomeSummary(BaseModel):
    """Gate result summary for a single candidate."""

    model_config = ConfigDict(frozen=True)

    axis: str
    score: float
    passed: bool


class CandidateSummary(BaseModel):
    """Summary of a single generated candidate and its evaluation."""

    model_config = ConfigDict(frozen=True)

    candidate_index: int
    gates_passed: bool
    composite_score: float | None = None
    votes: dict[str, float] = {}
    gate_outcomes: list[GateOutcomeSummary] = []


class GenerateResponse(BaseModel):
    """Response from POST /v1/generate."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(description="Session ID — use in /v1/replay to view the trace.")
    run_id: str = Field(description="Unique run identifier.")

    # Best output
    best_candidate: str | None = Field(
        description="The best HTML candidate selected by N4. None if no candidates were generated."
    )
    converged: bool = Field(
        description="True when composite_score >= convergence threshold (0.70)."
    )
    composite_score: float = Field(description="D-O-R-A-V composite score of the best candidate.")

    # Pipeline summary
    candidates_generated: int
    candidates_passed_gates: int
    stitch_degraded: bool
    degradation_reason: str | None = None
    user_message: str | None = None

    # Usage (AT-095: token-only — no dollars). ``tokens_used`` is the user's
    # cumulative lifetime total (input + output + thinking), the meter's source.
    tokens_used: int = 0
    token_cap: int = TOKEN_CAP_DEFAULT

    # Candidate details (all candidates, not just the best)
    candidates: list[CandidateSummary] = []

    # Metadata
    started_at: str
    completed_at: str


# ---------------------------------------------------------------------------
# Pipeline execution
# ---------------------------------------------------------------------------


async def _run_pipeline(
    brief: str,
    user: FirebaseUser,
    design_system_source: str | None,  # noqa: ARG001 — reserved; passed to runner when source resolution is wired
) -> dict[str, Any]:
    """Execute the full Atelier pipeline and return the raw result dict."""
    from atelier.models.data_contracts import TenantContext  # noqa: PLC0415
    from atelier.orchestrator.runner import AtelierRunner  # noqa: PLC0415

    tenant_ctx = TenantContext(
        tenant_id=user.tenant_id,
        user_id=user.uid,
        project_id=_PROJECT,
    )

    # AT-095: no per-run budget — usage is governed by the per-user lifetime token cap.
    runner = AtelierRunner()
    return await runner.run(brief, tenant_ctx)


async def _record_trajectory(
    result: dict[str, Any],
    user: FirebaseUser,
    run_id: str,
) -> None:
    """Persist trajectory to BigQuery (fail-soft — never raises)."""
    try:
        from atelier.nodes.trajectory import TrajectoryRecord  # noqa: PLC0415
        from atelier.recorders.trajectory_recorder import TrajectoryRecorder  # noqa: PLC0415

        now = datetime.now(tz=UTC)
        session_id = result.get("session_id", run_id)
        candidates = result.get("candidates", [])
        evaluations = result.get("evaluations", [])
        gate_results = result.get("gate_results", [])
        best_candidate = result.get("best_candidate", "")

        # Build a TrajectoryRecord for each N3a candidate.
        # P0-4: use actual per-candidate composite_score from evaluations (not 0.0 for losers).
        # Zero scores corrupt the DPO pair miner margin calculation and produce noise pairs.
        # P0-3 / P1-3: use the _MAX_CANDIDATE_RECORDS constant instead of hardcoded 3.
        records = []
        eval_cursor = 0
        for i, candidate in enumerate(candidates[:_MAX_CANDIDATE_RECORDS]):
            content = candidate if isinstance(candidate, str) else str(candidate)
            is_best = content == best_candidate
            outcome = "accepted" if is_best and result.get("converged") else "rejected"

            # Extract actual composite score for this candidate from the evaluations list.
            # Evaluations only exist for candidates that passed N3c gates.
            gate_passed = (
                gate_results[i].get("all_passed", False) if i < len(gate_results) else False
            )
            if gate_passed and eval_cursor < len(evaluations):
                candidate_score = float(evaluations[eval_cursor].get("composite_score", 0.0))
                eval_cursor += 1
            else:
                candidate_score = 0.0  # did not pass gates — no consensus score available

            record = TrajectoryRecord(
                trajectory_id=uuid4(),
                tenant_id=user.tenant_id,
                project_id=_PROJECT,
                surface_id=uuid4(),
                session_id=session_id,
                campaign_id="",
                candidate_id=uuid4(),
                iteration=i,
                started_at=now,
                ended_at=now,
                outcome=outcome,
                composite_score=candidate_score,
                total_cost_usd=0.0,  # AT-095: USD telemetry retired; usage is token-based
            )
            records.append(record)

        if records:
            from google.cloud import bigquery as _bq  # noqa: PLC0415  # type: ignore[attr-defined]

            bq_client = _bq.Client(project=_PROJECT)
            recorder = TrajectoryRecorder(bq_client)  # type: ignore[arg-type]  # BQ Client satisfies BigQueryClient Protocol at runtime
            for record in records:
                recorder.record(record)
            recorder.flush()

    except Exception as exc:  # noqa: BLE001
        # Fail-soft: trajectory recording must never break the generate response
        logger.warning(
            "Trajectory recording failed (fail-soft): %s: %s",
            type(exc).__name__,
            sanitize(str(exc)[:200]),
        )


def _build_response(
    result: dict[str, Any],
    run_id: str,
    started_at: str,
) -> GenerateResponse:
    """Build a GenerateResponse from the runner result dict."""
    raw_candidates = result.get("candidates", [])
    gate_results = result.get("gate_results", [])
    evaluations = result.get("evaluations", [])

    candidate_summaries: list[CandidateSummary] = []
    for i, _raw in enumerate(raw_candidates):
        gate_data = gate_results[i] if i < len(gate_results) else {}
        eval_data = {}
        if gate_data.get("all_passed") and evaluations:
            eval_idx = sum(1 for gr in gate_results[:i] if gr.get("all_passed")) - 1
            if 0 <= eval_idx < len(evaluations):
                eval_data = evaluations[eval_idx]

        candidate_summaries.append(
            CandidateSummary(
                candidate_index=i,
                gates_passed=gate_data.get("all_passed", False),
                composite_score=eval_data.get("composite_score"),
                votes={k: v["score"] for k, v in eval_data.get("votes", {}).items()},
                gate_outcomes=[
                    GateOutcomeSummary(
                        axis=o["axis"],
                        score=o["score"],
                        passed=o["passed"],
                    )
                    for o in gate_data.get("outcomes", [])
                ],
            )
        )

    return GenerateResponse(
        session_id=result.get("session_id", run_id),
        run_id=run_id,
        best_candidate=result.get("best_candidate"),
        converged=result.get("converged", False),
        composite_score=result.get("composite_score", 0.0),
        candidates_generated=result.get("candidates_evaluated", len(raw_candidates)),
        candidates_passed_gates=result.get("candidates_passed_gates", 0),
        stitch_degraded=result.get("stitch_degraded", False),
        degradation_reason=result.get("degradation_reason"),
        user_message=result.get("user_message"),
        tokens_used=int(result.get("tokens_used", 0)),
        token_cap=int(result.get("token_cap", TOKEN_CAP_DEFAULT)),
        candidates=candidate_summaries,
        started_at=started_at,
        completed_at=datetime.now(tz=UTC).isoformat(),
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=GenerateResponse,
    summary="Generate UI candidates from a design brief",
    description=(
        "Runs the full Atelier autonomous design pipeline: "
        "N1 (brief parsing) → N14 (web research) → N2 (source resolver) → "
        "N3a (K=3 generator ensemble) → N3c (deterministic gates) → "
        "N3d (D-O-R-A-V consensus) → N4 (best candidate selection). "
        "Persists a trajectory to BigQuery for the DPO flywheel. "
        "Requires authentication."
    ),
)
async def generate(
    request: GenerateRequest,
    user: Annotated[FirebaseUser, Depends(require_auth)],
) -> GenerateResponse:
    """Run the full design pipeline for the authenticated user.

    Args:
        request: Brief text and optional configuration.
        user: Verified Firebase user from Authorization: Bearer header.

    Returns:
        GenerateResponse with best_candidate HTML, convergence status,
        D-O-R-A-V composite score, gate results, and session_id for replay.

    Raises:
        GovernorTokenCapExceeded(→402): When the user's lifetime token cap is reached.
        GovernorRateLimitExceeded(→429): When the request-rate limit is exceeded.
        HTTPException(401): When the caller is unauthenticated.
    """
    run_id = str(uuid4())
    started_at = datetime.now(tz=UTC).isoformat()

    logger.info(
        "atelier.generate.start",
        extra={
            "run_id": run_id,
            "tenant_id": sanitize(user.tenant_id),
            "user_id": sanitize(user.uid),
            "brief_length": sanitize(str(len(request.brief))),
        },
    )

    # P0-12: Deterministic gate — reject injection attempts, empty briefs,
    # and over-long briefs before any LLM call reaches the pipeline.
    from atelier.intake.brief_parser import BriefParserGate  # noqa: PLC0415
    from atelier.models.enums import GateDecision  # noqa: PLC0415

    gate = BriefParserGate()
    gate_outcome = gate.check(request.brief)
    if gate_outcome.decision != GateDecision.PASS:
        from fastapi import HTTPException  # noqa: PLC0415

        logger.warning(
            "atelier.generate.gate_rejected",
            extra={
                "run_id": run_id,
                "tenant_id": sanitize(user.tenant_id),
                "diagnostic": sanitize(gate_outcome.diagnostic),
            },
        )
        raise HTTPException(status_code=400, detail=gate_outcome.diagnostic)

    result = await _run_pipeline(
        brief=request.brief,
        user=user,
        design_system_source=request.design_system_source,
    )

    # Persist trajectory (fail-soft — never raises)
    await _record_trajectory(result, user, run_id)

    response = _build_response(result, run_id, started_at)

    logger.info(
        "atelier.generate.complete",
        extra={
            "run_id": run_id,
            "converged": response.converged,
            "composite_score": response.composite_score,
            "candidates_generated": response.candidates_generated,
            "tokens_used": response.tokens_used,
        },
    )

    return response


def _extract_design_tokens(payload: dict[str, Any]) -> dict[str, Any]:
    """Pull the flat design-token map out of a runner ``complete`` payload.

    The runner stores ``project_context`` as a Pydantic ``ProjectContext`` (with a
    ``design_tokens`` attribute), but a re-serialized (``model_dump``) dict can
    also reach here. Read either shape; on absence/wrong-type, return an empty
    map so a valid (empty-row) A2UI surface is still emitted.

    Args:
        payload: The runner ``complete`` payload.

    Returns:
        ``{token_name: value}`` (possibly empty). Never raises — token absence is
        a normal degraded case (no DESIGN.md), not an error.
    """
    project_context = payload.get("project_context")
    tokens: Any = None
    if project_context is not None:
        if isinstance(project_context, dict):
            tokens = project_context.get("design_tokens")
        else:
            tokens = getattr(project_context, "design_tokens", None)
    return tokens if isinstance(tokens, dict) else {}


def _enrich_complete_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Enrich the SSE ``complete`` event payload for Studio frontend consumption.

    Adds three keys that the canvas/scorecard UI requires:

    * ``best_html`` — the converged ``index.html`` string (empty string if none).
    * ``dorav``     — flat per-axis D-O-R-A-V scores + composite for the best
                      candidate (extracted from the serialized evaluations list).
    * ``nielsen``   — presence-only Nielsen-10 report; a list of
                      ``{heuristic, present, votes}`` dicts (no severity per R6).

    This function is **pure** at the API boundary: it reads the runner result
    dict and calls the deterministic ``evaluate_nielsen`` oracle — no LLM calls,
    no I/O, no side effects.

    Args:
        payload: The raw ``response_payload`` dict emitted by the runner's
            ``complete`` progress event.

    Returns:
        A shallow copy of ``payload`` augmented with the three new keys.
        The original dict is never mutated.
    """
    from uuid import uuid4 as _uuid4  # noqa: PLC0415

    from atelier.a2ui.surface import build_design_system_surface  # noqa: PLC0415
    from atelier.models.data_contracts import CandidateUI  # noqa: PLC0415
    from atelier.nodes.nielsen import evaluate_nielsen  # noqa: PLC0415

    enriched: dict[str, Any] = dict(payload)

    # ------------------------------------------------------------------
    # a2ui_payload: the Governed A2UI v0.10-SDK/v0.9-wire surface for the
    # AT-044 design-system panel (ADR-0011). Threaded onto the complete event
    # alongside best_html so the frontend can render the Studio CHROME via
    # @a2ui/react behind a feature flag (the design deliverable stays the HTML
    # in best_html — A2UI never touches it). The SSE field carries the raw
    # ordered message LIST that the renderer consumes directly.
    # ------------------------------------------------------------------
    enriched["a2ui_payload"] = build_design_system_surface(
        _extract_design_tokens(payload),
        surface_id="atelier-design-system",
    )

    # ------------------------------------------------------------------
    # best_html: the converged candidate HTML (runner stores it as a
    # plain string under "best_candidate").
    # ------------------------------------------------------------------
    best_candidate_raw = payload.get("best_candidate")
    best_html: str = best_candidate_raw if isinstance(best_candidate_raw, str) else ""
    enriched["best_html"] = best_html

    # ------------------------------------------------------------------
    # dorav: per-axis scores from the first (best) evaluation entry.
    # runner.py serializes each evaluation as a dict with a "votes" key
    # mapping axis names to sub-dicts containing a "score" float.
    # The first entry in the sorted-descending evaluations list is the
    # best candidate's evaluation.
    # ------------------------------------------------------------------
    evaluations: list[Any] = payload.get("evaluations", [])
    best_eval: dict[str, Any] = evaluations[0] if evaluations else {}
    raw_votes: dict[str, Any] = best_eval.get("votes", {})
    dorav: dict[str, float] = {
        axis: float(v["score"]) if isinstance(v, dict) else float(v)
        for axis, v in raw_votes.items()
    }
    dorav["composite"] = float(
        best_eval.get("composite_score", payload.get("composite_score", 0.0))
    )
    enriched["dorav"] = dorav

    # ------------------------------------------------------------------
    # nielsen: presence-only Nielsen-10 report (advisory, never gates
    # convergence). Computed fresh at the API boundary from best_html.
    # Gracefully degrades to an empty list when there is no best HTML.
    # ------------------------------------------------------------------
    nielsen_list: list[dict[str, Any]] = []
    if best_html.strip():
        try:
            candidate_for_nielsen = CandidateUI(
                candidate_id=_uuid4(),
                surface_id=_uuid4(),
                iteration=0,
                artifacts={"index.html": best_html},
            )
            report = evaluate_nielsen(candidate_for_nielsen)
            nielsen_list = [
                {
                    "heuristic": v.heuristic.value,
                    "present": v.present,
                    "votes": v.votes,
                }
                for v in report.verdicts
            ]
        except Exception:  # noqa: BLE001
            # Fail-soft: Nielsen is advisory and must never break the SSE stream.
            # Log + fall through to empty list so the frontend gets a valid (empty)
            # nielsen field rather than a missing key or a 500.
            logger.warning(
                "atelier.generate.stream.nielsen_eval_failed (fail-soft)",
                exc_info=True,
            )
    enriched["nielsen"] = nielsen_list

    return enriched


@router.post(
    "/stream",
    summary="Generate UI candidates as a real-time event stream",
    description="Streams the pipeline progress events (plan, screen_start, candidates, evaluations, fixer, complete) in EventSource format.",
)
async def generate_stream(  # noqa: C901, PLR0915 — SSE orchestrator: nested pipeline + cap/rate-limit handling
    request: GenerateRequest,
    user: Annotated[FirebaseUser, Depends(require_auth)],
) -> StreamingResponse:
    """Run the pipeline and stream events in real-time.

    Args:
        request: Brief text and optional configuration.
        user: Verified Firebase user from Authorization: Bearer header.

    Returns:
        StreamingResponse yielding EventSource events.
    """
    from atelier.intake.brief_parser import BriefParserGate  # noqa: PLC0415
    from atelier.models.enums import GateDecision  # noqa: PLC0415

    # Deterministic validation before starting the pipeline
    gate = BriefParserGate()
    gate_outcome = gate.check(request.brief)
    if gate_outcome.decision != GateDecision.PASS:
        from fastapi import HTTPException  # noqa: PLC0415

        raise HTTPException(status_code=400, detail=gate_outcome.diagnostic)

    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    async def progress_callback(event_type: str, payload: dict[str, Any]) -> None:
        if event_type == "complete":
            payload = _enrich_complete_payload(payload)
        await queue.put((event_type, payload))

    async def _run_pipeline_task() -> None:
        from atelier.models.data_contracts import TenantContext  # noqa: PLC0415
        from atelier.orchestrator.governor import (  # noqa: PLC0415
            CIRCUIT_BREAKER_MESSAGE,
            TOKEN_CAP_MESSAGE,
            USAGE_UNAVAILABLE_MESSAGE,
            GovernorCircuitBreakerOpen,
            GovernorRateLimitExceeded,
            GovernorTokenCapExceeded,
            GovernorUsageUnavailable,
        )
        from atelier.orchestrator.runner import AtelierRunner  # noqa: PLC0415

        tenant_ctx = TenantContext(
            tenant_id=user.tenant_id,
            user_id=user.uid,
            project_id=_PROJECT,
        )

        # AT-095: no per-run budget — usage governed by the per-user lifetime token cap.
        runner = AtelierRunner()
        try:
            result = await runner.run(
                request.brief, tenant_ctx, progress_callback=progress_callback
            )
            await _record_trajectory(result, user, result.get("session_id", "default-id"))
        except GovernorUsageUnavailable as exc:
            # AT-095: the usage store could not be read/written (transient outage or
            # a corrupt counter). Fail-closed (deny) but acknowledge HONESTLY — this
            # is a transient infra fault, NOT a cap breach: a distinct `unavailable`
            # degraded event + a retryable message, never "you hit your limit".
            logger.error(  # noqa: TRY400
                "atelier.generate.stream.usage_unavailable",
                extra={"uid": sanitize(user.uid), "reason": exc.reason},
            )
            await queue.put(
                ("degraded", {"mode": "unavailable", "message": USAGE_UNAVAILABLE_MESSAGE})
            )
            await queue.put(("complete", {"user_message": USAGE_UNAVAILABLE_MESSAGE}))
        except GovernorCircuitBreakerOpen as exc:
            # AT-097: the fleet-wide token breaker is open — a SYSTEM protection,
            # not this user's fault. Acknowledge honestly with a retryable degraded
            # event (reuses the "unavailable" retryable bucket) + its own message;
            # never the per-user cap message. Logged for fleet-protection alerting.
            logger.error(  # noqa: TRY400
                "atelier.generate.stream.circuit_breaker_open",
                extra={
                    "uid": sanitize(user.uid),
                    "reason": exc.reason,
                    "retry_after_seconds": exc.retry_after_seconds,
                },
            )
            await queue.put(
                ("degraded", {"mode": "unavailable", "message": CIRCUIT_BREAKER_MESSAGE})
            )
            await queue.put(("complete", {"user_message": CIRCUIT_BREAKER_MESSAGE}))
        except GovernorTokenCapExceeded as exc:
            # AT-095: an already-at-cap user hits the run-start pre-flight. Surface
            # the branded message as a clean `degraded` cap event (PRD §7A.6) — never
            # a raw quota error. Logged at error level with the alertable context
            # (incl. which_cap) so a real breach is distinguishable in alerting.
            logger.error(  # noqa: TRY400
                "atelier.generate.stream.token_cap_exceeded",
                extra={
                    "uid": sanitize(user.uid),
                    "which_cap": exc.which_cap,
                    "used_tokens": exc.used_tokens,
                    "cap_tokens": exc.cap_tokens,
                },
            )
            await queue.put(("degraded", {"mode": "cap", "message": TOKEN_CAP_MESSAGE}))
            await queue.put(("complete", {"user_message": TOKEN_CAP_MESSAGE}))
        except GovernorRateLimitExceeded:
            logger.warning(
                "atelier.generate.stream.rate_limited", extra={"uid": sanitize(user.uid)}
            )
            await queue.put(
                (
                    "error",
                    {
                        "detail": "Too many requests. Please wait a moment and try again.",
                        "code": 429,
                    },
                )
            )
        except Exception as e:
            logger.exception("Error in streaming generation pipeline task")
            await queue.put(("error", {"detail": str(e)}))

    async def sse_generator() -> AsyncGenerator[str, None]:
        # Start the pipeline in the background
        task = asyncio.create_task(_run_pipeline_task())

        while True:
            try:
                # Wait for an event with a 1.0 second timeout to support keep-alive pinging
                event_type, payload = await asyncio.wait_for(queue.get(), timeout=1.0)
                yield f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"
                queue.task_done()
                if event_type in {"complete", "error"}:
                    break
            except TimeoutError:
                if task.done():
                    # Process remaining items in the queue
                    while not queue.empty():
                        event_type, payload = queue.get_nowait()
                        yield f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"
                        queue.task_done()
                    break
                # Yield keep-alive comment
                yield ": ping\n\n"

        await task

    return StreamingResponse(sse_generator(), media_type="text/event-stream")
