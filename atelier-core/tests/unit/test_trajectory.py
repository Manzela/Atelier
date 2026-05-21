"""Tests for trajectory recorder (N3h) and DPO pair extraction (FA-011)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from atelier.nodes.trajectory import (
    DPOPreferencePair,
    TrajectoryRecord,
    TrajectoryStep,
    extract_dpo_pairs,
)

# ---------------------------------------------------------------------------
# Constants for PLR2004 compliance
# ---------------------------------------------------------------------------

PASS_SCORE = 0.85
FAIL_SCORE = 0.45
MARGIN_THRESHOLD = 0.05
EXPECTED_TWO_PAIRS = 2
STEP_INDEX_ZERO = 0
TOKEN_COUNT = 100


def _now() -> datetime:
    return datetime.now(UTC)


def _make_step(*, name: str = "n3a_generator", index: int = 0) -> TrajectoryStep:
    """Factory for trajectory steps."""
    ts = _now()
    return TrajectoryStep(
        step_name=name,
        step_index=index,
        started_at=ts,
        ended_at=ts,
        model_id="gemini-2.5-flash",
        input_tokens=TOKEN_COUNT,
        output_tokens=TOKEN_COUNT,
        cost_usd=0.001,
    )


def _make_trajectory(
    *,
    outcome: str = "accepted",
    score: float = PASS_SCORE,
    surface_id: None = None,
) -> TrajectoryRecord:
    """Factory for trajectory records."""
    sid = surface_id or uuid4()
    ts = _now()
    return TrajectoryRecord(
        trajectory_id=uuid4(),
        tenant_id="tnt_test",
        project_id="prj_test",
        surface_id=sid,
        session_id="sess_test",
        campaign_id="camp_test",
        candidate_id=uuid4(),
        iteration=0,
        started_at=ts,
        ended_at=ts,
        outcome=outcome,
        composite_score=score,
        steps=(_make_step(),),
        total_cost_usd=0.001,
        total_input_tokens=TOKEN_COUNT,
        total_output_tokens=TOKEN_COUNT,
    )


@pytest.mark.unit
class TestTrajectoryStep:
    """Verify TrajectoryStep construction."""

    def test_create(self) -> None:
        step = _make_step()
        assert step.step_name == "n3a_generator"
        assert step.step_index == STEP_INDEX_ZERO

    def test_frozen(self) -> None:
        step = _make_step()
        with pytest.raises(AttributeError):
            step.step_name = "changed"  # type: ignore[misc]


@pytest.mark.unit
class TestTrajectoryRecord:
    """Verify TrajectoryRecord construction and serialization."""

    def test_create(self) -> None:
        record = _make_trajectory()
        assert record.outcome == "accepted"
        assert record.composite_score == PASS_SCORE

    def test_to_bq_row_has_required_fields(self) -> None:
        record = _make_trajectory()
        row = record.to_bq_row()
        required_keys = {
            "trajectory_id",
            "tenant_id",
            "project_id",
            "surface_id",
            "session_id",
            "campaign_id",
            "candidate_id",
            "iteration",
            "ts",
            "ended_at",
            "outcome",
            "composite_score",
            "steps_json",
            "gate_results_json",
            "judge_votes_json",
            "total_cost_usd",
            "total_input_tokens",
            "total_output_tokens",
        }
        assert required_keys.issubset(set(row.keys()))

    def test_to_bq_row_steps_json_is_string(self) -> None:
        record = _make_trajectory()
        row = record.to_bq_row()
        assert isinstance(row["steps_json"], str)
        assert "n3a_generator" in row["steps_json"]

    def test_frozen(self) -> None:
        record = _make_trajectory()
        with pytest.raises(AttributeError):
            record.outcome = "changed"  # type: ignore[misc]


@pytest.mark.unit
class TestDPOPreferencePair:
    """Verify DPO preference pair construction."""

    def test_create(self) -> None:
        pair = DPOPreferencePair(
            pair_id=uuid4(),
            tenant_id="tnt_test",
            project_id="prj_test",
            surface_id=uuid4(),
            chosen_id=uuid4(),
            rejected_id=uuid4(),
            chosen_score=PASS_SCORE,
            rejected_score=FAIL_SCORE,
            margin=PASS_SCORE - FAIL_SCORE,
            judge_axis="composite",
            extracted_at=_now(),
        )
        assert pair.chosen_score > pair.rejected_score
        assert pair.margin > 0

    def test_to_bq_row(self) -> None:
        pair = DPOPreferencePair(
            pair_id=uuid4(),
            tenant_id="tnt_test",
            project_id="prj_test",
            surface_id=uuid4(),
            chosen_id=uuid4(),
            rejected_id=uuid4(),
            chosen_score=PASS_SCORE,
            rejected_score=FAIL_SCORE,
            margin=PASS_SCORE - FAIL_SCORE,
            judge_axis="brand",
            extracted_at=_now(),
        )
        row = pair.to_bq_row()
        assert "pair_id" in row
        assert row["judge_axis"] == "brand"


@pytest.mark.unit
class TestExtractDPOPairs:
    """Verify DPO pair extraction from trajectories."""

    def test_no_trajectories(self) -> None:
        pairs = extract_dpo_pairs([])
        assert pairs == []

    def test_single_accepted_no_rejected(self) -> None:
        pairs = extract_dpo_pairs([_make_trajectory(outcome="accepted")])
        assert pairs == []

    def test_accepted_vs_rejected_emits_pair(self) -> None:
        accepted = _make_trajectory(outcome="accepted", score=PASS_SCORE)
        # Override surface_id to match
        rejected = TrajectoryRecord(
            trajectory_id=uuid4(),
            tenant_id="tnt_test",
            project_id="prj_test",
            surface_id=accepted.surface_id,
            session_id="sess_test",
            campaign_id="camp_test",
            candidate_id=uuid4(),
            iteration=1,
            started_at=_now(),
            ended_at=_now(),
            outcome="rejected",
            composite_score=FAIL_SCORE,
        )
        pairs = extract_dpo_pairs([accepted, rejected])
        assert len(pairs) == 1
        assert pairs[0].chosen_score == PASS_SCORE
        assert pairs[0].rejected_score == FAIL_SCORE

    def test_margin_below_threshold_skipped(self) -> None:
        accepted = _make_trajectory(outcome="accepted", score=0.50)
        rejected = TrajectoryRecord(
            trajectory_id=uuid4(),
            tenant_id="tnt_test",
            project_id="prj_test",
            surface_id=accepted.surface_id,
            session_id="sess_test",
            campaign_id="camp_test",
            candidate_id=uuid4(),
            iteration=1,
            started_at=_now(),
            ended_at=_now(),
            outcome="rejected",
            composite_score=0.49,
        )
        # Margin is 0.01 < default 0.05
        pairs = extract_dpo_pairs([accepted, rejected])
        assert pairs == []

    def test_different_surfaces_not_paired(self) -> None:
        a = _make_trajectory(outcome="accepted", score=PASS_SCORE)
        r = _make_trajectory(outcome="rejected", score=FAIL_SCORE)
        # Different surface_ids by default
        pairs = extract_dpo_pairs([a, r])
        assert pairs == []
