"""Generate Bench Observatory data from REAL sources — no fabrication.

Assembles the Bench Observatory's ``data.json`` from three real sources and
nothing else:

  1. Production telemetry — the deployed pipeline's own run records in
     ``atelier-build-2026.atelier_trajectories.trajectory_records``. These are
     event-level rows whose run fields live in a ``payload`` JSON column
     (``composite_score``, ``outcome``, ``candidate_id``, ...). This is the
     authoritative record of what Atelier actually produced in production.
  2. The Atelier-vs-single-shot A/B (``atelier-eval/results/calibration_ab.json``,
     written by ``scripts/eval/run_baseline_ab.py``) — a controlled experiment
     scoring both arms through the identical gate path.
  3. External benchmark context — the WebGen-Bench prompt set
     (``atelier-eval/datasets/webgen_bench_test.jsonl``) and a link to the
     published leaderboard.

There is NO demo/fallback data. If a source is absent the corresponding section
is emitted with an explicit ``status: "no_data"`` (or omitted) so the dashboard
renders an honest empty state — never a fabricated number. Every value the
dashboard shows is traceable to one of the sources above via the ``provenance``
block.

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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SCHEMA_VERSION = "2.0"
CONVERGENCE_BAR = 0.70  # The composite a candidate must reach to converge (R1/AT-005).

# GCP project IDs: 6-30 chars, lowercase alnum + hyphen. Validated before any
# interpolation into a query string (defense-in-depth against injection).
_PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")

_REPO = Path(__file__).resolve().parents[2]
_AB_RESULTS = _REPO / "atelier-eval" / "results" / "calibration_ab.json"
_WEBGEN_PROMPTS = _REPO / "atelier-eval" / "datasets" / "webgen_bench_test.jsonl"


# ---------------------------------------------------------------------------
# 1. Production telemetry (real trajectory_records)
# ---------------------------------------------------------------------------


def _fetch_production_telemetry(project: str) -> dict[str, Any] | None:
    """Aggregate the deployed pipeline's real run records, or None if none.

    Queries the event-level ``trajectory_records`` table, extracting the run
    fields from the ``payload`` JSON. Returns ``None`` (NOT demo data) on any
    failure or when the table is empty — the caller emits an honest empty state.
    """
    if not _PROJECT_ID_RE.match(project):
        logger.warning("Invalid GCP project ID format: %s", project)
        return None
    try:
        from google.api_core.exceptions import GoogleAPICallError  # noqa: PLC0415
        from google.cloud import bigquery  # noqa: PLC0415
    except ImportError:
        logger.warning("BigQuery SDK not installed; production telemetry unavailable.")
        return None

    try:
        client = bigquery.Client(project=project)
    except (OSError, ValueError, GoogleAPICallError):
        logger.warning("Failed to create BigQuery client.")
        return None

    # The run fields are nested in payload JSON; pull them with JSON_VALUE.
    # node_name='pipeline_trajectory' selects run-summary events (not per-node).
    # The only interpolation is `project`, validated by _PROJECT_ID_RE above
    # (a table reference has no value-level injection vector).
    _cols = (
        "session_id, JSON_VALUE(payload,'$.candidate_id') AS candidate_id, "
        "JSON_VALUE(payload,'$.trajectory_id') AS trajectory_id, "
        "JSON_VALUE(payload,'$.outcome') AS outcome, "
        "CAST(JSON_VALUE(payload,'$.composite_score') AS FLOAT64) AS composite_score, "
        "CAST(JSON_VALUE(payload,'$.total_cost_usd') AS FLOAT64) AS total_cost_usd, "
        "CAST(JSON_VALUE(payload,'$.total_input_tokens') AS INT64) AS in_tok, "
        "CAST(JSON_VALUE(payload,'$.total_output_tokens') AS INT64) AS out_tok, occurred_at"
    )
    table = f"`{project}.atelier_trajectories.trajectory_records`"
    query = f"SELECT {_cols} FROM {table} WHERE node_name = 'pipeline_trajectory' ORDER BY occurred_at DESC LIMIT 1000"  # noqa: S608
    try:
        rows = [dict(r) for r in client.query(query).result()]
    except (OSError, ValueError, GoogleAPICallError):
        logger.warning("Failed to query trajectory_records.")
        return None
    if not rows:
        logger.warning("trajectory_records is empty — emitting honest no_data state.")
        return None

    composites = [float(r["composite_score"] or 0.0) for r in rows]
    accepted = [r for r in rows if r["outcome"] == "accepted"]
    runs = sorted({r["session_id"] for r in rows})
    total_tokens = sum(int(r["in_tok"] or 0) + int(r["out_tok"] or 0) for r in rows)
    occurred = [r["occurred_at"] for r in rows if r["occurred_at"] is not None]

    return {
        "runs": len(runs),
        "candidates": len(rows),
        "accepted": len(accepted),
        "acceptance_rate": len(accepted) / len(rows),
        "avg_composite_all": sum(composites) / len(composites),
        "avg_composite_accepted": (
            sum(float(r["composite_score"] or 0.0) for r in accepted) / len(accepted)
            if accepted
            else None
        ),
        "max_composite": max(composites),
        "at_or_above_bar": sum(1 for c in composites if c >= CONVERGENCE_BAR),
        "convergence_bar": CONVERGENCE_BAR,
        "composite_distribution": [round(c, 3) for c in composites],
        "total_cost_usd": sum(float(r["total_cost_usd"] or 0.0) for r in rows),
        "total_tokens": total_tokens,
        "first_run": _iso(min(occurred)) if occurred else None,
        "last_run": _iso(max(occurred)) if occurred else None,
        "recent_runs": [
            {
                "trajectory_id": str(r["trajectory_id"] or "")[:18],
                "session_id": str(r["session_id"])[:18],
                "composite_score": round(float(r["composite_score"] or 0.0), 3),
                "outcome": str(r["outcome"]),
                "timestamp": _iso(r["occurred_at"]),
            }
            for r in rows[:25]
        ],
    }


# ---------------------------------------------------------------------------
# 2. Atelier-vs-single-shot A/B
# ---------------------------------------------------------------------------


def _load_ab_comparison() -> dict[str, Any]:
    """Aggregate the A/B harness output, or a no_data state if absent/empty."""
    if not _AB_RESULTS.exists():
        return {"status": "no_data", "note": "A/B eval has not been run yet."}
    try:
        doc = json.loads(_AB_RESULTS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "no_data", "note": "A/B results unreadable."}
    records = [r for r in doc.get("records", []) if r.get("atelier") and r.get("baseline")]
    if not records:
        return {"status": "no_data", "note": "A/B eval produced no complete records."}

    def _arm_means(arm: str) -> dict[str, Any]:
        gate = [
            r[arm]["mean_gate_score"] for r in records if r[arm].get("mean_gate_score") is not None
        ]
        a11y_pass = [bool("axe" not in (r[arm].get("failed_gates") or [])) for r in records]
        converged = [bool(r[arm].get("converged")) for r in records]
        return {
            "avg_mean_gate_score": round(sum(gate) / len(gate), 1) if gate else None,
            "a11y_pass_rate": round(sum(a11y_pass) / len(a11y_pass), 3) if a11y_pass else None,
            "convergence_rate": round(sum(converged) / len(converged), 3) if converged else None,
        }

    return {
        "status": "complete",
        "n_briefs": len(records),
        "brief_set": "calibration-seed-v0",
        "model": doc.get("model"),
        "generated_at": doc.get("generated_at"),
        "atelier": _arm_means("atelier"),
        "baseline": _arm_means("baseline"),
        "per_brief": [
            {
                "task_id": r["task_id"],
                "category": r.get("category", "general"),
                "reference_score": r.get("reference_score"),
                "atelier": {
                    "composite_score": r["atelier"].get("composite_score"),
                    "converged": r["atelier"].get("converged"),
                    "mean_gate_score": r["atelier"].get("mean_gate_score"),
                    "failed_gates": r["atelier"].get("failed_gates", []),
                },
                "baseline": {
                    "composite_score": r["baseline"].get("composite_score"),
                    "mean_gate_score": r["baseline"].get("mean_gate_score"),
                    "failed_gates": r["baseline"].get("failed_gates", []),
                },
            }
            for r in records
        ],
    }


# ---------------------------------------------------------------------------
# 3. Gate axes (real intents/thresholds) + external benchmark context
# ---------------------------------------------------------------------------


def _gate_axes() -> list[dict[str, str]]:
    """The N3c deterministic gates with their real intent + pass criterion.

    Static, source-grounded descriptions (the gate code is the source of truth)
    — these are explanations, not measurements, so a judge can read what each
    gate enforces and what "good" means for it.
    """
    return [
        {
            "key": "semantic-html",
            "name": "Semantic HTML",
            "intent": "Document is a real, well-formed HTML5 page with landmark elements.",
            "criterion": "Valid <!doctype> + semantic landmarks (header/main/section).",
        },
        {
            "key": "token-fidelity",
            "name": "Design-token fidelity",
            "intent": "Every colour resolves to a declared design token — no raw literals.",
            "criterion": "Zero-tolerance: one undeclared colour literal rejects the candidate.",
        },
        {
            "key": "axe",
            "name": "Accessibility (axe-core)",
            "intent": "No critical/serious accessibility violations (contrast, labels, ARIA).",
            "criterion": "Fail-closed on any axe-core critical/serious impact (WCAG AA aligned).",
        },
        {
            "key": "visual-diff",
            "name": "Visual consistency",
            "intent": "Rendered layout is structurally coherent, not a broken/empty frame.",
            "criterion": "Structure floor + visual regression check.",
        },
    ]


def _external_benchmark() -> dict[str, Any]:
    """WebGen-Bench context: the real prompt set + a link to published results.

    We do NOT assert an official WebGen-Bench score for Atelier (the official
    metric is a test-agent appearance/functionality eval, not implemented here).
    We surface the real prompt set as an external generalization set and link the
    published leaderboard for context. An Atelier slice scored by our OWN gates,
    when run, is labelled as such — never presented as the official metric.
    """
    n_prompts = 0
    if _WEBGEN_PROMPTS.exists():
        n_prompts = sum(
            1 for line in _WEBGEN_PROMPTS.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    return {
        "name": "WebGen-Bench",
        "source": "luzimu/WebGen-Bench (HuggingFace)",
        "paper": "arXiv:2505.03733",
        "n_prompts_available": n_prompts,
        "official_metric": "test-agent appearance/functionality score (not reproduced here)",
        "atelier_slice": {"status": "no_data", "note": "Atelier-gate-scored slice not yet run."},
    }


# ---------------------------------------------------------------------------
# Helpers + assembly
# ---------------------------------------------------------------------------


def _iso(val: Any) -> str:
    if hasattr(val, "isoformat"):
        return str(val.isoformat())
    return "" if val is None else str(val)


def build_payload(project: str) -> dict[str, Any]:
    """Assemble the v2 Bench Observatory payload from real sources only."""
    now = datetime.now(UTC).isoformat()
    telemetry = _fetch_production_telemetry(project)
    ab = _load_ab_comparison()
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now,
        "provenance": {
            "atelier_source": f"BigQuery {project}.atelier_trajectories.trajectory_records",
            "ab_source": "scripts/eval/run_baseline_ab.py (Atelier vs single-shot, identical gate path)",
            "benchmark_source": "luzimu/WebGen-Bench (arXiv:2505.03733)",
            "note": "Every figure traces to one of these sources. No demo or synthetic data.",
        },
        "production_telemetry": telemetry if telemetry is not None else {"status": "no_data"},
        "ab_comparison": ab,
        "gate_axes": _gate_axes(),
        "external_benchmark": _external_benchmark(),
        "targets": {
            "convergence_bar": CONVERGENCE_BAR,
            "accessibility": "WCAG AA (axe-core critical/serious = reject)",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Bench Observatory data from real sources."
    )
    parser.add_argument("--out", required=True, help="Path to write the bench JSON.")
    parser.add_argument("--project", default="atelier-build-2026", help="GCP project ID.")
    args = parser.parse_args()

    payload = build_payload(args.project)

    # Internal consistency check (no schema file dependency): a non-empty
    # production_telemetry must carry the headline aggregates the dashboard reads.
    tel = payload["production_telemetry"]
    if "status" not in tel:
        for key in ("runs", "candidates", "acceptance_rate", "avg_composite_all"):
            if key not in tel:
                logger.error(
                    "Telemetry missing required key %r — aborting (no partial write).", key
                )
                sys.exit(1)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    has_tel = "status" not in tel
    logger.info(
        "Wrote %s (telemetry=%s, ab=%s).",
        args.out,
        f"{tel.get('runs')} runs" if has_tel else "no_data",
        payload["ab_comparison"].get("status"),
    )


if __name__ == "__main__":
    main()
