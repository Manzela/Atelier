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

import logging
import os
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from atelier.auth.firebase import FirebaseUser, require_auth

logger = logging.getLogger(__name__)


def _sanitize_for_log(value: Any) -> str:
    """Return a single-line string safe for logging."""
    return str(value).replace("\r", "").replace("\n", "")


router = APIRouter(prefix="/v1/generate", tags=["pipeline"])

_PROJECT: str = os.environ.get("GOOGLE_CLOUD_PROJECT", "atelier-build-2026")
# K=3 ensemble size — must stay in sync with generator_ensemble.ENSEMBLE_SIZE
_ENSEMBLE_SIZE: int = 3


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
    budget_usd: float = Field(
        default=10.0,
        ge=0.1,
        le=5000.0,
        description="Per-request generation budget in USD. Default $10.",
    )


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

    # Cost
    cost_usd: float

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
    budget_usd: float,
    design_system_source: str | None,  # noqa: ARG001 — Phase 2: will be passed to runner
) -> dict[str, Any]:
    """Execute the full Atelier pipeline and return the raw result dict."""
    from decimal import Decimal  # noqa: PLC0415

    from atelier.models.data_contracts import TenantContext  # noqa: PLC0415
    from atelier.orchestrator.runner import AtelierRunner  # noqa: PLC0415

    tenant_ctx = TenantContext(
        tenant_id=user.tenant_id,
        user_id=user.uid,
        project_id=_PROJECT,
        cost_budget_usd=Decimal(str(budget_usd)),
        # descriptor left None; design_system_source is passed via brief parsing (BriefSpec.design_system_source)
    )

    runner = AtelierRunner(budget_cap_usd=budget_usd)
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
        # P0-3 / P1-3: use _ENSEMBLE_SIZE constant instead of hardcoded 3.
        records = []
        eval_cursor = 0
        for i, candidate in enumerate(candidates[:_ENSEMBLE_SIZE]):
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
                total_cost_usd=result.get("budget_used_usd", 0.0) / max(len(candidates), 1),
            )
            records.append(record)

        if records:
            from google.cloud import bigquery as _bq  # noqa: PLC0415

            bq_client = _bq.Client(project=_PROJECT)
            recorder = TrajectoryRecorder(bq_client)
            for record in records:
                recorder.record(record)
            recorder.flush()

    except Exception as exc:  # noqa: BLE001
        # Fail-soft: trajectory recording must never break the generate response
        logger.warning(
            "Trajectory recording failed (fail-soft): %s: %s",
            type(exc).__name__,
            str(exc)[:200],
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
        cost_usd=result.get("budget_used_usd", 0.0),
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
        HTTPException(402): When the user's generation budget cap is exceeded.
        HTTPException(401): When the caller is unauthenticated.
    """
    run_id = str(uuid4())
    started_at = datetime.now(tz=UTC).isoformat()

    logger.info(
        "atelier.generate.start",
        extra={
            "run_id": run_id,
            "tenant_id": user.tenant_id,
            "user_id": user.uid,
            "brief_length": _sanitize_for_log(len(request.brief)),
            "budget_usd": _sanitize_for_log(request.budget_usd),
        },
    )

    result = await _run_pipeline(
        brief=request.brief,
        user=user,
        budget_usd=request.budget_usd,
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
            "cost_usd": response.cost_usd,
        },
    )

    return response
