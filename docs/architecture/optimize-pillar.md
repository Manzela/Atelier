# Optimize Pillar — Observe → Simulate → Verify

> How Atelier continuously improves design quality through the DPO flywheel.

## Overview

The **Optimize** pillar implements a closed-loop learning system that transforms every design generation into training signal. Rather than relying on static model weights, Atelier uses **Direct Preference Optimization (DPO)** to continuously fine-tune its generative models based on real judge evaluations.

The loop follows three phases:

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ OBSERVE  │ ──► │ SIMULATE │ ──► │  VERIFY  │
│          │     │          │     │          │
│ Record   │     │ Extract  │     │ Evaluate │
│ outcomes │     │ DPO      │     │ against  │
│ + votes  │     │ pairs    │     │ baseline │
└──────────┘     └──────────┘     └──────────┘
      ▲                                │
      └────────────────────────────────┘
              Fine-tuned model
```

## Phase 1: Observe — Trajectory Recording

Every pipeline execution produces a `TrajectoryRecord` — a structured log of what happened, what judges scored, and whether the candidate was accepted or rejected.

```python
# From atelier-core/src/atelier/nodes/trajectory.py

@dataclass(frozen=True)
class TrajectoryRecord:
    trajectory_id: UUID
    surface_id: UUID
    outcome: str              # "accepted" | "rejected" | "error"
    composite_score: float    # 0.0–1.0 D-O-R-A-V composite
    judge_votes: dict         # Per-axis scores from all judges
    total_cost_usd: float
    # ... (19 fields total, stored in BigQuery)

    def to_bq_row(self) -> dict:
        """Serialize to BigQuery trajectory_records table."""
        ...
```

Records are streamed to BigQuery (`atelier_trajectories.trajectory_records`) in real-time. Each record includes:

- **Composite score** — the Bayesian consensus across all judge axes
- **Judge votes** — individual scores per axis (brand, originality, relevance, accessibility, visual clarity, copy, motion, token, coherence)
- **Cost and token usage** — for budget optimization
- **Timing** — `started_at`/`ended_at` for latency tracking

## Phase 2: Simulate — DPO Pair Extraction

The DPO builder scans trajectory records for **preference pairs** — cases where two candidates for the **same surface** received different outcomes.

```python
# From atelier-core/src/atelier/nodes/trajectory.py

def extract_dpo_pairs(
    records: list[TrajectoryRecord],
    *,
    min_margin: float = 0.05,
) -> list[DPOPreferencePair]:
    """Extract DPO training pairs from trajectory records.

    A valid pair requires:
    - Same surface_id (same design brief)
    - Different candidates
    - One accepted (chosen), one rejected
    - Score margin >= min_margin (avoids near-ties)
    """
```

The extracted pairs form the training dataset:

| Field         | Source                                              |
| ------------- | --------------------------------------------------- |
| `chosen_id`   | Accepted candidate's `trajectory_id`                |
| `rejected_id` | Rejected candidate's `trajectory_id`                |
| `margin`      | `chosen.composite_score - rejected.composite_score` |
| `surface_id`  | Shared design brief identifier                      |

## Phase 3: Verify — Calibration Dashboard

The [Bench Dashboard](https://atelier.autonomous-agent.dev/bench/) visualizes the flywheel's health:

- **Calibration pass rate** — % of trajectories meeting quality thresholds
- **Per-judge calibration** — agreement across the 9 evaluation axes
- **DPO promotion events** — which fine-tuning jobs produced models that beat the baseline (κ > 0.7)
- **Trajectory timeline** — real-time feed of generation outcomes

The `generate_bench_data.py` script queries BigQuery and publishes validated JSON to the dashboard nightly.

## Data Flow

```
Pipeline Execution
       │
       ▼
TrajectoryRecord.to_bq_row()
       │
       ▼
BigQuery: trajectory_records
       │
       ├──► extract_dpo_pairs() ──► DPO Training
       │                                │
       │                                ▼
       │                        Fine-tuned Model
       │                                │
       └──► generate_bench_data.py      │
                    │                   │
                    ▼                   │
            Bench Dashboard             │
                    │                   │
                    └──► Verify ◄───────┘
```

## Key Metrics

| Metric                | Target                        | Source                         |
| --------------------- | ----------------------------- | ------------------------------ |
| Calibration pass rate | ≥ 76%                         | `summary.acceptance_rate`      |
| DPO pair yield        | ≥ 3 pairs per 30 trajectories | `extract_dpo_pairs()`          |
| Judge axis agreement  | κ ≥ 0.7 per axis              | `per_judge_calibration`        |
| Model promotion gate  | κ ≥ 0.7                       | `dpo_promotion_events[].kappa` |

## Related Files

- [`trajectory.py`](../../atelier-core/src/atelier/nodes/trajectory.py) — TrajectoryRecord + DPO pair extraction + BQ serialization
- [`generate_bench_data.py`](../../atelier-core/scripts/generate_bench_data.py) — BQ → dashboard publisher
- [`bench-schema.json`](../dashboards/bench-schema.json) — Dashboard data contract
