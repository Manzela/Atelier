"""Scope-leak guard: a write under scope A MUST NOT be visible to scope B.

This is the load-bearing test for Virtual Context Isolation. If this
test ever passes for the wrong reason (e.g. both scopes happen to
share an underlying corpus), the whole multi-project parallelization
guarantee collapses.

We assert in TWO independent ways:
1. query_semantic(scope_B, query=identical_content) returns [].
2. The Vertex resource name returned by write_semantic(scope_A, ...)
   is NOT in any result page when querying under scope_B with
   top_k=1000 --- a brute-force exhaustion check that does not depend
   on similarity ranking.
"""

from __future__ import annotations

import os

import pytest
from atelier.memory.backends.vertex_semantic import VertexSemanticMemoryBackend
from atelier.memory.scope import MemoryScopeKey

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def project_id() -> str:
    project = os.environ.get("ATELIER_GCP_PROJECT", "atelier-build-2026")
    assert project == "atelier-build-2026", (
        "scope-leak test MUST run against atelier-build-2026 (greenfield, "
        "no pre-existing memories); refusing to run against i-for-ai"
    )
    return project


@pytest.fixture
def backend(project_id: str) -> VertexSemanticMemoryBackend:
    return VertexSemanticMemoryBackend(project_id=project_id, location="us-central1")


@pytest.mark.anyio
async def test_write_under_scope_a_is_invisible_under_scope_b(
    backend: VertexSemanticMemoryBackend,
    project_id: str,
) -> None:
    scope_a = MemoryScopeKey(project_id=project_id, phase="phase-1", actor_id="tenant-a")
    scope_b = MemoryScopeKey(project_id=project_id, phase="phase-1", actor_id="tenant-b")

    content = "scope-leak-guard canary: tenant_a_secret_v1"
    resource_name = await backend.write_semantic(scope_a, content)

    # Assertion 1: exact-content query under scope B returns []
    hits_b = await backend.query_semantic(scope_b, content, top_k=10)
    assert hits_b == [], (
        f"scope-leak DETECTED: scope_b saw {len(hits_b)} hit(s) for "
        f"content written under scope_a; first hit: "
        f"{hits_b[0] if hits_b else 'n/a'}"
    )

    # Assertion 2: brute-force exhaustion --- the resource name written
    # under scope_a is not present anywhere in scope_b's namespace.
    exhaustive = await backend.query_semantic(scope_b, "*", top_k=1000)
    assert resource_name not in {h.resource_name for h in exhaustive}, (
        "scope-leak DETECTED: scope_a's resource name appeared in scope_b's exhaustive query"
    )

    # Sanity check: the same query under scope_a DOES find it.
    hits_a = await backend.query_semantic(scope_a, content, top_k=10)
    assert any(h.resource_name == resource_name for h in hits_a), (
        "write_semantic returned a resource name that is not "
        "queryable under its own scope; fail-loud condition"
    )
