"""Incident Diagnostic Memory Bank — AT-080 (PRD v2.2 §20).

Serializes, indexes, and queries failed iteration states and their successful code resolutions.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from atelier.memory.scope import MemoryScopeKey
from atelier.models.enums import GateDecision

CONVERGENCE_THRESHOLD = 0.70
_DEFAULT_PROJECT_ID = "atelier-build-2026"

if TYPE_CHECKING:
    from atelier.memory.backends.vertex_semantic import SemanticHit
    from atelier.models.data_contracts import GateOutcome
    from atelier.nodes.consensus import ConsensusEvaluation

logger = logging.getLogger(__name__)


@runtime_checkable
class _SemanticBackend(Protocol):
    """Structural contract for the scope-keyed semantic substrate AT-080 needs.

    Matches ``VertexSemanticMemoryBackend``; the ADK ``BaseMemoryService`` that
    the orchestrator injects does NOT satisfy it (its surface is
    ``add_session_to_memory``/``search_memory``), which is why the bank resolves
    its own backend instead of trusting the injected service.
    """

    async def write_semantic(
        self,
        scope: MemoryScopeKey,
        content: str,
        *,
        embedding: Sequence[float] | None = ...,
        metadata: dict[str, str] | None = ...,
    ) -> str: ...

    async def query_semantic(
        self,
        scope: MemoryScopeKey,
        query_text: str,
        *,
        top_k: int = ...,
        min_similarity: float = ...,
    ) -> list[SemanticHit]: ...


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


def _resolve_semantic_backend(memory_service: Any) -> _SemanticBackend | None:
    """Resolve a scope-keyed semantic backend, never silently failing.

    If the injected ``memory_service`` already implements the semantic surface
    (``write_semantic``/``query_semantic``), it is used as-is. Otherwise — the
    common case, where the orchestrator injects an ADK ``BaseMemoryService`` —
    a ``VertexSemanticMemoryBackend`` is constructed (offline file store) and a
    single WARNING is logged so the fallback is visible. On construction failure
    the bank degrades to explicit logged no-ops rather than the prior silent
    ``hasattr``-gated dead end.
    """
    if isinstance(memory_service, _SemanticBackend):
        return memory_service

    logger.warning(
        "IncidentMemoryBank: injected memory service %s is not a semantic backend "
        "(no write_semantic/query_semantic); falling back to VertexSemanticMemoryBackend "
        "so the AT-080 learning loop records and queries resolutions instead of silently "
        "no-op'ing.",
        type(memory_service).__name__,
    )
    try:
        from atelier.memory.backends.vertex_semantic import (  # noqa: PLC0415
            VertexSemanticMemoryBackend,
        )

        project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or _DEFAULT_PROJECT_ID
        return VertexSemanticMemoryBackend(project_id=project_id)
    except Exception:
        logger.exception(
            "IncidentMemoryBank: could not construct fallback semantic backend; "
            "incident learning loop will be a logged no-op for this run.",
        )
        return None


class IncidentMemoryBank:
    """Incident Diagnostic Memory Bank manager."""

    def __init__(self, memory_service: Any) -> None:
        """Initialize the manager, resolving a real scope-keyed semantic backend.

        The orchestrator injects an ADK ``BaseMemoryService`` whose surface is
        ``add_session_to_memory``/``search_memory``, not the semantic API this
        bank speaks. ``_resolve_semantic_backend`` bridges that gap (or logs why
        it could not) so the AT-080 loop is never a silent no-op.
        """
        self._backend = _resolve_semantic_backend(memory_service)

    async def record_incident(
        self,
        tenant_id: str,
        incident_id: str,
        gate_outcomes: list[GateOutcome],
        consensus: ConsensusEvaluation | None,
    ) -> None:
        """Record a failure incident in the semantic memory bank."""
        if self._backend is None:
            logger.warning(
                "record_incident: no semantic backend; skipping incident %s", incident_id
            )
            return
        try:
            content = serialize_incident(tenant_id, incident_id, gate_outcomes, consensus)
            scope = MemoryScopeKey(
                project_id=tenant_id,
                phase="incident",
                actor_id="fixer",
            )
            await self._backend.write_semantic(
                scope,
                content,
                metadata={"type": "incident", "incident_id": incident_id},
            )
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
        if self._backend is None:
            logger.warning(
                "record_resolution: no semantic backend; skipping incident %s", incident_id
            )
            return
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
            await self._backend.write_semantic(
                scope,
                content,
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
        resolutions: list[str] = []
        if self._backend is None:
            logger.warning("query_similar_resolutions: no semantic backend; returning no matches")
            return resolutions
        try:
            query_text = serialize_incident(tenant_id, "query", gate_outcomes, consensus)
            incident_scope = MemoryScopeKey(
                project_id=tenant_id,
                phase="incident",
                actor_id="fixer",
            )
            resolution_scope = MemoryScopeKey(
                project_id=tenant_id,
                phase="incident_resolution",
                actor_id="fixer",
            )

            incident_hits = await self._backend.query_semantic(
                incident_scope,
                query_text,
                top_k=top_k,
            )
            for hit in incident_hits:
                try:
                    record = json.loads(hit.content)
                    inc_id = record.get("incident_id")
                    if not inc_id:
                        continue
                    # Two-step lookup: the matched incident points at its
                    # resolution, which lives under a distinct scope.
                    res_hits = await self._backend.query_semantic(
                        resolution_scope,
                        inc_id,
                        top_k=1,
                    )
                    for res_hit in res_hits:
                        res_record = json.loads(res_hit.content)
                        if res_record.get("incident_id") == inc_id:
                            resolutions.append(res_record.get("resolution"))
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Failed to parse historical resolution record (skipping): %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to query similar resolutions from memory bank (fail-soft): %s",
                exc,
                exc_info=True,
            )

        return [r for r in resolutions if r]
