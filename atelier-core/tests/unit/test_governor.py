"""Tests for the Metacognitive Governor (PRD §21 Failure Trichotomy).

Validates: fail-loud (budget), fail-soft (step budget, loop, stall),
self-heal (bounded retries), backoff calculation, and state reset.
"""

from __future__ import annotations

import pytest
from atelier.durability.governor import (
    FailureMode,
    GovernorConfig,
    GovernorError,
    MetacognitiveGovernor,
)

# --- Config for tests (extracted to avoid PLR2004 magic values) ---
TEST_MAX_COST_USD = 1.0
TEST_BACKOFF_ATTEMPT_1 = 1.0  # 2^0
TEST_BACKOFF_ATTEMPT_2 = 2.0  # 2^1
FLOAT_EPSILON = 1e-10


@pytest.fixture
def governor() -> MetacognitiveGovernor:
    """Governor with tight limits for test efficiency."""
    return MetacognitiveGovernor(
        GovernorConfig(
            max_consecutive_identical_calls=3,
            max_total_steps=5,
            max_cost_usd=TEST_MAX_COST_USD,
            self_heal_max_retries=2,
            stall_detection_window=3,
        ),
    )


@pytest.mark.unit
class TestFailLoud:
    """fail-loud: Security/budget breaches halt immediately."""

    def test_budget_exceeded_raises_fail_loud(self, governor: MetacognitiveGovernor) -> None:
        governor.register_tool_call("tool_a", {"k": "v"}, cost_usd=0.5)
        governor.register_tool_call("tool_b", {"k": "v2"}, cost_usd=0.4)
        with pytest.raises(GovernorError) as exc_info:
            governor.register_tool_call("tool_c", {"k": "v3"}, cost_usd=0.2)
        assert exc_info.value.failure_mode == FailureMode.FAIL_LOUD

    def test_budget_exactly_at_limit_is_ok(self, governor: MetacognitiveGovernor) -> None:
        governor.register_tool_call("tool_a", {"k": "v"}, cost_usd=TEST_MAX_COST_USD)
        # Should NOT raise — budget is exactly at limit, not exceeded


@pytest.mark.unit
class TestFailSoft:
    """fail-soft: Degradation, not crash."""

    def test_step_budget_exceeded_raises_fail_soft(self, governor: MetacognitiveGovernor) -> None:
        for i in range(5):
            governor.register_tool_call(f"tool_{i}", {"i": i})
        with pytest.raises(GovernorError) as exc_info:
            governor.register_tool_call("tool_6", {"i": 6})
        assert exc_info.value.failure_mode == FailureMode.FAIL_SOFT

    def test_infinite_loop_detected(self, governor: MetacognitiveGovernor) -> None:
        governor.register_tool_call("tool_x", {"arg": "same"})
        governor.register_tool_call("tool_x", {"arg": "same"})
        with pytest.raises(GovernorError, match="Infinite loop") as exc_info:
            governor.register_tool_call("tool_x", {"arg": "same"})
        assert exc_info.value.failure_mode == FailureMode.FAIL_SOFT

    def test_different_tools_no_loop(self, governor: MetacognitiveGovernor) -> None:
        governor.register_tool_call("tool_a", {"arg": "same"})
        governor.register_tool_call("tool_b", {"arg": "same"})
        governor.register_tool_call("tool_c", {"arg": "same"})
        # No loop — tools are different

    def test_stall_detected(self, governor: MetacognitiveGovernor) -> None:
        governor.register_tool_call(
            "tool_0",
            {"i": 0},
            made_progress=False,
        )
        governor.register_tool_call(
            "tool_1",
            {"i": 1},
            made_progress=False,
        )
        with pytest.raises(GovernorError, match="No progress") as exc_info:
            governor.register_tool_call(
                "tool_2",
                {"i": 2},
                made_progress=False,
            )
        assert exc_info.value.failure_mode == FailureMode.FAIL_SOFT

    def test_intermittent_progress_no_stall(self, governor: MetacognitiveGovernor) -> None:
        governor.register_tool_call("tool_0", {"i": 0}, made_progress=False)
        governor.register_tool_call("tool_1", {"i": 1}, made_progress=True)
        governor.register_tool_call("tool_2", {"i": 2}, made_progress=False)
        # No stall — progress was made in window


@pytest.mark.unit
class TestSelfHeal:
    """self-heal: Bounded retries with exponential backoff."""

    def test_retries_within_budget(self, governor: MetacognitiveGovernor) -> None:
        assert governor.should_self_heal("vertex_call") is True
        assert governor.should_self_heal("vertex_call") is True

    def test_retries_exhausted(self, governor: MetacognitiveGovernor) -> None:
        governor.should_self_heal("vertex_call")
        governor.should_self_heal("vertex_call")
        assert governor.should_self_heal("vertex_call") is False

    def test_different_operations_independent(self, governor: MetacognitiveGovernor) -> None:
        governor.should_self_heal("op_a")
        governor.should_self_heal("op_a")
        assert governor.should_self_heal("op_a") is False
        assert governor.should_self_heal("op_b") is True  # separate budget

    def test_backoff_delay_exponential(self, governor: MetacognitiveGovernor) -> None:
        governor.should_self_heal("op_x")  # attempt 1
        assert governor.get_retry_delay("op_x") == TEST_BACKOFF_ATTEMPT_1
        governor.should_self_heal("op_x")  # attempt 2
        assert governor.get_retry_delay("op_x") == TEST_BACKOFF_ATTEMPT_2


@pytest.mark.unit
class TestGovernorState:
    """State management and properties."""

    def test_step_count(self, governor: MetacognitiveGovernor) -> None:
        assert governor.step_count == 0
        governor.register_tool_call("tool_a", {"k": "v"})
        assert governor.step_count == 1

    def test_budget_remaining(self, governor: MetacognitiveGovernor) -> None:
        expected_remaining = 0.7
        assert governor.budget_remaining == TEST_MAX_COST_USD
        governor.register_tool_call("tool_a", {"k": "v"}, cost_usd=0.3)
        assert abs(governor.budget_remaining - expected_remaining) < FLOAT_EPSILON

    def test_reset(self, governor: MetacognitiveGovernor) -> None:
        governor.register_tool_call("tool_a", {"k": "v"}, cost_usd=0.5)
        governor.should_self_heal("op")
        governor.reset()
        assert governor.step_count == 0
        assert governor.total_cost_usd == 0.0
        assert governor.budget_remaining == TEST_MAX_COST_USD
        assert governor.should_self_heal("op") is True  # budget reset
