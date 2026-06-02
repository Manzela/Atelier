"""Unit tests for the AT-080 session and memory backend factory.

Verifies ``SESSION_BACKEND`` routing to the ADK session and memory services
(google-adk==2.1.0) with no network access. The Vertex services are constructed
with explicit project/location/agent_engine_id so no Application Default
Credentials lookup or RPC is triggered.

PRD Reference: §12 E8 (AT-080)
"""

from __future__ import annotations

import pytest
from atelier.orchestrator.backend_factory import (
    create_memory_service,
    create_session_service,
)

_VERTEX_KW = {"project_id": "test-proj", "location": "us-central1", "agent_engine_id": "123"}


def test_memory_backend_selects_in_memory_session_service() -> None:
    from google.adk.sessions import InMemorySessionService

    assert isinstance(create_session_service("memory"), InMemorySessionService)


def test_vertex_backend_selects_vertex_session_service() -> None:
    from google.adk.sessions import VertexAiSessionService

    assert isinstance(create_session_service("vertex", **_VERTEX_KW), VertexAiSessionService)


def test_bigquery_backend_selects_bigquery_session_backend() -> None:
    from atelier.memory.bigquery_session import BigQuerySessionBackend

    assert isinstance(create_session_service("bigquery"), BigQuerySessionBackend)


def test_unknown_session_backend_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown SESSION_BACKEND"):
        create_session_service("redis")


def test_env_var_selects_session_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    from google.adk.sessions import InMemorySessionService

    monkeypatch.setenv("SESSION_BACKEND", "memory")
    assert isinstance(create_session_service(), InMemorySessionService)


def test_default_session_backend_is_offline_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    from google.adk.sessions import InMemorySessionService

    monkeypatch.delenv("SESSION_BACKEND", raising=False)
    assert isinstance(create_session_service(), InMemorySessionService)


def test_memory_backend_selects_in_memory_memory_service() -> None:
    from google.adk.memory import InMemoryMemoryService

    assert isinstance(create_memory_service("memory"), InMemoryMemoryService)


def test_bigquery_backend_uses_in_memory_memory_service() -> None:
    from google.adk.memory import InMemoryMemoryService

    assert isinstance(create_memory_service("bigquery"), InMemoryMemoryService)


def test_vertex_backend_selects_vertex_memory_bank_service() -> None:
    from google.adk.memory import VertexAiMemoryBankService

    assert isinstance(create_memory_service("vertex", **_VERTEX_KW), VertexAiMemoryBankService)


def test_unknown_memory_backend_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown SESSION_BACKEND"):
        create_memory_service("redis")


def test_runner_wires_a_memory_service(monkeypatch: pytest.MonkeyPatch) -> None:
    # AT-080: the memory backend is consumed by the runner (not dead code).
    from atelier.orchestrator.runner import AtelierRunner
    from google.adk.memory import BaseMemoryService

    monkeypatch.delenv("SESSION_BACKEND", raising=False)
    runner = AtelierRunner()
    assert isinstance(runner._memory_service, BaseMemoryService)
