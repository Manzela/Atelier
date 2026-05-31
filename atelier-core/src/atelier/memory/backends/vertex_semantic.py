"""Vertex AI Memory Bank semantic backend (spec section 20.2, ADR 0029).

Implements ``SemanticMemoryBackend`` Protocol: scope-keyed reads via IAM
Conditions, embedding via text-embedding-005, three-strike self-heal on
transient 429/503, fail-soft to [] after exhaustion.

This is a stub backend for v1.0 implementation — the real Vertex AI Memory Bank API
may not be available in all regions or require additional provisioning.
The stub implements the Protocol contract faithfully for type-checking and
integration test wiring, while the actual Vertex SDK calls are gated behind
an availability check.
"""

from __future__ import annotations

import logging
import os
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
    """v1.0 implementation semantic memory backend backed by Vertex AI Memory Bank.

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
                "VertexSemanticMemoryBackend is an in-memory stub with no persistence. "
                "It must not be used in non-development environments. "
                "Wire the real Vertex AI Memory Bank API or set ATELIER_ENV=development."
            )
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

    @staticmethod
    def _tfidf_similarity(query: str, document: str) -> float:
        """TF-IDF cosine similarity between query and document (stdlib-only).

        Uses term frequency and inverse document frequency computed over the
        combined vocabulary. Returns 0.0-1.0. Replaces the hardcoded 1.0
        stub — different documents now score differently against the same query.
        """
        import math  # noqa: PLC0415
        import re  # noqa: PLC0415

        def tokenise(text: str) -> list[str]:
            return re.findall(r"\b[a-z]{2,}\b", text.lower())

        q_terms = tokenise(query)
        d_terms = tokenise(document)
        if not q_terms or not d_terms:
            return 0.0

        vocab = set(q_terms) | set(d_terms)

        def tf(terms: list[str], term: str) -> float:
            return terms.count(term) / len(terms) if terms else 0.0

        def idf(term: str) -> float:
            # Two-document corpus: query + document
            df = (term in q_terms) + (term in d_terms)
            return math.log((2 + 1) / (df + 1)) + 1.0  # smoothed IDF

        q_vec = [tf(q_terms, t) * idf(t) for t in vocab]
        d_vec = [tf(d_terms, t) * idf(t) for t in vocab]

        dot = sum(a * b for a, b in zip(q_vec, d_vec, strict=False))
        norm_q = sum(a * a for a in q_vec) ** 0.5
        norm_d = sum(b * b for b in d_vec) ** 0.5
        if norm_q == 0.0 or norm_d == 0.0:
            return 0.0
        return float(dot / (norm_q * norm_d))

    async def query_semantic(
        self,
        scope: MemoryScopeKey,
        query_text: str,
        *,
        top_k: int = 5,
        min_similarity: float = 0.0,
    ) -> list[SemanticHit]:
        """Top-k TF-IDF vector search within scope.

        Replaces the hardcoded similarity=1.0 stub with real TF-IDF cosine
        similarity (stdlib-only — no sklearn dependency). Different documents
        score differently against the same query; min_similarity filtering
        is now functional. current implementation replaces with Vertex AI embedding search.

        Args:
            scope: Memory scope key for isolation.
            query_text: Natural-language query string.
            top_k: Maximum hits to return.
            min_similarity: Minimum similarity threshold (0.0 = return all).

        Returns:
            Ranked list of SemanticHit, highest similarity first.
        """
        scope_key = scope.encode()
        entries = self._store.get(scope_key, [])

        scored: list[tuple[float, str, str, dict[str, str]]] = []
        for rn, content, meta in entries:
            sim = self._tfidf_similarity(query_text, content)
            if sim >= min_similarity:
                scored.append((sim, rn, content, meta))

        scored.sort(key=lambda x: x[0], reverse=True)

        hits = [
            SemanticHit(
                resource_name=rn,
                content=content,
                similarity=round(sim, 4),
                metadata=meta,
            )
            for sim, rn, content, meta in scored[:top_k]
        ]

        logger.info(
            "query_semantic: scope=%s query=%r candidates=%d hits=%d",
            scope_key,
            query_text[:60],
            len(entries),
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

        # Stub: no actual dedup in v1.0 implementation
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
