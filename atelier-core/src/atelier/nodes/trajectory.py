"""Trajectory Recorder — N3h pipeline node.

Records every step of the pipeline execution to BigQuery for:
    - DPO preference pair extraction
    - Calibration metric tracking
    - Cost ledger accounting
    - Audit trail compliance (PRD section 15)

Each trajectory record captures the full context of a pipeline step:
candidate state, gate outcomes, judge votes, mutations applied, and
the final decision. Records are written asynchronously to avoid
blocking the pipeline.

The trajectory table schema matches:
    ``i-for-ai.atelier_trajectories.trajectory_records``

PRD Reference: section 6.3 (N3h), section 7 (Infrastructure)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrajectoryStep:
    """A single step in the pipeline trajectory.

    Attributes:
        step_name: Name of the pipeline node (e.g., ``"n3a_generator"``).
        step_index: Ordinal position in the pipeline (0-based).
        started_at: UTC timestamp when the step started.
        ended_at: UTC timestamp when the step completed.
        input_summary: Brief summary of step input (for audit).
        output_summary: Brief summary of step output (for audit).
        model_id: Model used for this step (if applicable).
        input_tokens: Token count for model input (if applicable).
        output_tokens: Token count for model output (if applicable).
        cost_usd: Estimated cost in USD (if applicable).
        metadata: Additional step-specific metadata.
    """

    step_name: str
    step_index: int
    started_at: datetime
    ended_at: datetime
    input_summary: str = ""
    output_summary: str = ""
    model_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrajectoryRecord:
    """Complete trajectory for a single pipeline execution.

    This is the primary record written to BigQuery. One record per
    candidate generation attempt (brief -> generate -> gate -> judge -> fix cycle).

    Attributes:
        trajectory_id: Unique identifier for this trajectory.
        tenant_id: Multi-tenant isolation key.
        project_id: Project within the tenant.
        surface_id: Surface being designed.
        session_id: User session that triggered this execution.
        campaign_id: Campaign this execution belongs to.
        candidate_id: ID of the generated candidate.
        iteration: Iteration number within the campaign.
        started_at: UTC timestamp when the pipeline started.
        ended_at: UTC timestamp when the pipeline completed.
        outcome: Final outcome (``"accepted"``, ``"rejected"``, ``"error"``).
        composite_score: Final composite D-O-R-A-V score (0.0-1.0).
        steps: Ordered list of pipeline steps.
        gate_results: Serialized gate outcomes.
        judge_votes: Serialized judge votes.
        total_cost_usd: Total cost for this trajectory.
        total_input_tokens: Total input tokens across all steps.
        total_output_tokens: Total output tokens across all steps.
        error_message: Error message if outcome is ``"error"``.
    """

    trajectory_id: UUID
    tenant_id: str
    project_id: str
    surface_id: UUID
    session_id: str
    campaign_id: str
    candidate_id: UUID
    iteration: int
    started_at: datetime
    ended_at: datetime
    outcome: str
    composite_score: float
    steps: tuple[TrajectoryStep, ...] = ()
    gate_results: dict[str, Any] = field(default_factory=dict)
    judge_votes: dict[str, Any] = field(default_factory=dict)
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    error_message: str | None = None

    @property
    def latency_ms(self) -> float:
        """Wall-clock latency in milliseconds (derived from started_at / ended_at)."""
        return (self.ended_at - self.started_at).total_seconds() * 1000

    def to_bq_row(self) -> dict[str, Any]:
        """Serialize to a row matching the ``trajectory_records`` event schema.

        The table is the generic event schema shared with ``session_events``
        (``session_id, tenant_id, node_name, phase, expert_id, occurred_at,
        payload JSON, embedding FLOAT[]``). The full per-run detail is carried in
        the JSON ``payload``. The previous row used a wide schema (``ts``,
        ``ended_at``, ``steps_json`` ...) the table does not have, so every
        ``insert_rows_json`` failed with "no such field: ts" and no trajectory —
        and therefore no DPO training data — was ever recorded.
        """
        payload = {
            "trajectory_id": str(self.trajectory_id),
            "project_id": self.project_id,
            "surface_id": str(self.surface_id),
            "campaign_id": self.campaign_id,
            "candidate_id": str(self.candidate_id),
            "iteration": self.iteration,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "outcome": self.outcome,
            "composite_score": self.composite_score,
            "steps": [
                {
                    "step_name": s.step_name,
                    "step_index": s.step_index,
                    "started_at": s.started_at.isoformat(),
                    "ended_at": s.ended_at.isoformat(),
                    "model_id": s.model_id,
                    "input_tokens": s.input_tokens,
                    "output_tokens": s.output_tokens,
                    "cost_usd": s.cost_usd,
                }
                for s in self.steps
            ],
            "gate_results": self.gate_results,
            "judge_votes": self.judge_votes,
            "total_cost_usd": self.total_cost_usd,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "latency_ms": self.latency_ms,
            "error_message": self.error_message,
        }
        return {
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "node_name": "pipeline_trajectory",
            "phase": self.outcome,
            "expert_id": str(self.candidate_id),
            "occurred_at": self.started_at.isoformat(),
            "payload": json.dumps(payload),
            "embedding": [],
        }


@dataclass(frozen=True)
class DPOPreferencePair:
    """A preference pair for Direct Preference Optimization (DPO).

    Extracted from trajectory records where two candidates for the same
    surface were scored differently. The higher-scoring candidate becomes
    ``chosen`` and the lower-scoring becomes ``rejected``.

    Attributes:
        pair_id: Unique identifier for this preference pair.
        tenant_id: Multi-tenant isolation key.
        project_id: Project within the tenant.
        surface_id: Surface both candidates target.
        chosen_id: Candidate ID of the preferred (higher-scoring) candidate.
        rejected_id: Candidate ID of the non-preferred candidate.
        chosen_score: Composite score of the chosen candidate.
        rejected_score: Composite score of the rejected candidate.
        margin: Score difference (chosen - rejected).
        judge_axis: Which axis showed the most score difference.
        extracted_at: UTC timestamp when this pair was extracted.
    """

    pair_id: UUID
    tenant_id: str
    project_id: str
    surface_id: UUID
    chosen_id: UUID
    rejected_id: UUID
    chosen_score: float
    rejected_score: float
    margin: float
    judge_axis: str
    extracted_at: datetime

    def to_bq_row(self) -> dict[str, Any]:
        """Serialize to a BigQuery-compatible row dictionary.

        Returns:
            Dictionary matching the ``dpo_preference_pairs`` table schema.
        """
        return {
            "pair_id": str(self.pair_id),
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "surface_id": str(self.surface_id),
            "chosen_id": str(self.chosen_id),
            "rejected_id": str(self.rejected_id),
            "chosen_score": self.chosen_score,
            "rejected_score": self.rejected_score,
            "margin": self.margin,
            "judge_axis": self.judge_axis,
            "extracted_at": self.extracted_at.isoformat(),
        }


def extract_dpo_pairs(
    trajectories: list[TrajectoryRecord],
    *,
    min_margin: float = 0.05,
) -> list[DPOPreferencePair]:
    """Extract DPO preference pairs from trajectory records.

    Groups trajectories by surface_id, then compares all pairs of
    candidates within each group. A pair is emitted only if the score
    margin exceeds ``min_margin`` to avoid noisy training signal.

    Args:
        trajectories: List of trajectory records to analyze.
        min_margin: Minimum composite score difference to emit a pair.

    Returns:
        List of DPO preference pairs suitable for training data.
    """

    # Group by surface_id
    by_surface: dict[UUID, list[TrajectoryRecord]] = {}
    for t in trajectories:
        by_surface.setdefault(t.surface_id, []).append(t)

    pairs: list[DPOPreferencePair] = []
    now = datetime.now(tz=UTC)

    for surface_id, surface_trajectories in by_surface.items():
        # Only consider accepted candidates
        accepted = [t for t in surface_trajectories if t.outcome == "accepted"]
        rejected = [t for t in surface_trajectories if t.outcome == "rejected"]

        # Pair each accepted with each rejected
        for a in accepted:
            for r in rejected:
                margin = a.composite_score - r.composite_score
                if margin >= min_margin:
                    pairs.append(
                        DPOPreferencePair(
                            pair_id=uuid4(),
                            tenant_id=a.tenant_id,
                            project_id=a.project_id,
                            surface_id=surface_id,
                            chosen_id=a.candidate_id,
                            rejected_id=r.candidate_id,
                            chosen_score=a.composite_score,
                            rejected_score=r.composite_score,
                            margin=round(margin, 4),
                            judge_axis="composite",
                            extracted_at=now,
                        )
                    )

    return pairs
