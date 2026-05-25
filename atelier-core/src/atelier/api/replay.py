"""GET /v1/replay/{session_id} — Session Replay API.

Returns a SessionReplayPayload containing the full trajectory replay
for a given session, including:
    - Cloud Trace span graph (from BQ trajectory steps)
    - Memory Bank recalls (semantic + procedural)
    - AND-Gate scorecard (D-O-R-A-V per-axis scores)

PRD Reference: §7.1 (API surface), §6.3 (N3h trajectory)
AG-13 / Replay UI
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from atelier.auth.firebase import FirebaseUser, require_auth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/replay", tags=["replay"])


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
    """Full replay payload for a session.

    Contains everything needed to reconstruct the pipeline execution:
        - Trace graph (spans)
        - Memory recalls
        - AND-Gate scorecard
        - Summary metrics
    """

    model_config = ConfigDict(frozen=True)

    session_id: str
    tenant_id: str
    project_id: str
    started_at: str
    ended_at: str
    outcome: str
    composite_score: float

    # Trace graph
    spans: list[SpanNode] = []

    # Memory recalls
    memory_recalls: list[MemoryRecall] = []

    # AND-Gate scorecard
    gate_scores: list[GateScore] = []

    # Summary
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    candidate_count: int = 0
    iteration: int = 0


# ---------------------------------------------------------------------------
# Data loading (stub — production reads from BQ)
# ---------------------------------------------------------------------------


async def _load_session_replay(session_id: str) -> SessionReplayPayload | None:
    """Load session replay data from BigQuery.

    Phase 1 stub — returns None (no data).
    Production implementation will query:
        - atelier_trajectories.trajectory_records
        - atelier_trajectories.session_events
        - Cloud Trace API for span graph

    Args:
        session_id: Session to replay.

    Returns:
        SessionReplayPayload or None if session not found.
    """
    # TODO(phase-2): Replace with BigQuery + Cloud Trace queries
    logger.info("Replay requested for session %s (stub — no data)", session_id)
    return None


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

    Args:
        session_id: The session ID to replay. Must belong to the authenticated user.
        user: Verified Firebase user (from Authorization: Bearer header).

    Returns:
        SessionReplayPayload with trace graph, memory recalls, and scorecard.

    Raises:
        HTTPException(401): When the caller is unauthenticated.
        HTTPException(403): When the session does not belong to the caller.
        HTTPException(404): When the session is not found.
    """
    payload = await _load_session_replay(session_id)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session {session_id} not found or has no replay data.",
        )
    # Ownership check: prevent cross-user session enumeration
    if payload.tenant_id != user.tenant_id:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to view this session.",
        )
    return payload
