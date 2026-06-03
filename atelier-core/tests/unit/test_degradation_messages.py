"""User-facing degradation acknowledgments (PRD failure-handling trichotomy).

The trichotomy's user-facing rule is absolute: *the agent always acknowledges
degradation; trust over apparent capability.* Two paths previously degraded
SILENTLY and are covered here:

  1. Non-convergence — the loop exits on ``no_improvement`` / ``max_iterations`` /
     ``duplicate`` below the convergence bar. The pipeline still returns its
     strongest candidate, but it must say so rather than present a sub-bar design
     as converged (:func:`atelier.orchestrator.runner._non_convergence_message`).
  2. Model Armor block (fail-LOUD) — a brief carrying a prompt-injection pattern
     is short-circuited at the model boundary; the runner must raise a clean,
     branded acknowledgment instead of feeding refusal sentinels through the
     gates (:func:`atelier.models.model_armor_callbacks.was_model_armor_blocked`
     + :data:`MODEL_ARMOR_BLOCK_USER_MESSAGE`).

These assert the deterministic message/detection contract. The end-to-end wiring
(that the runner actually sets ``user_message`` on these paths) is type-checked by
mypy --strict and verified live against the deployed stream.
"""

from __future__ import annotations

import pytest
from atelier.models.model_armor_callbacks import (
    _BLOCK_MESSAGE,
    MODEL_ARMOR_BLOCK_USER_MESSAGE,
    was_model_armor_blocked,
)
from atelier.orchestrator.runner import _non_convergence_message
from atelier.orchestrator.stop_reason import (
    _PRECEDENCE,
    StopReason,
    StopSignals,
    resolve_stop_reason,
)


# No emoji / pictographs in user-facing copy (committed-docs hygiene). The
# threshold at U+2600 catches the emoji, misc-symbols, dingbat, and supplemental
# pictograph blocks while still allowing typographic punctuation the copy DOES
# use: em-dash (U+2014), en-dash (U+2013), and curly quotes (U+2018/U+2019).
def _has_emoji(text: str) -> bool:
    return any(ord(ch) >= 0x2600 for ch in text)


# ──────────────────────────────────────────────────────────────────────
# Non-convergence acknowledgment
# ──────────────────────────────────────────────────────────────────────


class TestNonConvergenceMessage:
    def test_singular_first_iteration(self) -> None:
        msg = _non_convergence_message(0)
        assert "1 design iteration" in msg
        assert "iterations" not in msg  # singular, not "1 design iterations"

    def test_plural_later_iterations(self) -> None:
        assert "3 design iterations" in _non_convergence_message(2)

    def test_acknowledges_partial_result_and_invites_retry(self) -> None:
        msg = _non_convergence_message(1)
        # Honest about the degradation: strongest candidate, did not fully clear.
        assert "strongest candidate" in msg
        assert "did not fully clear" in msg
        # Calls it a draft (not a converged/final result) and invites a retry.
        assert "draft" in msg
        assert "retry" in msg.lower()

    def test_no_emoji(self) -> None:
        assert not _has_emoji(_non_convergence_message(0))


# ──────────────────────────────────────────────────────────────────────
# Model Armor block acknowledgment (fail-LOUD)
# ──────────────────────────────────────────────────────────────────────


class TestModelArmorBlockDetection:
    def test_detects_block_sentinel(self) -> None:
        assert was_model_armor_blocked([_BLOCK_MESSAGE]) is True

    def test_detects_block_sentinel_among_other_candidates(self) -> None:
        assert was_model_armor_blocked(["<!DOCTYPE html>...", _BLOCK_MESSAGE]) is True

    def test_clean_candidates_are_not_blocked(self) -> None:
        assert was_model_armor_blocked(["<!DOCTYPE html><html></html>"]) is False

    def test_empty_candidates_are_not_blocked(self) -> None:
        assert was_model_armor_blocked([]) is False

    def test_non_string_candidates_are_ignored(self) -> None:
        # Defensive: a non-str candidate must not raise, just not match.
        assert was_model_armor_blocked([None, 42, {"k": "v"}]) is False


class TestModelArmorBlockUserMessage:
    def test_message_names_the_guard_and_the_cause(self) -> None:
        assert "Model Armor" in MODEL_ARMOR_BLOCK_USER_MESSAGE
        assert "blocked" in MODEL_ARMOR_BLOCK_USER_MESSAGE.lower()
        assert "prompt-injection" in MODEL_ARMOR_BLOCK_USER_MESSAGE

    def test_message_states_nothing_was_generated(self) -> None:
        # Fail-loud: be explicit that no design was produced (no silent partial).
        assert "Nothing was generated" in MODEL_ARMOR_BLOCK_USER_MESSAGE

    def test_message_is_distinct_from_internal_sentinel(self) -> None:
        # The user-facing copy must not be the raw model-boundary sentinel.
        assert MODEL_ARMOR_BLOCK_USER_MESSAGE != _BLOCK_MESSAGE

    def test_no_emoji(self) -> None:
        assert not _has_emoji(MODEL_ARMOR_BLOCK_USER_MESSAGE)


# ──────────────────────────────────────────────────────────────────────
# SAFETY_BLOCKED stop-reason invariant
# ──────────────────────────────────────────────────────────────────────


class TestSafetyBlockedStopReason:
    def test_enum_value(self) -> None:
        assert StopReason.SAFETY_BLOCKED.value == "safety_blocked"

    def test_safety_blocked_is_direct_only_never_resolved(self) -> None:
        """SAFETY_BLOCKED is set directly at the model boundary, never by signal
        resolution — so it must NOT appear in the precedence table (else a
        KeyError in resolve_stop_reason), and resolve must never return it for
        any combination of signals."""
        assert StopReason.SAFETY_BLOCKED not in _PRECEDENCE
        # All signals on → resolve returns the highest *signal* reason, not SAFETY_BLOCKED.
        every_signal_on = StopSignals(
            token_cap_exhausted=True,
            converged=True,
            max_iterations_reached=True,
            governor_loop_detected=True,
            no_improvement=True,
            duplicate=True,
            governor_fail_soft=True,
        )
        assert resolve_stop_reason(every_signal_on) is not StopReason.SAFETY_BLOCKED

    @pytest.mark.parametrize(
        "signals",
        [
            StopSignals(),
            StopSignals(converged=True),
            StopSignals(no_improvement=True),
            StopSignals(governor_fail_soft=True),
        ],
    )
    def test_resolve_never_emits_safety_blocked(self, signals: StopSignals) -> None:
        assert resolve_stop_reason(signals) is not StopReason.SAFETY_BLOCKED
