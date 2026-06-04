"""Incident Diagnostic Memory Bank — AT-080 (PRD v2.2 §20).

Serializes, indexes, and queries failed iteration states and their successful code resolutions.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from atelier.memory.scope import MemoryScopeKey
from atelier.models.enums import GateDecision

CONVERGENCE_THRESHOLD = 0.70

if TYPE_CHECKING:
    from atelier.models.data_contracts import GateOutcome
    from atelier.nodes.consensus import ConsensusEvaluation

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IncidentRecord:
    """Represents a serialized compiler, linter, or visual quality failure incident."""

    incident_id: str
    timestamp: str
    tenant_id: str
    failures: list[str]
    diagnostic_details: str
    resolution_delta: str | None = None


def serialize_incident(
    tenant_id: str,
    incident_id: str,
    gate_outcomes: list[GateOutcome],
    consensus: ConsensusEvaluation | None,
) -> str:
    """Serialize the incident failures and details into a search-friendly string."""
    failures = []
    details = []

    for outcome in gate_outcomes:
        if outcome.decision != GateDecision.PASS:
            failures.append(f"gate_fail:{outcome.axis.value}")
            details.append(f"Gate {outcome.axis.value} failed: {outcome.diagnostic}")

    if consensus:
        for axis, vote in consensus.votes.items():
            if vote.score < CONVERGENCE_THRESHOLD:
                failures.append(f"low_score:{axis.value}")
                details.append(
                    f"Consensus Axis {axis.value} low score {vote.score:.2f}: {vote.reasoning}"
                )

    record = {
        "incident_id": incident_id,
        "tenant_id": tenant_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "failures": failures,
        "diagnostic_details": "\n".join(details),
    }
    return json.dumps(record)


class IncidentMemoryBank:
    """Incident Diagnostic Memory Bank manager."""

    def __init__(self, memory_service: Any) -> None:
        """Initialize the manager with a HierarchicalMemory instance."""
        self._memory_service = memory_service

    async def record_incident(
        self,
        tenant_id: str,
        incident_id: str,
        gate_outcomes: list[GateOutcome],
        consensus: ConsensusEvaluation | None,
    ) -> None:
        """Record a failure incident in the semantic memory bank."""
        try:
            content = serialize_incident(tenant_id, incident_id, gate_outcomes, consensus)
            scope = MemoryScopeKey(
                project_id=tenant_id,
                phase="incident",
                actor_id="fixer",
            )
            # Fail-soft dynamic check for semantic memory service
            if hasattr(self._memory_service, "write_semantic"):
                await self._memory_service.write_semantic(
                    scope=scope,
                    content=content,
                    metadata={"type": "incident", "incident_id": incident_id},
                )
            elif hasattr(self._memory_service, "write_episodic"):
                # Fallback to episodic memory
                from atelier.memory.protocol import MemoryEvent  # noqa: PLC0415

                event = MemoryEvent(
                    event_id=incident_id,
                    occurred_at=datetime.now(UTC),
                    node_name="FixerIncident",
                    payload={"content": content},
                    embedding=None,
                )
                await self._memory_service.write_episodic(event)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to record incident in memory bank (fail-soft): %s",
                exc,
                exc_info=True,
            )

    async def record_resolution(
        self,
        tenant_id: str,
        incident_id: str,
        resolution_delta: str,
    ) -> None:
        """Record the resolution details for an incident to assist future fixes."""
        try:
            scope = MemoryScopeKey(
                project_id=tenant_id,
                phase="incident_resolution",
                actor_id="fixer",
            )
            content = json.dumps(
                {
                    "incident_id": incident_id,
                    "resolution": resolution_delta,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            if hasattr(self._memory_service, "write_semantic"):
                await self._memory_service.write_semantic(
                    scope=scope,
                    content=content,
                    metadata={"type": "resolution", "incident_id": incident_id},
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to record resolution in memory bank (fail-soft): %s",
                exc,
                exc_info=True,
            )

    async def query_similar_resolutions(
        self,
        tenant_id: str,
        gate_outcomes: list[GateOutcome],
        consensus: ConsensusEvaluation | None,
        top_k: int = 3,
    ) -> list[str]:
        """Query semantic memory for similar incidents and retrieve their resolutions."""
        resolutions = []
        try:
            query_text = serialize_incident(tenant_id, "query", gate_outcomes, consensus)

            if hasattr(self._memory_service, "query_semantic"):
                results = await self._memory_service.query_semantic(
                    query_text=query_text,
                    top_k=top_k,
                )
                for r in results:
                    try:
                        record = json.loads(r.passage)
                        inc_id = record.get("incident_id")
                        if inc_id:
                            # Search for the resolution record specifically
                            res_results = await self._memory_service.query_semantic(
                                query_text=inc_id,
                                top_k=1,
                            )
                            for rr in res_results:
                                res_record = json.loads(rr.passage)
                                if res_record.get("incident_id") == inc_id:
                                    resolutions.append(res_record.get("resolution"))
                    except Exception as exc:  # noqa: BLE001
                        logger.debug(
                            "Failed to parse historical resolution record (skipping): %s", exc
                        )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to query similar resolutions from memory bank (fail-soft): %s",
                exc,
                exc_info=True,
            )

        return [r for r in resolutions if r]
