"""consolidate() near-duplicate collapse — VertexSemanticMemoryBackend.

Guards finding 78: consolidate() was a permanent no-op that always reported
``duplicates_collapsed=0`` regardless of store contents, so the semantic store
grew unbounded with duplicates. These hermetic tests pin the real dedup
behaviour: a near-duplicate pair is reported (dry-run) and then collapsed
(non-dry-run), while a distinct entry is always retained.
"""

from __future__ import annotations

import pytest
from atelier.memory.backends.vertex_semantic import VertexSemanticMemoryBackend
from atelier.memory.scope import MemoryScopeKey

_DUP_A = (
    "The hero section uses a bold serif headline with a deep navy background "
    "and a coral call to action button."
)
# Same content, only trailing punctuation differs -> TF-IDF cosine ~1.0.
_DUP_B = _DUP_A.rstrip(".")
_DISTINCT = (
    "A minimalist pricing table lists three tiers in pale grey cards with "
    "green accents and monospace numerals."
)


def _scope() -> MemoryScopeKey:
    return MemoryScopeKey(project_id="atelier-build-2026", phase="phase-1", actor_id="tenant-a")


@pytest.mark.anyio
async def test_consolidate_dry_run_reports_duplicate_without_mutating() -> None:
    backend = VertexSemanticMemoryBackend(project_id="atelier-build-2026")
    scope = _scope()
    await backend.write_semantic(scope, _DUP_A)
    await backend.write_semantic(scope, _DUP_B)
    await backend.write_semantic(scope, _DISTINCT)

    report = await backend.consolidate(scope, dry_run=True)

    assert report.dry_run is True
    assert report.duplicates_collapsed == 1
    assert report.clusters_summarized == 0
    # dry-run must not mutate: all three writes are still queryable.
    hits = await backend.query_semantic(scope, _DUP_A, top_k=10)
    assert len(hits) == 3


@pytest.mark.anyio
async def test_consolidate_collapses_near_duplicate_and_keeps_distinct() -> None:
    backend = VertexSemanticMemoryBackend(project_id="atelier-build-2026")
    scope = _scope()
    rn_first = await backend.write_semantic(scope, _DUP_A)
    await backend.write_semantic(scope, _DUP_B)
    await backend.write_semantic(scope, _DISTINCT)

    report = await backend.consolidate(scope, dry_run=False)

    assert report.duplicates_collapsed == 1
    # The collapse retains the FIRST occurrence of the duplicate cluster and the
    # distinct entry; the store shrinks from 3 -> 2.
    hits = await backend.query_semantic(scope, _DUP_A, top_k=10)
    resource_names = {h.resource_name for h in hits}
    assert len(hits) == 2
    assert rn_first in resource_names
    assert any(h.content == _DISTINCT for h in hits)


@pytest.mark.anyio
async def test_consolidate_noop_on_all_distinct_entries() -> None:
    backend = VertexSemanticMemoryBackend(project_id="atelier-build-2026")
    scope = _scope()
    await backend.write_semantic(scope, _DUP_A)
    await backend.write_semantic(scope, _DISTINCT)

    report = await backend.consolidate(scope, dry_run=False)

    assert report.duplicates_collapsed == 0
    hits = await backend.query_semantic(scope, _DUP_A, top_k=10)
    assert len(hits) == 2
