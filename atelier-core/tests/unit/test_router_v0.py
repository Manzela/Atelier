"""Unit tests for ManagedRoutingRouter (§18.4) — Phase 1 v0."""

from __future__ import annotations

import numpy as np
import pytest
from atelier.router.protocol import (
    DAGPhase,
    ExpertID,
    RouteRequest,
)
from atelier.router.v0_managed import ManagedRoutingRouter


def _req(
    phase: DAGPhase,
    *,
    budget: float = 1.0,
    latency_target_ms: int = 5000,
    kappa: float | None = None,
) -> RouteRequest:
    return RouteRequest(
        phase=phase,
        task_embedding=np.zeros(768, dtype=np.float32),
        cost_budget_remaining_usd=budget,
        latency_target_ms=latency_target_ms,
        prior_judge_kappa=kappa,
        trace_id="trace-1",
        tenant_id="tenant-1",
    )


@pytest.mark.anyio
async def test_brief_parse_routes_to_flash() -> None:
    router = ManagedRoutingRouter()
    decision = await router.route(_req(DAGPhase.BRIEF_PARSE))
    assert decision.expert == ExpertID.GEMINI_3_FLASH
    assert decision.routing_mode == "v0_managed"


@pytest.mark.anyio
async def test_intent_schema_routes_to_flash_lite() -> None:
    router = ManagedRoutingRouter()
    decision = await router.route(_req(DAGPhase.INTENT_SCHEMA))
    assert decision.expert == ExpertID.GEMINI_3_1_FLASH_LITE


@pytest.mark.anyio
async def test_surface_plan_routes_to_flash() -> None:
    router = ManagedRoutingRouter()
    decision = await router.route(_req(DAGPhase.SURFACE_PLAN))
    assert decision.expert == ExpertID.GEMINI_3_FLASH


@pytest.mark.anyio
async def test_generate_candidates_low_budget_routes_to_flash_lite() -> None:
    router = ManagedRoutingRouter()
    decision = await router.route(_req(DAGPhase.GENERATE_CANDIDATES, budget=0.49))
    assert decision.expert == ExpertID.GEMINI_3_1_FLASH_LITE


@pytest.mark.anyio
async def test_generate_candidates_high_budget_routes_to_flash() -> None:
    router = ManagedRoutingRouter()
    decision = await router.route(_req(DAGPhase.GENERATE_CANDIDATES, budget=0.50))
    assert decision.expert == ExpertID.GEMINI_3_FLASH


@pytest.mark.anyio
async def test_judge_candidates_routes_to_2_5_pro() -> None:
    """Per §7.1: Originality judge is pinned to gemini-2.5-pro. v0 simplifies
    to 'all judging goes to 2.5-pro' since per-axis routing arrives in v1.
    """
    router = ManagedRoutingRouter()
    decision = await router.route(_req(DAGPhase.JUDGE_CANDIDATES))
    assert decision.expert == ExpertID.GEMINI_2_5_PRO


@pytest.mark.anyio
async def test_select_winner_routes_to_flash_lite() -> None:
    router = ManagedRoutingRouter()
    decision = await router.route(_req(DAGPhase.SELECT_WINNER))
    assert decision.expert == ExpertID.GEMINI_3_1_FLASH_LITE


@pytest.mark.anyio
async def test_polish_routes_to_flash() -> None:
    router = ManagedRoutingRouter()
    decision = await router.route(_req(DAGPhase.POLISH))
    assert decision.expert == ExpertID.GEMINI_3_FLASH


@pytest.mark.anyio
async def test_emit_routes_to_flash_lite() -> None:
    router = ManagedRoutingRouter()
    decision = await router.route(_req(DAGPhase.EMIT))
    assert decision.expert == ExpertID.GEMINI_3_1_FLASH_LITE


@pytest.mark.anyio
async def test_budget_exhausted_forces_flash_lite_with_degraded_rationale() -> None:
    """Per §18.7: cost-gate fail-soft — budget ≤ 0 MUST return flash-lite
    and the rationale MUST include 'cost.degraded' for the OTel pipeline.
    """
    router = ManagedRoutingRouter()
    decision = await router.route(_req(DAGPhase.JUDGE_CANDIDATES, budget=0.0))
    assert decision.expert == ExpertID.GEMINI_3_1_FLASH_LITE
    assert "cost.degraded" in decision.rationale
    assert decision.span_attrs.get("atelier.router.cost_degraded") is True


@pytest.mark.anyio
async def test_fallback_chain_excludes_primary_and_is_ordered() -> None:
    """Fallback chain must (a) not contain the primary, (b) be ordered from
    nearest-equivalent to cheapest-safe-fallback so MetacognitiveGovernor can
    walk it on transient errors.
    """
    router = ManagedRoutingRouter()
    decision = await router.route(_req(DAGPhase.GENERATE_CANDIDATES, budget=1.0))
    assert decision.expert == ExpertID.GEMINI_3_FLASH
    assert decision.expert not in decision.fallback_chain
    # Cheapest-safe-fallback must be at the tail.
    assert decision.fallback_chain[-1] == ExpertID.GEMINI_3_1_FLASH_LITE


@pytest.mark.anyio
async def test_observe_outcome_is_noop_for_v0() -> None:
    """v0 is a closed-loop Vertex managed router — observe_outcome is a no-op
    that returns None. v1 bandit will start consuming this feedback channel.
    """
    router = ManagedRoutingRouter()
    decision = await router.route(_req(DAGPhase.BRIEF_PARSE))
    result = await router.observe_outcome(
        decision=decision,
        achieved_score=0.85,
        actual_cost_usd=0.001,
        actual_latency_ms=200,
    )
    assert result is None
