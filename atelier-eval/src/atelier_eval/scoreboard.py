"""Scoreboard — publishes eval results to atelier.autonomous-agent.dev/bench.

Formats results as a scoreboard-compatible JSON payload and submits via
HTTPS POST to the canonical bench endpoint.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from atelier_eval.adapters._base import EvalResult

# Canonical Atelier bench endpoint — no *.atelier.dev aliases.
_DEFAULT_API_URL: str = "https://atelier.autonomous-agent.dev/bench/api/submit"


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
    api_url: str = _DEFAULT_API_URL,
) -> None:
    """Publish eval results to the scoreboard API.

    Submits a JSON payload via HTTP POST to ``api_url`` (defaults to the
    canonical bench endpoint).  Raises ``urllib.error.URLError`` on network
    failure so callers can decide whether to retry.

    Args:
        results: Eval results to publish.
        benchmark_name: Name of the benchmark (e.g. ``"design2code"``).
        model_name: Name/version of the model under evaluation.
        api_url: Scoreboard API endpoint.  Override in tests or staging.
    """
    body = format_scoreboard_json(
        results,
        benchmark_name=benchmark_name,
        model_name=model_name,
    )
    data = body.encode("utf-8")
    # api_url is an operator-configured endpoint; require https so a misconfigured
    # value cannot resolve to a file:// (local read) or plaintext scheme.
    if not api_url.startswith("https://"):
        msg = f"publish_to_scoreboard requires an https:// api_url, got: {api_url!r}"
        raise ValueError(msg)
    req = urllib.request.Request(  # noqa: S310
        api_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected -- api_url is operator-configured and https-guarded above; not attacker-reachable.
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        if resp.status not in {200, 201, 202}:
            msg = f"Scoreboard API returned HTTP {resp.status} for {benchmark_name}."
            raise RuntimeError(msg)
