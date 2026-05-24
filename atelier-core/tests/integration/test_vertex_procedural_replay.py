"""Procedure replay + scope-leak guard for the procedural tier.

Two assertions:
1. Scope leak guard (mirror of T11) --- procedures written under
   scope_a MUST NOT surface under scope_b.
2. Replay fidelity --- a procedure written with steps [s1, s2, s3]
   and outcome_score=0.85 MUST come back via query_procedural with
   the same step list, same outcome score, and same archetype_id.
   This is what makes the procedural tier load-bearing for the
   Polish loop: garbled replay would silently degrade the Polish
   chain into noise.
"""

from __future__ import annotations

import pytest
from atelier.memory.backends.vertex_procedural import (
    ProcedureStep,
    VertexProceduralMemoryBackend,
)
from atelier.memory.scope import MemoryScopeKey

pytestmark = pytest.mark.integration


@pytest.fixture
def backend() -> VertexProceduralMemoryBackend:
    return VertexProceduralMemoryBackend(
        project_id="atelier-build-2026",
        location="us-central1",
    )


@pytest.mark.asyncio
async def test_replay_fidelity_and_scope_isolation(
    backend: VertexProceduralMemoryBackend,
) -> None:
    scope_a = MemoryScopeKey("atelier-build-2026", "phase-2", "tenant-a")
    scope_b = MemoryScopeKey("atelier-build-2026", "phase-2", "tenant-b")
    archetype = "hero-section-rounded-cards-v1"

    steps = (
        ProcedureStep("apply_tailwind_class", '{"class":"rounded-2xl"}', 0.12),
        ProcedureStep("adjust_typography", '{"scale":"display-lg"}', 0.18),
        ProcedureStep("rebalance_spacing", '{"unit":"4"}', 0.07),
    )
    outcome = 0.85
    resource_name = await backend.write_procedural(scope_a, archetype, steps, outcome_score=outcome)

    # Scope-leak guard
    hits_b = await backend.query_procedural(scope_b, archetype, top_k=10)
    assert hits_b == [], f"scope-leak DETECTED in procedural tier: {hits_b}"

    # Replay fidelity
    hits_a = await backend.query_procedural(scope_a, archetype, top_k=10)
    match = next((h for h in hits_a if h.resource_name == resource_name), None)
    assert match is not None, "wrote a procedure that did not replay"
    assert match.archetype_id == archetype
    assert tuple(match.steps) == steps, (
        f"replay step list garbled: wrote {steps}, got {tuple(match.steps)}"
    )
    assert abs(match.outcome_score - outcome) < 1e-6, (
        f"outcome score drift: wrote {outcome}, got {match.outcome_score}"
    )
