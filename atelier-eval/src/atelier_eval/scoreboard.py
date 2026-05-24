"""Scoreboard — publishes eval results to bench.atelier.dev.

Phase 1 skeleton: formats results as JSON. Real publication (HTTPS POST
to the scoreboard API) and Markdown table rendering land in Phase 2.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atelier_eval.adapters._base import EvalResult


def format_scoreboard_json(
    results: list[EvalResult],
    *,
    benchmark_name: str,
    model_name: str,
) -> str:
    """Format eval results as a scoreboard-compatible JSON string."""
    passed = sum(1 for r in results if r.passed)
    mean_score = sum(r.score for r in results) / len(results) if results else 0.0
    payload = {
        "benchmark": benchmark_name,
        "model": model_name,
        "total_tasks": len(results),
        "passed": passed,
        "pass_rate": passed / len(results) if results else 0.0,
        "mean_score": mean_score,
        "results": [asdict(r) for r in results],
    }
    return json.dumps(payload, indent=2)


def publish_to_scoreboard(
    results: list[EvalResult],
    *,
    benchmark_name: str,
    model_name: str,
    api_url: str = "https://bench.atelier.dev/api/submit",
) -> None:
    """Publish eval results to the scoreboard API (Phase 2 stub).

    Raises:
        NotImplementedError: Always in Phase 1.
    """
    _ = format_scoreboard_json(
        results,
        benchmark_name=benchmark_name,
        model_name=model_name,
    )
    _ = api_url  # will be used in Phase 2
    msg = (
        "Scoreboard publication not yet implemented. "
        f"Use format_scoreboard_json() to preview the payload for {benchmark_name}."
    )
    raise NotImplementedError(msg)
