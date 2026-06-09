"""Session and memory backend factory — managed Vertex vs offline (AT-080, B4).

Selects the ADK session service and memory service for a pipeline run from the
``SESSION_BACKEND`` environment variable, per PRD v2.2 §12 E8 (AT-080).

Backends:
    ``memory`` (default)
        ``InMemorySessionService`` + ``InMemoryMemoryService``. No network is
        contacted; this is the offline lane exercised by ``make verify`` and the
        unit suite. It is the default when ``SESSION_BACKEND`` is unset so that a
        misconfigured environment fails safe rather than issuing implicit Vertex
        calls.
    ``vertex``
        ``VertexAiSessionService`` + ``VertexAiMemoryBankService`` — the managed
        production lane (cross-instance resumption plus long-term memory).
        Requires an Agent Engine id (AT-082) and Application Default Credentials;
        production deployments set ``SESSION_BACKEND=vertex`` explicitly.
    ``bigquery``
        ``BigQuerySessionBackend`` — the legacy BigQuery-backed session store,
        retained for compatibility; paired with ``InMemoryMemoryService``.

Symbols verified against google-adk==2.1.0 (AT-002 pin):
    google.adk.sessions.InMemorySessionService()
    google.adk.sessions.VertexAiSessionService(project, location, agent_engine_id)
    google.adk.memory.InMemoryMemoryService()
    google.adk.memory.VertexAiMemoryBankService(project, location, agent_engine_id)

PRD Reference: §12 E8 (AT-080), §22 D5 (ADK pin)
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.adk.memory import BaseMemoryService
    from google.adk.sessions import BaseSessionService

    from atelier.memory.bigquery_backend import BigQueryEpisodicBackend

logger = logging.getLogger(__name__)

DEFAULT_BACKEND = "memory"
VALID_BACKENDS = ("memory", "vertex", "bigquery")
_DEFAULT_LOCATION = "us-central1"


def _resolve_backend(backend_name: str | None) -> str:
    """Resolve the effective backend name, validating it against VALID_BACKENDS.

    Args:
        backend_name: Explicit override, or ``None`` to read ``SESSION_BACKEND``.

    Returns:
        A lowercased backend name guaranteed to be in ``VALID_BACKENDS``.

    Raises:
        ValueError: If the resolved name is not a recognised backend.
    """
    backend = (backend_name or os.environ.get("SESSION_BACKEND", DEFAULT_BACKEND)).strip().lower()
    if backend not in VALID_BACKENDS:
        raise ValueError(f"Unknown SESSION_BACKEND={backend!r}; expected one of {VALID_BACKENDS}.")
    return backend


def _vertex_kwargs(
    project_id: str | None,
    location: str | None,
    agent_engine_id: str | None,
) -> dict[str, str | None]:
    """Resolve Vertex constructor kwargs from explicit args then the environment."""
    return {
        "project": project_id or os.environ.get("GOOGLE_CLOUD_PROJECT"),
        "location": location or os.environ.get("GOOGLE_CLOUD_LOCATION", _DEFAULT_LOCATION),
        "agent_engine_id": agent_engine_id or os.environ.get("AGENT_ENGINE_ID"),
    }


def create_session_service(
    backend_name: str | None = None,
    *,
    project_id: str | None = None,
    location: str | None = None,
    agent_engine_id: str | None = None,
) -> BaseSessionService:
    """Return the session service selected by ``SESSION_BACKEND``.

    Args:
        backend_name: Explicit backend override. When ``None`` the
            ``SESSION_BACKEND`` env var is read (default ``"memory"``).
        project_id: GCP project for the ``vertex`` backend. Falls back to
            ``GOOGLE_CLOUD_PROJECT``.
        location: Vertex location for the ``vertex`` backend. Falls back to
            ``GOOGLE_CLOUD_LOCATION`` then ``"us-central1"``.
        agent_engine_id: Agent Engine id (AT-082) for the ``vertex`` backend.
            Falls back to ``AGENT_ENGINE_ID``.

    Returns:
        A ``BaseSessionService`` implementation.

    Raises:
        ValueError: If the resolved backend name is not recognised.
    """
    backend = _resolve_backend(backend_name)

    if backend == "memory":
        from google.adk.sessions import InMemorySessionService  # noqa: PLC0415

        logger.info("session backend: InMemorySessionService (offline)")
        return InMemorySessionService()

    if backend == "vertex":
        from google.adk.sessions import VertexAiSessionService  # noqa: PLC0415

        kwargs = _vertex_kwargs(project_id, location, agent_engine_id)
        logger.info(
            "session backend: VertexAiSessionService (project=%s, location=%s)",
            kwargs["project"],
            kwargs["location"],
        )
        return VertexAiSessionService(**kwargs)

    from atelier.memory.bigquery_session import BigQuerySessionBackend  # noqa: PLC0415

    logger.info("session backend: BigQuerySessionBackend (legacy)")
    return BigQuerySessionBackend()


def create_memory_service(
    backend_name: str | None = None,
    *,
    project_id: str | None = None,
    location: str | None = None,
    agent_engine_id: str | None = None,
) -> BaseMemoryService:
    """Return the memory service selected by ``SESSION_BACKEND``.

    The ``memory`` and ``bigquery`` backends both use ``InMemoryMemoryService``
    (there is no BigQuery-backed memory bank); ``vertex`` uses the managed
    ``VertexAiMemoryBankService``.

    Args:
        backend_name: Explicit backend override. When ``None`` the
            ``SESSION_BACKEND`` env var is read (default ``"memory"``).
        project_id: GCP project for the ``vertex`` backend. Falls back to
            ``GOOGLE_CLOUD_PROJECT``.
        location: Vertex location for the ``vertex`` backend. Falls back to
            ``GOOGLE_CLOUD_LOCATION`` then ``"us-central1"``.
        agent_engine_id: Agent Engine id (AT-082) for the ``vertex`` backend.
            Falls back to ``AGENT_ENGINE_ID``.

    Returns:
        A ``BaseMemoryService`` implementation.

    Raises:
        ValueError: If the resolved backend name is not recognised.
    """
    backend = _resolve_backend(backend_name)

    if backend == "vertex":
        from google.adk.memory import VertexAiMemoryBankService  # noqa: PLC0415

        kwargs = _vertex_kwargs(project_id, location, agent_engine_id)
        logger.info(
            "memory backend: VertexAiMemoryBankService (project=%s, location=%s)",
            kwargs["project"],
            kwargs["location"],
        )
        return VertexAiMemoryBankService(**kwargs)

    from google.adk.memory import InMemoryMemoryService  # noqa: PLC0415

    logger.info("memory backend: InMemoryMemoryService (offline)")
    return InMemoryMemoryService()


def create_episodic_backend(
    backend_name: str | None = None,
    *,
    project_id: str | None = None,
) -> BigQueryEpisodicBackend | None:
    """Return the EPISODIC-tier backend selected by ``SESSION_BACKEND`` (ADR 0029).

    The episodic tier (BigQuery ``atelier_trajectories.session_events``) is a
    distinct subsystem from the ADK ``BaseMemoryService`` session/long-term
    memory returned by :func:`create_memory_service`; it is constructed here so
    the backend is reachable from the canonical factory rather than only in
    tests. The ``vertex`` and ``bigquery`` backends both persist episodic events
    to BigQuery; the offline ``memory`` backend has no episodic store and returns
    ``None`` (the caller skips episodic writes, matching the no-network lane).

    Args:
        backend_name: Explicit backend override. When ``None`` the
            ``SESSION_BACKEND`` env var is read (default ``"memory"``).
        project_id: GCP project for the BigQuery client. Falls back to
            ``GOOGLE_CLOUD_PROJECT``, then the backend's own default project.

    Returns:
        A ``BigQueryEpisodicBackend`` for the persisted backends, or ``None``
        for the offline ``memory`` backend.

    Raises:
        ValueError: If the resolved backend name is not recognised.
    """
    backend = _resolve_backend(backend_name)
    if backend == "memory":
        logger.info("episodic backend: none (offline memory lane)")
        return None

    from atelier.memory.bigquery_backend import BigQueryEpisodicBackend  # noqa: PLC0415

    project = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
    logger.info("episodic backend: BigQueryEpisodicBackend (project=%s)", project)
    if project is not None:
        return BigQueryEpisodicBackend(project=project)
    return BigQueryEpisodicBackend()
