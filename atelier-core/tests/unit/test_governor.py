import time
from unittest.mock import AsyncMock, patch

import pytest
from atelier.orchestrator.governor import (
    STALL_TIMEOUT_SECONDS,
    FailureMode,
    GovernorBudgetExceeded,
    GovernorState,
    GovernorStepBudgetExceeded,
    MetacognitiveGovernor,
)


@pytest.fixture
def governor() -> MetacognitiveGovernor:
    return MetacognitiveGovernor()


class TestGovernorClassification:
    @pytest.mark.parametrize(
        ("exc", "expected"),
        [
            (GovernorBudgetExceeded("b"), FailureMode.FAIL_LOUD),
            (GovernorStepBudgetExceeded("s"), FailureMode.FAIL_LOUD),
            (ValueError("invalid"), FailureMode.FAIL_SOFT),
            (RuntimeError("context length exceeded"), FailureMode.FAIL_SOFT),
            (TimeoutError("timeout"), FailureMode.SELF_HEAL),
            (Exception("429 Too Many Requests"), FailureMode.SELF_HEAL),
            (Exception("503 Service Unavailable"), FailureMode.SELF_HEAL),
            (Exception("unauthenticated access"), FailureMode.FAIL_LOUD),
            (Exception("some random error"), FailureMode.FAIL_SOFT),
            (Exception("rate limit exceeded"), FailureMode.SELF_HEAL),
        ],
    )
    def test_failure_classification(
        self, governor: MetacognitiveGovernor, exc: Exception, expected: FailureMode
    ) -> None:
        assert governor._classify_failure(exc) == expected


@pytest.mark.anyio
class TestGovernorExecution:
    async def test_successful_execution(self, governor: MetacognitiveGovernor) -> None:
        op = AsyncMock(return_value="success")
        result = await governor.run_with_governance(op, "step1")
        assert result == "success"
        op.assert_awaited_once()

    async def test_fail_loud_raises_immediately(self, governor: MetacognitiveGovernor) -> None:
        op = AsyncMock(side_effect=GovernorBudgetExceeded("over budget"))
        with pytest.raises(GovernorBudgetExceeded):
            await governor.run_with_governance(op, "step1")
        op.assert_awaited_once()

    async def test_fail_soft_returns_none(self, governor: MetacognitiveGovernor) -> None:
        op = AsyncMock(side_effect=ValueError("bad value"))
        result = await governor.run_with_governance(op, "step1")
        assert result is None
        op.assert_awaited_once()

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_self_heal_retries(
        self, mock_sleep: AsyncMock, governor: MetacognitiveGovernor
    ) -> None:
        op = AsyncMock(side_effect=[TimeoutError(), TimeoutError(), "success"])
        result = await governor.run_with_governance(op, "step1")
        assert result == "success"
        assert op.call_count == 3
        assert mock_sleep.call_count == 2
        # Backoff: attempt 1 -> 1.0s, attempt 2 -> 2.0s
        assert mock_sleep.call_args_list[0][0][0] == 1.0
        assert mock_sleep.call_args_list[1][0][0] == 2.0

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_self_heal_max_retries_exceeded(
        self, mock_sleep: AsyncMock, governor: MetacognitiveGovernor
    ) -> None:
        op = AsyncMock(side_effect=TimeoutError("timeout"))
        with pytest.raises(TimeoutError):
            await governor.run_with_governance(op, "step1")
        assert op.call_count == 4  # 1 initial + 3 retries
        assert mock_sleep.call_count == 3
        # Backoff: 1.0s, 2.0s, 4.0s
        assert mock_sleep.call_args_list[2][0][0] == 4.0

    async def test_budget_exceeded_immediately_raises(
        self, governor: MetacognitiveGovernor
    ) -> None:
        op = AsyncMock()
        with pytest.raises(GovernorBudgetExceeded):
            await governor.run_with_governance(op, "step1", cost_estimate_usd=10.0)
        op.assert_not_called()

    async def test_step_budget_exceeded(self, governor: MetacognitiveGovernor) -> None:
        op = AsyncMock()
        # Step cost 0.60 > 0.50
        with pytest.raises(GovernorStepBudgetExceeded):
            await governor.run_with_governance(op, "step1", cost_estimate_usd=0.60)
        op.assert_not_called()

    async def test_cumulative_cost_tracking(self, governor: MetacognitiveGovernor) -> None:
        op = AsyncMock(return_value="ok")
        await governor.run_with_governance(op, "step1", cost_estimate_usd=0.2)
        await governor.run_with_governance(op, "step2", cost_estimate_usd=0.2)
        assert governor._state.total_cost_usd == 0.4

        governor._state.total_cost_usd = 4.9
        with pytest.raises(GovernorBudgetExceeded):
            await governor.run_with_governance(op, "step3", cost_estimate_usd=0.2)


class TestGovernorState:
    def test_is_loop(self) -> None:
        state = GovernorState()
        assert not state.is_loop()

        for _ in range(9):
            state.record_step("step_A")
        assert not state.is_loop()

        state.record_step("step_A")
        assert state.is_loop()

        state.record_step("step_B")
        assert not state.is_loop()

    def test_is_stalled(self) -> None:
        state = GovernorState()
        state.record_step("step_A")
        assert not state.is_stalled()

        state.last_step_time = time.monotonic() - STALL_TIMEOUT_SECONDS - 1.0
        assert state.is_stalled()

    def test_is_over_budget(self) -> None:
        state = GovernorState()
        assert not state.is_over_budget()

        state.total_cost_usd = 6.0
        assert state.is_over_budget()


@pytest.mark.anyio
class TestGovernorIntegration:
    async def test_stall_fails_soft(self) -> None:
        state = GovernorState()
        governor = MetacognitiveGovernor(state)
        state.record_step("step_init")
        state.last_step_time = time.monotonic() - STALL_TIMEOUT_SECONDS - 10.0

        op = AsyncMock()
        result = await governor.run_with_governance(op, "step_new")
        assert result is None
        op.assert_not_called()

    async def test_loop_fails_soft(self) -> None:
        state = GovernorState()
        governor = MetacognitiveGovernor(state)
        for _ in range(10):
            state.record_step("step_loop")

        op = AsyncMock()
        result = await governor.run_with_governance(op, "step_loop")
        assert result is None
        op.assert_not_called()
