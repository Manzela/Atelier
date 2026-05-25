import json
import pathlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from atelier.nodes.trajectory import TrajectoryRecord, TrajectoryStep, extract_dpo_pairs
from atelier.recorders.dpo_builder import prepare_dpo_dataset


def make_record(
    surface_id: str, candidate_id: str, iteration: int, score: float, node_name="N3a.generator"
) -> TrajectoryRecord:
    step = TrajectoryStep(
        step_name=node_name,
        step_index=0,
        started_at=datetime.now(tz=UTC),
        ended_at=datetime.now(tz=UTC),
        input_summary=f"Prompt for {surface_id}",
        output_summary=f"Response for {candidate_id}",
    )
    return TrajectoryRecord(
        trajectory_id=uuid4(),
        surface_id=uuid4(),  # Overridden below in each test
        tenant_id="tenant-1",
        project_id="proj-1",
        session_id="session-1",
        campaign_id="campaign-1",
        candidate_id=uuid4(),  # Overridden below in each test
        iteration=iteration,
        started_at=datetime.now(tz=UTC),
        ended_at=datetime.now(tz=UTC),
        outcome="accepted",
        composite_score=score,
        steps=(step,),
    )


def test_valid_pair_extracted():
    r1 = make_record("surf1", "cand1", 0, 0.72)
    # override manually to keep it string matchable or exact UUID
    surf_uuid = uuid4()
    c1_uuid = uuid4()
    c2_uuid = uuid4()
    r1 = make_record(str(surf_uuid), str(c1_uuid), 0, 0.72)
    r2 = make_record(str(surf_uuid), str(c2_uuid), 0, 0.49)
    # patch the objects
    object.__setattr__(r1, "surface_id", surf_uuid)
    object.__setattr__(r2, "surface_id", surf_uuid)
    object.__setattr__(r1, "candidate_id", c1_uuid)
    object.__setattr__(r2, "candidate_id", c2_uuid)

    result = prepare_dpo_dataset([r1, r2])
    assert len(result) == 1
    assert result[0]["margin"] == 0.23
    assert result[0]["metadata"]["chosen_score"] == 0.72
    assert result[0]["metadata"]["rejected_score"] == 0.49


def test_g10_fix_same_candidate_no_pair():
    surf_uuid = uuid4()
    c1_uuid = uuid4()
    r1 = make_record("s", "c", 0, 0.82)
    r2 = make_record("s", "c", 0, 0.40)
    object.__setattr__(r1, "surface_id", surf_uuid)
    object.__setattr__(r2, "surface_id", surf_uuid)
    object.__setattr__(r1, "candidate_id", c1_uuid)
    object.__setattr__(r2, "candidate_id", c1_uuid)  # SAME CANDIDATE

    result = prepare_dpo_dataset([r1, r2])
    assert len(result) == 0


def test_margin_too_small_rejected():
    surf_uuid = uuid4()
    r1 = make_record("s", "c1", 0, 0.75)
    r2 = make_record("s", "c2", 0, 0.63)
    object.__setattr__(r1, "surface_id", surf_uuid)
    object.__setattr__(r2, "surface_id", surf_uuid)

    result = prepare_dpo_dataset([r1, r2])
    assert len(result) == 0


def test_both_above_threshold_picks_highest_lowest():
    surf_uuid = uuid4()
    r1 = make_record("s", "c1", 0, 0.90)
    r2 = make_record("s", "c2", 0, 0.75)
    r3 = make_record("s", "c3", 0, 0.40)
    object.__setattr__(r1, "surface_id", surf_uuid)
    object.__setattr__(r2, "surface_id", surf_uuid)
    object.__setattr__(r3, "surface_id", surf_uuid)

    result = prepare_dpo_dataset([r1, r2, r3])
    assert len(result) == 1
    assert result[0]["metadata"]["chosen_score"] == 0.90
    assert result[0]["metadata"]["rejected_score"] == 0.40


def test_empty_records_returns_empty():
    assert prepare_dpo_dataset([]) == []


def test_chosen_threshold_boundary():
    surf_uuid = uuid4()
    r1 = make_record("s", "c1", 0, 0.70)
    r2 = make_record("s", "c2", 0, 0.40)
    object.__setattr__(r1, "surface_id", surf_uuid)
    object.__setattr__(r2, "surface_id", surf_uuid)

    result = prepare_dpo_dataset([r1, r2])
    assert len(result) == 1


def test_rejected_threshold_boundary():
    surf_uuid = uuid4()
    r1 = make_record("s", "c1", 0, 0.80)
    r2 = make_record("s", "c2", 0, 0.50)  # 0.50 is NOT < 0.50
    object.__setattr__(r1, "surface_id", surf_uuid)
    object.__setattr__(r2, "surface_id", surf_uuid)

    result = prepare_dpo_dataset([r1, r2])
    assert len(result) == 0


def test_multiple_decision_points_independent():
    s1 = uuid4()
    s2 = uuid4()

    r1 = make_record("s", "c1", 0, 0.80)
    r2 = make_record("s", "c2", 0, 0.40)
    object.__setattr__(r1, "surface_id", s1)
    object.__setattr__(r2, "surface_id", s1)

    r3 = make_record("s", "c3", 0, 0.85)
    r4 = make_record("s", "c4", 0, 0.35)
    object.__setattr__(r3, "surface_id", s2)
    object.__setattr__(r4, "surface_id", s2)

    result = prepare_dpo_dataset([r1, r2, r3, r4])
    assert len(result) == 2


def test_output_format_has_required_keys():
    surf_uuid = uuid4()
    r1 = make_record("s", "c1", 0, 0.72)
    r2 = make_record("s", "c2", 0, 0.49)
    object.__setattr__(r1, "surface_id", surf_uuid)
    object.__setattr__(r2, "surface_id", surf_uuid)

    result = prepare_dpo_dataset([r1, r2])
    assert len(result) == 1
    d = result[0]
    assert "prompt" in d
    assert "chosen" in d
    assert "rejected" in d
    assert "margin" in d
    assert "metadata" in d


def test_metadata_fields_present():
    surf_uuid = uuid4()
    r1 = make_record("s", "c1", 0, 0.72)
    r2 = make_record("s", "c2", 0, 0.49)
    object.__setattr__(r1, "surface_id", surf_uuid)
    object.__setattr__(r2, "surface_id", surf_uuid)

    result = prepare_dpo_dataset([r1, r2])
    assert len(result) == 1
    m = result[0]["metadata"]
    assert "surface_id" in m
    assert "node_name" in m
    assert "iteration" in m
    assert "chosen_score" in m
    assert "rejected_score" in m


FIXTURE = pathlib.Path(__file__).parent.parent / "fixtures" / "trajectories_seed.jsonl"


def load_fixture():
    return [json.loads(line) for line in FIXTURE.read_text().splitlines() if line.strip()]


@pytest.mark.unit
def test_fixture_completeness():
    records = load_fixture()
    assert len(records) == 30
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
        "error_message",
    }
    for r in records:
        assert set(r.keys()).issuperset(required_keys)


@pytest.mark.unit
def test_fixture_tenant_isolation():
    records = load_fixture()
    tenant_counts = {}
    for r in records:
        tenant_counts[r["tenant_id"]] = tenant_counts.get(r["tenant_id"], 0) + 1
    assert len(tenant_counts) == 2
    assert tenant_counts.get("tenant-alpha", 0) == 20
    assert tenant_counts.get("tenant-beta", 0) == 10


@pytest.mark.unit
def test_fixture_outcome_distribution():
    records = load_fixture()
    outcome_counts = {}
    for r in records:
        outcome_counts[r["outcome"]] = outcome_counts.get(r["outcome"], 0) + 1
    assert outcome_counts.get("accepted", 0) == 18
    assert outcome_counts.get("rejected", 0) == 8
    assert outcome_counts.get("error", 0) == 4


@pytest.mark.unit
def test_fixture_judge_votes():
    records = load_fixture()
    required_axes = {
        "brand",
        "originality",
        "relevance",
        "accessibility",
        "visual_clarity",
        "copy",
        "motion",
        "token",
        "coherence",
    }
    for r in records:
        votes = json.loads(r["judge_votes_json"])
        axes = {vote["axis"] for vote in votes}
        assert axes.issuperset(required_axes)


@pytest.mark.unit
def test_fixture_extract_dpo_pairs():
    """extract_dpo_pairs() produces >= 3 pairs from accepted+rejected records with min_margin=0.05."""
    from uuid import UUID

    records = load_fixture()
    trajectory_records = []
    for r in records:
        record = TrajectoryRecord(
            trajectory_id=UUID(r["trajectory_id"]),
            surface_id=UUID(r["surface_id"]),
            tenant_id=r["tenant_id"],
            project_id=r["project_id"],
            session_id=r["session_id"],
            campaign_id=r["campaign_id"],
            candidate_id=UUID(r["candidate_id"]),
            iteration=r["iteration"],
            started_at=datetime.fromisoformat(r["ts"]),
            ended_at=datetime.fromisoformat(r["ended_at"]),
            outcome=r["outcome"],
            composite_score=r["composite_score"],
            steps=(),
        )
        trajectory_records.append(record)

    pairs = extract_dpo_pairs(trajectory_records, min_margin=0.05)
    assert len(pairs) >= 3
