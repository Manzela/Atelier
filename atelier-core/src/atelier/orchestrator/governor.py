"""MetacognitiveGovernor — MAPE-K autonomous failure management.

Per PRD §21 Failure Trichotomy:
    FAIL_LOUD: security breach, token-cap breach, data corruption → alert + halt
    FAIL_SOFT: tool errors, stall, infinite loop → degrade + log + acknowledge
    SELF_HEAL: 429/503 transient → retry with bounded exponential backoff

MAPE-K mapping:
    Monitor  → _monitor_heartbeat(), _check_token_budget()
    Analyze  → _classify_failure()
    Plan     → should_self_heal(), should_fail_soft(), should_fail_loud()
    Execute  → execute_self_heal() (backoff), execute_fail_soft() (log + degrade)
    Knowledge → _loop_detection_window (sliding window of recent steps)

Hard caps (from architectural invariants):
    MAX_SELF_HEAL_RETRIES = 3   # per operation
    MAX_LOOP_ITERATIONS = 10    # detect infinite loops
    STALL_TIMEOUT_SECONDS = 300 # 5 minutes without progress → fail-soft

Usage governance (AT-095, PRD §13.2 / G14 / G16):
    The legacy per-RUN USD budget cap is removed — it reset every ``run()`` and
    was bypassable. The V1 caps are **per-user lifetime token caps per model
    tier** (proactive calibration per model_registry.TIER_TOKEN_CAPS):

        gemini-2.5-pro       ->  5_000_000 tokens (planning, originality judging)
        gemini-2.5-flash     -> 15_000_000 tokens (generation, visual judges)
        gemini-2.5-flash-lite -> 60_000_000 tokens (extraction, copy, accessibility)

    GovernorState tracks a ``per_tier_tokens`` accumulator alongside the legacy
    ``cumulative_user_tokens`` (aggregate for reporting). ``_check_token_budget``
    fails-loud if ANY tier exceeds its cap. The caps are persisted across runs by
    :mod:`atelier.durability.usage_counter` (per-tier Firestore fields).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, TypeVar

from atelier.models.model_registry import TIER_TOKEN_CAPS, model_tier_for_id
from atelier.runtime.failure import FailureMode

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

MAX_SELF_HEAL_RETRIES: Final[int] = 3
MAX_LOOP_ITERATIONS: Final[int] = 10
STALL_TIMEOUT_SECONDS: Final[float] = 300.0
BACKOFF_BASE_SECONDS: Final[float] = 1.0
BACKOFF_MAX_SECONDS: Final[float] = 32.0

#: Legacy single-cap fallback — used only when no tier is tracked (e.g. unit
#: tests that call add_user_tokens without a model_id).  Production code always
#: passes model_id so per-tier caps from TIER_TOKEN_CAPS are checked instead.
TOKEN_CAP_DEFAULT: Final[int] = TIER_TOKEN_CAPS["pro"]

#: The one branded, non-error message shown when a user reaches the cap (PRD
#: §13.2). Used identically by the graceful in-run stop and the 402 response so
#: the user sees it exactly once and never a raw quota error.
TOKEN_CAP_MESSAGE: Final[str] = (
    "You've reached this account's usage limit. Contact administrator to continue."  # noqa: S105
)

#: Shown when the usage store cannot be read/written (transient outage or a
#: corrupt counter). The cap is fail-CLOSED (we deny rather than serve without a
#: working guard on a paid endpoint), but the acknowledgement is HONEST: this is
#: a transient, retryable infra fault — NOT a cap breach (PRD §21 trichotomy:
#: "agent always acknowledges degradation"). Distinct message + HTTP 503.
USAGE_UNAVAILABLE_MESSAGE: Final[str] = (
    "We couldn't verify your usage right now and stopped to be safe. "
    "This is temporary — please retry shortly."
)

#: Shown when the fleet-wide (global) token circuit-breaker is open (AT-097). A
#: SYSTEM-level protection on the shared paid key: aggregate token consumption
#: across ALL users crossed the operator-set budget, so new work is paused for a
#: short cooldown. The individual user did nothing wrong (unlike the per-user cap
#: or per-user rate limit), so this is an HONEST, retryable degradation (PRD §21)
#: surfaced as HTTP 503 + Retry-After — never the per-user "you reached your
#: limit" message. Distinct from USAGE_UNAVAILABLE_MESSAGE (a read/write fault).
CIRCUIT_BREAKER_MESSAGE: Final[str] = (
    "The service is briefly busy protecting shared capacity and paused new work "
    "to stay reliable. This is temporary — please retry shortly."
)


class GovernorTokenCapExceeded(Exception):  # noqa: N818 — domain terminology
    """Raised when a user's cumulative lifetime token count reaches the cap.

    Fail-loud (PRD R5/§13): a cap is a security control, **never** self-healed.
    Carries the structured context the alertable breach log requires
    (uid / session / client IP / which cap).
    """

    def __init__(
        self,
        *,
        uid: str | None = None,
        used_tokens: int = 0,
        cap_tokens: int = TOKEN_CAP_DEFAULT,
        session_id: str | None = None,
        client_ip: str | None = None,
        which_cap: str = "per_user_lifetime",
        exceeded_tier: str | None = None,
    ) -> None:
        self.uid = uid
        self.used_tokens = used_tokens
        self.cap_tokens = cap_tokens
        self.session_id = session_id
        self.client_ip = client_ip
        self.which_cap = which_cap
        self.exceeded_tier = exceeded_tier
        tier_suffix = f" (tier={exceeded_tier})" if exceeded_tier else ""
        super().__init__(
            f"Token cap reached ({which_cap}){tier_suffix}: "
            f"{used_tokens} >= {cap_tokens} for uid={uid}"
        )


class GovernorUsageUnavailable(Exception):  # noqa: N818 — domain terminology
    """Raised when the usage store cannot be read/written (fail-closed deny).

    Distinct from :class:`GovernorTokenCapExceeded`: this is a TRANSIENT infra
    fault (Firestore unavailable) or a data-integrity fault (a non-coercible
    counter value) — retryable, surfaced as HTTP 503 + a retry message, NEVER
    the permanent "you reached your limit / contact admin" cap message. We still
    DENY generation (a paid endpoint must not run without a working cap guard),
    but we acknowledge the degradation honestly (PRD §21).
    """

    def __init__(
        self,
        *,
        uid: str | None = None,
        reason: str = "usage_store_unavailable",
        client_ip: str | None = None,
    ) -> None:
        self.uid = uid
        self.reason = reason
        self.client_ip = client_ip
        super().__init__(f"Usage store unavailable ({reason}) for uid={uid}; failing closed.")


class GovernorRateLimitExceeded(Exception):  # noqa: N818 — domain terminology
    """Raised when one uid issues too many requests inside the rate window.

    Guards against burning the lifetime cap in seconds (AT-095 acceptance (f);
    made global + tunable in AT-097). Fail-loud reject of the offending request.
    """

    def __init__(
        self,
        *,
        uid: str | None = None,
        max_requests: int = 0,
        window_seconds: float = 0.0,
        client_ip: str | None = None,
    ) -> None:
        self.uid = uid
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.client_ip = client_ip
        super().__init__(
            f"Rate limit exceeded for uid={uid}: > {max_requests} requests in {window_seconds:.0f}s"
        )


class GovernorCircuitBreakerOpen(Exception):  # noqa: N818 — domain terminology
    """Raised when the fleet-wide (global) token circuit-breaker is open (AT-097).

    The third of the three orthogonal limits (PRD §13.2): per-user lifetime cap ·
    **per-total/global circuit-breaker** · per-window request-rate limit. Trips
    when aggregate token consumption across ALL users inside a rolling window
    crosses the operator-set budget (§22 D-cap-numbers — operator-open; only the
    per-user 5M is fixed). Protects the shared paid Vertex key from a coordinated
    multi-account / sybil burn that each-individually stays under 5M.

    A SYSTEM protection, not a user fault — surfaced as a retryable HTTP 503 +
    Retry-After, never the per-user cap message. Fail-loud (never self-healed,
    R5): a breaker that silently self-heals is not a breaker.
    """

    def __init__(
        self,
        *,
        reason: str = "global_token_budget",
        retry_after_seconds: int = 60,
        window_tokens: int = 0,
        budget: int = 0,
        client_ip: str | None = None,
    ) -> None:
        self.reason = reason
        self.retry_after_seconds = retry_after_seconds
        self.window_tokens = window_tokens
        self.budget = budget
        self.client_ip = client_ip
        super().__init__(
            f"Global circuit-breaker open ({reason}): "
            f"{window_tokens} >= {budget} tokens in window; retry after {retry_after_seconds}s"
        )


@dataclass
class GovernorState:
    retry_count: int = 0
    last_step_time: float = field(default_factory=time.monotonic)
    step_history: deque[str] = field(default_factory=lambda: deque(maxlen=MAX_LOOP_ITERATIONS))
    # AT-095 per-user lifetime token cap.  ``user_id`` identifies whose cap this
    # is; ``cumulative_user_tokens`` is seeded at run start from the persisted
    # Firestore counter (so it spans runs) and grows as tokens are consumed.
    # ``token_cap`` (== the Pro-tier cap) is the ACTIVE aggregate ceiling on a
    # user's TOTAL cross-tier usage — ``is_over_token_cap`` checks it unconditionally
    # (L11). This is the conservative cost policy: a user is capped at the aggregate
    # regardless of which tier the tokens came from; the per-tier caps below are
    # ADDITIONAL enforcement layered on top, not a replacement. (To switch to a
    # per-tier-only policy — letting Flash/Flash-Lite users spend up to their higher
    # tier caps — see L11 in the audit ledger; that is a cost-policy change.)
    user_id: str | None = None
    cumulative_user_tokens: int = 0
    token_cap: int = TOKEN_CAP_DEFAULT
    # Per-tier token accumulators (tiered caps per user.spec).
    # Keyed by tier string ("pro", "flash", "flash_lite") matching TIER_TOKEN_CAPS.
    # Seeded at run start from UsageCounterStore.snapshot_tier() for each tier.
    per_tier_tokens: dict[str, int] = field(default_factory=dict)
    # AT-031 per-stage accumulators. Keyed by stable stage id.
    stage_call_counts: dict[str, int] = field(default_factory=dict)
    stage_token_counts: dict[str, int] = field(default_factory=dict)

    def record_step(self, step_id: str) -> None:
        self.step_history.append(step_id)
        self.last_step_time = time.monotonic()

    def record_stage_call(self, stage_id: str, tokens: int = 0) -> None:
        """Increment the per-stage call count and token accumulator for ``stage_id``.

        Args:
            stage_id: Stable stage identifier (not iteration-specific), e.g.
                ``"n1_brief_parse"``, ``"n2_source_resolve"``,
                ``"n3a_specialist_pipeline"``.
            tokens: Tokens attributed to this stage call (added to the running total).
        """
        self.stage_call_counts[stage_id] = self.stage_call_counts.get(stage_id, 0) + 1
        self.stage_token_counts[stage_id] = self.stage_token_counts.get(stage_id, 0) + tokens

    def add_user_tokens(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        thinking_tokens: int = 0,
        model_id: str | None = None,
    ) -> int:
        """Add a token delta to the lifetime total, attributed to the model tier.

        Updates both the aggregate ``cumulative_user_tokens`` (for reporting)
        and the per-tier ``per_tier_tokens`` accumulator (for tiered cap checks).

        Args:
            input_tokens: Input token count for this call.
            output_tokens: Output token count for this call.
            thinking_tokens: Thinking/reasoning token count for this call.
            model_id: Vertex AI model ID used for this call.  Passed to
                :func:`model_tier_for_id` to derive the tier key.  When absent
                the delta is added to the aggregate only (no per-tier check fires
                on the unknown tier — conservative safe path).

        Returns:
            The new cumulative total across all tiers.
        """
        if input_tokens < 0 or output_tokens < 0 or thinking_tokens < 0:
            raise ValueError("token deltas must be non-negative")
        delta = input_tokens + output_tokens + thinking_tokens
        self.cumulative_user_tokens += delta
        if model_id is not None:
            tier = model_tier_for_id(model_id)
            self.per_tier_tokens[tier] = self.per_tier_tokens.get(tier, 0) + delta
        return self.cumulative_user_tokens

    def reconcile_cumulative(self, shared_total: int) -> None:
        """L12: raise the in-memory cumulative to the durable store's atomic total.

        Each run builds a private ``GovernorState`` seeded once at run start, so two
        CONCURRENT runs for the SAME user would each only count their OWN tokens and
        both pass the cap check — a TOCTOU that lets N parallel runs each spend the
        full remaining cap. After every persisted charge, the runner feeds the
        ``UsageCounterStore.add`` return (the atomic post-write cumulative shared
        across instances) here, so this state reflects the user's TRUE total and the
        next cap check sees concurrent spend. Only ever RAISES the count (usage grows
        monotonically); ``max`` also guards the L52 degraded-read floor, where
        ``add`` may return the delta rather than the true total.
        """
        self.cumulative_user_tokens = max(self.cumulative_user_tokens, shared_total)

    def exceeded_tier(self) -> str | None:
        """Return the first tier that has reached its cap, or None if all are under.

        Checked in priority order: Pro (smallest cap) → Flash → Flash-Lite.
        Returns the tier string so the caller can surface which cap was hit.
        """
        for tier in ("pro", "flash", "flash_lite"):
            cap = TIER_TOKEN_CAPS.get(tier, TOKEN_CAP_DEFAULT)
            used = self.per_tier_tokens.get(tier, 0)
            if used >= cap:
                return tier
        return None

    @staticmethod
    def _stable_step_key(step_id: str) -> str:
        """Strip a trailing ``_<digits>`` iteration suffix from a step id.

        Runner step ids are formatted as ``<stage>_<screen>_<iteration>``
        (e.g. ``convergence_loop_landing_3``).  The iteration counter makes
        every recorded entry unique, so a naive all-equal comparison can never
        detect a true loop.  Stripping the suffix yields the stable stage key
        (``convergence_loop_landing``) that repeats across iterations.
        """
        return re.sub(r"_\d+$", "", step_id)

    def is_loop(self) -> bool:
        """Return True when the same stable stage has repeated MAX_LOOP_ITERATIONS times.

        Compares the iteration-stripped stage key of every entry in
        ``step_history`` so that step ids that embed an increasing iteration
        counter (e.g. ``convergence_loop_landing_0`` …
        ``convergence_loop_landing_9``) still trigger the guard.
        """
        if len(self.step_history) < MAX_LOOP_ITERATIONS:
            return False
        keys = [self._stable_step_key(s) for s in self.step_history]
        first = keys[0]
        return all(k == first for k in keys)

    def is_stalled(self) -> bool:
        return (time.monotonic() - self.last_step_time) > STALL_TIMEOUT_SECONDS

    def is_over_token_cap(self) -> bool:
        """True if any per-tier cap is reached, or the aggregate fallback cap is reached.

        Always checks the cumulative aggregate first: when legacy callers omit
        ``model_id`` the tokens only appear in ``cumulative_user_tokens``, not in
        any tier bucket.  A user who exhausted the Pro cap via non-attributed calls
        must still be stopped even if their per-tier buckets are all zero or still
        under cap.  Per-tier enforcement is additive on top of the aggregate check.
        """
        if self.cumulative_user_tokens >= self.token_cap:
            return True
        return self.exceeded_tier() is not None


T = TypeVar("T")


def _is_rate_limit_error(exc: BaseException) -> bool:
    """True when ``exc`` is a provider rate-limit / quota exhaustion (e.g. a Vertex
    AI ``429 RESOURCE_EXHAUSTED``).

    Used to surface a sustained, retry-exhausted rate limit as the graceful
    :class:`GovernorRateLimitExceeded` instead of a raw provider error.
    """
    s = str(exc).lower()
    return (
        "429" in s
        or "resource_exhausted" in s
        or "resource exhausted" in s
        or "too many requests" in s
        or "rate limit" in s
    )


class MetacognitiveGovernor:
    """Wraps any async coroutine with MAPE-K failure management."""

    def __init__(self, state: GovernorState | None = None) -> None:
        self._state = state or GovernorState()

    def _classify_failure(self, exc: BaseException) -> FailureMode:
        """Classify exception into trichotomy. Never returns None."""
        if isinstance(
            exc,
            GovernorTokenCapExceeded
            | GovernorRateLimitExceeded
            | GovernorUsageUnavailable
            | GovernorCircuitBreakerOpen,
        ):
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
    ) -> T | None:
        """Execute operation under MAPE-K governance. Retries on SELF_HEAL.

        Pre-flight: fail-loud if the user's lifetime token cap is already
        reached (no Vertex call is made once at cap — AT-095 acceptance (c)).
        """
        self._check_token_budget()

        if self._state.is_stalled():
            logger.warning("FAIL_SOFT: Pipeline stalled for step_id=%s", step_id)
            return None

        self._state.record_step(step_id)
        if self._state.is_loop():
            logger.warning("FAIL_SOFT: Infinite loop detected for step_id=%s", step_id)
            return None

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
                        # A sustained model-side rate limit (Vertex 429
                        # RESOURCE_EXHAUSTED) that survives the self-heal budget is
                        # surfaced as the graceful, domain GovernorRateLimitExceeded
                        # so the API emits the honest "too many requests, retry
                        # shortly" (HTTP 429) instead of a generic "Pipeline error".
                        # Other transient classes (503, timeouts) keep raw propagation.
                        if _is_rate_limit_error(e):
                            raise GovernorRateLimitExceeded() from e
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

    def _check_token_budget(self) -> None:
        """Raises GovernorTokenCapExceeded (FAIL_LOUD) if at/over any tier cap.

        When per-tier data is present, checks each tier against TIER_TOKEN_CAPS
        and raises with the exact exceeded tier in the exception.  Falls back to
        the legacy aggregate check when no tier data exists.
        """
        exceeded = self._state.exceeded_tier()
        if exceeded is not None:
            tier_cap = TIER_TOKEN_CAPS.get(exceeded, TOKEN_CAP_DEFAULT)
            used = self._state.per_tier_tokens.get(exceeded, 0)
            logger.error(
                "atelier.governor.tier_cap_exceeded",
                extra={
                    "uid": self._state.user_id,
                    "exceeded_tier": exceeded,
                    "used": used,
                    "cap": tier_cap,
                    "cumulative": self._state.cumulative_user_tokens,
                },
            )
            raise GovernorTokenCapExceeded(
                uid=self._state.user_id,
                used_tokens=used,
                cap_tokens=tier_cap,
                which_cap=f"per_user_lifetime_{exceeded}",
                exceeded_tier=exceeded,
            )
        # Legacy fallback: no per-tier data (older code path or test without model_id).
        if self._state.is_over_token_cap():
            raise GovernorTokenCapExceeded(
                uid=self._state.user_id,
                used_tokens=self._state.cumulative_user_tokens,
                cap_tokens=self._state.token_cap,
            )
