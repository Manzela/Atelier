"""Evaluate API — POST /v1/evaluate (AT-027).

The eval lane that finally wires the previously-dead ``run_simulation()`` into a
request path AND surfaces — read-only — the two optimize assets the product had
never exposed:

    1. The MoE routing decision: a real ``RouteDecision`` produced by the
       ``EpsilonGreedyBandit`` (v1_bandit) router. The decision is the router's
       phase-aware expert choice for the eval phase — surfaced for legibility,
       not used to dispatch a model (the simulation path is gate-only).
    2. A dreaming / DPO artifact: a real ``ExtractedPair`` produced by the
       dreaming module's mid-flight pair extractor, whose ``chosen_score``
       already reflects the §3.6 anti-sycophancy reward rule.

The endpoint persists ONE trajectory row (wide replay schema) carrying both
optimize assets as JSON columns, so the same trace is replayable via
``GET /v1/replay/{session_id}`` — the single trace surface (AT-026).

This is a READ-ONLY surfacing feature: it runs the existing optimize code and
displays its output. It does NOT submit tuning jobs, mutate router arm state
beyond the in-request route() call, or generate HTML. The BQ write is fail-soft
(PRD §21): a telemetry-write failure never fails the evaluation response.

PRD Reference: §6.5 (Simulation pillar), §9.3 (DPO flywheel), §3.6
    (anti-sycophancy), §18.4 (MoE router), §7.1 (API surface).
ADR Reference: 0027 (router Protocol ladder), 0028 (DPO parameters).
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

import numpy as np
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from atelier.auth.firebase import FirebaseUser, require_auth
from atelier.evaluation.agent_simulation import (
    ALL_BRIEFS,
    SimulationBrief,
    run_simulation,
)
from atelier.optimize.dreaming_module import extract_pairs_midflight
from atelier.router.protocol import (
    DAGPhase,
    RouteDecision,
    RouteRequest,
)
from atelier.router.v1_bandit import EpsilonGreedyBandit

logger: Any = structlog.get_logger("atelier.api.evaluate")

router = APIRouter(prefix="/v1/evaluate", tags=["optimize"])

# Embedding dimensionality of text-embedding-005 (router contract, §18.4).
_EMBEDDING_DIM = 768
_TRAJECTORY_TABLE = "atelier-build-2026.atelier_trajectories.trajectory_records"
_MAX_BRIEFS_PER_RUN = 24


def _make_bq_client() -> Any:
    """Construct a BigQuery client, or return None if the SDK is unavailable.

    Mirrors ``atelier.api.replay._make_bq_client`` so the write path (here) and
    the read path (replay) share one patchable factory. Returns None instead of
    raising when the optional extra is missing — the BQ write is fail-soft.
    """
    try:
        from google.cloud import bigquery  # noqa: PLC0415  # type: ignore[attr-defined]
    except ImportError:
        logger.warning("atelier.evaluate.bq_unavailable")
        return None
    import os  # noqa: PLC0415

    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "atelier-build-2026")
    return bigquery.Client(project=project)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class EvaluateRequest(BaseModel):
    """Request body for POST /v1/evaluate."""

    brief_ids: list[str] | None = Field(
        default=None,
        description=(
            "IDs of briefs from the simulation library to evaluate (e.g. "
            "'adv-001'). If omitted, the full adversarial + edge + stress "
            "library is run. Capped per request to bound work."
        ),
    )


class SimulationResultSchema(BaseModel):
    """Serialized SimulationResult for JSON output (read-only)."""

    brief_id: str
    category: str
    expected_outcome: str
    actual_outcome: str
    composite_score: float
    latency_ms: float
    matched_expected: bool
    error: str | None = None


class RouteDecisionSchema(BaseModel):
    """Serialized RouteDecision for JSON output (read-only)."""

    expert: str
    phase: str
    score: float
    rationale: str
    fallback_chain: list[str]
    routing_mode: str


class DreamingArtifactSchema(BaseModel):
    """Serialized dreaming/DPO ExtractedPair for JSON output (read-only)."""

    surface_id: str
    node_name: str
    chosen_score: float
    rejected_score: float
    margin: float


class EvaluateResponse(BaseModel):
    """Response body for POST /v1/evaluate."""

    session_id: str
    results: list[SimulationResultSchema]
    route_decision: RouteDecisionSchema | None = None
    dreaming_artifact: DreamingArtifactSchema | None = None
    matched_count: int
    total_count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_briefs(brief_ids: list[str] | None) -> list[SimulationBrief]:
    """Resolve requested brief IDs to SimulationBrief objects.

    Args:
        brief_ids: Requested IDs, or None for the full library.

    Returns:
        The resolved briefs, capped to _MAX_BRIEFS_PER_RUN.

    Raises:
        HTTPException(400): If a requested ID is not in the library.
    """
    if brief_ids is None:
        return ALL_BRIEFS[:_MAX_BRIEFS_PER_RUN]

    by_id = {b.id: b for b in ALL_BRIEFS}
    unknown = [bid for bid in brief_ids if bid not in by_id]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unknown_brief_ids",
                "code": 400,
                "title": "Unknown simulation brief id(s)",
                "detail": f"No such brief(s) in the simulation library: {unknown}",
                "user_action": "Use ids from GET /docs or omit brief_ids for the full set.",
            },
        )
    return [by_id[bid] for bid in brief_ids][:_MAX_BRIEFS_PER_RUN]


async def _compute_route_decision(trace_id: str, tenant_id: str) -> RouteDecision:
    """Produce a real MoE RouteDecision for the eval phase (read-only).

    Uses the v1_bandit ``EpsilonGreedyBandit`` router exactly as the orchestrator
    would, for the JUDGE_CANDIDATES phase (the eval lane's analogue). The
    decision is surfaced for legibility; no model is dispatched from it.
    """
    router_impl = EpsilonGreedyBandit()
    request = RouteRequest(
        phase=DAGPhase.JUDGE_CANDIDATES,
        task_embedding=np.zeros(_EMBEDDING_DIM, dtype=np.float32),
        cost_budget_remaining_usd=1.0,
        latency_target_ms=5000,
        prior_judge_kappa=None,
        trace_id=trace_id,
        tenant_id=tenant_id,
    )
    return await router_impl.route(request)


def _extract_dreaming_artifact(
    *,
    session_id: str,
    tenant_id: str,
) -> DreamingArtifactSchema | None:
    """Extract one real dreaming/DPO ExtractedPair for surfacing (read-only).

    Builds a two-candidate scored set (a justified winner vs an unjustified
    runner-up) and runs the REAL ``extract_pairs_midflight`` — so the
    anti-sycophancy reward (§3.6) is exercised on the live path, not faked.
    The chosen candidate carries a justification, so its score is NOT penalised;
    the contrast against a praise-only candidate is what the pair captures.

    Returns the highest-margin pair as a read-only schema, or None if no pair
    clears MIN_MARGIN (not an error — surfaced as null).
    """
    surface_id = str(uuid4())
    scored_candidates: list[dict[str, Any]] = [
        {
            "html": (
                "<main>Accessible dashboard. This layout meets the WCAG AA "
                "contrast standard because the chosen palette measures a 4.8:1 "
                "ratio against the background.</main>"
            ),
            "composite_score": 0.91,
        },
        {
            "html": "<main>Looks good! Great work, excellent.</main>",
            "composite_score": 0.62,
        },
    ]
    pairs = extract_pairs_midflight(
        session_id=session_id,
        tenant_id=tenant_id,
        surface_id=surface_id,
        brief_text="Design an accessible analytics dashboard.",
        scored_candidates=scored_candidates,
    )
    if not pairs:
        return None
    top = max(pairs, key=lambda p: p.margin)
    return DreamingArtifactSchema(
        surface_id=top.surface_id,
        node_name=top.node_name,
        chosen_score=top.chosen_score,
        rejected_score=top.rejected_score,
        margin=top.margin,
    )


def _build_trajectory_row(
    *,
    session_id: str,
    tenant_id: str,
    started_at: datetime,
    ended_at: datetime,
    results_count: int,
    matched_count: int,
    route: RouteDecisionSchema,
    artifact: DreamingArtifactSchema | None,
) -> dict[str, Any]:
    """L14: build the ``trajectory_records`` row in the DEPLOYED narrow schema.

    The deployed table is ``(session_id, tenant_id, node_name, phase, expert_id,
    occurred_at, payload JSON, embedding)``. The previous wide row named columns the
    table does not have (``ts``, ``ended_at``, ``outcome``, ``composite_score`` …)
    AND omitted the REQUIRED ``phase`` + ``occurred_at``, so every
    ``insert_rows_json`` failed 'no such field' — swallowed as a WARNING — and
    nothing was ever replayable. All per-run detail (including the AT-027 route
    decision + dreaming artifact that ``GET /v1/replay`` surfaces) now rides the
    JSON ``payload``; ``api.replay._unpack_event_row`` flattens it and maps
    ``occurred_at`` -> ``ts`` and ``route_decisions`` -> ``route_decisions_json``,
    so the row round-trips through replay.
    """
    return {
        "session_id": session_id,
        "tenant_id": tenant_id,
        "node_name": "evaluate.simulation",
        "phase": "completed",
        "expert_id": None,
        "occurred_at": ended_at.isoformat(),
        "payload": json.dumps(
            {
                "trajectory_id": str(uuid4()),
                "project_id": tenant_id,
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "outcome": "completed",
                "composite_score": (matched_count / results_count) if results_count else 0.0,
                "candidate_id": session_id,
                "iteration": 0,
                "route_decisions": [route.model_dump()],
                "dreaming_artifacts": [artifact.model_dump()] if artifact else [],
            }
        ),
    }


async def _persist_trace(
    *,
    session_id: str,
    tenant_id: str,
    started_at: datetime,
    results_count: int,
    matched_count: int,
    route: RouteDecisionSchema,
    artifact: DreamingArtifactSchema | None,
    bq_client: Any | None,
) -> None:
    """Persist ONE trajectory row carrying the optimize assets (fail-soft).

    The row uses the deployed NARROW ``trajectory_records`` schema (L14); the
    optimize detail rides the JSON ``payload`` that ``GET /v1/replay/{session_id}``
    unpacks. A BQ failure is logged and swallowed (PRD §21) — telemetry must never
    fail the eval response.
    """
    client = bq_client if bq_client is not None else _make_bq_client()
    if client is None:
        logger.warning("atelier.evaluate.persist_skipped", session_id=session_id)
        return

    ended_at = datetime.now(tz=UTC)
    row: dict[str, Any] = _build_trajectory_row(
        session_id=session_id,
        tenant_id=tenant_id,
        started_at=started_at,
        ended_at=ended_at,
        results_count=results_count,
        matched_count=matched_count,
        route=route,
        artifact=artifact,
    )

    try:
        loop = asyncio.get_running_loop()
        errors = await loop.run_in_executor(
            None,
            lambda: client.insert_rows_json(_TRAJECTORY_TABLE, [row]),
        )
        if errors:
            logger.warning(
                "atelier.evaluate.persist_errors",
                session_id=session_id,
                errors=str(errors)[:300],
            )
    except Exception as exc:  # noqa: BLE001
        # Fail-soft (§21): a telemetry write must never break the eval response.
        logger.warning(
            "atelier.evaluate.persist_failed",
            session_id=session_id,
            error_type=type(exc).__name__,
            error=str(exc)[:200],
        )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "",
    summary="Run the simulation eval lane and surface optimize assets (read-only)",
    response_model=EvaluateResponse,
)
async def evaluate(
    user: Annotated[FirebaseUser, Depends(require_auth)],
    body: EvaluateRequest,
) -> EvaluateResponse:
    """Run ``run_simulation`` over the requested briefs and surface optimize assets.

    Invokes the real simulation eval lane, the real v1_bandit router, and the
    real dreaming/DPO pair extractor (with the §3.6 anti-sycophancy reward), then
    persists a replayable trace. All read-only.

    Args:
        user: Verified Firebase user (tenant isolation via user.tenant_id).
        body: EvaluateRequest — optional brief_ids to scope the run.

    Returns:
        EvaluateResponse with simulation results, the MoE RouteDecision, and a
        dreaming/DPO artifact. The trace is replayable at /v1/replay/{session_id}.

    Raises:
        HTTPException(400): Unknown brief id(s).
    """
    session_id = str(uuid4())
    started_at = datetime.now(tz=UTC)
    briefs = _resolve_briefs(body.brief_ids)

    await logger.ainfo(
        "atelier.evaluate.start",
        user_id=user.uid,
        tenant_id=user.tenant_id,
        session_id=session_id,
        brief_count=len(briefs),
    )

    # --- Eval lane: actually invoke run_simulation (previously dead code) ---
    sim_results = await run_simulation(briefs)
    results = [
        SimulationResultSchema(
            brief_id=r.brief.id,
            category=r.brief.category,
            expected_outcome=r.brief.expected_outcome,
            actual_outcome=r.actual_outcome,
            composite_score=r.composite_score,
            latency_ms=r.latency_ms,
            matched_expected=r.matched_expected,
            error=r.error,
        )
        for r in sim_results
    ]
    matched_count = sum(1 for r in results if r.matched_expected)

    # --- Optimize asset 1: real MoE RouteDecision (read-only) ---------------
    decision = await _compute_route_decision(trace_id=session_id, tenant_id=user.tenant_id)
    route = RouteDecisionSchema(
        expert=str(decision.expert),
        phase=str(decision.phase),
        score=decision.score,
        rationale=decision.rationale,
        fallback_chain=[str(e) for e in decision.fallback_chain],
        routing_mode=decision.routing_mode,
    )

    # --- Optimize asset 2: real dreaming/DPO artifact (read-only) -----------
    artifact = _extract_dreaming_artifact(session_id=session_id, tenant_id=user.tenant_id)

    # --- Persist a replayable trace (fail-soft) -----------------------------
    await _persist_trace(
        session_id=session_id,
        tenant_id=user.tenant_id,
        started_at=started_at,
        results_count=len(results),
        matched_count=matched_count,
        route=route,
        artifact=artifact,
        bq_client=None,
    )

    await logger.ainfo(
        "atelier.evaluate.complete",
        session_id=session_id,
        matched_count=matched_count,
        total_count=len(results),
        route_expert=route.expert,
        has_dreaming_artifact=artifact is not None,
    )

    return EvaluateResponse(
        session_id=session_id,
        results=results,
        route_decision=route,
        dreaming_artifact=artifact,
        matched_count=matched_count,
        total_count=len(results),
    )
