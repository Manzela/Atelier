from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from atelier.nodes.trajectory import TrajectoryRecord
from atelier.recorders.trajectory_recorder import TrajectoryRecorder


@pytest.mark.anyio
async def test_trajectory_recorder_buffers_and_flushes() -> None:
    """Verify records buffer until threshold then flush to BQ (mocked client)."""
    mock_bq = MagicMock()
    mock_bq.insert_rows_json.return_value = []  # No errors

    record = TrajectoryRecord(
        trajectory_id=uuid4(),
        surface_id=uuid4(),
        tenant_id="tenant-123",
        project_id="proj-123",
        session_id="sess-123",
        campaign_id="camp-123",
        candidate_id=uuid4(),
        iteration=0,
        started_at=datetime.now(tz=UTC),
        ended_at=datetime.now(tz=UTC),
        outcome="accepted",
        composite_score=0.85,
    )

    async with TrajectoryRecorder(mock_bq, buffer_size=2) as rec:
        rec.record(record)
        assert rec.buffer_count == 1
        assert mock_bq.insert_rows_json.call_count == 0

        rec.record(record)
        assert rec.buffer_count == 0
        assert mock_bq.insert_rows_json.call_count == 1

        args, _kwargs = mock_bq.insert_rows_json.call_args
        assert args[0] == "atelier-build-2026.atelier_trajectories.trajectory_records"
        assert len(args[1]) == 2

        # Test flush on exit
        rec.record(record)
        assert rec.buffer_count == 1

    # Should flush remaining 1 record on exit
    assert mock_bq.insert_rows_json.call_count == 2
    args, _kwargs = mock_bq.insert_rows_json.call_args
    assert len(args[1]) == 1
