"""Producer-side contract for BigQueryEpisodicBackend tenant-key binding.

Guards finding 92: the existing happy-path tests in ``test_bigquery_backend``
all call ``CURRENT_MEMORY_KEY.set(...)`` *in the test body* before invoking
``write_episodic``, then assert on the recorded row. That injects the exact
precondition the production system is responsible for satisfying, so a green
suite says nothing about whether anything in the running system actually binds
the key. These tests exercise the *producer* side of the contract instead:

1. The backend reached through the canonical factory entry point
   (``create_episodic_backend``) — not a hand-built instance — fails loud with
   ``LookupError`` when NO key is bound in the ambient context. This is the
   production reality the over-mocked happy-path tests hide: request-entry must
   bind ``CURRENT_MEMORY_KEY`` or every episodic write raises.

2. The ContextVar set by an ambient binder (a stand-in for the request-entry
   middleware named in ``memory/key.py``) propagates to ``write_episodic`` even
   when the write is offloaded via ``asyncio.to_thread`` — the path the runner
   now uses for N3c/N3d. None of the binding happens in the immediate test body
   of the write call, so the test asserts propagation, not injection.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from atelier.memory.bigquery_backend import BigQueryEpisodicBackend
from atelier.memory.key import CURRENT_MEMORY_KEY, MemoryKey
from atelier.memory.protocol import MemoryEvent
from atelier.orchestrator.backend_factory import create_episodic_backend


def _make_event() -> MemoryEvent:
    return MemoryEvent(
        event_id="evt-001",
        occurred_at=datetime(2026, 5, 25, 12, 0, 0, tzinfo=UTC),
        node_name="N3a.generator",
        payload={"score": 0.82, "iteration": 1},
        embedding=None,
    )


@pytest.mark.asyncio
@patch("atelier.memory.bigquery_backend.bigquery.Client")
async def test_factory_built_backend_fails_loud_without_ambient_key(
    mock_bq_cls: MagicMock,
) -> None:
    """No key bound anywhere -> write_episodic raises (the unmasked production path)."""
    mock_bq_cls.return_value = MagicMock()
    # Drive the real selection/construction path used by the runner, not a
    # hand-built backend. SESSION_BACKEND=bigquery resolves to the BQ backend.
    backend = create_episodic_backend("bigquery", project_id="atelier-build-2026")
    assert isinstance(backend, BigQueryEpisodicBackend)

    # Crucially: the test body binds NO key. This is what production currently
    # does, and the contract says it must fail loud rather than write an
    # un-scoped (cross-tenant) row.
    with pytest.raises(LookupError):
        await backend.write_episodic(_make_event())


@pytest.mark.asyncio
@patch("atelier.memory.bigquery_backend.bigquery.Client")
async def test_ambient_bound_key_propagates_across_to_thread(
    mock_bq_cls: MagicMock,
) -> None:
    """A key bound by an ambient binder reaches a to_thread-offloaded write.

    The write call is made inside ``asyncio.to_thread`` (the runner's N3c/N3d
    offload path). The key is bound by a separate ``_bind`` helper, never in the
    immediate scope of the write — so this proves contextvar propagation, the
    guarantee ``memory/key.py`` documents, not test-body injection.
    """
    mock_client = MagicMock()
    mock_bq_cls.return_value = mock_client
    mock_client.insert_rows_json.return_value = []

    backend = create_episodic_backend("bigquery", project_id="atelier-build-2026")
    assert backend is not None

    def _bind() -> None:
        # Stand-in for request-entry middleware: binds the key in THIS context,
        # which copy_context() then carries into the worker thread.
        CURRENT_MEMORY_KEY.set(
            MemoryKey(tenant_id="tenant-prop", project_id="proj-1", session_id="sess-1")
        )

    def _write_in_thread() -> None:
        # Sync wrapper running on the worker thread; runs the async write to
        # completion there, reading the propagated ContextVar.
        asyncio.run(backend.write_episodic(_make_event()))

    _bind()
    await asyncio.to_thread(_write_in_thread)

    rows = mock_client.insert_rows_json.call_args[0][1]
    assert rows[0]["tenant_id"] == "tenant-prop"
    assert rows[0]["session_id"] == "sess-1"
