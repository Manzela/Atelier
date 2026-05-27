"""GET /v1/replay/{session_id} — Session Replay API.

Returns a SessionReplayPayload containing the full trajectory replay
for a given session, including:
    - Cloud Trace span graph (from BQ trajectory steps)
    - Memory Bank recalls (semantic + procedural)
    - AND-Gate scorecard (D-O-R-A-V per-axis scores)

PRD Reference: §7.1 (API surface), §6.3 (N3h trajectory)
AG-13 / Replay UI

BQ schema note: column names match TrajectoryRecord.to_bq_row() exactly.
    session_id, tenant_id, trajectory_id, node_name, ts (start), ended_at,
    composite_score, candidate_id, iteration, total_cost_usd,
    total_input_tokens, total_output_tokens, judge_votes_json (JSON str),
    gate_results_json (JSON str).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from atelier.auth.firebase import FirebaseUser, require_auth
from atelier.utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/v1/replay", tags=["replay"])

_DEFAULT_PROJECT: str = os.environ.get("GOOGLE_CLOUD_PROJECT", "atelier-build-2026")
_TRAJECTORY_TABLE: str = f"{_DEFAULT_PROJECT}.atelier_trajectories.trajectory_records"


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SpanNode(BaseModel):
    """A single span in the trace graph."""

    model_config = ConfigDict(frozen=True)

    span_id: str
    parent_span_id: str | None = None
    node_name: str
    started_at: str
    ended_at: str
    duration_ms: float
    model_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    status: str = "ok"


class MemoryRecall(BaseModel):
    """A memory recall event (semantic or procedural)."""

    model_config = ConfigDict(frozen=True)

    tier: str  # "semantic" | "procedural"
    query_text: str
    passage: str
    similarity: float
    source_event_ids: list[str] = []


class GateScore(BaseModel):
    """A single gate/judge score in the AND-Gate scorecard."""

    model_config = ConfigDict(frozen=True)

    axis: str
    score: float
    confidence_low: float
    confidence_high: float
    judge_model: str
    reasoning: str


class SessionReplayPayload(BaseModel):
    """Full replay payload for a session."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    tenant_id: str
    project_id: str
    started_at: str
    ended_at: str
    outcome: str
    composite_score: float
    degradation_reason: str | None = None
    user_message: str | None = None

    spans: list[SpanNode] = []
    memory_recalls: list[MemoryRecall] = []
    gate_scores: list[GateScore] = []

    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    candidate_count: int = 0
    iteration: int = 0


# ---------------------------------------------------------------------------
# Private helpers — extracted for C901 compliance
# ---------------------------------------------------------------------------


def _build_spans(rows: list[dict[str, Any]]) -> list[SpanNode]:
    """Build a list of SpanNode objects from trajectory record rows.

    Each row becomes one span. The span_id is the trajectory_id.
    Duration is not available from the trajectory_records schema
    (started_at and ended_at are stored but duration is not pre-computed);
    duration_ms is set to 0.0 and the UI computes it from timestamps.

    Args:
        rows: List of BQ row dictionaries (from trajectory_records).

    Returns:
        List of SpanNode, one per row, in the same order as rows.
    """
    spans: list[SpanNode] = []
    for row in rows:
        spans.append(
            SpanNode(
                span_id=str(row.get("trajectory_id", "")),
                parent_span_id=None,
                node_name=str(row.get("node_name", "unknown")),
                started_at=str(row.get("ts", "")),
                ended_at=str(row.get("ended_at", "")),
                duration_ms=0.0,
                model_id=None,
                input_tokens=int(row.get("total_input_tokens", 0)),
                output_tokens=int(row.get("total_output_tokens", 0)),
                cost_usd=float(row.get("total_cost_usd", 0.0)),
                status="ok",
            )
        )
    return spans


def _build_gate_scores(judge_votes_json_raw: str) -> list[GateScore]:
    """Parse judge_votes_json and build GateScore objects.

    The judge_votes_json column stores a JSON array of vote objects, each
    with keys: axis, score, confidence_interval (2-element list or str),
    judge_model, reasoning. Missing keys default to safe values.

    Args:
        judge_votes_json_raw: Raw JSON string from the judge_votes_json column.

    Returns:
        List of GateScore. Empty if the JSON is invalid or has no entries.
    """
    gate_scores: list[GateScore] = []
    try:
        parsed = json.loads(judge_votes_json_raw)
    except (json.JSONDecodeError, TypeError):
        return gate_scores

    if not isinstance(parsed, list):
        # "null", numbers, or bare objects are not valid vote arrays
        return gate_scores
    votes: list[dict[str, Any]] = parsed

    for vote in votes:
        if not isinstance(vote, dict) or "axis" not in vote:
            continue
        ci: list[float] = [0.0, 1.0]
        raw_ci = vote.get("confidence_interval", [0.0, 1.0])
        if isinstance(raw_ci, str):
            try:
                raw_ci = json.loads(raw_ci)
            except (json.JSONDecodeError, ValueError):
                raw_ci = [0.0, 1.0]
        if isinstance(raw_ci, list) and len(raw_ci) >= 2:  # noqa: PLR2004
            ci = [float(raw_ci[0]), float(raw_ci[1])]
        gate_scores.append(
            GateScore(
                axis=str(vote["axis"]),
                score=float(vote.get("score", 0.0)),
                confidence_low=ci[0],
                confidence_high=ci[1],
                judge_model=str(vote.get("judge_model", "unknown")),
                reasoning=str(vote.get("reasoning", "")),
            )
        )
    return gate_scores


# ---------------------------------------------------------------------------
# Data loading (BigQuery trajectory records)
# ---------------------------------------------------------------------------


async def _load_session_replay(
    session_id: str,
    tenant_id: str | None = None,
    bq_client: Any | None = None,
) -> SessionReplayPayload | None:
    """Load session replay data from BigQuery trajectory_records.

    Queries the trajectory_records table for all rows matching the given
    session_id (and optionally tenant_id for data-layer auth) and
    reconstructs a full SessionReplayPayload.

    Security: When tenant_id is provided, it is pushed into the SQL WHERE
    clause as a parameterised value — defense-in-depth on top of the
    application-level ownership check in get_replay(). The caller MUST
    still perform the application-level check.

    Fail-soft (PRD §21): Returns None if BigQuery is unavailable or the
    query fails — the endpoint returns 404.

    Args:
        session_id: Session to replay.
        tenant_id: Optional tenant ID for data-layer authorisation.
        bq_client: Optional pre-constructed BQ client (for testing). If None,
            a new google.cloud.bigquery.Client is created.

    Returns:
        SessionReplayPayload or None if not found / BQ unavailable.
    """
    try:
        from google.cloud import bigquery  # noqa: PLC0415
    except ImportError:
        logger.warning("BigQuery SDK not installed; replay unavailable")
        return None

    client = bq_client
    try:
        if client is None:
            project = os.environ.get("GOOGLE_CLOUD_PROJECT", "atelier-build-2026")
            client = bigquery.Client(project=project)

        # Parameterised WHERE — column names match TrajectoryRecord.to_bq_row()
        where = "WHERE session_id = @session_id"
        params: list[Any] = [
            bigquery.ScalarQueryParameter("session_id", "STRING", session_id),
        ]
        if tenant_id is not None:
            where += " AND tenant_id = @tenant_id"
            params.append(
                bigquery.ScalarQueryParameter("tenant_id", "STRING", tenant_id),
            )

        fqn = _TRAJECTORY_TABLE
        query = (
            f"SELECT * FROM `{fqn}` "  # noqa: S608
            f"{where} ORDER BY ts ASC"
        )
        job_config = bigquery.QueryJobConfig(query_parameters=params)
        rows = [dict(r) for r in client.query(query, job_config=job_config).result()]

        if not rows:
            logger.info(
                "No trajectory records found for session %s",
                sanitize(session_id),
            )
            return None

        return _assemble_payload(session_id, rows)

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to load replay from BQ (fail-soft): %s: %s",
            type(exc).__name__,
            sanitize(str(exc)[:200]),
        )
        return None


def _assemble_payload(
    session_id: str,
    rows: list[dict[str, Any]],
) -> SessionReplayPayload:
    """Assemble a SessionReplayPayload from a list of BQ row dicts.

    Extracted from _load_session_replay() for C901 compliance (complexity).

    Args:
        session_id: Session ID (used if the row is missing the field).
        rows: Non-empty list of BQ row dicts, ordered by ts ASC.

    Returns:
        Assembled SessionReplayPayload.
    """
    first, last = rows[0], rows[-1]

    spans = _build_spans(rows)

    # Gate scores come from the last record's judge_votes_json column.
    # Column name: "judge_votes_json" — matches TrajectoryRecord.to_bq_row().
    gate_scores = _build_gate_scores(str(last.get("judge_votes_json", "[]")))

    total_cost = sum(float(r.get("total_cost_usd", 0.0)) for r in rows)
    total_in = sum(int(r.get("total_input_tokens", 0)) for r in rows)
    total_out = sum(int(r.get("total_output_tokens", 0)) for r in rows)
    candidate_ids = {str(r.get("candidate_id", "")) for r in rows if r.get("candidate_id")}
    max_iter = max((int(r.get("iteration", 0)) for r in rows), default=0)

    payload = SessionReplayPayload(
        session_id=session_id,
        tenant_id=str(first.get("tenant_id", "")),
        project_id=str(first.get("project_id", "")),
        started_at=str(first.get("ts", "")),
        ended_at=str(last.get("ended_at", "")),
        outcome=str(last.get("outcome", "completed")),
        composite_score=float(last.get("composite_score", 0.0)),
        spans=spans,
        memory_recalls=[],  # Memory Bank recalls are a separate query surface
        gate_scores=gate_scores,
        total_cost_usd=total_cost,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        candidate_count=len(candidate_ids),
        iteration=max_iter,
    )
    logger.info(
        "Replay assembled for session %s: %d spans, %d gate scores, $%.4f cost",
        sanitize(session_id),
        len(spans),
        len(gate_scores),
        total_cost,
    )
    return payload


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/{session_id}",
    response_model=SessionReplayPayload,
    summary="Get session replay data",
    description="Returns the full trajectory replay for a session including "
    "span graph, memory recalls, and AND-Gate scorecard. Requires authentication.",
)
async def get_replay(
    session_id: str,
    user: Annotated[FirebaseUser, Depends(require_auth)],
) -> SessionReplayPayload:
    """Retrieve session replay data (authenticated).

    Raises:
        HTTPException(401): Unauthenticated caller.
        HTTPException(403): Session does not belong to the authenticated tenant.
        HTTPException(404): Session not found or BQ unavailable.
    """
    payload = await _load_session_replay(session_id, tenant_id=user.tenant_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id} not found or has no replay data.",
        )
    # Application-level ownership check — second layer of defense-in-depth
    if payload.tenant_id != user.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to view this session.",
        )
    return payload
