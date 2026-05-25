"""Unit tests for BigQueryEpisodicBackend (T8, spec §20.5)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from atelier.memory.bigquery_backend import BQ_SESSION_EVENTS_TABLE, BigQueryEpisodicBackend
from atelier.memory.key import CURRENT_MEMORY_KEY, MemoryKey
from atelier.memory.protocol import MemoryEvent


def _make_key(
    tenant_id: str = "tenant-xyz",
    project_id: str = "proj-abc",
    session_id: str = "sess-001",
) -> MemoryKey:
    return MemoryKey(tenant_id=tenant_id, project_id=project_id, session_id=session_id)


def _make_event(
    event_id: str = "evt-001",
    node_name: str = "N3a.generator",
    payload: dict[str, str | int | float | bool] | None = None,
) -> MemoryEvent:
    return MemoryEvent(
        event_id=event_id,
        occurred_at=datetime(2026, 5, 25, 12, 0, 0, tzinfo=UTC),
        node_name=node_name,
        payload=payload or {"score": 0.82, "iteration": 1},
        embedding=None,
    )


# ─── Constants ────────────────────────────────────────────────────────────────


def test_bq_table_points_to_correct_project() -> None:
    assert "atelier-build-2026" in BQ_SESSION_EVENTS_TABLE


def test_bq_table_points_to_session_events() -> None:
    assert "session_events" in BQ_SESSION_EVENTS_TABLE


# ─── fail-loud on missing MemoryKey ──────────────────────────────────────────


@pytest.mark.anyio
@patch("atelier.memory.bigquery_backend.bigquery.Client")
async def test_write_episodic_raises_lookup_error_when_no_key(
    mock_bq_cls: MagicMock,
) -> None:
    """LookupError must propagate if CURRENT_MEMORY_KEY is not bound."""
    mock_bq_cls.return_value = MagicMock()
    backend = BigQueryEpisodicBackend(project="atelier-build-2026")
    with pytest.raises(LookupError):
        await backend.write_episodic(_make_event())


# ─── happy path ───────────────────────────────────────────────────────────────


@pytest.mark.anyio
@patch("atelier.memory.bigquery_backend.bigquery.Client")
async def test_write_episodic_inserts_row_with_tenant_id(
    mock_bq_cls: MagicMock,
) -> None:
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.insert_rows_json.return_value = []

    key = _make_key(tenant_id="tenant-xyz")
    token = CURRENT_MEMORY_KEY.set(key)
    try:
        backend = BigQueryEpisodicBackend(project="atelier-build-2026")
        await backend.write_episodic(_make_event())
    finally:
        CURRENT_MEMORY_KEY.reset(token)

    rows = mock_client.insert_rows_json.call_args[0][1]
    assert rows[0]["tenant_id"] == "tenant-xyz"


@pytest.mark.anyio
@patch("atelier.memory.bigquery_backend.bigquery.Client")
async def test_write_episodic_inserts_row_with_session_id(
    mock_bq_cls: MagicMock,
) -> None:
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.insert_rows_json.return_value = []

    key = _make_key(session_id="sess-001")
    token = CURRENT_MEMORY_KEY.set(key)
    try:
        backend = BigQueryEpisodicBackend(project="atelier-build-2026")
        await backend.write_episodic(_make_event())
    finally:
        CURRENT_MEMORY_KEY.reset(token)

    rows = mock_client.insert_rows_json.call_args[0][1]
    assert rows[0]["session_id"] == "sess-001"


@pytest.mark.anyio
@patch("atelier.memory.bigquery_backend.bigquery.Client")
async def test_write_episodic_inserts_row_with_all_required_fields(
    mock_bq_cls: MagicMock,
) -> None:
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.insert_rows_json.return_value = []

    key = _make_key()
    token = CURRENT_MEMORY_KEY.set(key)
    try:
        backend = BigQueryEpisodicBackend(project="atelier-build-2026")
        await backend.write_episodic(_make_event(event_id="evt-999", node_name="N5.judge"))
    finally:
        CURRENT_MEMORY_KEY.reset(token)

    row = mock_client.insert_rows_json.call_args[0][1][0]
    assert row["event_id"] == "evt-999"
    assert row["node_name"] == "N5.judge"
    assert row["tenant_id"] == "tenant-xyz"
    assert row["project_id"] == "proj-abc"
    assert row["session_id"] == "sess-001"
    assert "occurred_at" in row
    assert "payload" in row


@pytest.mark.anyio
@patch("atelier.memory.bigquery_backend.bigquery.Client")
async def test_write_episodic_payload_is_json_string(mock_bq_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.insert_rows_json.return_value = []

    key = _make_key()
    token = CURRENT_MEMORY_KEY.set(key)
    try:
        backend = BigQueryEpisodicBackend(project="atelier-build-2026")
        await backend.write_episodic(_make_event(payload={"score": 0.82, "ok": True}))
    finally:
        CURRENT_MEMORY_KEY.reset(token)

    row = mock_client.insert_rows_json.call_args[0][1][0]
    payload = json.loads(row["payload"])
    assert "score" in payload
    assert "ok" in payload


@pytest.mark.anyio
@patch("atelier.memory.bigquery_backend.bigquery.Client")
async def test_write_episodic_inserts_to_correct_table(mock_bq_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.insert_rows_json.return_value = []

    key = _make_key()
    token = CURRENT_MEMORY_KEY.set(key)
    try:
        backend = BigQueryEpisodicBackend(project="atelier-build-2026")
        await backend.write_episodic(_make_event())
    finally:
        CURRENT_MEMORY_KEY.reset(token)

    table_arg = mock_client.insert_rows_json.call_args[0][0]
    assert table_arg == BQ_SESSION_EVENTS_TABLE


@pytest.mark.anyio
@patch("atelier.memory.bigquery_backend.bigquery.Client")
async def test_write_episodic_raises_runtime_error_on_bq_errors(
    mock_bq_cls: MagicMock,
) -> None:
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.insert_rows_json.return_value = [{"errors": [{"reason": "backendError"}]}]

    key = _make_key()
    token = CURRENT_MEMORY_KEY.set(key)
    try:
        backend = BigQueryEpisodicBackend(project="atelier-build-2026")
        with pytest.raises(RuntimeError, match="insert_rows_json failed"):
            await backend.write_episodic(_make_event())
    finally:
        CURRENT_MEMORY_KEY.reset(token)


@pytest.mark.anyio
@patch("atelier.memory.bigquery_backend.bigquery.Client")
async def test_write_episodic_embedding_not_written_to_bq(mock_bq_cls: MagicMock) -> None:
    """Embedding vector is never written to BQ — only to Vertex Memory Bank."""
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.insert_rows_json.return_value = []

    key = _make_key()
    token = CURRENT_MEMORY_KEY.set(key)
    try:
        backend = BigQueryEpisodicBackend(project="atelier-build-2026")
        await backend.write_episodic(_make_event())
    finally:
        CURRENT_MEMORY_KEY.reset(token)

    row = mock_client.insert_rows_json.call_args[0][1][0]
    assert "embedding" not in row


@pytest.mark.anyio
@patch("atelier.memory.bigquery_backend.bigquery.Client")
async def test_write_episodic_tenant_isolation_different_keys(
    mock_bq_cls: MagicMock,
) -> None:
    """Two sequential writes with different keys write different tenant_ids."""
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.insert_rows_json.return_value = []

    backend = BigQueryEpisodicBackend(project="atelier-build-2026")

    key_a = _make_key(tenant_id="tenant-A")
    token = CURRENT_MEMORY_KEY.set(key_a)
    try:
        await backend.write_episodic(_make_event(event_id="evt-A"))
    finally:
        CURRENT_MEMORY_KEY.reset(token)

    key_b = _make_key(tenant_id="tenant-B")
    token = CURRENT_MEMORY_KEY.set(key_b)
    try:
        await backend.write_episodic(_make_event(event_id="evt-B"))
    finally:
        CURRENT_MEMORY_KEY.reset(token)

    calls = mock_client.insert_rows_json.call_args_list
    tenant_a_row = calls[0][0][1][0]
    tenant_b_row = calls[1][0][1][0]
    assert tenant_a_row["tenant_id"] == "tenant-A"
    assert tenant_b_row["tenant_id"] == "tenant-B"
    assert tenant_a_row["event_id"] == "evt-A"
    assert tenant_b_row["event_id"] == "evt-B"
