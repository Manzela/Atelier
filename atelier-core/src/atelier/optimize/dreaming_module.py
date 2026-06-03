"""Dreaming Module — post-flight DPO pair extraction and κ calibration.

Implements the "Dreaming Module" pattern: between live inference runs, the
system processes accumulated trajectory data to extract preference pairs,
submit Vertex AI tuning jobs, and evaluate model quality against the
calibration seed dataset.

Named after the biological analogy: just as sleep consolidates memories into
durable knowledge, the Dreaming Module consolidates raw trajectory observations
into structured training signal (DPO preference pairs) that improve future
generation quality.

Two operational modes:

1. **Mid-flight** (synchronous, per-request):
   Called from the runner immediately after N3d consensus scores K=3 candidates.
   Extracts accepted/rejected pairs from the current request's candidates and
   writes them directly to the dpo_pairs BQ table. Zero latency impact because
   the write is fire-and-forget (non-blocking async task or synchronous fail-soft).

2. **Post-flight** (asynchronous, periodic / on-demand):
   Scans trajectory_records for surfaces with both accepted and rejected
   outcomes across multiple requests. Mines cross-request pairs (richer
   diversity than single-request pairs). Triggers a Vertex AI tuning job
   when MIN_PAIRS_FOR_TUNING threshold is reached. Evaluates the tuned
   model via κ agreement against calibration-seed-v0.jsonl.

PRD Reference: §9.3 (DPO flywheel), §21 (Failure Trichotomy)
ADR Reference: 0028 (DPO parameters — β=0.1, epochs=3, adapter=4)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from atelier.utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

_PROJECT: Final[str] = os.environ.get("GOOGLE_CLOUD_PROJECT", "atelier-build-2026")
_DPO_PAIRS_TABLE: Final[str] = f"{_PROJECT}.atelier_trajectories.dpo_pairs"
_TRAJECTORY_TABLE: Final[str] = f"{_PROJECT}.atelier_trajectories.trajectory_records"
_CALIBRATION_SEED_PATH: Final[Path] = (
    Path(__file__).resolve().parents[6] / "atelier-eval" / "datasets" / "calibration-seed-v0.jsonl"
)

# Minimum margin for a pair to be useful DPO training signal.
# Below this the chosen/rejected distinction is too noisy.
MIN_MARGIN: Final[float] = 0.12


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExtractedPair:
    """A DPO pair extracted from trajectory records."""

    surface_id: str
    tenant_id: str
    session_id: str
    prompt: str
    chosen_response: str
    rejected_response: str
    chosen_score: float
    rejected_score: float
    margin: float
    node_name: str
    iteration: int
    extracted_at: str


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    """Result of running the calibration seed against the generation pipeline."""

    task_id: str
    brief: str
    composite_score: float
    reference_score: float
    passed: bool
    delta: float  # composite_score - reference_score


@dataclass
class DreamingReport:
    """Summary of one Dreaming Module run."""

    pairs_extracted: int = 0
    pairs_written_to_bq: int = 0
    tuning_job_name: str | None = None
    achieved_kappa: float | None = None
    endpoint_promoted: str | None = None
    calibration_results: list[CalibrationResult] | None = None
    errors: list[str] | None = None

    @property
    def success(self) -> bool:
        return not self.errors


# ---------------------------------------------------------------------------
# Mid-flight: extract pairs from a single request's N3d evaluation results
# ---------------------------------------------------------------------------


def extract_pairs_midflight(
    *,
    session_id: str,
    tenant_id: str,
    surface_id: str,
    brief_text: str,
    scored_candidates: list[dict[str, Any]],
) -> list[ExtractedPair]:
    """Extract DPO pairs from a single /v1/generate request's results.

    Called synchronously from runner.run() immediately after N3d evaluation.
    Extracts accepted/rejected pairs from the current request's gate-passing
    candidates.

    Each ``scored_candidates`` entry already pairs a candidate's HTML with its
    OWN consensus score (joined by ``candidate_id`` in the runner, where
    html<->score alignment is provable). The chosen/rejected labels are derived
    from each candidate's own score, so they can never invert — unlike the
    previous positional zip of raw-order candidates against the
    score-descending evaluations list, which silently wrote direction-inverted
    training pairs whenever raw order != score order (audit 2026-06-03).

    Args:
        session_id: Current request's session ID.
        tenant_id: Tenant isolation key.
        surface_id: UUID for the surface being designed.
        brief_text: The design brief (used as the DPO prompt).
        scored_candidates: Per gate-passing candidate, each a dict with at least
            ``html`` (str) and ``composite_score`` (float). Order is irrelevant —
            each entry is self-describing.

    Returns:
        List of ExtractedPair ready for BQ insertion.
        Empty list if no valid pairs can be formed (not an error).
    """
    pairs: list[ExtractedPair] = []
    now = datetime.now(tz=UTC).isoformat()

    # Keep only candidates with real HTML, carrying each one's own score. No
    # positional cursor: the (html, score) pairing is fixed inside each entry.
    scored: list[tuple[str, float]] = [
        (str(c.get("html", "")), float(c.get("composite_score", 0.0)))
        for c in scored_candidates
        if str(c.get("html", "")).strip()
    ]

    if len(scored) < 2:  # noqa: PLR2004
        logger.debug(
            "Mid-flight pair extraction: insufficient scored candidates",
            extra={"session_id": session_id, "scored": len(scored)},
        )
        return []

    # Form pairs: best vs each loser
    scored.sort(key=lambda x: x[1], reverse=True)
    chosen_html, chosen_score = scored[0]

    for rejected_html, rejected_score in scored[1:]:
        margin = chosen_score - rejected_score
        if margin < MIN_MARGIN:
            continue  # Too close — not useful training signal

        pairs.append(
            ExtractedPair(
                surface_id=surface_id,
                tenant_id=tenant_id,
                session_id=session_id,
                prompt=brief_text[:2000],  # Truncate for DPO JSONL
                chosen_response=chosen_html,
                rejected_response=rejected_html,
                chosen_score=chosen_score,
                rejected_score=rejected_score,
                margin=margin,
                node_name="N3a.generator",
                iteration=0,
                extracted_at=now,
            )
        )

    logger.info(
        "Mid-flight pair extraction complete",
        extra={
            "session_id": session_id,
            "pairs_extracted": len(pairs),
            "chosen_score": scored[0][1] if scored else 0,
        },
    )
    return pairs


def write_pairs_to_bq(
    pairs: list[ExtractedPair],
    *,
    bq_client: Any | None = None,
) -> int:
    """Write extracted pairs to the dpo_pairs BigQuery table (fail-soft).

    Args:
        pairs: ExtractedPair objects to insert.
        bq_client: Optional pre-constructed BQ client (for testing).

    Returns:
        Number of pairs successfully written. 0 on any failure (fail-soft).
    """
    if not pairs:
        return 0

    try:
        from google.cloud import bigquery  # noqa: PLC0415  # type: ignore[attr-defined]

        client = bq_client or bigquery.Client(project=_PROJECT)

        rows = []
        for pair in pairs:
            rows.append(
                {
                    "surface_id": pair.surface_id,
                    "tenant_id": pair.tenant_id,
                    "session_id": pair.session_id,
                    "node_name": pair.node_name,
                    "iteration": pair.iteration,
                    "prompt": pair.prompt,
                    "chosen_response": pair.chosen_response,
                    "rejected_response": pair.rejected_response,
                    "chosen_score": pair.chosen_score,
                    "rejected_score": pair.rejected_score,
                    "margin": pair.margin,
                    "created_at": pair.extracted_at,
                }
            )

        errors = client.insert_rows_json(_DPO_PAIRS_TABLE, rows)
        if errors:
            logger.warning(
                "BQ insert errors writing DPO pairs (fail-soft)",
                extra={"errors": str(errors)[:300], "pair_count": len(pairs)},
            )
            return 0

        logger.info(
            "DPO pairs written to BigQuery",
            extra={"count": len(pairs), "table": _DPO_PAIRS_TABLE},
        )
        return len(pairs)

    except Exception as exc:  # noqa: BLE001
        # Fail-soft: pair writing must never break the generate response
        logger.warning(
            "Failed to write DPO pairs to BQ (fail-soft): %s: %s",
            type(exc).__name__,
            sanitize(str(exc)[:200]),
        )
        return 0


# ---------------------------------------------------------------------------
# Post-flight: κ calibration against the golden seed dataset
# ---------------------------------------------------------------------------


def load_calibration_seed(
    path: Path | None = None,
) -> list[dict[str, Any]]:
    """Load the calibration seed dataset from JSONL.

    Args:
        path: Path to the JSONL file. Defaults to atelier-eval/datasets/calibration-seed-v0.jsonl.

    Returns:
        List of calibration task dicts.

    Raises:
        FileNotFoundError: If the calibration seed file does not exist.
    """
    seed_path = path or _CALIBRATION_SEED_PATH
    if not seed_path.exists():
        msg = f"Calibration seed not found: {seed_path}. Run CL-08 to generate it."
        raise FileNotFoundError(msg)

    tasks = []
    for raw_line in seed_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped:
            tasks.append(json.loads(stripped))

    logger.info("Loaded calibration seed", extra={"tasks": len(tasks), "path": str(seed_path)})
    return tasks


def evaluate_kappa_against_calibration(
    calibration_tasks: list[dict[str, Any]],
    *,
    generate_fn: Any,
) -> tuple[float, list[CalibrationResult]]:
    """Compute κ by running the pipeline on the calibration seed.

    For each calibration task:
      1. Calls generate_fn(brief) to get a composite_score from the tuned model
      2. Checks whether composite_score >= quality_criteria.min_composite_score

    Args:
        calibration_tasks: Loaded calibration seed tasks.
        generate_fn: Callable(brief: str) -> composite_score: float.
            Should invoke the pipeline with the TUNED model endpoint.

    Returns:
        Tuple of (kappa: float, results: list[CalibrationResult]).
        kappa = fraction of tasks where composite_score >= min_composite_score
                from the quality_criteria (not inter-rater κ, but the production
                definition: % of seeds that pass the quality gate).
    """
    results: list[CalibrationResult] = []

    for task in calibration_tasks:
        brief = task["brief"]
        reference_score = float(task["reference_score"])
        min_score = float(task["quality_criteria"].get("min_composite_score", 0.70))

        try:
            composite_score = float(generate_fn(brief))
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Calibration eval failed for task %s: %s",
                task["task_id"],
                sanitize(str(exc)[:100]),
            )
            composite_score = 0.0

        passed = composite_score >= min_score
        delta = composite_score - reference_score

        results.append(
            CalibrationResult(
                task_id=task["task_id"],
                brief=brief[:100],
                composite_score=composite_score,
                reference_score=reference_score,
                passed=passed,
                delta=delta,
            )
        )

    # κ = fraction passing their quality gate (production definition)
    if not results:
        return 0.0, results
    kappa = sum(1 for r in results if r.passed) / len(results)

    logger.info(
        "Calibration evaluation complete",
        extra={
            "kappa": kappa,
            "tasks_evaluated": len(results),
            "tasks_passed": sum(1 for r in results if r.passed),
        },
    )
    return kappa, results


# ---------------------------------------------------------------------------
# Post-flight orchestration: full Dreaming Module run
# ---------------------------------------------------------------------------


def run_dreaming_module(
    *,
    tenant_id: str | None = None,
    min_pairs: int = 50,
    dry_run: bool = False,
) -> DreamingReport:
    """Execute one full post-flight Dreaming Module cycle.

    Scans trajectory_records, extracts pairs, optionally submits a tuning job,
    evaluates κ, and promotes if the threshold is met.

    This is the "Dreaming Module" — called periodically between live inference
    runs to consolidate experience into durable model improvements.

    Args:
        tenant_id: If set, restricts pair mining to this tenant. Admin callers
            pass None with allow_cross_tenant=True in the inner mine_pairs() call.
        min_pairs: Minimum pairs required to start a tuning job.
        dry_run: If True, extracts pairs and computes κ but does NOT submit the
            Vertex tuning job. Safe for testing / cost control.

    Returns:
        DreamingReport summarizing what happened.

    Raises:
        Nothing — all errors are caught and reported in DreamingReport.errors.
    """
    report = DreamingReport(errors=[])
    assert report.errors is not None  # mypy

    logger.info(
        "Dreaming Module starting",
        extra={"tenant_id": sanitize(tenant_id or ""), "min_pairs": min_pairs, "dry_run": dry_run},
    )

    # Step 1: Mine pairs from BQ
    try:
        from atelier.optimize.generator_tuner import (  # noqa: PLC0415
            MIN_PAIRS_FOR_TUNING,
            GeneratorTuner,
        )

        tuner = GeneratorTuner(project=_PROJECT)
        effective_min_pairs = max(min_pairs, MIN_PAIRS_FOR_TUNING)

        pairs = tuner.mine_pairs(
            tenant_id=tenant_id,
            limit=500,
        )
        report.pairs_extracted = len(pairs)
        logger.info(
            "Dreaming Module: mined pairs",
            extra={"count": len(pairs), "required": effective_min_pairs},
        )

    except Exception as exc:
        msg = f"Pair mining failed: {type(exc).__name__}: {sanitize(str(exc)[:200])}"
        report.errors.append(msg)
        logger.exception(msg)
        return report

    if len(pairs) < min_pairs:
        logger.info(
            "Dreaming Module: insufficient pairs — skipping tuning",
            extra={"available": len(pairs), "required": min_pairs},
        )
        return report

    # Step 2: Submit Vertex AI tuning job (unless dry_run)
    if dry_run:
        logger.info(
            "Dreaming Module: dry_run=True — skipping tuning job submission",
            extra={"pairs_available": len(pairs)},
        )
        return report

    try:
        job_name = tuner.tune(pairs, display_name="atelier-dreaming-module")
        report.tuning_job_name = job_name
        logger.info("Dreaming Module: tuning job submitted", extra={"job_name": job_name})

    except Exception as exc:
        msg = f"Tuning job submission failed: {type(exc).__name__}: {sanitize(str(exc)[:200])}"
        report.errors.append(msg)
        logger.exception(msg)
        return report

    # Step 3: Load calibration seed + evaluate κ
    # (Called separately by the caller after the job completes, since Vertex
    # AI tuning takes 2-4 hours. The caller polls get_state() and calls
    # compute_and_promote() when SUCCEEDED.)
    logger.info(
        "Dreaming Module: tuning job submitted, κ evaluation deferred until job completes",
        extra={"job_name": report.tuning_job_name},
    )
    return report


def compute_and_promote(
    job_name: str,
    *,
    generate_fn: Any,
    calibration_seed_path: Path | None = None,
) -> DreamingReport:
    """Evaluate κ after the tuning job completes and promote if gate passes.

    This is the second half of the post-flight cycle, called after polling
    confirms the Vertex AI tuning job has reached SUCCEEDED state.

    Args:
        job_name: The Vertex AI tuning job resource name from run_dreaming_module().
        generate_fn: Callable(brief: str) -> composite_score: float.
            Must use the TUNED endpoint for accurate κ measurement.
        calibration_seed_path: Override path to the calibration seed JSONL.

    Returns:
        DreamingReport with achieved_kappa and endpoint_promoted (if gate passed).
    """
    report = DreamingReport(errors=[], tuning_job_name=job_name)
    assert report.errors is not None

    try:
        tasks = load_calibration_seed(calibration_seed_path)
    except FileNotFoundError as exc:
        report.errors.append(sanitize(str(exc)))
        return report

    kappa, results = evaluate_kappa_against_calibration(tasks, generate_fn=generate_fn)
    report.achieved_kappa = kappa
    report.calibration_results = results

    logger.info(
        "Dreaming Module: κ evaluation complete",
        extra={"kappa": kappa, "threshold": 0.70, "gate": "PASS" if kappa >= 0.70 else "FAIL"},  # noqa: PLR2004
    )

    if kappa < 0.70:  # noqa: PLR2004
        logger.info(
            "Dreaming Module: κ gate did not pass — model NOT promoted",
            extra={"achieved_kappa": kappa, "threshold": 0.70},
        )
        return report

    # κ gate passed — promote the model
    try:
        from atelier.optimize.generator_tuner import GeneratorTuner  # noqa: PLC0415

        tuner = GeneratorTuner(project=_PROJECT)
        endpoint = tuner.evaluate_and_promote(job_name=job_name, achieved_kappa=kappa)
        report.endpoint_promoted = endpoint
        logger.info(
            "Dreaming Module: model PROMOTED",
            extra={"endpoint": endpoint, "kappa": kappa},
        )
    except Exception as exc:
        msg = f"Promotion failed: {type(exc).__name__}: {sanitize(str(exc)[:200])}"
        report.errors.append(msg)
        logger.exception(msg)

    return report
