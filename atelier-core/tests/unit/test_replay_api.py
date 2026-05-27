"""Unit tests for the session replay API — replay.py.

Coverage:
    _build_spans()          — row → SpanNode conversion, column names
    _build_gate_scores()    — judge_votes_json parsing, edge cases
    _assemble_payload()     — full payload assembly from row list
    _load_session_replay()  — tenant_id filter in WHERE clause (IDOR fix),
                              BQ client injection, fail-soft on BQ error
    get_replay()            — auth required, ownership check (403 path),
                              session not found (404 path)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from atelier.api.replay import (
    GateScore,
    SessionReplayPayload,
    SpanNode,
    _assemble_payload,
    _build_gate_scores,
    _build_spans,
    _load_session_replay,
    router,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _row(
    *,
    trajectory_id: str = "traj-001",
    tenant_id: str = "tenant-abc",
    project_id: str = "proj-001",
    node_name: str = "N3a.generator",
    ts: str = "2026-05-25T10:00:00+00:00",
    ended_at: str = "2026-05-25T10:00:05+00:00",
    outcome: str = "accepted",
    composite_score: float = 0.85,
    candidate_id: str = "cand-001",
    iteration: int = 1,
    total_cost_usd: float = 0.15,
    total_input_tokens: int = 500,
    total_output_tokens: int = 300,
    judge_votes_json: str = "[]",
    session_id: str = "sess-001",
) -> dict[str, Any]:
    return {
        "trajectory_id": trajectory_id,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "node_name": node_name,
        "ts": ts,
        "ended_at": ended_at,
        "outcome": outcome,
        "composite_score": composite_score,
        "candidate_id": candidate_id,
        "iteration": iteration,
        "total_cost_usd": total_cost_usd,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "judge_votes_json": judge_votes_json,
        "session_id": session_id,
    }


# ---------------------------------------------------------------------------
# _build_spans
# ---------------------------------------------------------------------------


def test_build_spans_uses_trajectory_id_as_span_id() -> None:
    rows = [_row(trajectory_id="traj-xyz")]
    spans = _build_spans(rows)
    assert len(spans) == 1
    assert spans[0].span_id == "traj-xyz"


def test_build_spans_node_name_column() -> None:
    rows = [_row(node_name="N1.brief_parser")]
    spans = _build_spans(rows)
    assert spans[0].node_name == "N1.brief_parser"


def test_build_spans_ts_is_started_at() -> None:
    rows = [_row(ts="2026-05-25T09:00:00")]
    spans = _build_spans(rows)
    assert spans[0].started_at == "2026-05-25T09:00:00"


def test_build_spans_accumulates_cost_from_column() -> None:
    rows = [_row(total_cost_usd=0.042)]
    spans = _build_spans(rows)
    assert spans[0].cost_usd == pytest.approx(0.042)


def test_build_spans_returns_one_span_per_row() -> None:
    rows = [_row(trajectory_id=f"t-{i}") for i in range(5)]
    assert len(_build_spans(rows)) == 5


def test_build_spans_empty_rows_returns_empty() -> None:
    assert _build_spans([]) == []


# ---------------------------------------------------------------------------
# _build_gate_scores
# ---------------------------------------------------------------------------


def test_build_gate_scores_parses_valid_json() -> None:
    raw = '[{"axis":"brand","score":0.8,"confidence_interval":[0.7,0.9],"judge_model":"gemini-3-pro","reasoning":"ok"}]'
    scores = _build_gate_scores(raw)
    assert len(scores) == 1
    assert scores[0].axis == "brand"
    assert scores[0].score == pytest.approx(0.8)
    assert scores[0].confidence_low == pytest.approx(0.7)
    assert scores[0].confidence_high == pytest.approx(0.9)
    assert scores[0].judge_model == "gemini-3-pro"


def test_build_gate_scores_empty_array_returns_empty() -> None:
    assert _build_gate_scores("[]") == []


def test_build_gate_scores_invalid_json_returns_empty() -> None:
    assert _build_gate_scores("NOT JSON") == []


def test_build_gate_scores_null_returns_empty() -> None:
    assert _build_gate_scores("null") == []


def test_build_gate_scores_skips_entries_without_axis() -> None:
    raw = '[{"score":0.5,"judge_model":"x"},{"axis":"copy","score":0.7,"confidence_interval":[0,1],"judge_model":"y","reasoning":"r"}]'
    scores = _build_gate_scores(raw)
    assert len(scores) == 1
    assert scores[0].axis == "copy"


def test_build_gate_scores_string_confidence_interval_parsed() -> None:
    raw = '[{"axis":"motion","score":0.6,"confidence_interval":"[0.5,0.7]","judge_model":"m","reasoning":"r"}]'
    scores = _build_gate_scores(raw)
    assert scores[0].confidence_low == pytest.approx(0.5)
    assert scores[0].confidence_high == pytest.approx(0.7)


def test_build_gate_scores_multiple_entries() -> None:
    raw = '[{"axis":"brand","score":0.8,"confidence_interval":[0.7,0.9],"judge_model":"m","reasoning":"r"},{"axis":"copy","score":0.7,"confidence_interval":[0.6,0.8],"judge_model":"m","reasoning":"r"}]'
    scores = _build_gate_scores(raw)
    assert len(scores) == 2
    axes = {s.axis for s in scores}
    assert axes == {"brand", "copy"}


# ---------------------------------------------------------------------------
# _assemble_payload
# ---------------------------------------------------------------------------


def test_assemble_payload_uses_first_row_for_tenant() -> None:
    rows = [_row(tenant_id="t-first"), _row(tenant_id="t-last")]
    p = _assemble_payload("sess-001", rows)
    assert p.tenant_id == "t-first"


def test_assemble_payload_uses_last_row_composite_score() -> None:
    rows = [_row(composite_score=0.5), _row(composite_score=0.9)]
    p = _assemble_payload("sess-001", rows)
    assert p.composite_score == pytest.approx(0.9)


def test_assemble_payload_accumulates_cost() -> None:
    rows = [_row(total_cost_usd=0.10), _row(total_cost_usd=0.15)]
    p = _assemble_payload("sess-001", rows)
    assert p.total_cost_usd == pytest.approx(0.25)


def test_assemble_payload_candidate_count_deduplicates() -> None:
    rows = [
        _row(candidate_id="c-001"),
        _row(candidate_id="c-001"),  # duplicate — same candidate
        _row(candidate_id="c-002"),
    ]
    p = _assemble_payload("sess-001", rows)
    assert p.candidate_count == 2


def test_assemble_payload_gate_scores_from_last_row_judge_votes_json() -> None:
    raw = '[{"axis":"brand","score":0.8,"confidence_interval":[0.7,0.9],"judge_model":"m","reasoning":"r"}]'
    rows = [_row(judge_votes_json="[]"), _row(judge_votes_json=raw)]
    p = _assemble_payload("sess-001", rows)
    assert len(p.gate_scores) == 1
    assert p.gate_scores[0].axis == "brand"


def test_assemble_payload_max_iteration_tracked() -> None:
    rows = [_row(iteration=0), _row(iteration=1), _row(iteration=2)]
    p = _assemble_payload("sess-001", rows)
    assert p.iteration == 2


# ---------------------------------------------------------------------------
# _load_session_replay — tenant_id WHERE clause (IDOR security test)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_load_session_replay_tenant_id_in_where_clause() -> None:
    """SECURITY: tenant_id must appear in the BQ WHERE clause (defense-in-depth).

    If this test fails, an attacker who knows a session_id can read another
    tenant's session data by omitting the tenant_id at the application layer.
    """
    mock_bq = MagicMock()
    mock_bq.query.return_value.result.return_value = []

    await _load_session_replay(
        "sess-001",
        tenant_id="tenant-target",
        bq_client=mock_bq,
    )

    mock_bq.query.assert_called_once()
    call_args = mock_bq.query.call_args
    sql: str = call_args[0][0]

    assert "tenant_id" in sql.lower(), "BUG: tenant_id not in SQL WHERE clause — IDOR vulnerability"
    assert "@tenant_id" in sql, (
        "BUG: tenant_id must be a parameterised placeholder, not interpolated"
    )


@pytest.mark.anyio
async def test_load_session_replay_without_tenant_id_no_tenant_filter() -> None:
    """When tenant_id is None, the query must NOT add a tenant filter.

    This is the admin / internal-use path. Callers that pass tenant_id=None
    must perform their own ownership check.
    """
    mock_bq = MagicMock()
    mock_bq.query.return_value.result.return_value = []

    await _load_session_replay("sess-001", tenant_id=None, bq_client=mock_bq)

    sql: str = mock_bq.query.call_args[0][0]
    assert "tenant_id" not in sql.lower()


@pytest.mark.anyio
async def test_load_session_replay_session_id_always_in_where() -> None:
    """session_id must always appear in the WHERE clause regardless of tenant_id."""
    mock_bq = MagicMock()
    mock_bq.query.return_value.result.return_value = []

    await _load_session_replay("my-session", tenant_id="t1", bq_client=mock_bq)

    sql: str = mock_bq.query.call_args[0][0]
    assert "@session_id" in sql


@pytest.mark.anyio
async def test_load_session_replay_returns_none_when_no_rows() -> None:
    mock_bq = MagicMock()
    mock_bq.query.return_value.result.return_value = []

    result = await _load_session_replay("sess-empty", bq_client=mock_bq)
    assert result is None


@pytest.mark.anyio
async def test_load_session_replay_fail_soft_on_bq_error() -> None:
    """BQ error must be caught and return None (fail-soft per PRD §21)."""
    mock_bq = MagicMock()
    mock_bq.query.side_effect = RuntimeError("BQ connection failed")

    result = await _load_session_replay("sess-001", bq_client=mock_bq)
    assert result is None


@pytest.mark.anyio
async def test_load_session_replay_returns_payload_on_success() -> None:
    mock_bq = MagicMock()
    mock_bq.query.return_value.result.return_value = [_row()]

    result = await _load_session_replay("sess-001", tenant_id="tenant-abc", bq_client=mock_bq)

    assert result is not None
    assert isinstance(result, SessionReplayPayload)
    assert result.session_id == "sess-001"
    assert result.tenant_id == "tenant-abc"


# ---------------------------------------------------------------------------
# get_replay endpoint — auth + ownership
# ---------------------------------------------------------------------------


@pytest.fixture
def app_client():
    """TestClient with FIREBASE_DISABLE_AUTH=true (dev bypass)."""
    with patch("atelier.auth.firebase._BYPASS_AUTH", True):
        app = FastAPI()
        app.include_router(router)
        yield TestClient(app, raise_server_exceptions=False)


def test_get_replay_returns_404_when_session_not_found(app_client: TestClient) -> None:
    with patch(
        "atelier.api.replay._load_session_replay",
        new=AsyncMock(return_value=None),
    ):
        resp = app_client.get("/v1/replay/nonexistent-session")
    assert resp.status_code == 404


def test_get_replay_returns_403_when_tenant_mismatch(app_client: TestClient) -> None:
    wrong_tenant_payload = SessionReplayPayload(
        session_id="sess-001",
        tenant_id="other-tenant",  # does not match dev user's tenant_id
        project_id="p",
        started_at="t",
        ended_at="t",
        outcome="accepted",
        composite_score=0.8,
    )
    with patch(
        "atelier.api.replay._load_session_replay",
        new=AsyncMock(return_value=wrong_tenant_payload),
    ):
        resp = app_client.get("/v1/replay/sess-001")
    assert resp.status_code == 403


def test_get_replay_returns_200_when_tenant_matches(app_client: TestClient) -> None:
    # Dev bypass user has tenant_id = "dev-tenant"
    correct_payload = SessionReplayPayload(
        session_id="sess-001",
        tenant_id="dev-tenant",
        project_id="p",
        started_at="t",
        ended_at="t",
        outcome="accepted",
        composite_score=0.8,
    )
    with patch(
        "atelier.api.replay._load_session_replay",
        new=AsyncMock(return_value=correct_payload),
    ):
        resp = app_client.get("/v1/replay/sess-001")
    assert resp.status_code == 200
    assert resp.json()["session_id"] == "sess-001"


def test_get_replay_passes_tenant_id_to_load_function(app_client: TestClient) -> None:
    """Verify the endpoint passes user.tenant_id into _load_session_replay."""
    load_mock = AsyncMock(return_value=None)
    with patch("atelier.api.replay._load_session_replay", new=load_mock):
        app_client.get("/v1/replay/sess-001")
    load_mock.assert_called_once()
    _, kwargs = load_mock.call_args
    assert kwargs.get("tenant_id") == "dev-tenant"
