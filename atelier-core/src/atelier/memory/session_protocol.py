"""SessionBackend Protocol — ADK 2.0 session service abstraction (CL-01, B4).

Replaces ``InMemoryRunner`` (which bundles ``InMemorySessionService``) with an
explicit Protocol that ``VertexAiSessionService`` satisfies without runner changes.

The Protocol mirrors the two methods used by ``AtelierRunner``:
    create_session — called once at the start of each pipeline run
    get_session    — called on resume (multi-turn, replay UI)

ADK 2.0 contract (google-adk==2.0.0):
    ``from google.adk.sessions import VertexAiSessionService`` satisfies this
    Protocol structurally — it is ``@runtime_checkable`` so isinstance() works.

BigQuery implementation (AG-07):
    ``BigQuerySessionBackend`` in ``atelier.memory.bigquery_session`` implements
    this Protocol and can be injected into ``AtelierRunner`` as the production
    session service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from google.adk.sessions import Session


@runtime_checkable
class SessionBackend(Protocol):
    """Structural protocol for ADK session services.

    Implementations: ``VertexAiSessionService``, ``BigQuerySessionBackend``,
    ``InMemorySessionService`` (local dev / tests).

    All methods are async; the Protocol does NOT mandate a constructor signature
    so any conforming class can inject project/location/app_name differently.
    """

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Session:
        """Create a new session.

        Args:
            app_name: The ADK app name (constant per deployment: ``"atelier"``).
            user_id: Identity Platform user ID for the session owner.
            state: Optional initial state dict (key-value metadata).
            session_id: Client-provided ID. If omitted, the backend generates one.

        Returns:
            The newly created ``google.adk.sessions.Session`` object.
        """
        ...

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Any | None = None,
    ) -> Session | None:
        """Retrieve an existing session by ID.

        Args:
            app_name: The ADK app name.
            user_id: Owner of the session.
            session_id: The session to retrieve.
            config: Optional ``GetSessionConfig`` (ADK base class param); pass
                ``None`` to get all events.

        Returns:
            The ``Session`` if found, ``None`` if the session does not exist.
        """
        ...
