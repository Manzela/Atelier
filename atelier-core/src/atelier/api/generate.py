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
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Any, Final
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from atelier.auth.firebase import FirebaseUser, require_auth, require_auth_strict
from atelier.orchestrator.governor import TOKEN_CAP_DEFAULT
from atelier.utils.log_sanitizer import sanitize

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/v1/generate", tags=["pipeline"])

# AT-026 (R13): the user-initiated Stop. Separate router so the path is the clean
# ``POST /v1/stop/{session_id}`` the legibility UI calls. Authenticated — only the
# run's owner may halt it. The handler arms the in-process cooperative stop flag;
# the convergence loop honors it at the next iteration top (no model call after).
stop_router = APIRouter(prefix="/v1/stop", tags=["pipeline"])

# Input-validation barrier for the untrusted ``session_id`` path param (CWE-117,
# log-injection). A session id is an opaque token; we accept only URL-safe id
# characters and bound its length. This is an explicit allow-list at the trust
# boundary (in addition to the sanitize() applied at the log sink) so a hostile id
# never reaches the logger, the stop controller, or the response body.
_SESSION_ID_RE: Final = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


@stop_router.post(
    "/{session_id}",
    summary="Stop an in-flight generation run",
    description=(
        "Requests a cooperative Stop for the given run. The convergence loop halts "
        "within one iteration BEFORE its next model call (no model call after Stop, "
        "R13), persists a durable checkpoint, and emits a `stop` SSE event. Resume "
        "continues from the checkpoint. Requires authentication."
    ),
)
async def stop_run(
    session_id: str,
    user: Annotated[FirebaseUser, Depends(require_auth)],
) -> dict[str, str]:
    """Arm a cooperative Stop for ``session_id`` (AT-026 / R13).

    The flag is honored by :class:`AtelierRunner`'s convergence loop at the top of
    its next iteration, before any model call — so the Stop is a real, enforced halt
    with the no-model-call-after guarantee, not a best-effort cancel.
    """
    # Validate the untrusted path param at the trust boundary BEFORE it touches the
    # stop controller, the logger, or the response (CWE-117 log-injection barrier).
    if not _SESSION_ID_RE.fullmatch(session_id):
        from fastapi import HTTPException  # noqa: PLC0415

        raise HTTPException(status_code=400, detail="Invalid session_id format.")

    from atelier.orchestrator.stop_controller import request_stop, stop_key  # noqa: PLC0415

    # L04: arm the per-REQUESTER key. A non-owner's Stop arms a key the target run
    # never polls (the runner reads only its own owner key), so a cross-tenant Stop
    # is a structural no-op with no session-owner lookup and no existence oracle.
    request_stop(stop_key(user.uid, session_id))
    logger.info(
        "atelier.generate.stop_requested",
        extra={"session_id": sanitize(session_id), "uid": sanitize(user.uid)},
    )
    return {"status": "stop_requested", "session_id": session_id}


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
    model: str | None = Field(
        default=None,
        description="Custom model override for the UI Generator.",
    )
    # L47: bound the sampling knobs at the trust boundary. An unbounded
    # temperature/top_k/max_tokens is a cost- and latency-amplification vector
    # (the body crosses straight into GenerateContentConfig). Rejecting out-of-range
    # values here returns a 422 at the edge instead of forwarding abuse to Vertex.
    temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Sampling temperature parameter (0.0-2.0).",
    )
    top_k: int | None = Field(
        default=None,
        ge=1,
        le=200,
        description="Top-k sampling parameter (1-200).",
    )
    max_tokens: int | None = Field(
        default=None,
        ge=1,
        le=8192,
        description="Maximum tokens to generate (1-8192).",
    )
    # AT-095: the per-request USD budget knob is removed. Usage is governed solely
    # by the per-user lifetime 5M-token cap (server-side); there is no dollar budget.

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str | None) -> str | None:
        """L05: constrain ``model`` to the served catalog (allow-list).

        Without this, a request body could pin any string as the UI Generator
        model, bypassing operator-pin and tiered cost routing (e.g. forcing the
        Pro tier on the paid service account). Reject anything not in the live
        ``get_model_catalog()`` allow-list with a 422 at the boundary.
        """
        if value is None:
            return None
        from atelier.models.model_registry import (  # noqa: PLC0415
            SELECTABLE_MODEL_OVERRIDES,
            get_model_catalog,
            normalize_model_id,
        )

        normalized = normalize_model_id(value.strip())
        # The allow-list is the routing-derived catalog PLUS the explicit
        # user-selectable overrides (e.g. gemini-3.5-flash) — overrides are
        # offered in the picker but are not production routing targets.
        allowed = {entry.model_id for entry in get_model_catalog()} | set(
            SELECTABLE_MODEL_OVERRIDES
        )
        if normalized not in allowed:
            raise ValueError(
                f"model must be one of {sorted(allowed)} (operator-served catalog); got {value!r}"
            )
        return normalized


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
    model: str | None = None,
    temperature: float | None = None,
    top_k: int | None = None,
    max_tokens: int | None = None,
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
    runner = AtelierRunner(
        model=model,
        temperature=temperature,
        top_k=top_k,
        max_tokens=max_tokens,
    )
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
        scored_candidates = result.get("scored_candidates", [])
        best_candidate = result.get("best_candidate", "")
        converged = result.get("converged", False)

        # Build a TrajectoryRecord per gate-passing candidate from the canonical
        # scored_candidates join (candidate_id + html + composite_score, paired
        # correctly in the runner). The previous positional walk of raw candidates
        # against the score-descending evaluations attached the wrong score to the
        # wrong candidate and poisoned the DPO pair-miner margins (audit 2026-06-03).
        # P0-3 / P1-3: use the _MAX_CANDIDATE_RECORDS constant instead of hardcoded 3.
        records = []
        for i, scored in enumerate(scored_candidates[:_MAX_CANDIDATE_RECORDS]):
            html = scored.get("html", "")
            is_best = html == best_candidate
            outcome = "accepted" if is_best and converged else "rejected"
            candidate_score = float(scored.get("composite_score", 0.0))

            total_input_tokens = int(result.get("total_input_tokens") or 0) if i == 0 else 0
            total_output_tokens = int(result.get("total_output_tokens") or 0) if i == 0 else 0

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
                total_input_tokens=total_input_tokens,
                total_output_tokens=total_output_tokens,
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


async def _build_optimize_events(
    result: dict[str, Any],
    *,
    tenant_id: str,
    session_id: str,
) -> list[tuple[str, dict[str, Any]]]:
    """Derive the AT-027 read-only optimize SSE events for a completed run.

    Returns up to two events — ``route_decision`` (the real phase-aware MoE
    routing decision from the v1_bandit router) and ``dreaming_artifact`` (a real
    dreaming/DPO ``ExtractedPair`` mined from THIS run's ``scored_candidates``,
    with the §3.6 anti-sycophancy reward applied at extraction). Both are
    surfaced read-only for trace legibility (PRD §3.5); neither dispatches a
    model nor mutates training state.

    Fail-soft (§21): any error returns the events gathered so far (possibly
    empty) — surfacing the optimize trace must never break a generation.

    Args:
        result: The runner result dict (carries ``scored_candidates``).
        tenant_id: The run's tenant (router + pair isolation key).
        session_id: The run's session id.

    Returns:
        A list of ``(event_type, payload)`` tuples, in emission order.
    """
    events: list[tuple[str, dict[str, Any]]] = []
    try:
        import numpy as np  # noqa: PLC0415

        from atelier.optimize.dreaming_module import extract_pairs_midflight  # noqa: PLC0415
        from atelier.router.protocol import DAGPhase, RouteRequest  # noqa: PLC0415
        from atelier.router.v1_bandit import EpsilonGreedyBandit  # noqa: PLC0415

        # Real MoE routing decision for the JUDGE_CANDIDATES phase (read-only).
        router_impl = EpsilonGreedyBandit()
        decision = await router_impl.route(
            RouteRequest(
                phase=DAGPhase.JUDGE_CANDIDATES,
                task_embedding=np.zeros(768, dtype=np.float32),
                cost_budget_remaining_usd=1.0,
                latency_target_ms=5000,
                prior_judge_kappa=None,
                trace_id=session_id,
                tenant_id=tenant_id,
            )
        )
        events.append(
            (
                "route_decision",
                {
                    "expert": str(decision.expert),
                    "phase": str(decision.phase),
                    "score": decision.score,
                    "rationale": decision.rationale,
                    "fallback_chain": [str(e) for e in decision.fallback_chain],
                    "routing_mode": decision.routing_mode,
                },
            )
        )

        # Real dreaming/DPO artifact from this run's gate-passing candidates.
        scored_candidates = result.get("scored_candidates", [])
        pairs = extract_pairs_midflight(
            session_id=session_id,
            tenant_id=tenant_id,
            surface_id=str(result.get("session_id", session_id)),
            brief_text=str(result.get("brief", "")),
            scored_candidates=scored_candidates,
        )
        if pairs:
            top = max(pairs, key=lambda p: p.margin)
            events.append(
                (
                    "dreaming_artifact",
                    {
                        "surface_id": top.surface_id,
                        "node_name": top.node_name,
                        "chosen_score": top.chosen_score,
                        "rejected_score": top.rejected_score,
                        "margin": top.margin,
                    },
                )
            )
    except Exception as exc:  # noqa: BLE001
        # Fail-soft: surfacing the optimize trace must never break a generation.
        logger.warning(
            "Optimize-event surfacing failed (fail-soft): %s: %s",
            type(exc).__name__,
            sanitize(str(exc)[:200]),
        )
    return events


def _build_response(
    result: dict[str, Any],
    run_id: str,
    started_at: str,
) -> GenerateResponse:
    """Build a GenerateResponse from the runner result dict."""
    raw_candidates = result.get("candidates", [])
    gate_results = result.get("gate_results", [])
    scored_candidates = result.get("scored_candidates", [])
    # Join each gate result to its consensus score/votes by candidate_id. The
    # gate results are in raw candidate order while the evaluations are
    # score-descending, so indexing one by the other's position attaches the
    # wrong score to the wrong candidate (audit 2026-06-03). scored_candidates
    # carries html + score + votes keyed by candidate_id.
    score_by_id: dict[str, dict[str, Any]] = {
        str(sc.get("candidate_id")): sc for sc in scored_candidates
    }

    candidate_summaries: list[CandidateSummary] = []
    for i, gate_data in enumerate(gate_results):
        eval_data = score_by_id.get(str(gate_data.get("candidate_id")), {})

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
        tokens_used=int(result.get("tokens_used") or 0),
        token_cap=int(result.get("token_cap") or TOKEN_CAP_DEFAULT),
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
    user: Annotated[FirebaseUser, Depends(require_auth_strict)],
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
        model=request.model,
        temperature=request.temperature,
        top_k=request.top_k,
        max_tokens=request.max_tokens,
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


def _extract_persisted_design_tokens(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Pull the tenant's PERSISTED design system (AT-053) from a runner payload.

    The runner threads the auto-applied persisted system onto
    ``ProjectContext.persisted_design_tokens`` (``None`` on a tenant's first run).
    The AT-012 token-fidelity gate enforces it zero-tolerance: an off-system
    literal in this run's rendered surface is REJECTed.

    Args:
        payload: The runner ``complete`` payload.

    Returns:
        The persisted ``{token_name: value}`` map, or ``None`` when no system is
        persisted (first run → no enforcement, first runs are never blocked).
    """
    project_context = payload.get("project_context")
    persisted: Any = None
    if project_context is not None:
        if isinstance(project_context, dict):
            persisted = project_context.get("persisted_design_tokens")
        else:
            persisted = getattr(project_context, "persisted_design_tokens", None)
    return persisted if isinstance(persisted, dict) else None


def _screens_html_map(payload: dict[str, Any]) -> dict[str, str]:
    """Flat ``{surface_name: best_candidate_html}`` over every produced surface (A1).

    The runner threads the full per-surface result set as ``payload["screens"]``;
    this projection lets the Studio render every converged surface, not just
    surfaces[0]. Surfaces with no/empty HTML are omitted (never a blank tab).
    """
    screens = payload.get("screens")
    if not isinstance(screens, dict):
        return {}
    out: dict[str, str] = {}
    for name, res in screens.items():
        html = res.get("best_candidate") if isinstance(res, dict) else None
        if isinstance(html, str) and html.strip():
            out[str(name)] = html
    return out


def _required_surfaces_from_plan(payload: dict[str, Any], produced: dict[str, Any]) -> list[str]:
    """Plan-seeded completeness set (A2): the surfaces the APPROVED PLAN required.

    Seeding ``required_surfaces`` from the plan (not the produced ``screens``) means
    a planned-but-dropped surface fails ``surface:exists``. Falls back to the produced
    keys when no plan surfaces are available (legacy/degraded paths).
    """
    plan = payload.get("plan")
    if isinstance(plan, dict):
        raw = plan.get("surfaces")
        if isinstance(raw, list):
            planned = [str(s) for s in raw if str(s).strip()]
            if planned:
                return planned
    return list(produced.keys())


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

    from atelier.a2ui.gate import gate_a2ui_surface  # noqa: PLC0415
    from atelier.a2ui.surface import build_design_system_surface  # noqa: PLC0415
    from atelier.models.data_contracts import CandidateUI  # noqa: PLC0415
    from atelier.nodes.nielsen import evaluate_nielsen  # noqa: PLC0415

    enriched: dict[str, Any] = dict(payload)

    # The runner's complete payload carries rich pydantic objects (brief,
    # project_context, web_research) that are NOT JSON-serializable. The SSE
    # layer json.dumps the event, so coerce them to plain JSON here. Without
    # this the complete event used to crash json.dumps (TypeError, uncaught by
    # the stream's TimeoutError handler) and the connection closed WITHOUT a
    # complete event — the Studio then showed "Pipeline error" despite a fully
    # converged design. The SSE json.dumps(default=str) is the backstop;
    # model_dump keeps the data structured for the frontend.
    for _obj_key in ("brief", "project_context", "web_research"):
        _obj = enriched.get(_obj_key)
        if _obj is not None and hasattr(_obj, "model_dump"):
            try:
                enriched[_obj_key] = _obj.model_dump(mode="json")
            except Exception:  # noqa: BLE001
                enriched[_obj_key] = str(_obj)

    # ------------------------------------------------------------------
    # a2ui_payload: the Governed A2UI v0.10-SDK/v0.9-wire surface for the
    # AT-044 design-system panel (ADR-0024). Threaded onto the complete event
    # alongside best_html so the frontend can render the Studio CHROME via
    # @a2ui/react behind a feature flag (the design deliverable stays the HTML
    # in best_html — A2UI never touches it). The SSE field carries the raw
    # ordered message LIST that the renderer consumes directly.
    #
    # CANONICAL GATE SITE (G2, ADR-0024 §2): this enrichment runs LAST in the
    # SSE pipeline and OVERWRITES a2ui_payload, so it governs the surface that
    # actually RENDERS. The fail-closed gate validates envelope/catalog/
    # accessible-name/contrast; on PASS the surface ships unchanged (identity),
    # on REJECT we blank a2ui_payload (frontend fail-soft) and carry the custom
    # governance event on a2ui_governance + log fail-closed at WARNING.
    # ------------------------------------------------------------------
    _design_tokens = _extract_design_tokens(payload)
    _persisted_design_tokens = _extract_persisted_design_tokens(payload)
    _a2ui_surface = build_design_system_surface(
        _design_tokens,
        surface_id="atelier-design-system",
    )
    # AT-053 enforcement: thread the tenant's persisted design system into the
    # gate. When present, any off-system literal in the rendered /tokens rows is
    # REJECTed zero-tolerance (the "enforced, not merely applied" guarantee);
    # None → first run, no enforcement.
    _a2ui_gate = gate_a2ui_surface(
        _a2ui_surface,
        design_tokens=_design_tokens,
        surface_id="atelier-design-system",
        persisted_design_tokens=_persisted_design_tokens,
    )
    if _a2ui_gate.passed:
        enriched["a2ui_payload"] = _a2ui_surface
    else:
        # Fail-closed (server): never emit the rejected surface. Empty payload
        # drives the frontend's existing fail-soft fallback (hand-built panel).
        enriched["a2ui_payload"] = []
        enriched["a2ui_governance"] = _a2ui_gate.governance_messages
        logger.warning(
            "atelier.a2ui.gate.rejected",
            extra={
                "surface_id": "atelier-design-system",
                "reason_count": len(_a2ui_gate.reasons),
                "validators": sorted({r.validator for r in _a2ui_gate.reasons}),
                "first_json_pointer": (
                    _a2ui_gate.reasons[0].json_pointer if _a2ui_gate.reasons else ""
                ),
            },
        )

    # ------------------------------------------------------------------
    # best_html: the converged candidate HTML (runner stores it as a
    # plain string under "best_candidate").
    # ------------------------------------------------------------------
    best_candidate_raw = payload.get("best_candidate")
    best_html: str = best_candidate_raw if isinstance(best_candidate_raw, str) else ""
    enriched["best_html"] = best_html

    # screens_html: the DELIVERED multi-surface product — a flat
    # {surface_name: best_candidate_html} map over EVERY converged surface, so the
    # Studio renders the whole product, not just surfaces[0] (A1).
    screens_html = _screens_html_map(payload)
    if screens_html:
        enriched["screens_html"] = screens_html

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

    # ------------------------------------------------------------------
    # run_verdict: the AT-007 run-completion oracle output (AT-026 Post /
    # Attribution). Every ACCEPTANCE.json criterion -> verdict + evidence, the
    # data source for the §14 Attribution view. Computed deterministically at the
    # API boundary from the converged surfaces (the oracle recomputes from
    # artifacts; it never trusts the agent-written converged/composite — G2).
    # Fail-soft: an oracle error degrades to a null verdict (the Attribution view
    # renders "unavailable") rather than breaking the SSE stream.
    # ------------------------------------------------------------------
    enriched["run_verdict"] = _build_run_verdict(payload)

    # ------------------------------------------------------------------
    # degraded / degradation_reason: failure-trichotomy honesty (PRD §21).
    # When the loop did NOT converge, best_html is the strongest SUB-BAR draft,
    # not a blessed result. The Studio keys its acknowledgment off `degraded`,
    # so derive it here from the runner's `converged` flag and surface the
    # already-composed `user_message` (the "strong draft — did not clear every
    # gate, retry to refine" acknowledgment). Without this the frontend takes
    # the success branch and reports "All screens converged" over a sub-bar
    # design — the exact "apparent capability over trust" failure the PRD
    # forbids. A more specific per-iteration cause (stitch / governor fail-soft)
    # already in `degradation_reason` is preserved; an explicit upstream
    # `degraded=True` is never downgraded.
    if not enriched.get("converged", False) and not enriched.get("degraded", False):
        enriched["degraded"] = True
        enriched["degradation_reason"] = (
            enriched.get("degradation_reason")
            or enriched.get("user_message")
            or "This design did not clear every convergence gate; showing the strongest draft."
        )

    return enriched


def _build_run_verdict(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Compute the AT-007 ``verify_run`` verdict for the AT-026 Attribution panel.

    Derives an ``AcceptanceCriteria`` from the runner payload (run id, brief hash,
    the converged surface set, the convergence threshold, and any user-confirmed
    domain standards) and the final ``{surface: CandidateUI}`` map from each screen's
    best candidate HTML, then runs the deterministic oracle. Returns the serialized
    ``RunVerdict`` (``complete`` + per-criterion verdict + evidence + provenance), or
    ``None`` on any error so the frontend renders an honest "unavailable" Attribution
    state instead of the SSE stream crashing (R8 fail-soft).
    """
    import hashlib  # noqa: PLC0415
    from uuid import uuid4 as _uuid4  # noqa: PLC0415

    from atelier.models.acceptance import AcceptanceCriteria, BrandConstraints  # noqa: PLC0415
    from atelier.models.data_contracts import CandidateUI  # noqa: PLC0415
    from atelier.oracle.verify_run import verify_run  # noqa: PLC0415
    from atelier.orchestrator.runner import CONVERGENCE_THRESHOLD  # noqa: PLC0415

    try:
        screens = payload.get("screens")
        if not isinstance(screens, dict) or not screens:
            # No per-surface results (e.g. a degraded early-exit) — fall back to the
            # single best_html so the Post panel still has a criterion map.
            best = payload.get("best_candidate")
            best_html = best if isinstance(best, str) else ""
            if not best_html.strip():
                return None
            screens = {"design": {"best_candidate": best_html}}

        # Plan-seeded completeness (A2): require EVERY surface the APPROVED PLAN
        # named, not just the produced set, so a planned-but-dropped surface fails
        # ``surface:NAME:exists`` (honest about completeness, not self-satisfying).
        required_surfaces = _required_surfaces_from_plan(payload, screens)
        surfaces: dict[str, CandidateUI] = {}
        for name, res in screens.items():
            html = res.get("best_candidate") if isinstance(res, dict) else None
            surfaces[name] = CandidateUI(
                candidate_id=_uuid4(),
                surface_id=_uuid4(),
                iteration=0,
                artifacts={"index.html": html if isinstance(html, str) else ""},
            )

        # brief_sha256: bind the verdict to the exact brief that produced it. The
        # enriched payload carries the brief as a dumped dict; hash its intent.
        brief_obj = payload.get("brief")
        brief_seed = ""
        if isinstance(brief_obj, dict):
            brief_seed = str(brief_obj.get("intent", ""))
        brief_sha256 = hashlib.sha256(brief_seed.encode("utf-8")).hexdigest()

        # confirmed_standards: the AT-030 cited defaults the user accepted at sign-off
        # (each recorded as an honored attribution criterion). The plan carries them;
        # absent on legacy paths.
        plan = payload.get("plan")
        confirmed: list[str] = []
        forbidden: list[str] = []
        if isinstance(plan, dict):
            for d in plan.get("proposed_defaults", []) or []:
                if isinstance(d, dict) and d.get("standard_id"):
                    confirmed.append(str(d["standard_id"]))

        acceptance = AcceptanceCriteria(
            run_id=str(payload.get("session_id", "")),
            brief_sha256=brief_sha256,
            required_surfaces=required_surfaces,
            min_composite=CONVERGENCE_THRESHOLD,
            confirmed_standards=confirmed,
            brand_constraints=BrandConstraints(forbidden_colors=forbidden),
        )
        verdict = verify_run(acceptance, surfaces)
        return verdict.model_dump(mode="json")
    except Exception:  # noqa: BLE001
        # Fail-soft: the Attribution panel must never break the SSE stream. Log +
        # return None so the frontend renders the honest "unavailable" state.
        logger.warning(
            "atelier.generate.stream.run_verdict_failed (fail-soft)",
            exc_info=True,
        )
        return None


@router.post(
    "/stream",
    summary="Generate UI candidates as a real-time event stream",
    description="Streams the pipeline progress events (plan, screen_start, candidates, evaluations, fixer, complete) in EventSource format.",
)
async def generate_stream(  # noqa: C901, PLR0915 — SSE orchestrator: nested pipeline + cap/rate-limit handling
    http_request: Request,
    request: GenerateRequest,
    user: Annotated[FirebaseUser, Depends(require_auth_strict)],
) -> StreamingResponse:
    """Run the pipeline and stream events in real-time.

    Args:
        http_request: Starlette request object used to detect client disconnect.
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
    # Shared container: populated by progress_callback as soon as the runner
    # emits a payload carrying a session_id.  Used by sse_generator to arm the
    # cooperative Stop on client disconnect.
    _session_id_holder: list[str] = []

    async def progress_callback(event_type: str, payload: dict[str, Any]) -> None:
        # Capture session_id from the first event that carries one so the
        # sse_generator can stop the run on client disconnect.
        if not _session_id_holder and payload.get("session_id"):
            _session_id_holder.append(str(payload["session_id"]))
        if event_type == "complete":
            # AT-027: surface the read-only optimize assets (MoE route decision +
            # dreaming/DPO artifact) for THIS run, just BEFORE the complete event so
            # the Studio trace renders them. Derived from the raw runner payload
            # (carries scored_candidates); fail-soft inside the helper.
            optimize_events = await _build_optimize_events(
                payload,
                tenant_id=user.tenant_id,
                session_id=str(payload.get("session_id", "default-id")),
            )
            for opt_type, opt_payload in optimize_events:
                await queue.put((opt_type, opt_payload))
            payload = _enrich_complete_payload(payload)
        await queue.put((event_type, payload))

    async def _run_pipeline_task() -> None:
        from atelier.models.data_contracts import TenantContext  # noqa: PLC0415
        from atelier.models.model_armor_callbacks import ModelArmorInputBlocked  # noqa: PLC0415
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
        runner = AtelierRunner(
            model=request.model,
            temperature=request.temperature,
            top_k=request.top_k,
            max_tokens=request.max_tokens,
        )
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
            # The Studio keys its acknowledgment off the complete event's `degraded`
            # field (there is no separate degraded-event handler), and this direct
            # queue.put bypasses _enrich_complete_payload. Without degraded=True the
            # frontend takes the success branch ("All screens converged") over a run
            # that produced NO output — a false success. Mark it degraded honestly.
            await queue.put(
                (
                    "complete",
                    {
                        "degraded": True,
                        "degradation_reason": USAGE_UNAVAILABLE_MESSAGE,
                        "user_message": USAGE_UNAVAILABLE_MESSAGE,
                    },
                )
            )
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
            # degraded=True so the frontend acknowledges the breaker honestly rather
            # than reporting "All screens converged" over a run that never produced
            # output (the complete event bypasses _enrich_complete_payload).
            await queue.put(
                (
                    "complete",
                    {
                        "degraded": True,
                        "degradation_reason": CIRCUIT_BREAKER_MESSAGE,
                        "user_message": CIRCUIT_BREAKER_MESSAGE,
                    },
                )
            )
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
            # degraded=True + the branded cap message so the frontend acknowledges
            # the cap honestly (the complete event bypasses _enrich_complete_payload;
            # without this it reports "All screens converged" over a capped run).
            await queue.put(
                (
                    "complete",
                    {
                        "degraded": True,
                        "degradation_reason": TOKEN_CAP_MESSAGE,
                        "user_message": TOKEN_CAP_MESSAGE,
                    },
                )
            )
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
        except ModelArmorInputBlocked as exc:
            # The brief itself was a prompt-injection that Model Armor blocked at the
            # N1 parse boundary. Fail LOUD but HONESTLY: surface the branded safety
            # acknowledgment as a clean degraded+complete (the same shape as the cap
            # path), never the generic "internal error" that reads as a crash. The
            # design thesis is fail-closed safety stated plainly — see PRD §21.
            logger.warning(
                "atelier.generate.stream.input_blocked", extra={"uid": sanitize(user.uid)}
            )
            await queue.put(("degraded", {"mode": "blocked", "message": exc.user_message}))
            # The Studio keys its acknowledgment off the complete event's `degraded`
            # field (there is no separate degraded-event handler), so set it here —
            # otherwise onComplete takes the success branch over a blocked run. This
            # direct queue.put bypasses _enrich_complete_payload, so the mapping the
            # normal path does is applied inline.
            await queue.put(
                (
                    "complete",
                    {
                        "degraded": True,
                        "degradation_reason": exc.user_message,
                        "user_message": exc.user_message,
                    },
                )
            )
        except Exception:
            # Do not leak the raw exception string to the client; return a generic
            # message plus a correlation id and keep the full detail server-side.
            correlation_id = uuid4().hex[:12]
            logger.exception(
                "Error in streaming generation pipeline task [correlation_id=%s]",
                correlation_id,
            )
            await queue.put(
                (
                    "error",
                    {
                        "detail": "Internal error during generation.",
                        "correlation_id": correlation_id,
                    },
                )
            )

    async def sse_generator() -> AsyncGenerator[str, None]:
        # Start the pipeline in the background
        task = asyncio.create_task(_run_pipeline_task())

        while True:
            # Check for client disconnect on each keep-alive tick so disconnected
            # clients do not continue consuming paid Vertex quota.
            if await http_request.is_disconnected():
                logger.info(
                    "atelier.generate.stream.client_disconnected",
                    extra={"uid": sanitize(user.uid)},
                )
                if _session_id_holder:
                    from atelier.orchestrator.stop_controller import (  # noqa: PLC0415
                        request_stop,
                        stop_key,
                    )

                    # L04: the owner's own client disconnect arms the owner key.
                    request_stop(stop_key(user.uid, _session_id_holder[0]))
                task.cancel()
                break

            try:
                # Wait for an event with a 1.0 second timeout to support keep-alive pinging
                event_type, payload = await asyncio.wait_for(queue.get(), timeout=1.0)
                yield f"event: {event_type}\ndata: {json.dumps(payload, default=str)}\n\n"
                queue.task_done()
                if event_type in {"complete", "error"}:
                    break
            except TimeoutError:
                if task.done():
                    # Process remaining items in the queue
                    while not queue.empty():
                        event_type, payload = queue.get_nowait()
                        yield f"event: {event_type}\ndata: {json.dumps(payload, default=str)}\n\n"
                        queue.task_done()
                    break
                # Yield keep-alive comment
                yield ": ping\n\n"

        await task

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        # L48: keep the event stream un-buffered end-to-end. Without these,
        # intermediary proxies / the Cloud Run front end may buffer or chunk the
        # response in ways that enlarge and re-split SSE frames (compounding the
        # L07 chunk-straddle hazard) or delay live events. `X-Accel-Buffering: no`
        # disables proxy buffering; `Cache-Control: no-cache` forbids caching the
        # stream; keep-alive holds the connection open for the run's duration.
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
