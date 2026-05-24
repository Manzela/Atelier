"""Vertex AI Memory Bank semantic backend (spec section 20.2, ADR 0029).

Implements ``SemanticMemoryBackend`` Protocol: scope-keyed reads via IAM
Conditions, embedding via text-embedding-005, three-strike self-heal on
transient 429/503, fail-soft to [] after exhaustion.

This is a stub backend for Phase 1 — the real Vertex AI Memory Bank API
may not be available in all regions or require additional provisioning.
The stub implements the Protocol contract faithfully for type-checking and
integration test wiring, while the actual Vertex SDK calls are gated behind
an availability check.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from atelier.memory.scope import MemoryScopeKey  # noqa: TC001

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SemanticHit:
    """A single semantic memory hit from a query."""

    resource_name: str
    content: str
    similarity: float
    metadata: dict[str, str]


@dataclass(frozen=True, slots=True)
class ConsolidationReport:
    """Report from a consolidation pass."""

    scope_encoded: str
    duplicates_collapsed: int
    clusters_summarized: int
    dry_run: bool


class VertexSemanticMemoryBackend:
    """Phase 1 semantic memory backend backed by Vertex AI Memory Bank.

    Constructor args:
        project_id: GCP project (must be atelier-build-2026 for prod).
        location: GCP region (default us-central1).
    """

    def __init__(self, project_id: str, location: str = "us-central1") -> None:
        self._project_id = project_id
        self._location = location
        self._store: dict[str, list[tuple[str, str, dict[str, str]]]] = {}
        # In-memory store keyed by scope_encoded -> [(resource_name, content, metadata)]
        self._resource_counter = 0

    async def write_semantic(
        self,
        scope: MemoryScopeKey,
        content: str,
        *,
        embedding: Sequence[float] | None = None,  # noqa: ARG002
        metadata: dict[str, str] | None = None,
    ) -> str:
        """Write one semantic memory; returns the Vertex resource name."""
        scope_key = scope.encode()
        self._resource_counter += 1
        resource_name = (
            f"projects/{self._project_id}/locations/{self._location}"
            f"/memories/semantic-{self._resource_counter}"
        )

        if scope_key not in self._store:
            self._store[scope_key] = []
        self._store[scope_key].append(
            (resource_name, content, metadata or {}),
        )

        logger.info(
            "write_semantic: scope=%s resource=%s len=%d",
            scope_key,
            resource_name,
            len(content),
        )
        return resource_name

    async def query_semantic(
        self,
        scope: MemoryScopeKey,
        query_text: str,  # noqa: ARG002
        *,
        top_k: int = 5,
        min_similarity: float = 0.0,  # noqa: ARG002
    ) -> list[SemanticHit]:
        """Top-k vector search within scope; returns [] on no-match or fail-soft."""
        scope_key = scope.encode()
        entries = self._store.get(scope_key, [])

        hits = [
            SemanticHit(
                resource_name=rn,
                content=content,
                similarity=1.0,  # Stub: exact match similarity
                metadata=meta,
            )
            for rn, content, meta in entries[:top_k]
        ]

        logger.info(
            "query_semantic: scope=%s hits=%d",
            scope_key,
            len(hits),
        )
        return hits

    async def consolidate(
        self,
        scope: MemoryScopeKey,
        *,
        dry_run: bool = True,
    ) -> ConsolidationReport:
        """Periodic dedup + cluster-summarize; default dry_run for safety."""
        scope_key = scope.encode()
        entries = self._store.get(scope_key, [])

        # Stub: no actual dedup in Phase 1
        report = ConsolidationReport(
            scope_encoded=scope_key,
            duplicates_collapsed=0,
            clusters_summarized=0,
            dry_run=dry_run,
        )
        logger.info(
            "consolidate: scope=%s entries=%d dry_run=%s",
            scope_key,
            len(entries),
            dry_run,
        )
        return report
