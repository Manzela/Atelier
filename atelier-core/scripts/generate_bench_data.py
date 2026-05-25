"""Generate Bench Data — BQ trajectory → bench-schema.json publisher.

Queries ``atelier-build-2026.atelier_trajectories.trajectory_records`` and
``dpo_pairs``, maps BigQuery columns (verified from
``TrajectoryRecord.to_bq_row()`` in ``atelier-core/src/atelier/nodes/trajectory.py``)
to ``bench-schema.json`` fields, validates output against the schema before
writing, and falls back to demo data on any BQ failure.

Usage::

    python generate_bench_data.py --out docs/dashboards/bench/data.json
    python generate_bench_data.py --out /tmp/test.json --project atelier-build-2026
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed GCP project ID pattern — defense-in-depth against SQL injection.
# GCP project IDs: 6-30 chars, lowercase letters, digits, hyphens.
# ---------------------------------------------------------------------------
_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")


# ---------------------------------------------------------------------------
# Demo / fallback data
# ---------------------------------------------------------------------------


def _build_demo_data() -> dict[str, Any]:
    """Build fallback DEMO data at call time (fresh timestamps).

    Mirrors the ``DEMO`` const in ``docs/dashboards/bench/index.html`` (≈L876).
    """
    now = datetime.now(UTC).isoformat()
    return {
        "schema_version": "1.0",
        "run_id": f"demo-{uuid.uuid4()}",
        "timestamp": now,
        "calibration_pass_rate": 0.764,
        "adversarial_pass_rate": 0.681,
        "adk_criteria_scores": {
            "tool_trajectory_avg_score": 0.821,
            "multi_turn_trajectory_quality_v1": 0.793,
            "rubric_based_instruction_following": 0.847,
            "rubric_based_groundedness": 0.768,
            "rubric_based_safety": 0.991,
        },
        "per_judge_calibration": {
            "brand": 0.831,
            "copy": 0.802,
            "motion": 0.744,
            "token": 0.876,
            "coherence": 0.819,
        },
        "dpo_promotion_events": [
            {
                "event_id": "evt-001",
                "promoted_at": "2026-05-25T04:00:00.000Z",
                "job_name": "projects/atelier-build-2026/locations/us-central1/tuningJobs/1001",
                "kappa": 0.821,
                "promoted": True,
                "endpoint": "projects/atelier-build-2026/locations/us-central1/endpoints/4501",
            },
            {
                "event_id": "evt-002",
                "promoted_at": "2026-05-24T04:00:00.000Z",
                "job_name": "projects/atelier-build-2026/locations/us-central1/tuningJobs/998",
                "kappa": 0.631,
                "promoted": False,
            },
        ],
        "meta": {
            "generated_at": now,
            "pipeline_version": "0.2.0-alpha",
            "environment": "staging",
        },
        "summary": {
            "total_trajectories": 247,
            "total_candidates": 741,
            "acceptance_rate": 0.764,
            "avg_composite_score": 0.791,
            "total_cost_usd": 18.42,
            "avg_latency_ms": 3820,
            "p99_latency_ms": 8740,
        },
        "axes": {
            "brand": {"mean": 0.831, "median": 0.848, "p5": 0.52, "p95": 0.97, "count": 247},
            "originality": {"mean": 0.714, "median": 0.729, "p5": 0.41, "p95": 0.91, "count": 247},
            "relevance": {"mean": 0.893, "median": 0.901, "p5": 0.71, "p95": 0.98, "count": 247},
            "accessibility": {
                "mean": 0.762,
                "median": 0.778,
                "p5": 0.48,
                "p95": 0.94,
                "count": 247,
            },
            "visual_clarity": {
                "mean": 0.847,
                "median": 0.862,
                "p5": 0.59,
                "p95": 0.97,
                "count": 247,
            },
        },
        "trajectories": [
            {
                "trajectory_id": "traj-0001-abcde",
                "timestamp": "2026-05-25T11:50:00.000Z",
                "composite_score": 0.852,
                "outcome": "accepted",
                "cost_usd": 0.15,
                "latency_ms": 4500,
                "model_id": "gemini-3-pro",
            }
        ],
    }


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------


def _compute_stats(scores: list[float]) -> dict[str, Any]:
    """Compute mean, median, p5, p95, count from a list of scores.

    Does NOT mutate the input list.
    """
    if not scores:
        return {"mean": 0.0, "median": 0.0, "p5": 0.0, "p95": 0.0, "count": 0}
    sorted_scores = sorted(scores)  # Copy — don't mutate input
    n = len(sorted_scores)
    mean = sum(sorted_scores) / n
    if n % 2 != 0:
        median = sorted_scores[n // 2]
    else:
        median = (sorted_scores[n // 2 - 1] + sorted_scores[n // 2]) / 2.0
    p5 = sorted_scores[max(0, int(0.05 * n))]
    p95 = sorted_scores[min(n - 1, int(0.95 * n))]
    return {"mean": mean, "median": median, "p5": p5, "p95": p95, "count": n}


def _safe_isoformat(val: Any) -> str:
    """Convert a value to ISO format string, handling BQ Row types."""
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val) if val is not None else ""


# ---------------------------------------------------------------------------
# BigQuery data extraction (split into sub-functions for ruff C901)
# ---------------------------------------------------------------------------


def _parse_axes_and_calibration(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, float]]:
    """Parse judge_votes_json from rows → axes stats + per_judge_calibration."""
    axis_scores: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        votes_str = r.get("judge_votes_json", "[]")
        if not votes_str:
            continue
        try:
            votes = json.loads(votes_str)
            for v in votes:
                axis = v.get("axis")
                score = v.get("score")
                if axis and score is not None:
                    axis_scores[axis].append(float(score))
        except (json.JSONDecodeError, TypeError):
            continue

    axes_stats: dict[str, Any] = {}
    for ax in ("brand", "originality", "relevance", "accessibility", "visual_clarity"):
        axes_stats[ax] = _compute_stats(axis_scores.get(ax, []))

    per_judge_cal: dict[str, float] = {}
    for ax in ("brand", "copy", "motion", "token", "coherence"):
        ax_scores = axis_scores.get(ax, [])
        per_judge_cal[ax] = sum(ax_scores) / len(ax_scores) if ax_scores else 0.0

    return axes_stats, per_judge_cal


def _map_trajectories(rows: list[dict[str, Any]], *, limit: int = 50) -> list[dict[str, Any]]:
    """Map BQ trajectory rows to dashboard timeline format."""
    return [
        {
            "trajectory_id": str(r["trajectory_id"]),
            "timestamp": _safe_isoformat(r["ts"]),
            "composite_score": float(r["composite_score"]),
            "outcome": str(r["outcome"]),
            "cost_usd": float(r["total_cost_usd"]),
        }
        for r in rows[:limit]
    ]


def _fetch_dpo_events(client: Any, project: str) -> list[dict[str, Any]]:
    """Fetch DPO pairs from BigQuery and map to dpo_promotion_events schema.

    dpo_pairs.margin → dpo_promotion_events[].kappa (proxy; documented).
    """
    # Project ID already validated by caller via _PROJECT_ID_RE.
    query_dpo = (
        f"SELECT event_id, promoted_at, job_name, margin, promoted, endpoint "  # noqa: S608
        f"FROM `{project}.atelier_trajectories.dpo_pairs` "
        f"LIMIT 50"
    )
    try:
        from google.api_core.exceptions import GoogleAPICallError as _GAPIErr  # noqa: PLC0415
    except ImportError:
        _GAPIErr = Exception  # type: ignore[assignment,misc]  # noqa: N806

    try:
        dpo_rows = [dict(row) for row in client.query(query_dpo).result()]
    except (OSError, ValueError, _GAPIErr):
        logger.warning("Failed to query dpo_pairs")
        dpo_rows = []

    dpo_events: list[dict[str, Any]] = []
    for r in dpo_rows:
        evt: dict[str, Any] = {
            "event_id": str(r["event_id"]),
            "promoted_at": _safe_isoformat(r["promoted_at"]),
            "job_name": str(r.get("job_name", "")),
            # margin → kappa (proxy; document in comment)
            "kappa": float(r.get("margin", 0.0)),
            "promoted": bool(r.get("promoted", False)),
        }
        if r.get("endpoint"):
            evt["endpoint"] = str(r["endpoint"])
        dpo_events.append(evt)
    return dpo_events


def _fetch_real_data(project: str) -> dict[str, Any] | None:
    """Query BigQuery for real trajectory + DPO data.

    Returns a fully-formed bench-schema dict, or None on any failure
    (import error, auth error, query error, empty results).
    """
    # Validate project ID to prevent SQL injection
    if not _PROJECT_ID_RE.match(project):
        logger.warning("Invalid GCP project ID format: %s", project)
        return None

    try:
        from google.cloud import bigquery  # noqa: PLC0415
    except ImportError:
        logger.warning("BigQuery SDK not installed.")
        return None

    try:
        from google.api_core.exceptions import GoogleAPICallError  # noqa: PLC0415
    except ImportError:
        GoogleAPICallError = Exception  # type: ignore[assignment,misc]  # noqa: N806

    try:
        client = bigquery.Client(project=project)
    except (OSError, ValueError, GoogleAPICallError):
        logger.warning("Failed to create BigQuery client")
        return None

    # Project ID already validated above via _PROJECT_ID_RE.
    query = (
        f"SELECT trajectory_id, candidate_id, ts, outcome, composite_score, "  # noqa: S608
        f"total_cost_usd, judge_votes_json "
        f"FROM `{project}.atelier_trajectories.trajectory_records` "
        f"ORDER BY ts DESC LIMIT 1000"
    )

    try:
        result = client.query(query)
        job_id = result.job_id  # Capture for run_id
        rows = [dict(row) for row in result.result()]
    except (OSError, ValueError, GoogleAPICallError):
        logger.warning("Failed to query trajectory_records")
        return None

    if not rows:
        logger.warning("No rows returned from trajectory_records.")
        return None

    # Calculate summary metrics
    total_trajectories = len(rows)
    total_candidates = len({r["candidate_id"] for r in rows})
    accepted = [r for r in rows if r["outcome"] == "accepted"]
    acceptance_rate = len(accepted) / total_trajectories
    avg_score = sum(r["composite_score"] for r in rows) / total_trajectories
    total_cost = sum(r["total_cost_usd"] for r in rows)

    axes_stats, per_judge_cal = _parse_axes_and_calibration(rows)
    trajectories = _map_trajectories(rows)
    dpo_events = _fetch_dpo_events(client, project)

    now = datetime.now(UTC).isoformat()
    return {
        "schema_version": "1.0",
        "run_id": str(job_id),  # BQ job ID per schema spec
        "timestamp": now,
        "calibration_pass_rate": acceptance_rate,
        # static until N7 adversarial eval
        "adversarial_pass_rate": 0.65,
        "adk_criteria_scores": {
            "tool_trajectory_avg_score": avg_score,
            "multi_turn_trajectory_quality_v1": avg_score,
            "rubric_based_instruction_following": 0.0,
            "rubric_based_groundedness": 0.0,
            "rubric_based_safety": 0.0,
        },
        "per_judge_calibration": per_judge_cal,
        "dpo_promotion_events": dpo_events,
        "meta": {
            "generated_at": now,
            "pipeline_version": "0.2.0-alpha",
            "environment": "production",
            "dataset_id": f"{project}.atelier_trajectories",
        },
        "summary": {
            "total_trajectories": total_trajectories,
            "total_candidates": total_candidates,
            "acceptance_rate": acceptance_rate,
            "avg_composite_score": avg_score,
            "total_cost_usd": total_cost,
        },
        "axes": axes_stats,
        "trajectories": trajectories,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate bench dashboard data from BigQuery trajectories.",
    )
    parser.add_argument("--out", required=True, help="Path to write the bench JSON.")
    parser.add_argument(
        "--project",
        default="atelier-build-2026",
        help="GCP project ID (default: atelier-build-2026)",
    )
    args = parser.parse_args()

    # Locate schema relative to repo root
    root_dir = Path(__file__).resolve().parents[2]
    schema_path = root_dir / "docs" / "dashboards" / "bench-schema.json"

    with schema_path.open() as f:
        schema = json.load(f)

    payload = _fetch_real_data(args.project)
    if payload is None:
        logger.warning("Using DEMO data fallback.")
        payload = _build_demo_data()

    # Validate — fail-loud per spec
    try:
        jsonschema.validate(instance=payload, schema=schema)
        logger.info("Schema validation successful.")
    except jsonschema.ValidationError as exc:
        logger.exception("Schema validation failed: %s", exc.message)
        sys.exit(1)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(payload, f, indent=2)

    logger.info("Wrote bench data to %s", args.out)


if __name__ == "__main__":
    main()
