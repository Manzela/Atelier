"""Stop-reason precedence + detection helpers (PRD v2.2 R1 / AT-005)."""

from __future__ import annotations

import pytest
from atelier.orchestrator.stop_reason import (
    DEFAULT_CONVERGENCE_THRESHOLD,
    NO_IMPROVEMENT_EPSILON,
    StopReason,
    StopSignals,
    candidate_fingerprint,
    is_converged,
    is_duplicate,
    is_no_improvement,
    resolve_stop_reason,
)

# Each StopReason and the single StopSignals field that activates it.
_REASON_TO_FIELD = {
    StopReason.TOKEN_CAP_EXHAUSTED: "token_cap_exhausted",
    StopReason.CONVERGED: "converged",
    StopReason.MAX_ITERATIONS: "max_iterations_reached",
    StopReason.GOVERNOR_LOOP_DETECTED: "governor_loop_detected",
    StopReason.NO_IMPROVEMENT: "no_improvement",
    StopReason.DUPLICATE: "duplicate",
    StopReason.GOVERNOR_FAIL_SOFT: "governor_fail_soft",
}


@pytest.mark.unit
@pytest.mark.parametrize(("reason", "field"), list(_REASON_TO_FIELD.items()))
def test_each_reason_resolves_when_only_it_is_active(reason: StopReason, field: str) -> None:
    """One test per stop reason: it resolves when it is the sole active signal."""
    signals = StopSignals(**{field: True})
    assert resolve_stop_reason(signals) is reason


@pytest.mark.unit
def test_no_active_signal_returns_none() -> None:
    """No stop signal -> None (the loop continues)."""
    assert resolve_stop_reason(StopSignals()) is None


@pytest.mark.unit
def test_token_cap_outranks_converged() -> None:
    """Precedence (PRD R1): token-cap AND converged -> token_cap_exhausted."""
    signals = StopSignals(token_cap_exhausted=True, converged=True)
    assert resolve_stop_reason(signals) is StopReason.TOKEN_CAP_EXHAUSTED


@pytest.mark.unit
def test_full_precedence_order_holds() -> None:
    """With every signal active, the highest-precedence reason wins; and removing
    the top signal reveals the next one in exact R1 order."""
    order = [
        StopReason.TOKEN_CAP_EXHAUSTED,
        StopReason.CONVERGED,
        StopReason.MAX_ITERATIONS,
        StopReason.GOVERNOR_LOOP_DETECTED,
        StopReason.NO_IMPROVEMENT,
        StopReason.DUPLICATE,
        StopReason.GOVERNOR_FAIL_SOFT,
    ]
    active = dict.fromkeys(_REASON_TO_FIELD.values(), True)
    for expected in order:
        assert resolve_stop_reason(StopSignals(**active)) is expected
        active[_REASON_TO_FIELD[expected]] = False  # retire the winner, re-resolve


@pytest.mark.unit
def test_converged_is_at_or_above_threshold_never_below() -> None:
    """Sub-0.70 is never converged; exactly 0.70 converges."""
    assert is_converged(DEFAULT_CONVERGENCE_THRESHOLD) is True
    assert is_converged(0.70) is True
    assert is_converged(0.699) is False
    assert is_converged(0.0) is False


@pytest.mark.unit
def test_no_improvement_epsilon_and_first_iteration() -> None:
    """First iteration never 'no improvement'; Delta<epsilon is no improvement (R1)."""
    assert NO_IMPROVEMENT_EPSILON == 0.02  # documents the R1 threshold
    assert is_no_improvement(None, 0.5) is False  # first iteration
    assert is_no_improvement(0.50, 0.51) is True  # delta 0.01 < 0.02 -> no improvement
    assert is_no_improvement(0.50, 0.55) is False  # delta 0.05 >= 0.02 -> improved
    assert is_no_improvement(0.50, 0.49) is True  # regressed -> no improvement


@pytest.mark.unit
def test_duplicate_detection_by_fingerprint() -> None:
    """A repeated candidate is detected by its stable sha256 fingerprint."""
    seen: set[str] = set()
    html = "<html><body>same</body></html>"
    assert is_duplicate(html, seen) is False
    seen.add(candidate_fingerprint(html))
    assert is_duplicate(html, seen) is True
    assert is_duplicate("<html><body>different</body></html>", seen) is False
    # Fingerprint is stable across calls.
    assert candidate_fingerprint(html) == candidate_fingerprint(html)


@pytest.mark.unit
def test_no_usd_budget_stop_reason_exists() -> None:
    """AT-095 removed the USD path entirely — there is NO budget_exhausted reason."""
    assert not hasattr(StopReason, "BUDGET_EXHAUSTED")
    assert "budget_exhausted" not in {r.value for r in StopReason}
