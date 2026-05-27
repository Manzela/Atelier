"""BigQuery episodic memory backend (ADR 0029 + spec §20).

Implements HierarchicalMemory.write_episodic() for the EPISODIC tier.
Semantic and procedural tiers (Vertex Memory Bank) are in vertex_semantic.py
and vertex_procedural.py respectively.

TTL enforcement: rows older than 30 days are handled by a BigQuery table
expiration policy (set at terraform provisioning time), not in this module.

Tenant isolation: every row carries tenant_id sourced from CURRENT_MEMORY_KEY.
IAM Conditions on aiplatform.googleapis.com/memoryScope provide defense-in-depth
at the GCP authorization layer — this module's in-process check is not the only
guard.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Final

from google.cloud import bigquery

from atelier.memory.key import current_key

if TYPE_CHECKING:
    from atelier.memory.protocol import MemoryEvent

logger = logging.getLogger(__name__)

BQ_SESSION_EVENTS_TABLE: Final[str] = "atelier-build-2026.atelier_trajectories.session_events"


class BigQueryEpisodicBackend:
    """Write episodic MemoryEvents to BigQuery session_events table.

    Reads the active MemoryKey from CURRENT_MEMORY_KEY ContextVar at call
    time — fail-loud with LookupError if no key is bound (no middleware set it).

    Embedding is intentionally excluded from the BQ row: the raw float32 vector
    is never written to BigQuery. Semantic/procedural consolidation happens
    separately (consolidate_session) using Vertex Memory Bank, not BQ.
    """

    def __init__(self, project: str = "atelier-build-2026") -> None:
        self._client = bigquery.Client(project=project)
        self._table = BQ_SESSION_EVENTS_TABLE

    async def write_episodic(self, event: MemoryEvent) -> None:
        """Append an episodic event to BigQuery.

        Reads the active MemoryKey from the ContextVar. Raises LookupError
        (fail-loud) if no key is bound — no memory write is safe without it.

        Args:
            event: The episodic event to write.

        Raises:
            LookupError: No MemoryKey bound in the current context.
            google.cloud.exceptions.GoogleCloudError: BQ write failure;
                propagates to caller (fail-soft — caller logs + degrades).
        """
        key = current_key()  # LookupError if not bound — fail-loud, by design
        # Security WARN: blank tenant_id would write a row with an empty discriminator,
        # making the IAM Conditions the sole isolation layer. Enforce non-empty here.
        if not key.tenant_id:
            msg = "MemoryKey.tenant_id is empty — cannot write episodic event without tenant isolation."
            raise ValueError(msg)
        row = {
            "event_id": event.event_id,
            "session_id": key.session_id,
            "project_id": key.project_id,
            "tenant_id": key.tenant_id,
            "node_name": event.node_name,
            "occurred_at": event.occurred_at.isoformat(),
            "payload": json.dumps({k: str(v) for k, v in event.payload.items()}),
        }
        errors = self._client.insert_rows_json(self._table, [row])
        if errors:
            msg = f"BigQuery insert_rows_json failed: {errors}"
            logger.error(msg, extra={"event_id": event.event_id, "tenant_id": key.tenant_id})
            raise RuntimeError(msg)
        logger.debug(
            "Episodic event written",
            extra={
                "event_id": event.event_id,
                "tenant_id": key.tenant_id,
                "session_id": key.session_id,
            },
        )
