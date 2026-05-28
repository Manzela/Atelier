"""Vertex AI Memory Bank procedural backend (spec section 20.3).

Implements ``ProceduralMemoryBackend`` Protocol: scope-keyed reads via IAM
Conditions (shared with semantic tier), JSON-line step serialization,
archetype-based querying.

Phase 1 stub — in-memory store implementing the Protocol contract faithfully
for type-checking and integration test wiring.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass

from atelier.memory.scope import MemoryScopeKey  # noqa: TC001

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProcedureStep:
    """One step in a procedural memory trace."""

    tool_name: str
    args_json: str
    observed_delta_score: float


@dataclass(frozen=True, slots=True)
class ProcedureHit:
    """A single procedural memory hit from a query."""

    resource_name: str
    archetype_id: str
    steps: Sequence[ProcedureStep]
    outcome_score: float
    metadata: dict[str, str]


@dataclass(frozen=True)
class _StoredProcedure:
    """Internal storage record."""

    resource_name: str
    archetype_id: str
    steps: tuple[ProcedureStep, ...]
    outcome_score: float
    metadata: dict[str, str]
    steps_json: str  # JSON-line serialized steps for persistence


class VertexProceduralMemoryBackend:
    """Phase 1 procedural memory backend backed by Vertex AI Memory Bank.

    Constructor args:
        project_id: GCP project (must be atelier-build-2026 for prod).
        location: GCP region (default us-central1).
    """

    def __init__(self, project_id: str, location: str = "us-central1") -> None:
        # H-7: In-memory stub loses all data on process restart. In production
        # (Cloud Run scales to zero), this silently pretends memory works.
        # Fail-loud outside development until real Vertex Memory Bank is wired.
        if os.getenv("ATELIER_ENV", "development") != "development":
            raise NotImplementedError(
                "VertexProceduralMemoryBackend is an in-memory stub with no persistence. "
                "It must not be used in non-development environments. "
                "Wire the real Vertex AI Memory Bank API or set ATELIER_ENV=development."
            )
        self._project_id = project_id
        self._location = location
        self._store: dict[str, list[_StoredProcedure]] = {}
        # Keyed by scope_encoded -> list of stored procedures
        self._resource_counter = 0

    def _serialize_steps(self, steps: Sequence[ProcedureStep]) -> str:
        """Serialize steps to JSON-line format for persistence."""
        return "\n".join(
            json.dumps(
                {
                    "tool_name": s.tool_name,
                    "args_json": s.args_json,
                    "observed_delta_score": s.observed_delta_score,
                },
            )
            for s in steps
        )

    def _deserialize_steps(self, steps_json: str) -> tuple[ProcedureStep, ...]:
        """Deserialize steps from JSON-line format."""
        return tuple(
            ProcedureStep(
                tool_name=obj["tool_name"],
                args_json=obj["args_json"],
                observed_delta_score=obj["observed_delta_score"],
            )
            for line in steps_json.strip().split("\n")
            if line.strip()
            for obj in [json.loads(line)]
        )

    async def write_procedural(
        self,
        scope: MemoryScopeKey,
        archetype_id: str,
        steps: Sequence[ProcedureStep],
        *,
        outcome_score: float,
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Write one procedure trace; returns the Vertex resource name."""
        scope_key = scope.encode()
        self._resource_counter += 1
        resource_name = (
            f"projects/{self._project_id}/locations/{self._location}"
            f"/memories/procedural-{self._resource_counter}"
        )

        steps_json = self._serialize_steps(steps)
        record = _StoredProcedure(
            resource_name=resource_name,
            archetype_id=archetype_id,
            steps=tuple(steps),
            outcome_score=outcome_score,
            metadata=metadata or {},
            steps_json=steps_json,
        )

        if scope_key not in self._store:
            self._store[scope_key] = []
        self._store[scope_key].append(record)

        logger.info(
            "write_procedural: scope=%s archetype=%s steps=%d score=%.4f",
            scope_key,
            archetype_id,
            len(steps),
            outcome_score,
        )
        return resource_name

    async def query_procedural(
        self,
        scope: MemoryScopeKey,
        archetype_id: str,
        *,
        top_k: int = 3,
        min_outcome_score: float = 0.7,
    ) -> list[ProcedureHit]:
        """Top-k procedures for the given archetype; returns [] on no-match."""
        scope_key = scope.encode()
        entries = self._store.get(scope_key, [])

        hits = [
            ProcedureHit(
                resource_name=rec.resource_name,
                archetype_id=rec.archetype_id,
                steps=self._deserialize_steps(rec.steps_json),
                outcome_score=rec.outcome_score,
                metadata=rec.metadata,
            )
            for rec in entries
            if rec.archetype_id == archetype_id and rec.outcome_score >= min_outcome_score
        ]

        # Sort by outcome_score descending, take top_k
        hits.sort(key=lambda h: h.outcome_score, reverse=True)
        result = hits[:top_k]

        logger.info(
            "query_procedural: scope=%s archetype=%s hits=%d",
            scope_key,
            archetype_id,
            len(result),
        )
        return result
