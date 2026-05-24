"""Design2Code adapter — 484 real-world webpages (CC BY 4.0).

Dataset: https://github.com/SALT-NLP/Design2Code
Paper: arXiv 2403.03163 (Stanford, NAACL 2025)

Metric: visual element recall + layout correctness via rendered screenshot comparison.
Phase 2 use: SSIM between Atelier-generated HTML and Design2Code reference renders
provides an objective DPO reward signal anchored to real production quality.

Data must be downloaded locally before use — no runtime HTTP calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from atelier_eval.adapters._base import EvalResult

DESIGN2CODE_TASK_COUNT: Final[int] = 484


@dataclass(frozen=True, slots=True)
class Design2CodeTask:
    """A single Design2Code benchmark task."""

    task_id: str
    reference_screenshot_path: str  # relative to data_dir
    reference_html_path: str
    description: str


def load_design2code_tasks(data_dir: str | Path) -> list[Design2CodeTask]:
    """Load task manifest from a local Design2Code dataset directory."""
    root = Path(data_dir)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        msg = (
            f"Design2Code manifest not found at {manifest_path}. "
            "Download from https://github.com/SALT-NLP/Design2Code"
        )
        raise FileNotFoundError(msg)
    raw: list[dict[str, str]] = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [
        Design2CodeTask(
            task_id=t["id"],
            reference_screenshot_path=t["screenshot"],
            reference_html_path=t["html"],
            description=t.get("description", ""),
        )
        for t in raw
    ]


def evaluate_design2code_visual_similarity(
    *,
    task: Design2CodeTask,
    generated_html: str,
    data_dir: str | Path,
    ssim_floor: float = 0.60,
) -> EvalResult:
    """Compute SSIM between rendered generated HTML and reference screenshot.

    The SSIM floor of 0.60 is conservative — real production pages vs generated
    output will rarely exceed 0.80 even for high-quality generators. The floor
    is used as a DPO eligibility gate (higher is preferred).

    Requires: atelier_eval.metrics.visual_similarity (pillow + scikit-image).
    """
    from atelier_eval.metrics.visual_similarity import (  # noqa: PLC0415
        compute_ssim,
        render_html_to_screenshot,
    )

    reference_path = Path(data_dir) / task.reference_screenshot_path
    generated_screenshot = render_html_to_screenshot(generated_html)
    ssim_score = compute_ssim(generated_screenshot, str(reference_path))
    return EvalResult(
        task_id=task.task_id,
        passed=ssim_score >= ssim_floor,
        score=ssim_score,
        error=None,
        metadata={"ssim": ssim_score, "ssim_floor": ssim_floor},
    )
