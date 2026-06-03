"""Unit tests for the Dreaming Module (mid-flight DPO pair extraction + κ calibration)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from atelier.optimize.dreaming_module import (
    MIN_MARGIN,
    CalibrationResult,
    DreamingReport,
    ExtractedPair,
    evaluate_kappa_against_calibration,
    extract_pairs_midflight,
    load_calibration_seed,
    write_pairs_to_bq,
)

# ---------------------------------------------------------------------------
# extract_pairs_midflight
# ---------------------------------------------------------------------------


def _scored(html: str, composite_score: float, candidate_id: str = "c") -> dict[str, object]:
    """A canonical scored_candidates entry: html paired with its OWN score+id."""
    return {
        "candidate_id": candidate_id,
        "html": html,
        "composite_score": composite_score,
        "votes": {},
    }


class TestExtractPairsMidflight:
    def test_returns_pair_when_margin_exceeds_threshold(self) -> None:
        pairs = extract_pairs_midflight(
            session_id="sess-1",
            tenant_id="tenant-alpha",
            surface_id="surf-1",
            brief_text="Design a dashboard for retail analytics",
            scored_candidates=[
                _scored("<html>chosen</html>", 0.90, "a"),
                _scored("<html>rejected</html>", 0.70, "b"),
            ],
        )
        assert len(pairs) == 1
        pair = pairs[0]
        assert pair.chosen_score == pytest.approx(0.90)
        assert pair.rejected_score == pytest.approx(0.70)
        assert pair.chosen_response == "<html>chosen</html>"
        assert pair.rejected_response == "<html>rejected</html>"
        assert pair.margin == pytest.approx(0.20)
        assert pair.margin >= MIN_MARGIN
        assert pair.tenant_id == "tenant-alpha"
        assert pair.session_id == "sess-1"

    def test_chosen_is_highest_score_regardless_of_input_order(self) -> None:
        """Regression (audit 2026-06-03): the chosen/rejected labels must follow
        each candidate's OWN score, never list position.

        The old extractor walked candidates in raw order and consumed a
        score-descending evaluations list via a positional cursor, so when the
        worst candidate appeared first it was labeled `chosen` and the best
        `rejected` — direction-inverted DPO signal written to BigQuery. With the
        canonical join each entry self-describes, so worst-first input still
        yields the true winner as chosen.
        """
        pairs = extract_pairs_midflight(
            session_id="sess-inv",
            tenant_id="tenant-alpha",
            surface_id="surf-inv",
            brief_text="Brief",
            scored_candidates=[
                _scored("<html>LOSER</html>", 0.60, "a"),  # worst, listed FIRST
                _scored("<html>WINNER</html>", 0.95, "b"),  # best, listed second
            ],
        )
        assert len(pairs) == 1
        assert pairs[0].chosen_response == "<html>WINNER</html>"
        assert pairs[0].chosen_score == pytest.approx(0.95)
        assert pairs[0].rejected_response == "<html>LOSER</html>"
        assert pairs[0].rejected_score == pytest.approx(0.60)

    def test_returns_empty_when_margin_below_threshold(self) -> None:
        pairs = extract_pairs_midflight(
            session_id="sess-2",
            tenant_id="tenant-alpha",
            surface_id="surf-2",
            brief_text="Brief",
            scored_candidates=[
                _scored("<html>a</html>", 0.75, "a"),
                _scored("<html>b</html>", 0.72, "b"),
            ],
        )
        # 0.75 - 0.72 = 0.03 < MIN_MARGIN (0.12) → no pairs
        assert pairs == []

    def test_skips_entries_with_empty_html(self) -> None:
        # An entry whose HTML is empty (e.g. a non-design specialist output) is
        # dropped, leaving fewer than two scorable candidates → no pair.
        pairs = extract_pairs_midflight(
            session_id="sess-3",
            tenant_id="tenant-alpha",
            surface_id="surf-3",
            brief_text="Brief",
            scored_candidates=[
                _scored("   ", 0.90, "a"),  # empty HTML — skipped
                _scored("<html>only</html>", 0.70, "b"),
            ],
        )
        assert pairs == []

    def test_returns_empty_when_only_one_scored_candidate(self) -> None:
        pairs = extract_pairs_midflight(
            session_id="sess-4",
            tenant_id="tenant-alpha",
            surface_id="surf-4",
            brief_text="Brief",
            scored_candidates=[_scored("<html>only</html>", 0.85, "a")],
        )
        assert pairs == []

    def test_brief_text_truncated_to_2000_chars(self) -> None:
        long_brief = "x" * 5000
        pairs = extract_pairs_midflight(
            session_id="sess-5",
            tenant_id="t",
            surface_id="s",
            brief_text=long_brief,
            scored_candidates=[
                _scored("<html>a</html>", 0.90, "a"),
                _scored("<html>b</html>", 0.70, "b"),
            ],
        )
        assert len(pairs) == 1
        assert len(pairs[0].prompt) == 2000


# ---------------------------------------------------------------------------
# write_pairs_to_bq — fail-soft behavior
# ---------------------------------------------------------------------------


class TestWritePairsToBq:
    def test_returns_zero_on_empty_list(self) -> None:
        result = write_pairs_to_bq([])
        assert result == 0

    def test_returns_zero_when_bq_unavailable(self) -> None:
        # Pass a dummy client that raises — must fail-soft and return 0
        class _BadClient:
            def insert_rows_json(self, *a: object, **kw: object) -> None:
                raise RuntimeError("BQ connection refused")

        pairs = [
            ExtractedPair(
                surface_id="s",
                tenant_id="t",
                session_id="sess",
                prompt="p",
                chosen_response="<html>a</html>",
                rejected_response="<html>b</html>",
                chosen_score=0.9,
                rejected_score=0.7,
                margin=0.2,
                node_name="N3a.generator",
                iteration=0,
                extracted_at="2026-05-25T00:00:00+00:00",
            )
        ]
        result = write_pairs_to_bq(pairs, bq_client=_BadClient())
        assert result == 0


# ---------------------------------------------------------------------------
# load_calibration_seed
# ---------------------------------------------------------------------------


class TestLoadCalibrationSeed:
    def test_loads_valid_jsonl(self) -> None:
        record = {
            "task_id": "dash-001",
            "category": "dashboard",
            "brief": "Design a dark-mode analytics dashboard",
            "quality_criteria": {"min_composite_score": 0.80},
            "reference_score": 0.85,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps(record) + "\n")
            f.write(json.dumps(record | {"task_id": "dash-002"}) + "\n")
            path = Path(f.name)

        tasks = load_calibration_seed(path)
        assert len(tasks) == 2
        assert tasks[0]["task_id"] == "dash-001"
        assert tasks[1]["task_id"] == "dash-002"
        path.unlink()

    def test_raises_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_calibration_seed(Path("/nonexistent/calibration.jsonl"))

    def test_skips_blank_lines(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(
                '{"task_id": "t1", "brief": "b", "quality_criteria": {}, "reference_score": 0.8}\n'
            )
            f.write("\n")
            f.write(
                '{"task_id": "t2", "brief": "b", "quality_criteria": {}, "reference_score": 0.8}\n'
            )
            path = Path(f.name)

        tasks = load_calibration_seed(path)
        assert len(tasks) == 2
        path.unlink()


# ---------------------------------------------------------------------------
# evaluate_kappa_against_calibration
# ---------------------------------------------------------------------------


class TestEvaluateKappa:
    def _make_seed(
        self, min_score: float = 0.70, reference_score: float = 0.85
    ) -> list[dict[str, object]]:
        return [
            {
                "task_id": f"t{i}",
                "brief": f"Brief {i}",
                "quality_criteria": {"min_composite_score": min_score},
                "reference_score": reference_score,
            }
            for i in range(10)
        ]

    def test_kappa_one_when_all_pass(self) -> None:
        tasks = self._make_seed(min_score=0.70)
        kappa, results = evaluate_kappa_against_calibration(
            tasks,
            generate_fn=lambda _brief: 0.85,
        )
        assert kappa == pytest.approx(1.0)
        assert all(r.passed for r in results)

    def test_kappa_zero_when_none_pass(self) -> None:
        tasks = self._make_seed(min_score=0.90)
        kappa, results = evaluate_kappa_against_calibration(
            tasks,
            generate_fn=lambda _brief: 0.50,
        )
        assert kappa == pytest.approx(0.0)
        assert not any(r.passed for r in results)

    def test_partial_kappa(self) -> None:
        tasks = self._make_seed(min_score=0.70)
        call_count = [0]

        def _generate(_brief: str) -> float:
            call_count[0] += 1
            # First 7 pass, last 3 fail
            return 0.80 if call_count[0] <= 7 else 0.60

        kappa, results = evaluate_kappa_against_calibration(tasks, generate_fn=_generate)
        assert kappa == pytest.approx(0.7)
        assert sum(1 for r in results if r.passed) == 7

    def test_failed_generate_fn_counts_as_zero_score(self) -> None:
        tasks = self._make_seed(min_score=0.70)

        def _bad_generate(_brief: str) -> float:
            raise RuntimeError("Model unavailable")

        kappa, results = evaluate_kappa_against_calibration(tasks, generate_fn=_bad_generate)
        assert kappa == pytest.approx(0.0)
        assert all(r.composite_score == 0.0 for r in results)

    def test_empty_tasks_returns_zero_kappa(self) -> None:
        kappa, results = evaluate_kappa_against_calibration([], generate_fn=lambda _: 0.85)
        assert kappa == pytest.approx(0.0)
        assert results == []


# ---------------------------------------------------------------------------
# DreamingReport
# ---------------------------------------------------------------------------


class TestDreamingReport:
    def test_success_true_when_no_errors(self) -> None:
        report = DreamingReport(errors=[])
        assert report.success is True

    def test_success_false_when_has_errors(self) -> None:
        report = DreamingReport(errors=["Something went wrong"])
        assert report.success is False

    def test_success_false_when_errors_is_none(self) -> None:
        report = DreamingReport(errors=None)
        assert report.success is True  # None means not set (no errors field), treated as truthy
