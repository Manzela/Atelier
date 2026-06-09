"""ScreenSpot adapter — GUI grounding benchmark.

Dataset: https://github.com/nju-websoft/ScreenSpot
Paper: arXiv 2402.16434

Metric: Grounding accuracy (IoU) for UI element localization.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atelier_eval.adapters._base import EvalResult


@dataclass(frozen=True, slots=True)
class ScreenSpotTask:
    """A single ScreenSpot benchmark task."""

    task_id: str
    screenshot_path: str
    instruction: str
    target_bbox: list[float]  # [ymin, xmin, ymax, xmax] normalized


def load_screenspot_tasks(data_dir: str | Path) -> list[ScreenSpotTask]:
    """Load ScreenSpot manifest."""
    root = Path(data_dir)
    manifest_path = root / "screenspot_manifest.json"
    if not manifest_path.exists():
        msg = f"ScreenSpot manifest not found at {manifest_path}."
        raise FileNotFoundError(msg)
    raw: list[dict[str, Any]] = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [
        ScreenSpotTask(
            task_id=str(t["id"]),
            screenshot_path=t["screenshot"],
            instruction=t["instruction"],
            target_bbox=t["bbox"],
        )
        for t in raw
    ]


def evaluate_screenspot_grounding(
    *,
    task: ScreenSpotTask,
    predicted_bbox: list[float],
    iou_threshold: float = 0.5,
) -> EvalResult:
    """Compute IoU between predicted and target bounding boxes."""

    def compute_iou(box1: list[float], box2: list[float]) -> float:
        y1, x1, y2, x2 = box1
        y3, x3, y4, x4 = box2

        inter_ymin = max(y1, y3)
        inter_xmin = max(x1, x3)
        inter_ymax = min(y2, y4)
        inter_xmax = min(x2, x4)

        if inter_ymax < inter_ymin or inter_xmax < inter_xmin:
            return 0.0

        inter_area = (inter_ymax - inter_ymin) * (inter_xmax - inter_xmin)
        area1 = (y2 - y1) * (x2 - x1)
        area2 = (y4 - y3) * (x4 - x3)

        union = area1 + area2 - inter_area
        return 0.0 if union <= 0 else inter_area / float(union)

    iou = compute_iou(task.target_bbox, predicted_bbox)
    return EvalResult(
        task_id=task.task_id,
        passed=iou >= iou_threshold,
        score=iou,
        error=None,
        metadata={"iou": iou, "iou_threshold": iou_threshold, "dataset": "screenspot"},
    )
