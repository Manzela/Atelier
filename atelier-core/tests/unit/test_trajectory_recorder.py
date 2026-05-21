"""Tests for TrajectoryRecorder BigQuery streaming writer (C6, FA-011).

7 tests with mocked BQ client covering:
    - record + manual flush
    - auto-flush at buffer_size threshold
    - async context manager auto-flush on exit
    - flush with BQ errors raises TrajectoryRecorderError
    - OTel span emission on flush
    - empty flush returns 0
    - insert_id idempotency (trajectory_id used as row_id)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from atelier.nodes.trajectory import TrajectoryRecord, TrajectoryStep
from atelier.recorders.trajectory_recorder import (
    DEFAULT_TABLE_ID,
    SPAN_NAME,
    TrajectoryRecorder,
    TrajectoryRecorderError,
)

# ---------------------------------------------------------------------------
# Constants (PLR2004 compliance)
# ---------------------------------------------------------------------------

BUFFER_SIZE = 3
SINGLE_RECORD = 1
TWO_RECORDS = 2
ZERO_RECORDS = 0
LARGE_BUFFER = 100


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_NOW = datetime.now(tz=UTC)


def _make_step(name: str = "n3a_generator") -> TrajectoryStep:
    """Create a minimal TrajectoryStep matching the actual schema."""
    return TrajectoryStep(
        step_name=name,
        step_index=0,
        started_at=_NOW,
        ended_at=_NOW,
        input_summary="test input",
        output_summary="test output",
    )


def _make_record() -> TrajectoryRecord:
    """Create a minimal TrajectoryRecord matching the actual schema."""
    return TrajectoryRecord(
        trajectory_id=uuid4(),
        tenant_id="test-tenant",
        project_id="test-project",
        surface_id=uuid4(),
        session_id="test-session",
        campaign_id="test-campaign",
        candidate_id=uuid4(),
        iteration=0,
        started_at=_NOW,
        ended_at=_NOW,
        outcome="accepted",
        composite_score=0.85,
        steps=(_make_step(),),
    )


def _mock_bq_client(*, errors: list[dict[str, Any]] | None = None) -> MagicMock:
    """Create a mock BQ client."""
    mock = MagicMock()
    mock.insert_rows_json.return_value = errors or []
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRecordAndFlush:
    """Manual record + flush cycle."""

    def test_record_and_flush(self) -> None:
        bq = _mock_bq_client()
        rec = TrajectoryRecorder(bq, buffer_size=LARGE_BUFFER)
        record = _make_record()
        rec.record(record)
        assert rec.buffer_count == SINGLE_RECORD
        flushed = rec.flush()
        assert flushed == SINGLE_RECORD
        assert rec.buffer_count == ZERO_RECORDS
        assert rec.total_flushed == SINGLE_RECORD
        bq.insert_rows_json.assert_called_once()
        call_args = bq.insert_rows_json.call_args
        assert call_args[0][0] == DEFAULT_TABLE_ID


@pytest.mark.unit
class TestAutoFlush:
    """Auto-flush when buffer reaches threshold."""

    def test_auto_flushes_at_buffer_size(self) -> None:
        bq = _mock_bq_client()
        rec = TrajectoryRecorder(bq, buffer_size=BUFFER_SIZE)
        for _ in range(BUFFER_SIZE):
            rec.record(_make_record())
        # Should have auto-flushed
        assert rec.buffer_count == ZERO_RECORDS
        assert rec.total_flushed == BUFFER_SIZE
        bq.insert_rows_json.assert_called_once()


@pytest.mark.unit
class TestContextManagerFlush:
    """Async context manager flushes remaining buffer on exit."""

    def test_context_exit_flushes(self) -> None:
        bq = _mock_bq_client()

        async def _run() -> TrajectoryRecorder:
            async with TrajectoryRecorder(bq, buffer_size=LARGE_BUFFER) as rec:
                rec.record(_make_record())
                rec.record(_make_record())
                assert rec.buffer_count == TWO_RECORDS
            return rec

        rec = asyncio.run(_run())
        assert rec.buffer_count == ZERO_RECORDS
        assert rec.total_flushed == TWO_RECORDS


@pytest.mark.unit
class TestFlushWithErrors:
    """BQ insert errors raise TrajectoryRecorderError (fail-loud)."""

    def test_bq_errors_raise(self) -> None:
        bq = _mock_bq_client(errors=[{"index": 0, "errors": [{"reason": "invalid"}]}])
        rec = TrajectoryRecorder(bq, buffer_size=LARGE_BUFFER)
        rec.record(_make_record())
        with pytest.raises(TrajectoryRecorderError, match="BQ insert had 1 errors"):
            rec.flush()
        assert rec.total_errors == SINGLE_RECORD


@pytest.mark.unit
class TestOTelSpanEmission:
    """OTel span is emitted on flush with correct attributes."""

    def test_span_emitted_with_attributes(self) -> None:
        bq = _mock_bq_client()
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_tracer = MagicMock()
        mock_tracer.start_span.return_value = mock_span
        rec = TrajectoryRecorder(
            bq,
            buffer_size=LARGE_BUFFER,
            tracer=mock_tracer,
        )
        rec.record(_make_record())
        rec.flush()
        mock_tracer.start_span.assert_called_once_with(SPAN_NAME)
        # Check span attributes were set
        attr_calls = {call.args[0]: call.args[1] for call in mock_span.set_attribute.call_args_list}
        assert attr_calls["flush.row_count"] == SINGLE_RECORD
        assert attr_calls["flush.table_id"] == DEFAULT_TABLE_ID
        assert attr_calls["flush.errors"] == ZERO_RECORDS
        assert "flush.elapsed_ms" in attr_calls
        mock_span.end.assert_called_once()


@pytest.mark.unit
class TestEmptyFlush:
    """Flush with empty buffer returns 0."""

    def test_empty_flush_returns_zero(self) -> None:
        bq = _mock_bq_client()
        rec = TrajectoryRecorder(bq, buffer_size=BUFFER_SIZE)
        assert rec.flush() == ZERO_RECORDS
        bq.insert_rows_json.assert_not_called()


@pytest.mark.unit
class TestInsertIdIdempotency:
    """Insert IDs are passed as row_ids for BQ idempotency."""

    def test_row_ids_match_trajectory_ids(self) -> None:
        bq = _mock_bq_client()
        rec = TrajectoryRecorder(bq, buffer_size=LARGE_BUFFER)
        record = _make_record()
        rec.record(record)
        rec.flush()
        call_kwargs = bq.insert_rows_json.call_args
        row_ids = call_kwargs[1]["row_ids"]
        assert row_ids == [str(record.trajectory_id)]
