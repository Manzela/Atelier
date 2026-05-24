"""Lighthouse CLI wrapper — runs audits and parses JSON output.

Lighthouse is Google's open-source automated web audit tool (Chrome DevTools).
This wrapper integrates Lighthouse a11y and performance scores into Atelier's
eval pipeline as an objective DPO reward signal.

No published paper has used Lighthouse scores as DPO predicates — this is a
first. The claim: 'Atelier uses Google's own Lighthouse tool as an objective
gate in its DPO reward function.'

Prerequisites: lighthouse CLI installed (``npm install -g lighthouse``).
Chrome/Chromium must be available at the system level.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

LIGHTHOUSE_A11Y_FLOOR: Final[float] = 0.90
LIGHTHOUSE_PERF_FLOOR: Final[float] = 0.90


@dataclass(frozen=True, slots=True)
class LighthouseScores:
    """Parsed Lighthouse category scores."""

    accessibility: float  # 0.0-1.0
    performance: float  # 0.0-1.0
    best_practices: float  # 0.0-1.0
    seo: float  # 0.0-1.0


def run_lighthouse(
    url: str,
    *,
    chrome_flags: str = "--headless",
) -> LighthouseScores:
    """Run Lighthouse against a URL and return the parsed scores.

    Raises:
        RuntimeError: If the lighthouse CLI is not available or exits non-zero.
        ValueError: If the JSON output cannot be parsed.
    """
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        output_path = Path(tmp.name)

    try:
        result = subprocess.run(  # noqa: S603
            [  # noqa: S607
                "lighthouse",
                url,
                "--output=json",
                f"--output-path={output_path}",
                f"--chrome-flags={chrome_flags}",
                "--only-categories=accessibility,performance,best-practices,seo",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode not in (0, 1):
            msg = f"lighthouse exited {result.returncode}: {result.stderr[:500]}"
            raise RuntimeError(msg)

        raw: dict[str, Any] = json.loads(output_path.read_text(encoding="utf-8"))
    finally:
        output_path.unlink(missing_ok=True)

    cats = raw["categories"]
    return LighthouseScores(
        accessibility=float(cats["accessibility"]["score"]),
        performance=float(cats["performance"]["score"]),
        best_practices=float(cats["best-practices"]["score"]),
        seo=float(cats["seo"]["score"]),
    )


def passes_lighthouse_gate(scores: LighthouseScores) -> bool:
    """Return True if both a11y and perf meet the DPO reward floors."""
    return (
        scores.accessibility >= LIGHTHOUSE_A11Y_FLOOR
        and scores.performance >= LIGHTHOUSE_PERF_FLOOR
    )
