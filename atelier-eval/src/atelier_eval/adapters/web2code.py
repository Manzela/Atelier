"""Web2Code adapter — 1,198 real-world website screenshots (NeurIPS 2024).

Dataset: https://github.com/zekun-li/Web2Code
Paper: arXiv 2406.20098 (NeurIPS 2024)

Metric: Visual similarity (SSIM) between rendered HTML and original screenshot.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from atelier_eval.adapters._base import EvalResult

WEB2CODE_TASK_COUNT: Final[int] = 1198


@dataclass(frozen=True, slots=True)
class Web2CodeTask:
    """A single Web2Code benchmark task."""

    task_id: str
    screenshot_path: str  # relative to data_dir
    html_path: str
    website_url: str


def load_web2code_tasks(data_dir: str | Path) -> list[Web2CodeTask]:
    """Load task manifest from a local Web2Code dataset directory."""
    root = Path(data_dir)
    manifest_path = root / "web2code_manifest.json"
    if not manifest_path.exists():
        msg = (
            f"Web2Code manifest not found at {manifest_path}. "
            "Download from https://github.com/zekun-li/Web2Code"
        )
        raise FileNotFoundError(msg)
    raw: list[dict[str, Any]] = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [
        Web2CodeTask(
            task_id=t["id"],
            screenshot_path=t["screenshot"],
            html_path=t["html"],
            website_url=t.get("url", ""),
        )
        for t in raw
    ]


def evaluate_web2code_visual_similarity(
    *,
    task: Web2CodeTask,
    generated_html: str,
    data_dir: str | Path,
    ssim_floor: float = 0.65,
) -> EvalResult:
    """Compute SSIM between rendered generated HTML and reference screenshot.

    Web2Code tasks are often complex; a 0.65 floor reflects production-grade
    visual convergence requirements.
    """
    from atelier_eval.metrics.visual_similarity import (  # noqa: PLC0415
        compute_ssim,
        render_html_to_screenshot,
    )

    reference_path = Path(data_dir) / task.screenshot_path
    generated_screenshot = render_html_to_screenshot(generated_html)
    ssim_score = compute_ssim(generated_screenshot, str(reference_path))
    return EvalResult(
        task_id=task.task_id,
        passed=ssim_score >= ssim_floor,
        score=ssim_score,
        error=None,
        metadata={"ssim": ssim_score, "ssim_floor": ssim_floor, "dataset": "web2code"},
    )
