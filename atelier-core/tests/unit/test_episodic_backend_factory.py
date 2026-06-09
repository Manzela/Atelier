"""Unit tests for the episodic-tier backend factory (AT-080 / ADR 0029).

Verifies that ``create_episodic_backend`` is wired (not dead code): the
persisted backends construct a ``BigQueryEpisodicBackend`` and the offline
``memory`` lane returns ``None`` so episodic writes are skipped without network.
The BigQuery client is patched so no GCP credentials or RPC are required.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from atelier.orchestrator.backend_factory import create_episodic_backend


def test_memory_backend_has_no_episodic_store() -> None:
    assert create_episodic_backend("memory") is None


@patch("atelier.memory.bigquery_backend.bigquery.Client")
def test_vertex_backend_selects_bigquery_episodic_backend(mock_client: object) -> None:
    from atelier.memory.bigquery_backend import BigQueryEpisodicBackend

    backend = create_episodic_backend("vertex", project_id="proj-test")
    assert isinstance(backend, BigQueryEpisodicBackend)


@patch("atelier.memory.bigquery_backend.bigquery.Client")
def test_bigquery_backend_selects_bigquery_episodic_backend(mock_client: object) -> None:
    from atelier.memory.bigquery_backend import BigQueryEpisodicBackend

    backend = create_episodic_backend("bigquery", project_id="proj-test")
    assert isinstance(backend, BigQueryEpisodicBackend)


@patch("atelier.memory.bigquery_backend.bigquery.Client")
def test_env_var_selects_episodic_backend(
    mock_client: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from atelier.memory.bigquery_backend import BigQueryEpisodicBackend

    monkeypatch.setenv("SESSION_BACKEND", "vertex")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj-from-env")
    assert isinstance(create_episodic_backend(), BigQueryEpisodicBackend)


def test_unknown_backend_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown SESSION_BACKEND"):
        create_episodic_backend("redis")
