"""Regression tests for the per-candidate score join at the API boundary.

Both ``_build_response`` and ``_record_trajectory`` used to pair candidates to
their D-O-R-A-V scores positionally: they walked the candidates / gate_results
in raw order while consuming the ``evaluations`` list, which the runner returns
score-descending. Whenever raw order != score order (the common case — the DDLC
SequentialAgent emits non-HTML specialist outputs that are skipped from
gate_results, and the best candidate is rarely generated first) this attached
the wrong composite_score to the wrong candidate. In ``_record_trajectory`` that
corrupted the per-candidate scores written to BigQuery, which feed the
post-flight DPO pair miner's margin calculation.

The fix threads a canonical ``scored_candidates`` structure (candidate_id + html
+ composite_score + votes, joined upstream where html<->score alignment is
provable) and joins by candidate_id at every consumer (audit 2026-06-03).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from atelier.api.generate import _build_response, _record_trajectory


def _result_with_inverted_order() -> dict[str, Any]:
    """A runner result where gate/raw order (c-low, c-high) is the REVERSE of
    score order. A positional join would hand c-low the high score."""
    return {
        "session_id": "sess-join",
        "best_candidate": "<html>high</html>",
        "converged": True,
        "composite_score": 0.95,
        "candidates_evaluated": 3,
        "candidates_passed_gates": 2,
        # Raw candidates include a non-gradeable specialist output first.
        "candidates": ["# research notes", "<html>low</html>", "<html>high</html>"],
        # gate_results: raw order of the two gradeable candidates (low, then high).
        "gate_results": [
            {
                "candidate_id": "id-low",
                "all_passed": True,
                "outcomes": [{"axis": "a11y", "score": 88.0, "passed": True}],
            },
            {
                "candidate_id": "id-high",
                "all_passed": True,
                "outcomes": [{"axis": "a11y", "score": 99.0, "passed": True}],
            },
        ],
        # Canonical join: each candidate carries its OWN score, keyed by id.
        "scored_candidates": [
            {
                "candidate_id": "id-low",
                "html": "<html>low</html>",
                "composite_score": 0.60,
                "votes": {"a11y": {"score": 0.6}},
            },
            {
                "candidate_id": "id-high",
                "html": "<html>high</html>",
                "composite_score": 0.95,
                "votes": {"a11y": {"score": 0.95}},
            },
        ],
    }


class TestBuildResponseJoin:
    def test_each_candidate_summary_gets_its_own_score(self) -> None:
        response = _build_response(
            _result_with_inverted_order(), "run-1", "2026-06-03T00:00:00+00:00"
        )
        by_id = {s.candidate_index: s for s in response.candidates}
        # gate_results order: low at index 0, high at index 1.
        assert by_id[0].composite_score == pytest.approx(0.60)
        assert by_id[0].gate_outcomes[0].score == pytest.approx(88.0)
        assert by_id[1].composite_score == pytest.approx(0.95)
        assert by_id[1].gate_outcomes[0].score == pytest.approx(99.0)
        # The per-axis votes follow the score, not the position.
        assert by_id[0].votes["a11y"] == pytest.approx(0.6)
        assert by_id[1].votes["a11y"] == pytest.approx(0.95)

    def test_headline_fields_unaffected(self) -> None:
        response = _build_response(
            _result_with_inverted_order(), "run-1", "2026-06-03T00:00:00+00:00"
        )
        assert response.best_candidate == "<html>high</html>"
        assert response.composite_score == pytest.approx(0.95)
        assert response.converged is True
        assert response.candidates_passed_gates == 2


class TestRecordTrajectoryJoin:
    @pytest.mark.anyio
    async def test_records_attach_each_candidates_own_score(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: list[Any] = []

        class _FakeRecorder:
            def __init__(self, _client: Any) -> None:
                pass

            def record(self, rec: Any) -> None:
                captured.append(rec)

            def flush(self) -> None:
                pass

        monkeypatch.setattr(
            "atelier.recorders.trajectory_recorder.TrajectoryRecorder", _FakeRecorder
        )
        # Avoid constructing a real BigQuery client.
        import google.cloud.bigquery as bq

        monkeypatch.setattr(bq, "Client", lambda **_kw: object())

        user = SimpleNamespace(tenant_id="tenant-x", uid="user-x")
        await _record_trajectory(_result_with_inverted_order(), user, "run-1")

        outcome_by_score = {round(r.composite_score, 2): r.outcome for r in captured}
        # The high-scoring candidate is best_candidate AND converged → accepted,
        # and it carries 0.95 (NOT the low candidate's 0.60).
        assert outcome_by_score[0.95] == "accepted"
        assert outcome_by_score[0.60] == "rejected"
        assert len(captured) == 2
