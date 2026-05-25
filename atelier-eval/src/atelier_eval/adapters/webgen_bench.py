"""WebGen-Bench adapter — 101 web generation tasks.

Dataset: https://huggingface.co/datasets/WebGen-Bench/WebGen-Bench
Paper: arXiv 2505.XXXXX (benchmark for autonomous web generation agents)

This adapter loads the 101 WebGen-Bench tasks from a local data directory
and evaluates generated HTML/CSS/JS output against reference screenshots
using SSIM and Lighthouse scores.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from atelier_eval.adapters._base import EvalResult

WEBGEN_BENCH_TASK_COUNT: Final[int] = 101


@dataclass(frozen=True, slots=True)
class WebGenBenchTask:
    """A single WebGen-Bench task."""

    task_id: str
    prompt: str
    reference_path: str  # relative to data_dir
    category: str


def load_webgen_bench_tasks(data_dir: str | Path) -> list[WebGenBenchTask]:
    """Load WebGen-Bench tasks from a local directory.

    Raises:
        FileNotFoundError: if the data directory doesn't exist.
    """
    import json  # noqa: PLC0415

    root = Path(data_dir)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        msg = (
            f"WebGen-Bench manifest not found at {manifest_path}. "
            "Download from https://huggingface.co/datasets/WebGen-Bench/WebGen-Bench"
        )
        raise FileNotFoundError(msg)
    raw: list[dict[str, str]] = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [
        WebGenBenchTask(
            task_id=t["id"],
            prompt=t["prompt"],
            reference_path=t.get("reference", ""),
            category=t.get("category", "general"),
        )
        for t in raw
    ]


def evaluate_webgen_bench(
    *,
    task: WebGenBenchTask,
    generated_html: str,
    data_dir: str | Path,
    ssim_floor: float = 0.50,
) -> EvalResult:
    """Evaluate a WebGen-Bench task by visual similarity to reference.

    Requires: atelier_eval.metrics.visual_similarity.
    """
    from atelier_eval.metrics.visual_similarity import (  # noqa: PLC0415
        compute_ssim,
        render_html_to_screenshot,
    )

    reference_path = Path(data_dir) / task.reference_path
    generated_screenshot = render_html_to_screenshot(generated_html)
    ssim_score = compute_ssim(generated_screenshot, str(reference_path))
    return EvalResult(
        task_id=task.task_id,
        passed=ssim_score >= ssim_floor,
        score=ssim_score,
        error=None,
        metadata={"ssim": ssim_score, "ssim_floor": ssim_floor, "category": task.category},
    )
