"""Dream API — POST /v1/dream and POST /v1/dream/promote.

Exposes the Dreaming Module as REST endpoints so the orchestrator and
external tooling (Cloud Scheduler, admin dashboard) can trigger post-flight
DPO tuning cycles and promote tuned models via the κ gate.

Endpoints:
    POST /v1/dream         — Trigger a full post-flight Dreaming Module run.
    POST /v1/dream/promote — Evaluate κ on a completed tuning job and promote.

Both endpoints require Firebase Authentication. Tuning jobs run synchronously
within the request lifetime (fire for local dev / testing); production callers
should dispatch via Cloud Tasks and treat the response as a job receipt.

PRD Reference: §9.3 (DPO flywheel), §7.1 (API surface)
ADR Reference: 0028 (DPO parameters — κ gate ≥ 0.70)
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from atelier.auth.firebase import FirebaseUser, require_auth

logger: Any = structlog.get_logger("atelier.api.dream")

router = APIRouter(prefix="/v1/dream", tags=["optimize"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class DreamRequest(BaseModel):
    """Request body for POST /v1/dream."""

    min_pairs: int = Field(
        default=50,
        ge=1,
        le=10_000,
        description="Minimum DPO pairs required to trigger a Vertex AI tuning job.",
    )
    dry_run: bool = Field(
        default=False,
        description=(
            "If True, mines and scores pairs but does NOT submit a Vertex AI tuning job. "
            "Use for cost-free validation of the pair pipeline."
        ),
    )


class CalibrationResultSchema(BaseModel):
    """Serialized CalibrationResult for JSON output."""

    task_id: str
    brief: str
    composite_score: float
    reference_score: float
    passed: bool
    delta: float


class DreamResponse(BaseModel):
    """Response body for POST /v1/dream."""

    pairs_extracted: int
    pairs_written_to_bq: int
    tuning_job_name: str | None = None
    achieved_kappa: float | None = None
    endpoint_promoted: str | None = None
    calibration_results: list[CalibrationResultSchema] | None = None
    errors: list[str] | None = None
    success: bool


class PromoteRequest(BaseModel):
    """Request body for POST /v1/dream/promote."""

    job_name: str = Field(
        description="Vertex AI tuning job resource name from a previous POST /v1/dream response.",
    )


class PromoteResponse(BaseModel):
    """Response body for POST /v1/dream/promote."""

    job_name: str
    achieved_kappa: float | None = None
    endpoint_promoted: str | None = None
    calibration_results: list[CalibrationResultSchema] | None = None
    errors: list[str] | None = None
    success: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    summary="Trigger a post-flight Dreaming Module DPO tuning cycle",
    response_model=DreamResponse,
)
async def trigger_dreaming_module(
    user: Annotated[FirebaseUser, Depends(require_auth)],
    body: DreamRequest,
) -> DreamResponse:
    """Mine DPO pairs and optionally submit a Vertex AI PREFERENCE_TUNING job.

    Scans `atelier_trajectories.dpo_pairs` for the caller's tenant, extracts
    preference pairs above the margin threshold, and submits a tuning job when
    `min_pairs` threshold is reached. κ evaluation runs after the job completes
    via a subsequent call to `POST /v1/dream/promote`.

    Args:
        user: Verified Firebase user (tenant isolation via user.tenant_id).
        body: DreamRequest parameters.

    Returns:
        DreamResponse with the result of the Dreaming Module run.
    """
    from atelier.optimize.dreaming_module import run_dreaming_module  # noqa: PLC0415

    await logger.ainfo(
        "atelier.dream.trigger",
        user_id=user.uid,
        tenant_id=user.tenant_id,
        min_pairs=body.min_pairs,
        dry_run=body.dry_run,
    )

    report = run_dreaming_module(
        tenant_id=user.tenant_id,
        min_pairs=body.min_pairs,
        dry_run=body.dry_run,
    )

    cal_results: list[CalibrationResultSchema] | None = None
    if report.calibration_results is not None:
        cal_results = [
            CalibrationResultSchema(
                task_id=r.task_id,
                brief=r.brief,
                composite_score=r.composite_score,
                reference_score=r.reference_score,
                passed=r.passed,
                delta=r.delta,
            )
            for r in report.calibration_results
        ]

    await logger.ainfo(
        "atelier.dream.complete",
        user_id=user.uid,
        pairs_extracted=report.pairs_extracted,
        tuning_job_name=report.tuning_job_name,
        success=report.success,
    )

    return DreamResponse(
        pairs_extracted=report.pairs_extracted,
        pairs_written_to_bq=report.pairs_written_to_bq,
        tuning_job_name=report.tuning_job_name,
        achieved_kappa=report.achieved_kappa,
        endpoint_promoted=report.endpoint_promoted,
        calibration_results=cal_results,
        errors=report.errors,
        success=report.success,
    )


@router.post(
    "/promote",
    summary="Evaluate κ on a completed tuning job and promote if gate passes",
    response_model=PromoteResponse,
)
async def promote_tuned_model(
    user: Annotated[FirebaseUser, Depends(require_auth)],
    body: PromoteRequest,
) -> PromoteResponse:
    """Evaluate κ against the calibration seed and promote the tuned model.

    Called after a Vertex AI tuning job from `POST /v1/dream` reaches SUCCEEDED
    state. Runs the calibration seed through the tuned model endpoint, computes
    κ, and promotes the endpoint if κ ≥ 0.70 (ADR 0028).

    The `generate_fn` used for calibration runs the live pipeline in dry-run
    mode against the tuned model's endpoint. In staging, the mock scorer
    returns the reference score ± noise to simulate real behaviour.

    Args:
        user: Verified Firebase user (tenant isolation).
        body: PromoteRequest with the tuning job name.

    Returns:
        PromoteResponse with the κ score and endpoint (if promoted).
    """
    from atelier.optimize.dreaming_module import compute_and_promote  # noqa: PLC0415

    await logger.ainfo(
        "atelier.dream.promote",
        user_id=user.uid,
        job_name=body.job_name,
    )

    import os  # noqa: PLC0415

    # P0-03: Tenant ownership — prevent one tenant from promoting another's
    # tuning job. The previous `in` check was vulnerable to substring attacks
    # (tenant "t1" would match job names containing "t123"). This fix uses
    # segment-boundary matching: the tenant_id must appear as a complete
    # segment between '/' delimiters or at string boundaries. Vertex AI job
    # names look like "projects/<project>/locations/<location>/tuningJobs/<id>",
    # so the tenant_id must match a whole segment, never a substring of one.
    import re  # noqa: PLC0415

    tenant_pattern = re.compile(r"(?:^|/)" + re.escape(user.tenant_id) + r"(?:/|$)")
    if not tenant_pattern.search(body.job_name):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "forbidden",
                "detail": "Tuning job does not belong to the authenticated tenant.",
            },
        )

    # H-3b: Gate staging mock scorer — must not run in production.
    if os.getenv("ATELIER_ENV", "development") != "development":
        raise HTTPException(
            status_code=501,
            detail={
                "error": "not_implemented",
                "detail": (
                    "Production scorer not wired. The staging mock scorer must not "
                    "be used outside local development — it deterministically passes "
                    "the κ gate regardless of actual model quality. Contact engineering."
                ),
            },
        )

    # Staging mock scorer: returns 0.82 (above the 0.70 κ gate).
    # Production callers replace this with a real pipeline invocation against
    # the tuned endpoint. The scorer is injected here (not in compute_and_promote)
    # because the endpoint URL is only known after the job completes — the
    # runner must resolve the tuned endpoint name from the job_name via Vertex AI
    # before invoking generation.
    def _staging_generate_fn(brief: str) -> float:
        import hashlib  # noqa: PLC0415

        digest = int(hashlib.md5(brief.encode()).hexdigest()[:4], 16)  # noqa: S324
        return 0.78 + (digest % 100) / 1000  # 0.780-0.879, always above 0.70 gate

    report = compute_and_promote(
        body.job_name,
        generate_fn=_staging_generate_fn,
    )

    cal_results_promote: list[CalibrationResultSchema] | None = None
    if report.calibration_results is not None:
        cal_results_promote = [
            CalibrationResultSchema(
                task_id=r.task_id,
                brief=r.brief,
                composite_score=r.composite_score,
                reference_score=r.reference_score,
                passed=r.passed,
                delta=r.delta,
            )
            for r in report.calibration_results
        ]

    await logger.ainfo(
        "atelier.dream.promote.complete",
        user_id=user.uid,
        achieved_kappa=report.achieved_kappa,
        endpoint_promoted=report.endpoint_promoted,
        success=report.success,
    )

    return PromoteResponse(
        job_name=body.job_name,
        achieved_kappa=report.achieved_kappa,
        endpoint_promoted=report.endpoint_promoted,
        calibration_results=cal_results_promote,
        errors=report.errors,
        success=report.success,
    )
