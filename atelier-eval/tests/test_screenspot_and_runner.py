"""Tests for the ScreenSpot adapter and EvalRunner.

Covers:
- IoU boundary values (identical, disjoint, half-overlap, zero-area).
- load_screenspot_tasks round-trip from a fixture manifest.
- EvalRunner.run_screenspot with a partial predictions dict.

Finding 40: atelier-eval/tests/ had zero test files; the IoU math and runner
methods were unexercised.  These tests are hermetic (no network, no creds) and
run under the default pytest collect rules.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from atelier_eval.adapters.screenspot import (
    ScreenSpotTask,
    evaluate_screenspot_grounding,
    load_screenspot_tasks,
)
from atelier_eval.runner import EvalRunner

# ---------------------------------------------------------------------------
# IoU golden-value tests
# ---------------------------------------------------------------------------


def _make_task(bbox: list[float]) -> ScreenSpotTask:
    return ScreenSpotTask(
        task_id="t0",
        screenshot_path="screen.png",
        instruction="click the button",
        target_bbox=bbox,
    )


class TestScreenSpotIoU:
    """Golden IoU boundary values for evaluate_screenspot_grounding."""

    def test_identical_boxes_score_one(self) -> None:
        """Identical predicted and target boxes must produce IoU == 1.0."""
        box = [0.1, 0.1, 0.5, 0.5]
        result = evaluate_screenspot_grounding(
            task=_make_task(box),
            predicted_bbox=box,
            iou_threshold=0.5,
        )
        assert result.score == pytest.approx(1.0)
        assert result.passed is True

    def test_disjoint_boxes_score_zero(self) -> None:
        """Non-overlapping boxes must produce IoU == 0.0 (no ZeroDivisionError)."""
        target = [0.0, 0.0, 0.2, 0.2]
        predicted = [0.5, 0.5, 0.9, 0.9]
        result = evaluate_screenspot_grounding(
            task=_make_task(target),
            predicted_bbox=predicted,
            iou_threshold=0.5,
        )
        assert result.score == pytest.approx(0.0)
        assert result.passed is False

    def test_half_overlap_known_value(self) -> None:
        """Two unit boxes offset by 0.5 along the x-axis produce IoU = 1/3.

        target [0,0,1,1] and predicted [0,0.5,1,1.5] share an intersection
        area of 0.5 against a union of 1.5, giving IoU = 0.5 / 1.5 = 1/3.
        """
        target = [0.0, 0.0, 1.0, 1.0]
        predicted = [0.0, 0.5, 1.0, 1.5]
        result = evaluate_screenspot_grounding(
            task=_make_task(target),
            predicted_bbox=predicted,
            iou_threshold=0.5,
        )
        assert result.score == pytest.approx(1.0 / 3.0, abs=1e-6)
        assert result.passed is False  # below 0.5 threshold

    def test_zero_area_box_does_not_crash(self) -> None:
        """A predicted box with zero area must not raise ZeroDivisionError."""
        target = [0.1, 0.1, 0.5, 0.5]
        zero_area = [0.2, 0.2, 0.2, 0.2]
        result = evaluate_screenspot_grounding(
            task=_make_task(target),
            predicted_bbox=zero_area,
            iou_threshold=0.5,
        )
        assert result.score == pytest.approx(0.0)
        assert result.passed is False

    def test_metadata_contains_iou_and_dataset(self) -> None:
        box = [0.0, 0.0, 0.4, 0.4]
        result = evaluate_screenspot_grounding(
            task=_make_task(box),
            predicted_bbox=box,
        )
        assert result.metadata["dataset"] == "screenspot"
        assert "iou" in result.metadata
        assert "iou_threshold" in result.metadata


# ---------------------------------------------------------------------------
# Manifest loader round-trip
# ---------------------------------------------------------------------------


class TestLoadScreenspotTasks:
    """Round-trip load from a minimal fixture manifest."""

    def test_load_two_tasks(self, tmp_path: Path) -> None:
        manifest = [
            {
                "id": "ss-001",
                "screenshot": "img/001.png",
                "instruction": "tap submit",
                "bbox": [0.1, 0.2, 0.3, 0.4],
            },
            {
                "id": "ss-002",
                "screenshot": "img/002.png",
                "instruction": "tap cancel",
                "bbox": [0.5, 0.6, 0.7, 0.8],
            },
        ]
        (tmp_path / "screenspot_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        tasks = load_screenspot_tasks(tmp_path)
        assert len(tasks) == 2
        assert tasks[0].task_id == "ss-001"
        assert tasks[1].target_bbox == [0.5, 0.6, 0.7, 0.8]

    def test_missing_manifest_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_screenspot_tasks(tmp_path)


# ---------------------------------------------------------------------------
# EvalRunner.run_screenspot — partial predictions dict
# ---------------------------------------------------------------------------


class TestEvalRunnerScreenspot:
    """EvalRunner returns results only for tasks present in predictions dict."""

    def test_partial_predictions_skips_unmatched(self, tmp_path: Path) -> None:
        manifest = [
            {
                "id": "a",
                "screenshot": "a.png",
                "instruction": "click a",
                "bbox": [0.0, 0.0, 0.5, 0.5],
            },
            {
                "id": "b",
                "screenshot": "b.png",
                "instruction": "click b",
                "bbox": [0.5, 0.5, 1.0, 1.0],
            },
        ]
        (tmp_path / "screenspot_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        runner = EvalRunner(data_dir=str(tmp_path))
        # Only supply a prediction for task "a"; "b" should be skipped.
        results = runner.run_screenspot({"a": [0.0, 0.0, 0.5, 0.5]})
        assert len(results) == 1
        assert results[0].task_id == "a"
        assert results[0].score == pytest.approx(1.0)

    def test_empty_predictions_returns_empty(self, tmp_path: Path) -> None:
        manifest = [
            {
                "id": "x",
                "screenshot": "x.png",
                "instruction": "tap x",
                "bbox": [0.0, 0.0, 1.0, 1.0],
            }
        ]
        (tmp_path / "screenspot_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        runner = EvalRunner(data_dir=str(tmp_path))
        results = runner.run_screenspot({})
        assert results == []

    def test_summary_aggregates_correctly(self, tmp_path: Path) -> None:
        manifest = [
            {
                "id": "p",
                "screenshot": "p.png",
                "instruction": "tap p",
                "bbox": [0.0, 0.0, 0.5, 0.5],
            },
            {
                "id": "q",
                "screenshot": "q.png",
                "instruction": "tap q",
                "bbox": [0.5, 0.5, 1.0, 1.0],
            },
        ]
        (tmp_path / "screenspot_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        runner = EvalRunner(data_dir=str(tmp_path))
        # "p" matches (IoU=1.0, passes), "q" misses (IoU=0.0, fails).
        runner.run_screenspot(
            {
                "p": [0.0, 0.0, 0.5, 0.5],
                "q": [0.0, 0.0, 0.1, 0.1],
            }
        )
        summary = runner.summary()
        assert summary["pass_rate"] == pytest.approx(0.5)
        assert 0.0 <= summary["mean_score"] <= 1.0
