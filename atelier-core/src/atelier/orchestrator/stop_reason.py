"""Bounded-loop stop reasons + strict precedence (PRD v2.2 R1 / AT-005).

The convergence loop can have several stop signals true at once (e.g. the final
iteration both reaches ``max_iterations`` AND converges). R1 fixes the order so
the loop always reports the single highest-precedence reason:

    token_cap_exhausted > converged(>=0.70) > max_iterations
        > governor_loop_detected > no_improvement(delta<0.02)
        > duplicate(sha256) > governor_fail_soft

``token_cap_exhausted`` is fail-LOUD and always wins (a cap is security, never
transient -- PRD R1/R5/§13). The legacy per-run USD ``budget_exhausted`` reason
is retired by AT-095; it is kept only as a deprecated alias so any remaining
reference resolves to ``token_cap_exhausted`` rather than silently breaking.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

#: Convergence threshold -- a candidate's composite must reach this to converge.
DEFAULT_CONVERGENCE_THRESHOLD: float = 0.70
#: An iteration improves only if the composite rises by more than this epsilon.
NO_IMPROVEMENT_EPSILON: float = 0.02


class StopReason(StrEnum):
    """Why the bounded creative loop stopped (str-valued for JSON/state)."""

    TOKEN_CAP_EXHAUSTED = "token_cap_exhausted"  # noqa: S105 - enum value, not a secret
    CONVERGED = "converged"
    MAX_ITERATIONS = "max_iterations"
    GOVERNOR_LOOP_DETECTED = "governor_loop_detected"
    NO_IMPROVEMENT = "no_improvement"
    DUPLICATE = "duplicate"
    GOVERNOR_FAIL_SOFT = "governor_fail_soft"
    #: Deprecated: the per-run USD cap is removed by AT-095. Retained as an alias
    #: target only; new code never sets this -- use TOKEN_CAP_EXHAUSTED.
    BUDGET_EXHAUSTED = "budget_exhausted"


#: Highest precedence first. The deprecated BUDGET_EXHAUSTED is intentionally
#: absent -- it is never a live outcome; it maps to TOKEN_CAP_EXHAUSTED.
_PRECEDENCE: tuple[StopReason, ...] = (
    StopReason.TOKEN_CAP_EXHAUSTED,
    StopReason.CONVERGED,
    StopReason.MAX_ITERATIONS,
    StopReason.GOVERNOR_LOOP_DETECTED,
    StopReason.NO_IMPROVEMENT,
    StopReason.DUPLICATE,
    StopReason.GOVERNOR_FAIL_SOFT,
)


@dataclass(frozen=True)
class StopSignals:
    """The independent stop conditions evaluated each iteration.

    Several may be true simultaneously; :func:`resolve_stop_reason` collapses
    them to the single highest-precedence :class:`StopReason`.
    """

    token_cap_exhausted: bool = False
    converged: bool = False
    max_iterations_reached: bool = False
    governor_loop_detected: bool = False
    no_improvement: bool = False
    duplicate: bool = False
    governor_fail_soft: bool = False


def resolve_stop_reason(signals: StopSignals) -> StopReason | None:
    """Return the single highest-precedence active stop reason, or ``None``.

    ``None`` means no stop signal fired and the loop should continue.
    """
    active = {
        StopReason.TOKEN_CAP_EXHAUSTED: signals.token_cap_exhausted,
        StopReason.CONVERGED: signals.converged,
        StopReason.MAX_ITERATIONS: signals.max_iterations_reached,
        StopReason.GOVERNOR_LOOP_DETECTED: signals.governor_loop_detected,
        StopReason.NO_IMPROVEMENT: signals.no_improvement,
        StopReason.DUPLICATE: signals.duplicate,
        StopReason.GOVERNOR_FAIL_SOFT: signals.governor_fail_soft,
    }
    for reason in _PRECEDENCE:
        if active[reason]:
            return reason
    return None


def is_converged(composite_score: float, threshold: float = DEFAULT_CONVERGENCE_THRESHOLD) -> bool:
    """A candidate converges only at or above the threshold (never below)."""
    return composite_score >= threshold


def is_no_improvement(
    previous_best: float | None,
    current_best: float,
    epsilon: float = NO_IMPROVEMENT_EPSILON,
) -> bool:
    """True when the composite did not rise by more than ``epsilon``.

    Per R1 the loop has improved only when the composite rose by ``epsilon`` or
    more (Δ < epsilon -> no improvement). The first iteration
    (``previous_best is None``) is never "no improvement".
    """
    if previous_best is None:
        return False
    return (current_best - previous_best) < epsilon


def candidate_fingerprint(candidate_html: str) -> str:
    """Stable sha256 of a candidate, used to detect duplicate regenerations."""
    return hashlib.sha256(candidate_html.encode("utf-8")).hexdigest()


def is_duplicate(candidate_html: str, seen_fingerprints: set[str]) -> bool:
    """True when this candidate's fingerprint was already produced this run."""
    return candidate_fingerprint(candidate_html) in seen_fingerprints
