"""Failure trichotomy — typed failure modes for external-IO callsites (ADR 0031).

Every function that performs external IO (gcloud, Vertex API, BigQuery, etc.)
MUST be decorated with ``@failure_trichotomy`` to declare its failure mode at
the type level. This eliminates silent error suppression and makes the failure
contract machine-verifiable via grep + mypy.

Three modes per architectural invariants §5 (failure-handling trichotomy):

- **FAIL_LOUD**: Raise immediately. No retries. Used for auth failures,
  missing projects, corrupted state — situations where retrying is
  meaningless or dangerous.

- **FAIL_SOFT**: Log a warning and return ``None``. No retries. Used for
  degradable paths (e.g., optional telemetry, missing CI workflow job)
  where the caller can proceed without the result.

- **SELF_HEAL**: Retry up to ``max_retries`` times, then escalate to
  FAIL_LOUD (raise). Used for transient errors (gcloud 429/503,
  pip install timeouts, ``gh api`` rate limits).
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Callable
from enum import StrEnum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class FailureMode(StrEnum):
    """Exhaustive failure modes — every external-IO callsite picks exactly one."""

    FAIL_LOUD = "fail_loud"
    FAIL_SOFT = "fail_soft"
    SELF_HEAL = "self_heal"


def failure_trichotomy(  # noqa: C901
    *,
    fail_mode: FailureMode,
    max_retries: int = 0,
) -> Callable[[F], F]:
    """Decorator that stamps a failure mode on any function.

    Args:
        fail_mode: One of the three ``FailureMode`` variants.
        max_retries: Number of retry attempts for ``SELF_HEAL`` mode.
            Ignored for ``FAIL_LOUD`` and ``FAIL_SOFT``. Must be >= 0.

    Returns:
        The decorated function with failure-mode behavior applied.

    Raises:
        ValueError: If ``max_retries`` is negative.
    """
    if max_retries < 0:
        msg = f"max_retries must be >= 0, got {max_retries}"
        raise ValueError(msg)

    def decorator(func: F) -> F:  # noqa: C901
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                if fail_mode is FailureMode.FAIL_LOUD:
                    return await func(*args, **kwargs)

                if fail_mode is FailureMode.FAIL_SOFT:
                    try:
                        return await func(*args, **kwargs)
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            "FAIL_SOFT in %s: swallowed exception, returning None",
                            func.__qualname__,
                            exc_info=True,
                        )
                        return None

                # SELF_HEAL async
                last_exc: BaseException | None = None
                attempts = max_retries if max_retries > 0 else 1
                for attempt in range(1, attempts + 1):
                    try:
                        return await func(*args, **kwargs)
                    except Exception as exc:  # noqa: BLE001
                        last_exc = exc
                        if attempt < attempts:
                            logger.info(
                                "SELF_HEAL retry %d/%d for %s: %s",
                                attempt,
                                attempts,
                                func.__qualname__,
                                exc,
                            )
                logger.error(
                    "SELF_HEAL exhausted %d retries for %s — escalating to FAIL_LOUD",
                    attempts,
                    func.__qualname__,
                )
                raise last_exc  # type: ignore[misc]

            async_wrapper._failure_mode = fail_mode  # type: ignore[attr-defined]
            async_wrapper._max_retries = max_retries  # type: ignore[attr-defined]
            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if fail_mode is FailureMode.FAIL_LOUD:
                # No retries, no catching — let the exception propagate.
                return func(*args, **kwargs)

            if fail_mode is FailureMode.FAIL_SOFT:
                # Catch, log, return None.
                try:
                    return func(*args, **kwargs)
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "FAIL_SOFT in %s: swallowed exception, returning None",
                        func.__qualname__,
                        exc_info=True,
                    )
                    return None

            # SELF_HEAL: retry up to max_retries times.
            last_exc: BaseException | None = None
            attempts = max_retries if max_retries > 0 else 1
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt < attempts:
                        logger.info(
                            "SELF_HEAL retry %d/%d for %s: %s",
                            attempt,
                            attempts,
                            func.__qualname__,
                            exc,
                        )
            # Exhausted retries — escalate to FAIL_LOUD.
            logger.error(
                "SELF_HEAL exhausted %d retries for %s — escalating to FAIL_LOUD",
                attempts,
                func.__qualname__,
            )
            raise last_exc  # type: ignore[misc]

        # Stamp the failure mode on the wrapper for introspection.
        wrapper._failure_mode = fail_mode  # type: ignore[attr-defined]
        wrapper._max_retries = max_retries  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
