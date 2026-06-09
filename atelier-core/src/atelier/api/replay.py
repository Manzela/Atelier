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

import asyncio
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


def _make_bq_client() -> Any:
    """Construct a BigQuery client, or return None if the SDK is unavailable.

    Extracted so callers (and the AT-027 evaluate endpoint, which writes the
    rows this module reads) share one client factory that is trivially
    patchable in tests. Returns None — not raising — when the optional
    ``google-cloud-bigquery`` extra is not installed, so the replay endpoint
    degrades to 404 (fail-soft, PRD §21) rather than 500.
    """
    try:
        from google.cloud import bigquery  # noqa: PLC0415  # type: ignore[attr-defined]
    except ImportError:
        logger.warning("BigQuery SDK not installed; replay unavailable")
        return None
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "atelier-build-2026")
    return bigquery.Client(project=project)


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


class RouteDecisionView(BaseModel):
    """Read-only view of a MoE ``RouteDecision`` (AT-027).

    Surfaces the router's phase-aware expert choice for trace legibility.
    Mirrors ``atelier.router.protocol.RouteDecision`` fields that are safe to
    expose (no internal ``span_attrs`` mutation surface beyond a flat map).
    """

    model_config = ConfigDict(frozen=True)

    expert: str
    phase: str
    score: float
    rationale: str
    fallback_chain: list[str] = []
    routing_mode: str


class DreamingArtifactView(BaseModel):
    """Read-only view of a dreaming / DPO ``ExtractedPair`` (AT-027).

    Surfaces one preference pair the dreaming module would feed the DPO
    flywheel — the chosen vs rejected candidate and the margin between them.
    The ``chosen_score`` already reflects the anti-sycophancy reward rule
    (§3.6) applied at extraction time.
    """

    model_config = ConfigDict(frozen=True)

    surface_id: str
    node_name: str
    chosen_score: float
    rejected_score: float
    margin: float


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

    # AT-027: read-only optimize-asset surfaces threaded through the trace.
    route_decisions: list[RouteDecisionView] = []
    dreaming_artifacts: list[DreamingArtifactView] = []

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


def _build_route_decisions(rows: list[dict[str, Any]]) -> list[RouteDecisionView]:
    """Hydrate read-only RouteDecisionView objects from trajectory rows (AT-027).

    Each row may carry a ``route_decisions_json`` column: a JSON array of
    route-decision dicts written by the /v1/evaluate endpoint. Malformed or
    absent columns are skipped silently (fail-soft — the optimize surface is
    additive and must never break a replay).

    Args:
        rows: List of BQ row dictionaries (ordered by ts ASC).

    Returns:
        Flattened list of RouteDecisionView across all rows, in row order.
    """
    out: list[RouteDecisionView] = []
    for row in rows:
        raw = row.get("route_decisions_json")
        if not raw:
            continue
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(parsed, list):
            continue
        for d in parsed:
            if not isinstance(d, dict) or "expert" not in d:
                continue
            chain = d.get("fallback_chain", [])
            out.append(
                RouteDecisionView(
                    expert=str(d["expert"]),
                    phase=str(d.get("phase", "")),
                    score=float(d.get("score", 0.0)),
                    rationale=str(d.get("rationale", "")),
                    fallback_chain=[str(e) for e in chain] if isinstance(chain, list) else [],
                    routing_mode=str(d.get("routing_mode", "")),
                )
            )
    return out


def _build_dreaming_artifacts(rows: list[dict[str, Any]]) -> list[DreamingArtifactView]:
    """Hydrate read-only DreamingArtifactView objects from trajectory rows (AT-027).

    Each row may carry a ``dreaming_artifacts_json`` column: a JSON array of
    DPO-pair dicts written by the /v1/evaluate endpoint. Malformed or absent
    columns are skipped (fail-soft).

    Args:
        rows: List of BQ row dictionaries (ordered by ts ASC).

    Returns:
        Flattened list of DreamingArtifactView across all rows, in row order.
    """
    out: list[DreamingArtifactView] = []
    for row in rows:
        raw = row.get("dreaming_artifacts_json")
        if not raw:
            continue
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(parsed, list):
            continue
        for d in parsed:
            if not isinstance(d, dict) or "surface_id" not in d:
                continue
            out.append(
                DreamingArtifactView(
                    surface_id=str(d["surface_id"]),
                    node_name=str(d.get("node_name", "")),
                    chosen_score=float(d.get("chosen_score", 0.0)),
                    rejected_score=float(d.get("rejected_score", 0.0)),
                    margin=float(d.get("margin", 0.0)),
                )
            )
    return out


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
        from google.cloud import bigquery  # noqa: PLC0415  # type: ignore[attr-defined]
    except ImportError:
        logger.warning("BigQuery SDK not installed; replay unavailable")
        return None

    client = bq_client if bq_client is not None else _make_bq_client()
    if client is None:
        return None
    try:
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
        query_job = client.query(query, job_config=job_config)
        loop = asyncio.get_running_loop()
        result_rows = await loop.run_in_executor(None, query_job.result)
        rows = [dict(r) for r in result_rows]

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

    # AT-027: read-only optimize-asset surfaces (MoE routing + dreaming/DPO).
    route_decisions = _build_route_decisions(rows)
    dreaming_artifacts = _build_dreaming_artifacts(rows)

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
        route_decisions=route_decisions,
        dreaming_artifacts=dreaming_artifacts,
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
# Recent-runs list (tenant-scoped) — backs the /v1/platform/optimize surface
# ---------------------------------------------------------------------------


class RecentRun(BaseModel):
    """One row of the tenant's recent-runs list (a compact replay header).

    A deliberately small projection of the latest record per session — enough
    for a list row that deep-links to ``/v1/replay/{session_id}`` for the full
    trajectory. The optimize surface that consumes this does NOT claim spend
    caps are enforced (RR-05 is not fixed); these are read-only telemetry rows.
    """

    model_config = ConfigDict(frozen=True)

    session_id: str
    ended_at: str
    outcome: str
    composite_score: float
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    iteration: int
    replay_url: str


async def list_recent_runs(
    tenant_id: str,
    limit: int = 20,
    *,
    bq_client: Any | None = None,
) -> list[RecentRun] | None:
    """Return the tenant's most recent runs (one row per session), or None.

    Tenant-scoped by construction: ``tenant_id`` is pushed into the SQL WHERE
    clause as a parameterised value — never interpolated, never client-trusted
    (the caller takes it from the verified ``FirebaseUser.tenant_id``). One row
    is emitted per session (the latest trajectory record by ``ts``), newest
    first, capped at ``limit``.

    Fail-soft (PRD §21): returns ``None`` — never raises, never 500s — when the
    BigQuery SDK is absent or the query fails, so the optimize surface degrades
    to ``{"available": false, ...}`` rather than erroring. The returned cost
    figures are observed telemetry, NOT an enforced budget (RR-05 open).

    Args:
        tenant_id: The verified tenant id (from the authed JWT).
        limit: Max number of session rows to return (clamped to [1, 100]).
        bq_client: Optional pre-constructed BQ client (test injection).

    Returns:
        A list of :class:`RecentRun` (possibly empty), or ``None`` if BQ is
        unavailable / the query failed.
    """
    try:
        from google.cloud import bigquery  # noqa: PLC0415  # type: ignore[attr-defined]
    except ImportError:
        logger.warning("BigQuery SDK not installed; recent-runs unavailable")
        return None

    client = bq_client if bq_client is not None else _make_bq_client()
    if client is None:
        return None

    capped = max(1, min(int(limit), 100))
    try:
        # One row per session: the latest trajectory record (by ts) per
        # session_id, scoped to the tenant. Parameterised throughout.
        fqn = _TRAJECTORY_TABLE
        query = (
            "SELECT t.* FROM ("  # noqa: S608
            f"  SELECT *, ROW_NUMBER() OVER ("
            "    PARTITION BY session_id ORDER BY ts DESC"
            "  ) AS _rn"
            f"  FROM `{fqn}` WHERE tenant_id = @tenant_id"
            ") AS t WHERE t._rn = 1 "
            "ORDER BY t.ts DESC LIMIT @limit"
        )
        params: list[Any] = [
            bigquery.ScalarQueryParameter("tenant_id", "STRING", tenant_id),
            bigquery.ScalarQueryParameter("limit", "INT64", capped),
        ]
        job_config = bigquery.QueryJobConfig(query_parameters=params)
        query_job = client.query(query, job_config=job_config)
        loop = asyncio.get_running_loop()
        result_rows = await loop.run_in_executor(None, query_job.result)
        rows = [dict(r) for r in result_rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to list recent runs from BQ (fail-soft): %s: %s",
            type(exc).__name__,
            sanitize(str(exc)[:200]),
        )
        return None

    runs: list[RecentRun] = []
    for row in rows:
        session_id = str(row.get("session_id", ""))
        runs.append(
            RecentRun(
                session_id=session_id,
                ended_at=str(row.get("ended_at", "")),
                outcome=str(row.get("outcome", "completed")),
                composite_score=float(row.get("composite_score", 0.0)),
                total_cost_usd=float(row.get("total_cost_usd", 0.0)),
                total_input_tokens=int(row.get("total_input_tokens", 0)),
                total_output_tokens=int(row.get("total_output_tokens", 0)),
                iteration=int(row.get("iteration", 0)),
                replay_url=f"/v1/replay/{session_id}",
            )
        )
    return runs


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
