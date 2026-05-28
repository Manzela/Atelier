"""BigQuery Session Backend — ADK 2.0 SessionService for production (AG-07 / B4).

Implements ``SessionBackend`` Protocol (memory/session_protocol.py) and
subclasses ``BaseSessionService`` (google.adk.sessions) so it can be
injected into ``Runner(session_service=...)`` as a drop-in replacement
for ``InMemorySessionService``.

Storage layout:
    BigQuery table ``{project}.{dataset}.sessions``
    Columns: session_id, app_name, user_id, state_json, events_json,
             created_at, updated_at

In local development (no BQ SDK), transparently falls back to in-memory
storage per failure trichotomy (§21 fail-soft).

PRD Reference: §6.3 (N3h session persistence), §7 (infrastructure)
Audit Reference: B4 (swap InMemoryRunner → VertexAiSessionService)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from google.adk.sessions import Session
from google.adk.sessions.base_session_service import (
    BaseSessionService,
    GetSessionConfig,
    ListSessionsResponse,
)

logger = logging.getLogger(__name__)


class BigQuerySessionBackend(BaseSessionService):  # type: ignore[misc]
    """ADK-compatible session service backed by BigQuery.

    Conforms to both:
        - ``atelier.memory.session_protocol.SessionBackend`` (structural Protocol)
        - ``google.adk.sessions.BaseSessionService`` (ABC subclass)

    In production, sessions are stored in BigQuery for:
        - Cross-instance session resumption (Cloud Run auto-scaling)
        - Trajectory extraction for DPO training
        - Audit trail compliance
        - Cost accounting per session

    Usage::

        from google.adk.runners import Runner
        from atelier.memory.bigquery_session import BigQuerySessionBackend

        session_svc = BigQuerySessionBackend(project_id="atelier-build-2026")
        runner = Runner(agent=my_agent, session_service=session_svc)
    """

    def __init__(
        self,
        *,
        project_id: str = "atelier-build-2026",
        dataset_id: str = "atelier_trajectories",
        table_id: str = "sessions",
    ) -> None:
        self._project_id = project_id
        self._dataset_id = dataset_id
        self._table_id = table_id
        self._fqn = f"{project_id}.{dataset_id}.{table_id}"
        self._client: Any | None = None
        self._fallback_store: dict[str, Session] = {}

    # ------------------------------------------------------------------
    # Lazy BigQuery client
    # ------------------------------------------------------------------

    def _get_client(self) -> Any | None:
        """Lazy-init BigQuery client. Returns None if SDK unavailable."""
        if self._client is None:
            try:
                from google.cloud import bigquery  # noqa: PLC0415

                self._client = bigquery.Client(project=self._project_id)
            except ImportError:
                logger.warning(
                    "BigQuery SDK not available; using in-memory session fallback. "
                    "Install google-cloud-bigquery for production session persistence."
                )
                return None
        return self._client

    # ------------------------------------------------------------------
    # BaseSessionService abstract method implementations
    # ------------------------------------------------------------------

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> Session:
        """Create a new session and persist it.

        Args:
            app_name: ADK app name (constant per deployment: ``"atelier"``).
            user_id: Identity Platform user ID for the session owner.
            state: Optional initial state dict.
            session_id: Client-provided ID. If omitted, a UUID is generated.

        Returns:
            The newly created ``Session`` object.
        """
        sid = session_id or str(uuid.uuid4())
        session = Session(
            id=sid,
            app_name=app_name,
            user_id=user_id,
            state=state or {},
            events=[],
            last_update_time=time.time(),
        )

        client = self._get_client()
        if client is None:
            self._fallback_store[sid] = session
            return session

        row = {
            "session_id": sid,
            "app_name": app_name,
            "user_id": user_id,
            "state_json": json.dumps(session.state),
            "events_json": json.dumps([]),
            "created_at": session.last_update_time,
            "updated_at": session.last_update_time,
        }
        try:
            loop = asyncio.get_running_loop()
            errors = await loop.run_in_executor(None, client.insert_rows_json, self._fqn, [row])
            if errors:
                logger.warning("BQ insert errors for session %s: %s", sid, errors)
                self._fallback_store[sid] = session
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to create session in BQ: %s", type(exc).__name__)
            self._fallback_store[sid] = session

        return session

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: GetSessionConfig | None = None,
    ) -> Session | None:
        """Retrieve an existing session by ID.

        Args:
            app_name: The ADK app name.
            user_id: Owner of the session.
            session_id: The session to retrieve.
            config: Optional ``GetSessionConfig`` for event filtering.

        Returns:
            The ``Session`` if found, ``None`` if not.
        """
        # Check in-memory fallback first
        if session_id in self._fallback_store:
            return self._fallback_store[session_id]

        client = self._get_client()
        if client is None:
            return None

        query = (
            f"SELECT * FROM `{self._fqn}` "  # noqa: S608
            "WHERE session_id = @session_id AND user_id = @user_id AND app_name = @app_name "
            "ORDER BY updated_at DESC "
            "LIMIT 1"
        )
        try:
            from google.cloud import bigquery  # noqa: PLC0415

            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("session_id", "STRING", session_id),
                    bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
                    bigquery.ScalarQueryParameter("app_name", "STRING", app_name),
                ]
            )
            loop = asyncio.get_running_loop()
            query_job = client.query(query, job_config=job_config)
            result = await loop.run_in_executor(None, query_job.result)
            rows = list(result)
            if not rows:
                return None

            row = dict(rows[0])
            state = json.loads(row.get("state_json", "{}"))

            session = Session(
                id=row["session_id"],
                app_name=row.get("app_name", app_name),
                user_id=row.get("user_id", user_id),
                state=state,
                events=[],  # Events reconstructed separately if needed
                last_update_time=row.get("updated_at", 0.0),
            )

            # Apply GetSessionConfig filtering
            if config and config.num_recent_events == 0:
                session.events = []

        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to get session from BQ: %s", type(exc).__name__)
            return None
        else:
            return session

    async def list_sessions(
        self,
        *,
        app_name: str,
        user_id: str | None = None,
    ) -> ListSessionsResponse:
        """List sessions, optionally filtered by user_id.

        Args:
            app_name: The ADK app name.
            user_id: Optional filter by user.

        Returns:
            ListSessionsResponse containing matching sessions (without events/state).
        """
        # In-memory fallback
        client = self._get_client()
        if client is None:
            sessions = [
                s
                for s in self._fallback_store.values()
                if s.app_name == app_name and (user_id is None or s.user_id == user_id)
            ]
            return ListSessionsResponse(sessions=sessions)

        try:
            from google.cloud import bigquery  # noqa: PLC0415

            params = [
                bigquery.ScalarQueryParameter("app_name", "STRING", app_name),
            ]
            where = "WHERE app_name = @app_name"
            if user_id is not None:
                where += " AND user_id = @user_id"
                params.append(
                    bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
                )

            query = (
                f"SELECT session_id, app_name, user_id, updated_at FROM `{self._fqn}` "  # noqa: S608
                f"{where} ORDER BY updated_at DESC LIMIT 100"
            )
            job_config = bigquery.QueryJobConfig(query_parameters=params)
            loop = asyncio.get_running_loop()
            query_job = client.query(query, job_config=job_config)
            result = await loop.run_in_executor(None, query_job.result)

            sessions = [
                Session(
                    id=row["session_id"],
                    app_name=row.get("app_name", app_name),
                    user_id=row.get("user_id", ""),
                    last_update_time=row.get("updated_at", 0.0),
                )
                for row in result
            ]
            return ListSessionsResponse(sessions=sessions)

        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to list sessions from BQ: %s", type(exc).__name__)
            return ListSessionsResponse(sessions=[])

    async def delete_session(
        self,
        *,
        app_name: str,  # noqa: ARG002
        user_id: str,
        session_id: str,
    ) -> None:
        """Delete a session.

        Args:
            app_name: The ADK app name.
            user_id: Owner of the session.
            session_id: The session to delete.
        """
        self._fallback_store.pop(session_id, None)

        client = self._get_client()
        if client is None:
            return

        try:
            from google.cloud import bigquery  # noqa: PLC0415

            query = (
                f"DELETE FROM `{self._fqn}` "  # noqa: S608
                "WHERE session_id = @session_id AND user_id = @user_id"
            )
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("session_id", "STRING", session_id),
                    bigquery.ScalarQueryParameter("user_id", "STRING", user_id),
                ]
            )
            loop = asyncio.get_running_loop()
            query_job = client.query(query, job_config=job_config)
            await loop.run_in_executor(None, query_job.result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to delete session from BQ: %s", type(exc).__name__)

    # ------------------------------------------------------------------
    # BaseSessionService hooks
    # ------------------------------------------------------------------

    async def append_event(self, session: Session, event: Any) -> Any:
        """Append event to session and persist state update.

        Delegates to the base class for in-memory state management,
        then persists the updated state to BigQuery.
        """
        result = await super().append_event(session, event)

        # Persist state update to BQ
        client = self._get_client()
        if client is not None:
            try:
                from google.cloud import bigquery  # noqa: PLC0415

                query = (
                    f"UPDATE `{self._fqn}` "  # noqa: S608
                    "SET state_json = @state_json, updated_at = @updated_at "
                    "WHERE session_id = @session_id"
                )
                job_config = bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter(
                            "state_json", "STRING", json.dumps(session.state)
                        ),
                        bigquery.ScalarQueryParameter("updated_at", "FLOAT64", time.time()),
                        bigquery.ScalarQueryParameter("session_id", "STRING", session.id),
                    ]
                )
                loop = asyncio.get_running_loop()
                query_job = client.query(query, job_config=job_config)
                await loop.run_in_executor(None, query_job.result)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to persist event to BQ: %s", type(exc).__name__)

        return result
