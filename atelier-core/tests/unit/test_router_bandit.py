"""Unit tests for EpsilonGreedyBandit (T13, ADR 0027 v1)."""

from __future__ import annotations

import math
import random

import numpy as np
import pytest
from atelier.router.protocol import (
    DAGPhase,
    ExpertID,
    RouteDecision,
    RouteRequest,
)
from atelier.router.v1_bandit import (
    EPSILON_DECAY_SECONDS,
    EPSILON_FLOOR,
    EPSILON_START,
    UCB1_EXPLORATION_CONSTANT,
    EpsilonGreedyBandit,
    _ArmState,
)


def _make_request(
    phase: DAGPhase = DAGPhase.GENERATE_CANDIDATES,
    trace_id: str = "trace-001",
) -> RouteRequest:
    return RouteRequest(
        phase=phase,
        task_embedding=np.zeros(768, dtype=np.float32),
        cost_budget_remaining_usd=1.0,
        latency_target_ms=500,
        prior_judge_kappa=None,
        trace_id=trace_id,
        tenant_id="tenant-xyz",
    )


def _make_decision(expert: ExpertID = ExpertID.GEMINI_3_FLASH) -> RouteDecision:
    return RouteDecision(
        expert=expert,
        score=0.75,
        rationale="test",
        fallback_chain=(ExpertID.GEMINI_3_PRO,),
        routing_mode="v1_bandit",
    )


# ─── Constants ────────────────────────────────────────────────────────────────


def test_epsilon_start_and_floor() -> None:
    assert pytest.approx(0.10) == EPSILON_START
    assert pytest.approx(0.02) == EPSILON_FLOOR
    assert EPSILON_FLOOR < EPSILON_START


def test_ucb1_constant_is_sqrt_two() -> None:
    assert pytest.approx(math.sqrt(2.0)) == UCB1_EXPLORATION_CONSTANT


def test_epsilon_decay_is_seven_days() -> None:
    assert pytest.approx(7.0 * 24 * 3600) == EPSILON_DECAY_SECONDS


# ─── ArmState ────────────────────────────────────────────────────────────────


def test_arm_state_mean_score_zero_when_no_pulls() -> None:
    arm = _ArmState()
    assert arm.mean_score == pytest.approx(0.0)


def test_arm_state_ucb1_inf_when_no_pulls() -> None:
    arm = _ArmState()
    assert arm.ucb1(total_all_arms=10) == float("inf")


def test_arm_state_update_increments_pulls_and_score() -> None:
    arm = _ArmState()
    arm.update(0.8)
    arm.update(0.6)
    assert arm.total_pulls == 2
    assert arm.total_score == pytest.approx(1.4)
    assert arm.mean_score == pytest.approx(0.7)


def test_arm_state_ucb1_decreases_as_pulls_increase() -> None:
    arm = _ArmState()
    arm.update(0.8)
    ucb1_after_1 = arm.ucb1(total_all_arms=10)
    arm.update(0.8)
    ucb1_after_2 = arm.ucb1(total_all_arms=10)
    assert ucb1_after_2 < ucb1_after_1


# ─── EpsilonGreedyBandit initialization ──────────────────────────────────────


def test_bandit_initializes_all_phase_expert_arms() -> None:
    bandit = EpsilonGreedyBandit()
    expected_arms = len(DAGPhase) * len(ExpertID)
    assert len(bandit._arms) == expected_arms


def test_bandit_initial_epsilon_is_epsilon_start() -> None:
    bandit = EpsilonGreedyBandit()
    eps = bandit._epsilon()
    assert eps == pytest.approx(EPSILON_START, abs=0.001)


# ─── route() ─────────────────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_route_returns_route_decision() -> None:
    bandit = EpsilonGreedyBandit(rng=random.Random(42))  # noqa: S311
    decision = await bandit.route(_make_request())
    assert isinstance(decision, RouteDecision)


@pytest.mark.anyio
async def test_route_decision_routing_mode_is_v1_bandit() -> None:
    bandit = EpsilonGreedyBandit(rng=random.Random(42))  # noqa: S311
    decision = await bandit.route(_make_request())
    assert decision.routing_mode == "v1_bandit"


@pytest.mark.anyio
async def test_route_decision_expert_is_valid_expert_id() -> None:
    bandit = EpsilonGreedyBandit(rng=random.Random(42))  # noqa: S311
    decision = await bandit.route(_make_request())
    assert decision.expert in ExpertID


@pytest.mark.anyio
async def test_route_returns_non_empty_fallback_chain() -> None:
    bandit = EpsilonGreedyBandit(rng=random.Random(42))  # noqa: S311
    decision = await bandit.route(_make_request())
    assert len(decision.fallback_chain) > 0
    assert decision.expert not in decision.fallback_chain


@pytest.mark.anyio
async def test_route_span_attrs_contains_epsilon() -> None:
    bandit = EpsilonGreedyBandit(rng=random.Random(42))  # noqa: S311
    decision = await bandit.route(_make_request())
    assert "router.epsilon" in decision.span_attrs


@pytest.mark.anyio
async def test_route_exploit_picks_highest_mean_arm() -> None:
    """With ε=0 (always exploit), bandit picks arm with highest mean score."""
    rng = random.Random()  # noqa: S311
    rng.random = lambda: 1.0  # type: ignore[method-assign]  # always > epsilon → exploit

    bandit = EpsilonGreedyBandit(rng=rng)
    phase = DAGPhase.GENERATE_CANDIDATES

    # Pre-load one expert with high score
    bandit._arms[(phase, ExpertID.GEMINI_3_PRO)].update(0.95)
    bandit._arms[(phase, ExpertID.GEMINI_3_PRO)].update(0.95)

    decision = await bandit.route(_make_request(phase=phase))
    assert decision.expert == ExpertID.GEMINI_3_PRO


@pytest.mark.anyio
async def test_route_unsampled_arm_always_wins_exploration() -> None:
    """UCB1 returns inf for unsampled arms — they should always be explored first."""
    rng = random.Random()  # noqa: S311
    rng.random = lambda: 0.0  # type: ignore[method-assign]  # always < epsilon → explore

    bandit = EpsilonGreedyBandit(rng=rng)
    phase = DAGPhase.GENERATE_CANDIDATES

    # Sample all experts except GEMINI_2_5_PRO
    for expert in ExpertID:
        if expert != ExpertID.GEMINI_2_5_PRO:
            bandit._arms[(phase, expert)].update(0.8)

    decision = await bandit.route(_make_request(phase=phase))
    assert decision.expert == ExpertID.GEMINI_2_5_PRO


# ─── observe_outcome() ───────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_observe_outcome_updates_arm_for_expert() -> None:
    bandit = EpsilonGreedyBandit()
    decision = _make_decision(expert=ExpertID.GEMINI_3_FLASH)

    initial_pulls = sum(
        arm.total_pulls
        for (_, expert), arm in bandit._arms.items()
        if expert == ExpertID.GEMINI_3_FLASH
    )
    await bandit.observe_outcome(
        decision=decision,
        achieved_score=0.82,
        actual_cost_usd=0.0005,
        actual_latency_ms=120,
    )
    updated_pulls = sum(
        arm.total_pulls
        for (_, expert), arm in bandit._arms.items()
        if expert == ExpertID.GEMINI_3_FLASH
    )
    assert updated_pulls > initial_pulls


@pytest.mark.anyio
async def test_observe_outcome_improves_mean_score_for_expert() -> None:
    bandit = EpsilonGreedyBandit()
    phase = DAGPhase.GENERATE_CANDIDATES
    decision = _make_decision(expert=ExpertID.GEMINI_3_FLASH)

    await bandit.observe_outcome(
        decision=decision,
        achieved_score=0.90,
        actual_cost_usd=0.0005,
        actual_latency_ms=120,
    )
    arm = bandit._arms[(phase, ExpertID.GEMINI_3_FLASH)]
    assert arm.mean_score == pytest.approx(0.90)


# ─── epsilon decay ────────────────────────────────────────────────────────────


def test_epsilon_floor_is_respected_after_large_elapsed_time() -> None:
    bandit = EpsilonGreedyBandit()
    # Simulate 30 days elapsed
    bandit._start_time -= 30 * 24 * 3600
    eps = bandit._epsilon()
    assert eps == pytest.approx(EPSILON_FLOOR)


def test_epsilon_is_less_after_elapsed_time() -> None:
    bandit = EpsilonGreedyBandit()
    eps_initial = bandit._epsilon()
    bandit._start_time -= 1 * 24 * 3600  # 1 day elapsed
    eps_later = bandit._epsilon()
    assert eps_later < eps_initial


# ─── Protocol compliance ──────────────────────────────────────────────────────


def test_bandit_satisfies_phase_aware_moe_router_protocol() -> None:
    """Structural duck-type check — PhaseAwareMoERouter is not @runtime_checkable."""
    bandit = EpsilonGreedyBandit()
    # Both Protocol methods must exist and be callable
    assert callable(getattr(bandit, "route", None))
    assert callable(getattr(bandit, "observe_outcome", None))
