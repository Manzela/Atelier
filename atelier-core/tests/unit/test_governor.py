import time
from unittest.mock import AsyncMock, patch

import pytest
from atelier.orchestrator.governor import (
    STALL_TIMEOUT_SECONDS,
    TOKEN_CAP_DEFAULT,
    FailureMode,
    GovernorRateLimitExceeded,
    GovernorState,
    GovernorTokenCapExceeded,
    MetacognitiveGovernor,
)


@pytest.fixture
def governor() -> MetacognitiveGovernor:
    return MetacognitiveGovernor()


class TestGovernorClassification:
    @pytest.mark.parametrize(
        ("exc", "expected"),
        [
            # AT-095: the token cap + rate limit are fail-loud security controls.
            (GovernorTokenCapExceeded(uid="u1"), FailureMode.FAIL_LOUD),
            (GovernorRateLimitExceeded(uid="u1"), FailureMode.FAIL_LOUD),
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
        op = AsyncMock(side_effect=GovernorTokenCapExceeded(uid="u1"))
        with pytest.raises(GovernorTokenCapExceeded):
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

    async def test_token_cap_preflight_raises_before_operation(
        self, governor: MetacognitiveGovernor
    ) -> None:
        # AT-095 acceptance (c): once at/over the cap, the governance pre-flight
        # raises BEFORE the operation runs — no Vertex call is made.
        governor._state.user_id = "u1"
        governor._state.cumulative_user_tokens = TOKEN_CAP_DEFAULT
        op = AsyncMock()
        with pytest.raises(GovernorTokenCapExceeded):
            await governor.run_with_governance(op, "step1")
        op.assert_not_called()

    async def test_under_cap_runs_normally(self, governor: MetacognitiveGovernor) -> None:
        governor._state.user_id = "u1"
        governor._state.cumulative_user_tokens = TOKEN_CAP_DEFAULT - 1
        op = AsyncMock(return_value="ok")
        assert await governor.run_with_governance(op, "step1") == "ok"
        op.assert_awaited_once()

    async def test_add_user_tokens_accumulates_input_output_thinking(
        self, governor: MetacognitiveGovernor
    ) -> None:
        # AT-095 acceptance (g): thinking tokens count toward the lifetime total.
        total = governor._state.add_user_tokens(
            input_tokens=10, output_tokens=20, thinking_tokens=5
        )
        assert total == 35
        assert governor._state.cumulative_user_tokens == 35

    async def test_add_user_tokens_rejects_negative(self, governor: MetacognitiveGovernor) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            governor._state.add_user_tokens(input_tokens=-1)


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

    def test_is_over_token_cap(self) -> None:
        state = GovernorState()
        assert not state.is_over_token_cap()

        state.cumulative_user_tokens = TOKEN_CAP_DEFAULT - 1
        assert not state.is_over_token_cap()

        # The cap fires AT the limit (>=), not only strictly above it.
        state.cumulative_user_tokens = TOKEN_CAP_DEFAULT
        assert state.is_over_token_cap()


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
