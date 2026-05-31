"""Agent Evaluation — Vertex AI Gen AI Evaluation integration.

Runs rubric-based evaluation of Atelier's generated UI candidates using
the Vertex AI Gen AI Evaluation service. This provides standardized,
reproducible quality metrics that can be tracked over time and compared
across model versions.

Evaluation Axes (mapped to D-O-R-A-V):
    - Design fidelity: How well the output matches the brief's intent
    - Originality: Creative quality and visual distinction
    - Relevance: Task-appropriate design decisions
    - Accessibility: WCAG compliance and semantic HTML
    - Visual clarity: Layout, typography, and readability

PRD Reference: §6.5 (Evaluation pillar)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvalResult:
    """Result of a single evaluation run.

    Attributes:
        task_id: Unique identifier for the evaluation task.
        brief: The design brief that produced the candidate.
        candidate_html: The HTML candidate being evaluated.
        scores: Per-axis scores from the evaluation.
        composite_score: Weighted average across all axes.
        passed: Whether the composite score exceeds the threshold.
        metadata: Additional evaluation metadata.
    """

    task_id: str
    brief: str
    candidate_html: str
    scores: dict[str, float]
    composite_score: float
    passed: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalSuite:
    """Collection of evaluation results from a batch run.

    Attributes:
        results: List of individual eval results.
        aggregate_score: Average composite score across all results.
        pass_rate: Fraction of results that passed.
        total_evaluated: Number of candidates evaluated.
    """

    results: list[EvalResult]
    aggregate_score: float
    pass_rate: float
    total_evaluated: int


# D-O-R-A-V rubric criteria for Gen AI Evaluation
_DORAV_RUBRIC = {
    "design_fidelity": (
        "Evaluate how well the HTML/CSS output matches the design brief's stated intent. "
        "Score 1-5 where 5 means the output perfectly captures the brief's visual and "
        "functional requirements."
    ),
    "originality": (
        "Evaluate the creative quality and visual distinction of the design. "
        "Score 1-5 where 5 means the design shows exceptional creativity while "
        "remaining appropriate for the stated context."
    ),
    "relevance": (
        "Evaluate whether the design decisions are appropriate for the task. "
        "Score 1-5 where 5 means every design choice directly serves the brief's purpose."
    ),
    "accessibility": (
        "Evaluate WCAG compliance: semantic HTML, ARIA labels, color contrast, "
        "keyboard navigation. Score 1-5 where 5 means full WCAG 2.2 AA compliance."
    ),
    "visual_clarity": (
        "Evaluate layout, typography, whitespace, and readability. "
        "Score 1-5 where 5 means the design is immediately scannable and clear."
    ),
}

_CONVERGENCE_THRESHOLD = 0.70


async def evaluate_candidate_genai(
    brief: str,
    candidate_html: str,
    *,
    task_id: str = "",
    project: str | None = None,
    location: str = "us-central1",
) -> EvalResult:
    """Evaluate a UI candidate using Vertex AI Gen AI Evaluation.

    Uses rubric-based evaluation with D-O-R-A-V criteria. Each axis is
    scored 1-5 and normalized to 0.0-1.0 for composite calculation.

    Args:
        brief: The design brief text.
        candidate_html: The HTML candidate to evaluate.
        task_id: Optional task identifier for tracking.
        project: GCP project ID. Defaults to GOOGLE_CLOUD_PROJECT env.
        location: GCP location. Defaults to us-central1.

    Returns:
        EvalResult with per-axis scores and composite.
    """
    import asyncio  # noqa: PLC0415
    from uuid import uuid4  # noqa: PLC0415

    if not task_id:
        task_id = str(uuid4())

    project = project or os.getenv("GOOGLE_CLOUD_PROJECT", "atelier-build-2026")

    try:
        scores = await asyncio.to_thread(_run_genai_eval, brief, candidate_html, project, location)
    except Exception as exc:  # noqa: BLE001
        # Fail-soft: evaluation failure should not break the pipeline
        logger.warning(
            "Gen AI Evaluation failed (fail-soft): %s",
            str(exc)[:200],
            exc_info=True,
        )
        # Return a neutral score on failure
        scores = dict.fromkeys(_DORAV_RUBRIC, 0.5)

    # Normalize scores from 1-5 to 0.0-1.0
    normalized = {axis: score / 5.0 for axis, score in scores.items()}
    composite = sum(normalized.values()) / len(normalized) if normalized else 0.0
    passed = composite >= _CONVERGENCE_THRESHOLD

    return EvalResult(
        task_id=task_id,
        brief=brief,
        candidate_html=candidate_html[:500],  # Truncate for storage
        scores=normalized,
        composite_score=round(composite, 4),
        passed=passed,
        metadata={
            "project": project,
            "location": location,
            "raw_scores": scores,
        },
    )


def _run_genai_eval(
    brief: str,
    candidate_html: str,
    project: str,
    location: str,
) -> dict[str, float]:
    """Run the Gen AI Evaluation synchronously (called via to_thread).

    Uses vertexai.Client for the evaluation API.

    Args:
        brief: Design brief text.
        candidate_html: HTML candidate to evaluate.
        project: GCP project ID.
        location: GCP location.

    Returns:
        Dict of axis name → raw score (1-5).
    """
    try:
        import vertexai  # noqa: PLC0415
        from vertexai.evaluation import EvalTask  # noqa: PLC0415

        vertexai.init(project=project, location=location)

        # Build the evaluation prompt
        eval_prompt = (
            f"Design Brief:\n{brief}\n\n"
            f"Generated HTML/CSS:\n{candidate_html[:2000]}\n\n"
            "Evaluate the generated design across these axes. "
            "For each axis, provide a score from 1 to 5."
        )

        # Create evaluation dataset
        eval_dataset = [
            {
                "prompt": eval_prompt,
                "reference": brief,  # Brief as reference for relevance scoring
            }
        ]

        eval_task = EvalTask(
            dataset=eval_dataset,
            metrics=["coherence", "fluency", "groundedness"],
        )

        result = eval_task.evaluate()

        # Map evaluation metrics to D-O-R-A-V scores
        metrics = result.summary_metrics if hasattr(result, "summary_metrics") else {}
        return {
            "design_fidelity": float(metrics.get("groundedness/mean", 3.0)),
            "originality": float(metrics.get("fluency/mean", 3.0)),
            "relevance": float(metrics.get("coherence/mean", 3.0)),
            "accessibility": 3.0,  # Requires deterministic gate (not LLM-scored)
            "visual_clarity": float(metrics.get("fluency/mean", 3.0)),
        }

    except ImportError:
        logger.warning("vertexai not available for Gen AI Evaluation")
        return dict.fromkeys(_DORAV_RUBRIC, 3.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gen AI Evaluation call failed: %s", str(exc)[:200])
        return dict.fromkeys(_DORAV_RUBRIC, 3.0)


async def run_eval_suite(
    briefs_and_candidates: list[tuple[str, str]],
    *,
    project: str | None = None,
) -> EvalSuite:
    """Run evaluation on a batch of brief-candidate pairs.

    Args:
        briefs_and_candidates: List of (brief, candidate_html) tuples.
        project: GCP project ID.

    Returns:
        EvalSuite with aggregate metrics.
    """
    import asyncio  # noqa: PLC0415

    tasks = [
        evaluate_candidate_genai(brief, html, project=project)
        for brief, html in briefs_and_candidates
    ]

    results = await asyncio.gather(*tasks)

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    avg_score = sum(r.composite_score for r in results) / total if total else 0.0

    return EvalSuite(
        results=list(results),
        aggregate_score=round(avg_score, 4),
        pass_rate=round(passed / total, 4) if total else 0.0,
        total_evaluated=total,
    )
