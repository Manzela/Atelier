"""TrajectoryRecorder — BigQuery streaming insert writer for trajectory records.

Streams :class:`~atelier.nodes.trajectory.TrajectoryRecord` objects to the
``i-for-ai.atelier_trajectories.trajectory_records`` BigQuery table with:

    * Async context manager (``async with TrajectoryRecorder(...) as rec``)
    * Auto-flush on buffer size threshold or context manager exit
    * Idempotent writes via ``insertId`` (maps to ``record_id``)
    * OTel span emission per flush (``atelier.trajectory.flush``)
    * Failure-trichotomy compliant error handling

Auth: uses Application Default Credentials via ``google-cloud-bigquery``.
The BQ client is injected via constructor for testability.

PRD Reference: §6.3 N3h (Trajectory Logger)
Audit Reference: C6 (FA-011 TrajectoryRecorder class)
ADR Reference: 0006 (Google-native stack — BigQuery for telemetry)
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Protocol

from atelier.nodes.trajectory import (
    TrajectoryRecord,  # noqa: TC001  # runtime: buffer ops + to_bq_row()
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (PLR2004 compliance)
# ---------------------------------------------------------------------------

DEFAULT_TABLE_ID = "i-for-ai.atelier_trajectories.trajectory_records"
DEFAULT_BUFFER_SIZE = 50
SPAN_NAME = "atelier.trajectory.flush"


class TrajectoryRecorderError(Exception):
    """Raised on non-retriable BigQuery failures (auth, quota, schema).

    Per the failure-trichotomy (CLAUDE.md): fail-loud for errors that
    indicate a configuration or quota problem that won't self-heal.
    """


# ---------------------------------------------------------------------------
# Protocol for BigQuery client (testability)
# ---------------------------------------------------------------------------


class BigQueryClient(Protocol):
    """Minimal protocol for a BigQuery client.

    Allows the real ``google.cloud.bigquery.Client`` or a mock to be
    injected. Only the ``insert_rows_json`` method is required.
    """

    def insert_rows_json(
        self,
        table: str,
        json_rows: list[dict[str, Any]],
        *,
        row_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Insert rows as JSON into a BigQuery table.

        Args:
            table: Fully-qualified table ID.
            json_rows: List of row dictionaries.
            row_ids: Optional list of ``insertId`` values.

        Returns:
            List of errors (empty if all rows succeeded).
        """
        ...


# ---------------------------------------------------------------------------
# Tracer protocol (optional OTel integration)
# ---------------------------------------------------------------------------


class TracerProtocol(Protocol):
    """Minimal tracer interface for span emission."""

    def start_span(self, name: str, **kwargs: Any) -> Any:
        """Start a new span."""
        ...


class NoOpSpan:
    """No-op span for when OTel is not configured."""

    def __enter__(self) -> NoOpSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        """No-op attribute setter."""

    def end(self) -> None:
        """No-op end."""


class NoOpTracer:
    """No-op tracer for when OTel is not configured."""

    def start_span(self, name: str, **kwargs: Any) -> NoOpSpan:  # noqa: ARG002
        """Return a no-op span."""
        return NoOpSpan()


# ---------------------------------------------------------------------------
# TrajectoryRecorder
# ---------------------------------------------------------------------------


class TrajectoryRecorder:
    """BigQuery streaming insert writer for trajectory records.

    Usage::

        async with TrajectoryRecorder(bq_client) as rec:
            rec.record(trajectory_record)
            # auto-flushes at buffer_size or on context exit

    Args:
        bq_client: BigQuery client (real or mock).
        table_id: Fully-qualified BQ table ID.
        buffer_size: Flush threshold. Records are buffered until this
            count is reached, then flushed in a single insert.
        tracer: Optional OTel tracer for span emission.
    """

    def __init__(
        self,
        bq_client: BigQueryClient,
        *,
        table_id: str = DEFAULT_TABLE_ID,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        tracer: TracerProtocol | None = None,
    ) -> None:
        self._client = bq_client
        self._table_id = table_id
        self._buffer_size = buffer_size
        self._tracer = tracer or NoOpTracer()
        self._buffer: list[TrajectoryRecord] = []
        self._total_flushed: int = 0
        self._total_errors: int = 0

    # -- Context manager ---------------------------------------------------

    async def __aenter__(self) -> TrajectoryRecorder:
        """Enter the async context manager."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit the context manager, flushing remaining records."""
        if self._buffer:
            self.flush()

    # -- Public API --------------------------------------------------------

    def record(self, trajectory: TrajectoryRecord) -> None:
        """Buffer a trajectory record for later flush.

        Automatically flushes when the buffer reaches ``buffer_size``.

        Args:
            trajectory: The trajectory record to buffer.
        """
        self._buffer.append(trajectory)
        if len(self._buffer) >= self._buffer_size:
            self.flush()

    # Phase-1 scope: fail-loud only on BQ errors.
    # Self-heal (retry on 503/429) + fail-soft (partial-batch separation)
    # deferred to F0222 per audit Run 2 P1-3. Full trichotomy required for Phase-2 production.
    def flush(self) -> int:
        """Flush the buffer to BigQuery.

        Emits an OTel span ``atelier.trajectory.flush`` with attributes:
            - ``flush.row_count``: number of rows in this flush
            - ``flush.table_id``: target BQ table
            - ``flush.errors``: number of insert errors

        Returns:
            Number of rows successfully flushed.

        Raises:
            TrajectoryRecorderError: If BQ insert returns errors (fail-loud per
                failure-trichotomy).
        """
        if not self._buffer:
            return 0

        rows = [rec.to_bq_row() for rec in self._buffer]
        row_ids = [str(rec.trajectory_id) for rec in self._buffer]
        count = len(rows)

        span = self._tracer.start_span(SPAN_NAME)
        start = time.monotonic()

        try:
            errors = self._client.insert_rows_json(
                self._table_id,
                rows,
                row_ids=row_ids,
            )

            elapsed_ms = (time.monotonic() - start) * 1000

            if hasattr(span, "set_attribute"):
                span.set_attribute("flush.row_count", count)
                span.set_attribute("flush.table_id", self._table_id)
                span.set_attribute("flush.errors", len(errors))
                span.set_attribute("flush.elapsed_ms", elapsed_ms)

            if errors:
                self._total_errors += len(errors)
                logger.error(
                    "BQ insert errors (%d/%d rows): %s",
                    len(errors),
                    count,
                    errors,
                )
                msg = f"BQ insert had {len(errors)} errors: {errors}"
                raise TrajectoryRecorderError(msg)

            self._total_flushed += count
            self._buffer.clear()
            logger.info(
                "Flushed %d trajectory rows to %s (%.1fms)",
                count,
                self._table_id,
                elapsed_ms,
            )
            return count

        finally:
            if hasattr(span, "end"):
                span.end()

    @property
    def buffer_count(self) -> int:
        """Number of records currently buffered."""
        return len(self._buffer)

    @property
    def total_flushed(self) -> int:
        """Total records flushed since creation."""
        return self._total_flushed

    @property
    def total_errors(self) -> int:
        """Total BQ insert errors since creation."""
        return self._total_errors

    def make_insert_id(self) -> str:
        """Generate a unique insert ID for idempotency.

        Returns:
            UUID4 string suitable for BQ ``insertId``.
        """
        return str(uuid.uuid4())
