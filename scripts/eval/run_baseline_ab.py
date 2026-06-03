"""Atelier-vs-single-shot baseline A/B eval (real Vertex, real gates/judges).

Runs each calibration brief through TWO arms scored by the IDENTICAL N3c gate +
N3d D-O-R-A-V consensus path, so the comparison is apples-to-apples:

  * Atelier arm   — the full DDLC multi-agent pipeline with the N3c gates, N3d
    consensus, N4 selection, and the bounded fixer loop (``AtelierRunner.run``).
  * Baseline arm  — a single-shot LLM call (same model, one pass, no gates, no
    consensus, no fixer loop) whose HTML is scored through the SAME
    ``_run_n3c_n3d_n4`` path the Atelier arm uses.

This isolates the contribution of Atelier's gate-first multi-agent architecture
over a naive single-shot generation. Output is a JSON document consumed by the
Bench Observatory; every number is a real, reproducible measurement (no demo
data). Each brief carries a published ``reference_score`` used as the per-task
"what good looks like" target.

Usage::

    python scripts/eval/run_baseline_ab.py --limit 5 --out /tmp/ab.json

Requires: ADC for Vertex (project atelier-build-2026), a launchable chromium
(the a11y gate), and the atelier-core package importable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("baseline_ab")

# Repo paths
_REPO = Path(__file__).resolve().parents[2]
_CAL_SEED = _REPO / "atelier-eval" / "datasets" / "calibration-seed-v0.jsonl"

# The served model (mirrors resolve_model_id() / AT-024) for the baseline arm.
_BASELINE_MODEL = "gemini-2.5-pro"
_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "atelier-build-2026")
_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")

# Route google-genai / ADK through Vertex AI (ADC), not Google AI Studio. The
# Atelier arm's ADK LlmAgents read these; without GOOGLE_GENAI_USE_VERTEXAI the
# client defaults to AI Studio and every model call fails with "No API key was
# provided" (mirrors atelier-deploy/terraform/main.tf, which sets the same vars
# on Cloud Run). Set before any google-genai import-time client construction.
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", _PROJECT)
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", _LOCATION)
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")

_BASELINE_SYSTEM = (
    "You are an expert front-end web designer. Generate a single, complete, "
    "production-ready, accessible HTML document (semantic HTML5 with inline "
    "<style> CSS, WCAG AA contrast, ARIA labels on interactive elements, and "
    "CSS custom-property design tokens). Output ONLY the HTML document, starting "
    "at <!DOCTYPE html>. No markdown fences, no commentary."
)


def _load_briefs(limit: int) -> list[dict[str, Any]]:
    """Load up to ``limit`` calibration briefs (with their reference_score)."""
    briefs: list[dict[str, Any]] = []
    with _CAL_SEED.open(encoding="utf-8") as fh:
        for raw_line in fh:
            stripped = raw_line.strip()
            if stripped:
                briefs.append(json.loads(stripped))
    return briefs[:limit]


def _single_shot_html(brief_text: str) -> tuple[str, int, int]:
    """Generate one HTML candidate with a single LLM pass (the baseline arm).

    Returns ``(html, input_tokens, output_tokens)``. No gates, no consensus, no
    fixer loop — exactly one model call, the naive baseline.
    """
    from google import genai  # noqa: PLC0415
    from google.genai import types  # noqa: PLC0415

    client = genai.Client(vertexai=True, project=_PROJECT, location=_LOCATION)
    resp = client.models.generate_content(
        model=_BASELINE_MODEL,
        contents=f"{_BASELINE_SYSTEM}\n\nBRIEF:\n{brief_text}",
        config=types.GenerateContentConfig(max_output_tokens=32768, temperature=0.7),
    )
    html = resp.text or ""
    usage = resp.usage_metadata
    in_tok = getattr(usage, "prompt_token_count", 0) or 0
    out_tok = getattr(usage, "candidates_token_count", 0) or 0
    return html, in_tok, out_tok


def _baseline_gate_summary(all_gate_results: list[Any]) -> dict[str, Any]:
    """Failed gate axes + mean 0-100 gate score for the single baseline candidate.

    Makes the comparison legible: a single-shot page can earn a high mean gate
    score yet still score 0.0 composite because it fails one binary gate (e.g.
    the axe-core a11y gate). Surfacing *which* gate it fails is the most
    informative part of the Atelier-vs-baseline story.
    """
    from atelier.models.enums import GateDecision  # noqa: PLC0415

    if not all_gate_results:
        return {"failed_axes": [], "mean_gate_score": None}
    gr = all_gate_results[0]
    failed = [o.axis.value for o in gr.outcomes if o.decision != GateDecision.PASS]
    scores = [float(o.score) for o in gr.outcomes if o.score is not None]
    return {
        "failed_axes": failed,
        "mean_gate_score": round(sum(scores) / len(scores), 1) if scores else None,
    }


def _atelier_gate_summary(gate_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Best candidate's mean 0-100 gate score + failed axes, from serialized gates.

    The Atelier arm's binary composite can be 0.0 (a single hard gate — usually
    the axe a11y gate — rejects every candidate), yet the design itself is strong
    on the continuous gate scale. Surfacing the best candidate's mean gate score
    makes the Atelier-vs-baseline comparison fair on the same continuous axis the
    baseline reports, independent of the binary convergence outcome.
    """
    best: dict[str, Any] | None = None
    for gr in gate_results or []:
        outs = gr.get("outcomes", [])
        scores = [o["score"] for o in outs if o.get("score") is not None]
        if not scores:
            continue
        mean = sum(scores) / len(scores)
        if best is None or mean > best["mean_gate_score"]:
            best = {
                "mean_gate_score": round(mean, 1),
                "failed_gates": [o["axis"] for o in outs if not o.get("passed")],
            }
    return best or {"mean_gate_score": None, "failed_gates": []}


def _best_axes(scored_candidates: list[dict[str, Any]]) -> dict[str, float]:
    """Per-axis D-O-R-A-V scores of the highest-composite scored candidate.

    Both arms emit identically-shaped ``scored_candidates`` entries
    (``{composite_score, votes: {axis: {score}}}``), so this works for either.
    """
    if not scored_candidates:
        return {}
    best = max(scored_candidates, key=lambda c: c.get("composite_score", 0.0))
    return {axis: float(v.get("score", 0.0)) for axis, v in best.get("votes", {}).items()}


async def _run_one(brief: dict[str, Any]) -> dict[str, Any]:
    """Run both arms for one brief; return the per-brief comparison record."""
    from atelier.models.data_contracts import TenantContext  # noqa: PLC0415
    from atelier.orchestrator.runner import AtelierRunner  # noqa: PLC0415

    task_id = brief["task_id"]
    brief_text = brief["brief"]
    reference_score = float(brief.get("reference_score", 0.0))
    # Distinct user per brief so the per-user lifetime token cap never accrues
    # across the slice (each eval brief is an independent measurement).
    tenant_ctx = TenantContext(
        tenant_id="atelier-eval",
        user_id=f"eval-{task_id}-{uuid4().hex[:8]}",
        project_id=_PROJECT,
    )

    record: dict[str, Any] = {
        "task_id": task_id,
        "category": brief.get("category", "general"),
        "reference_score": reference_score,
        "min_composite_score": float(
            brief.get("quality_criteria", {}).get("min_composite_score", 0.70)
        ),
    }

    # --- Atelier arm (full pipeline) ---
    t0 = time.perf_counter()
    try:
        runner = AtelierRunner()
        result = await runner.run(brief_text, tenant_ctx)
        gate_summary = _atelier_gate_summary(result.get("gate_results", []))
        record["atelier"] = {
            "composite_score": float(result.get("composite_score", 0.0)),
            "converged": bool(result.get("converged", False)),
            "candidates_evaluated": int(result.get("candidates_evaluated", 0)),
            "candidates_passed_gates": int(result.get("candidates_passed_gates", 0)),
            "exit_reason": result.get("exit_reason"),
            "mean_gate_score": gate_summary["mean_gate_score"],
            "failed_gates": gate_summary["failed_gates"],
            "axes": _best_axes(result.get("scored_candidates", [])),
            "latency_s": round(time.perf_counter() - t0, 1),
            "error": None,
        }
    except Exception as exc:
        logger.exception("Atelier arm failed for %s", task_id)
        record["atelier"] = {
            "error": f"{type(exc).__name__}: {exc}"[:300],
            "latency_s": round(time.perf_counter() - t0, 1),
        }

    # --- Baseline arm (single-shot, scored by the SAME gates/judges) ---
    t1 = time.perf_counter()
    try:
        html, _in, _out = _single_shot_html(brief_text)
        scoring = AtelierRunner()._run_n3c_n3d_n4([html], brief_text, iteration=0)
        gate_summary = _baseline_gate_summary(scoring.get("all_gate_results", []))
        record["baseline"] = {
            "composite_score": float(scoring.get("composite_score", 0.0)),
            "converged": bool(scoring.get("converged", False)),
            "candidates_passed_gates": int(scoring.get("candidates_passed_gates", 0)),
            "axes": _best_axes(scoring.get("scored_candidates", [])),
            "failed_gates": gate_summary["failed_axes"],
            "mean_gate_score": gate_summary["mean_gate_score"],
            "html_bytes": len(html),
            "latency_s": round(time.perf_counter() - t1, 1),
            "error": None,
        }
    except Exception as exc:
        logger.exception("Baseline arm failed for %s", task_id)
        record["baseline"] = {
            "error": f"{type(exc).__name__}: {exc}"[:300],
            "latency_s": round(time.perf_counter() - t1, 1),
        }

    a = record.get("atelier", {}).get("composite_score")
    b = record.get("baseline", {}).get("composite_score")
    logger.info("[%s] Atelier=%s  Baseline=%s  ref=%.2f", task_id, a, b, reference_score)
    return record


async def _main_async(limit: int, out_path: Path) -> None:
    briefs = _load_briefs(limit)
    logger.info("Loaded %d briefs from %s", len(briefs), _CAL_SEED.name)
    records: list[dict[str, Any]] = []
    for i, brief in enumerate(briefs, 1):
        logger.info("=== Brief %d/%d: %s ===", i, len(briefs), brief["task_id"])
        records.append(await _run_one(brief))
        # Checkpoint after every brief so a late failure never loses earlier work.
        _write(out_path, records)
    logger.info("Done. %d records → %s", len(records), out_path)


def _write(out_path: Path, records: list[dict[str, Any]]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "model": _BASELINE_MODEL,
                "records": records,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Atelier-vs-baseline A/B eval.")
    parser.add_argument("--limit", type=int, default=5, help="Number of briefs to run.")
    parser.add_argument(
        "--out",
        default="atelier-eval/results/calibration_ab.json",
        help="Output JSON path.",
    )
    args = parser.parse_args()
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", _PROJECT)
    try:
        asyncio.run(_main_async(args.limit, Path(args.out)))
    except KeyboardInterrupt:
        logger.warning("Interrupted; partial results were checkpointed.")
        sys.exit(130)


if __name__ == "__main__":
    main()
