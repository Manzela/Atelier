"""DPO dataset builder — offline batch path that produces preference pairs from
recorded trajectory records.

This is the POST-FLIGHT / batch builder: it consumes ``TrajectoryRecord`` rows
(the DPO flywheel tiers in PRD §6.6 / models.data_contracts.TrajectoryRecord) and
emits JSONL preference pairs for a tuning job. It is the documented consumer of
``TrajectoryRecord`` and is exercised by tests; it is intentionally NOT on the
per-request hot path.

It is deliberately distinct from the mid-flight miner
(``optimize.dreaming_module.extract_pairs_midflight``), which runs synchronously
inside a single ``/v1/generate`` request and selects the best candidate against
each rejected candidate by relative margin. This builder instead groups recorded
candidates at a shared decision point and applies ABSOLUTE quality tiers — a
``chosen`` floor (T2) and a ``rejected`` ceiling (T3) — because over the batched
corpus the absolute composite_score is meaningful, unlike a single request where
only the relative ordering is. Both surfaces share the same minimum-margin floor
(``MIN_MARGIN``), single-sourced from ``reward.composite.EXTRINSIC_MARGIN_FLOOR``,
so the two paths cannot silently diverge on the noise floor.

G10 fix: compares DIFFERENT candidates evaluated at the same (surface_id, node_name, iteration)
decision point. Does NOT compare consecutive iterations of the same candidate.

Output format: JSONL, one JSON object per line:
{
  "prompt": "...",       # the shared prompt for this decision point
  "chosen": "...",       # candidate with composite_score >= T2_THRESHOLD
  "rejected": "...",     # candidate with composite_score < T3_THRESHOLD
  "margin": 0.23,        # chosen.score - rejected.score (always >= MIN_MARGIN)
  "metadata": {
    "surface_id": "...",
    "node_name": "...",
    "iteration": 0,
    "chosen_score": 0.82,
    "rejected_score": 0.59
  }
}
"""

from typing import Any, Final

from atelier.nodes.trajectory import TrajectoryRecord
from atelier.reward.composite import EXTRINSIC_MARGIN_FLOOR

T2_THRESHOLD: Final[float] = 0.70  # chosen floor
T3_THRESHOLD: Final[float] = 0.50  # rejected ceiling
# Single-sourced from the AND-gate floor so every DPO surface agrees on the
# minimum chosen/rejected score gap (mid-flight, this builder, offline gate).
MIN_MARGIN: Final[float] = EXTRINSIC_MARGIN_FLOOR  # minimum score gap to be a valid pair


def prepare_dpo_dataset(records: list[TrajectoryRecord]) -> list[dict[str, Any]]:
    """Group records by decision point, extract preference pairs, return JSONL-ready dicts."""

    groups: dict[tuple[str, str, int], list[TrajectoryRecord]] = {}
    for r in records:
        node_name = r.steps[0].step_name if r.steps else "unknown"
        key = (str(r.surface_id), node_name, r.iteration)
        groups.setdefault(key, []).append(r)

    results = []

    for (surface_id, node_name, iteration), group_records in groups.items():
        chosen_candidates = [r for r in group_records if r.composite_score >= T2_THRESHOLD]
        rejected_candidates = [r for r in group_records if r.composite_score < T3_THRESHOLD]

        if not chosen_candidates or not rejected_candidates:
            continue

        best_chosen = max(chosen_candidates, key=lambda r: r.composite_score)
        worst_rejected = min(rejected_candidates, key=lambda r: r.composite_score)

        margin = best_chosen.composite_score - worst_rejected.composite_score
        if margin < MIN_MARGIN:
            continue

        if best_chosen.candidate_id == worst_rejected.candidate_id:
            continue

        # M-6: Guard against empty steps — would produce empty-string DPO pairs
        # that poison the tuning dataset.
        if not best_chosen.steps or not worst_rejected.steps:
            continue

        prompt = best_chosen.steps[0].input_summary if best_chosen.steps else ""
        chosen_response = best_chosen.steps[-1].output_summary if best_chosen.steps else ""
        rejected_response = worst_rejected.steps[-1].output_summary if worst_rejected.steps else ""

        results.append(
            {
                "prompt": prompt,
                "chosen": chosen_response,
                "rejected": rejected_response,
                "margin": round(margin, 4),
                "metadata": {
                    "surface_id": surface_id,
                    "node_name": node_name,
                    "iteration": iteration,
                    "chosen_score": best_chosen.composite_score,
                    "rejected_score": worst_rejected.composite_score,
                },
            }
        )

    return results
