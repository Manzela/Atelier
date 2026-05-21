"""Metacognitive Governor — PRD §21 Failure Trichotomy enforcement.

Implements a MAPE-K (Monitor → Analyze → Plan → Execute → Knowledge)
control loop that monitors agent execution health and applies corrections.

Every detected issue maps to exactly ONE failure mode:
    - **fail-loud**: Security breach, budget exhaustion, data corruption
      → Alert + HALT immediately. Non-negotiable.
    - **fail-soft**: Step budget exhausted, infinite loop, stall detected
      → Degrade gracefully, return best partial result, log + notify user.
    - **self-heal**: Transient errors (429, 503, network timeout)
      → Retry with exponential backoff, bounded to max 3 attempts.

This classification is exhaustive and mutually exclusive: every error
the system can encounter is pre-classified into exactly one mode.

Usage:
    governor = MetacognitiveGovernor()

    # Register each tool call:
    governor.register_tool_call(
        tool_name="generate_ui",
        arguments={"prompt": "hero section"},
        cost_usd=0.02,
        made_progress=True,
    )

    # Check if retryable:
    if governor.should_self_heal("vertex_api_call"):
        # retry with backoff
        ...

PRD Reference: §21 (Failure Trichotomy)
Audit Reference: §6 (C7, G12 fix)
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger("atelier.governor")


class FailureMode(StrEnum):
    """Exhaustive failure classification — every error is exactly one of these."""

    FAIL_LOUD = "fail_loud"
    FAIL_SOFT = "fail_soft"
    SELF_HEAL = "self_heal"


class GovernorError(Exception):
    """Raised when the Governor detects a condition requiring intervention.

    Attributes:
        failure_mode: Which failure mode was triggered.
        message: Human-readable description of the issue.
    """

    def __init__(self, message: str, failure_mode: FailureMode) -> None:
        super().__init__(message)
        self.failure_mode = failure_mode


@dataclass(frozen=True)
class ToolCall:
    """Immutable record of a single tool invocation."""

    tool_name: str
    arguments_hash: str
    timestamp: float


@dataclass
class GovernorConfig:
    """Tunable configuration for the Governor's health checks.

    Defaults are conservative — designed for a single-surface generation
    session (~50 tool calls, ~$5 budget).

    Attributes:
        max_consecutive_identical_calls: Threshold for infinite loop detection.
        max_total_steps: Maximum tool calls before forced degradation.
        max_cost_usd: Budget ceiling (fail-loud on breach).
        self_heal_max_retries: Max retries per unique operation key.
        context_exhaustion_threshold: Fraction of context window before warning.
        stall_detection_window: Number of recent steps checked for progress.
    """

    max_consecutive_identical_calls: int = 3
    max_total_steps: int = 50
    max_cost_usd: float = 5.0
    self_heal_max_retries: int = 3
    context_exhaustion_threshold: float = 0.9
    stall_detection_window: int = 10


class MetacognitiveGovernor:
    """MAPE-K governor that monitors agent health and enforces the Failure Trichotomy.

    The governor is stateful — it accumulates tool call history, cost,
    and progress markers across the lifetime of a session.

    Thread Safety:
        NOT thread-safe. Designed for single-threaded agent execution loops.
        If parallel execution is needed, use one Governor per worker.
    """

    def __init__(self, config: GovernorConfig | None = None) -> None:
        self.config = config or GovernorConfig()
        self.tool_history: list[ToolCall] = []
        self.total_cost_usd: float = 0.0
        self.retry_counts: dict[str, int] = {}
        self.progress_markers: list[bool] = []

    @property
    def step_count(self) -> int:
        """Total number of tool calls registered."""
        return len(self.tool_history)

    @property
    def budget_remaining(self) -> float:
        """Remaining budget in USD."""
        return max(0.0, self.config.max_cost_usd - self.total_cost_usd)

    def register_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, object],
        cost_usd: float = 0.0,
        *,
        made_progress: bool = True,
    ) -> None:
        """Register a tool call and run all health checks.

        This is the primary integration point. Call this AFTER every tool
        invocation to let the governor assess system health.

        Args:
            tool_name: Name of the tool that was called.
            arguments: Tool arguments (hashed for loop detection).
            cost_usd: Cost incurred by this call.
            made_progress: Whether this call produced meaningful progress.

        Raises:
            GovernorError: If any health check fails.
        """
        args_hash = hashlib.md5(
            str(sorted(arguments.items())).encode(),
            usedforsecurity=False,
        ).hexdigest()
        self.tool_history.append(ToolCall(tool_name, args_hash, time.time()))
        self.total_cost_usd += cost_usd
        self.progress_markers.append(made_progress)

        # Run all health checks — order matters (most severe first)
        self._check_budget()
        self._check_step_budget()
        self._check_infinite_loop()
        self._check_stall()

    def _check_budget(self) -> None:
        """fail-loud: Budget breach is a security event — HALT immediately."""
        if self.total_cost_usd > self.config.max_cost_usd:
            raise GovernorError(
                f"Budget exceeded: ${self.total_cost_usd:.2f} > "
                f"${self.config.max_cost_usd:.2f}. Halting.",
                FailureMode.FAIL_LOUD,
            )

    def _check_step_budget(self) -> None:
        """fail-soft: Step budget exhaustion degrades gracefully."""
        if len(self.tool_history) > self.config.max_total_steps:
            logger.warning(
                "Step budget exhausted (%d/%d). Entering degraded mode.",
                len(self.tool_history),
                self.config.max_total_steps,
            )
            raise GovernorError(
                f"Step budget exhausted ({len(self.tool_history)} steps). "
                "Returning best partial result.",
                FailureMode.FAIL_SOFT,
            )

    def _check_infinite_loop(self) -> None:
        """fail-soft: Identical consecutive tool calls detected → break loop."""
        n = self.config.max_consecutive_identical_calls
        if len(self.tool_history) < n:
            return
        recent = self.tool_history[-n:]
        fingerprints = {f"{c.tool_name}:{c.arguments_hash}" for c in recent}
        if len(fingerprints) == 1:
            logger.warning(
                "Infinite loop detected: %s called %d times with identical args.",
                recent[0].tool_name,
                n,
            )
            raise GovernorError(
                f"Infinite loop: {recent[0].tool_name} called {n}x "
                "with identical arguments. Breaking loop.",
                FailureMode.FAIL_SOFT,
            )

    def _check_stall(self) -> None:
        """fail-soft: No progress in last N steps → agent is stuck."""
        window = self.config.stall_detection_window
        if len(self.progress_markers) < window:
            return
        recent_progress = self.progress_markers[-window:]
        if not any(recent_progress):
            logger.warning(
                "Stall detected: no progress in last %d steps.",
                window,
            )
            raise GovernorError(
                f"No progress in last {window} steps. Returning best partial result.",
                FailureMode.FAIL_SOFT,
            )

    def should_self_heal(self, operation_key: str) -> bool:
        """self-heal: Check if retry budget remains for a specific operation.

        Args:
            operation_key: Unique key identifying the operation to retry
                (e.g., ``"vertex_api_generate_ui"``).

        Returns:
            True if retry is allowed; False if retry budget exhausted.
        """
        count = self.retry_counts.get(operation_key, 0)
        if count >= self.config.self_heal_max_retries:
            return False
        self.retry_counts[operation_key] = count + 1
        return True

    def get_retry_delay(self, operation_key: str) -> float:
        """Calculate exponential backoff delay for a retryable operation.

        Returns seconds to wait: ``2^(attempt - 1)`` capped at 30s.
        """
        attempt = self.retry_counts.get(operation_key, 1)
        return min(2.0 ** (attempt - 1), 30.0)

    def reset(self) -> None:
        """Reset all governor state. Used between sessions."""
        self.tool_history.clear()
        self.total_cost_usd = 0.0
        self.retry_counts.clear()
        self.progress_markers.clear()
