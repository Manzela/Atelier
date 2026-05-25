"""MetacognitiveGovernor — MAPE-K autonomous failure management.

Per PRD §21 Failure Trichotomy:
    FAIL_LOUD: security breach, budget cap, data corruption → alert + halt
    FAIL_SOFT: tool errors, stall, infinite loop → degrade + log + acknowledge
    SELF_HEAL: 429/503 transient → retry with bounded exponential backoff

MAPE-K mapping:
    Monitor  → _monitor_heartbeat(), _check_budget(), _check_step_budget()
    Analyze  → _classify_failure()
    Plan     → should_self_heal(), should_fail_soft(), should_fail_loud()
    Execute  → execute_self_heal() (backoff), execute_fail_soft() (log + degrade)
    Knowledge → _loop_detection_window (sliding window of recent steps)

Hard caps (from CLAUDE.md):
    MAX_SELF_HEAL_RETRIES = 3   # per operation
    MAX_LOOP_ITERATIONS = 10    # detect infinite loops
    STALL_TIMEOUT_SECONDS = 300 # 5 minutes without progress → fail-soft
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Final, TypeVar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

MAX_SELF_HEAL_RETRIES: Final[int] = 3
MAX_LOOP_ITERATIONS: Final[int] = 10
STALL_TIMEOUT_SECONDS: Final[float] = 300.0
BACKOFF_BASE_SECONDS: Final[float] = 1.0
BACKOFF_MAX_SECONDS: Final[float] = 32.0
MAX_STEP_COST_USD: Final[float] = 0.50


class FailureMode(StrEnum):
    FAIL_LOUD = "FAIL_LOUD"
    FAIL_SOFT = "FAIL_SOFT"
    SELF_HEAL = "SELF_HEAL"


class GovernorBudgetExceeded(Exception):  # noqa: N818  # name matches domain terminology
    """Raised when the cumulative budget cap is exceeded."""


class GovernorStepBudgetExceeded(Exception):  # noqa: N818  # name matches domain terminology
    """Raised when a single step exceeds the cost limit."""


@dataclass
class GovernorState:
    retry_count: int = 0
    last_step_time: float = field(default_factory=time.monotonic)
    step_history: deque[str] = field(default_factory=lambda: deque(maxlen=MAX_LOOP_ITERATIONS))
    total_cost_usd: float = 0.0
    budget_cap_usd: float = 5.0  # PRD §7.2

    def record_step(self, step_id: str) -> None:
        self.step_history.append(step_id)
        self.last_step_time = time.monotonic()

    def is_loop(self) -> bool:
        if len(self.step_history) < MAX_LOOP_ITERATIONS:
            return False
        # A loop is if all items in the history are exactly the same
        first = self.step_history[0]
        return all(s == first for s in self.step_history)

    def is_stalled(self) -> bool:
        return (time.monotonic() - self.last_step_time) > STALL_TIMEOUT_SECONDS

    def is_over_budget(self) -> bool:
        return self.total_cost_usd > self.budget_cap_usd


T = TypeVar("T")


class MetacognitiveGovernor:
    """Wraps any async coroutine with MAPE-K failure management."""

    def __init__(self, state: GovernorState | None = None) -> None:
        self._state = state or GovernorState()

    def _classify_failure(self, exc: BaseException) -> FailureMode:
        """Classify exception into trichotomy. Never returns None."""
        if isinstance(exc, GovernorBudgetExceeded | GovernorStepBudgetExceeded):
            return FailureMode.FAIL_LOUD

        # We classify timeouts and specific http errors as SELF_HEAL
        exc_str = str(exc).lower()
        exc_type_name = type(exc).__name__

        if exc_type_name in ("TimeoutException", "TimeoutError", "ConnectTimeout", "ReadTimeout"):
            return FailureMode.SELF_HEAL

        if (
            "429" in exc_str
            or "503" in exc_str
            or "rate limit" in exc_str
            or "too many requests" in exc_str
        ):
            return FailureMode.SELF_HEAL

        if "unauthenticated" in exc_str or "unauthorized" in exc_str or "credentials" in exc_str:
            return FailureMode.FAIL_LOUD

        if isinstance(exc, ValueError | RuntimeError):
            return FailureMode.FAIL_SOFT

        return FailureMode.FAIL_SOFT

    async def run_with_governance(
        self,
        operation: Callable[[], Awaitable[T]],
        step_id: str,
        cost_estimate_usd: float = 0.0,
    ) -> T | None:
        """Execute operation under MAPE-K governance. Retries on SELF_HEAL."""
        self._check_budget(cost_estimate_usd)
        self._check_step_budget(cost_estimate_usd)

        if self._state.is_stalled():
            logger.warning("FAIL_SOFT: Pipeline stalled for step_id=%s", step_id)
            return None

        self._state.record_step(step_id)
        if self._state.is_loop():
            logger.warning("FAIL_SOFT: Infinite loop detected for step_id=%s", step_id)
            return None

        self._state.total_cost_usd += cost_estimate_usd

        # Reset retry count for a new operation
        self._state.retry_count = 0

        while True:
            try:
                return await operation()
            except Exception as e:
                mode = self._classify_failure(e)
                if mode == FailureMode.FAIL_LOUD:
                    logger.exception("FAIL_LOUD: Unrecoverable error")
                    raise
                if mode == FailureMode.SELF_HEAL:
                    if self._state.retry_count >= MAX_SELF_HEAL_RETRIES:
                        logger.exception("FAIL_LOUD: Max retries exceeded for SELF_HEAL error")
                        raise

                    self._state.retry_count += 1
                    backoff = min(
                        BACKOFF_MAX_SECONDS,
                        BACKOFF_BASE_SECONDS * (2 ** (self._state.retry_count - 1)),
                    )
                    logger.info(
                        "SELF_HEAL: Transient error %s, retrying in %f seconds (attempt %d/%d)",
                        type(e).__name__,
                        backoff,
                        self._state.retry_count,
                        MAX_SELF_HEAL_RETRIES,
                    )
                    await asyncio.sleep(backoff)
                else:  # FAIL_SOFT
                    logger.warning("FAIL_SOFT: Degraded execution due to error: %s", e)
                    return None

    def _check_budget(self, cost_usd: float) -> None:
        """Raises GovernorBudgetExceeded (FAIL_LOUD) if over budget."""
        if self._state.total_cost_usd + cost_usd > self._state.budget_cap_usd:
            raise GovernorBudgetExceeded(
                f"Budget exceeded. Cap: {self._state.budget_cap_usd}, "
                f"Current: {self._state.total_cost_usd}, Requested: {cost_usd}"
            )

    def _check_step_budget(self, step_cost: float) -> None:
        """Raises GovernorStepBudgetExceeded if single step exceeds $0.50."""
        if step_cost > MAX_STEP_COST_USD:
            raise GovernorStepBudgetExceeded(
                f"Step cost {step_cost} exceeds ${MAX_STEP_COST_USD} limit"
            )
