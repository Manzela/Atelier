"""Tests for the ScreenSpot grounding adapter IoU scoring.

Covers the degenerate (zero-area) bounding box that previously raised
ZeroDivisionError in the IoU union denominator.
"""

from __future__ import annotations

from atelier_eval.adapters.screenspot import (
    ScreenSpotTask,
    evaluate_screenspot_grounding,
)


def _task(bbox: list[float]) -> ScreenSpotTask:
    return ScreenSpotTask(
        task_id="t1",
        screenshot_path="screen.png",
        instruction="click the button",
        target_bbox=bbox,
    )


def test_identical_boxes_pass() -> None:
    result = evaluate_screenspot_grounding(
        task=_task([0.0, 0.0, 10.0, 10.0]),
        predicted_bbox=[0.0, 0.0, 10.0, 10.0],
    )
    assert result.passed is True


def test_disjoint_boxes_fail() -> None:
    result = evaluate_screenspot_grounding(
        task=_task([0.0, 0.0, 10.0, 10.0]),
        predicted_bbox=[20.0, 20.0, 30.0, 30.0],
    )
    assert result.passed is False


def test_zero_area_box_does_not_divide_by_zero() -> None:
    # A degenerate zero-area prediction must score 0.0, not raise.
    result = evaluate_screenspot_grounding(
        task=_task([0.0, 0.0, 0.0, 0.0]),
        predicted_bbox=[0.0, 0.0, 0.0, 0.0],
    )
    assert result.passed is False
