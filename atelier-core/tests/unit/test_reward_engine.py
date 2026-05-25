"""Unit tests for CompositeRewardEngine — AND-gate composite reward (§21.3).

TDD spec: at least 25 explicit cases + 5 property-based tests with hypothesis
asserting determinism, implication (eligible → all floors met), failed_checks /
eligibility consistency, composite-score in [0,1], and axis-regression ≤ MAX
passes axis gate. See spec §21.4 acceptance criteria.
"""

from __future__ import annotations

from typing import Final

import pytest
from atelier.reward.composite import (
    EXTRINSIC_MARGIN_FLOOR,
    KAPPA_VS_GOLDEN_FLOOR,
    MAX_AXIS_REGRESSION,
    SWAP_STABILITY_FLOOR,
    AndGateRewardEngine,
    RewardComponents,
    RewardDecision,
)
from hypothesis import given, settings
from hypothesis import strategies as st

# Canonical axis set matching §7 JUDGE_MODEL_CONFIG — changes here indicate
# the upstream axis schema drifted. The reward engine accepts any axis set,
# but tests use this canonical set so the test suite stays aligned with §21.
_AXES: Final[tuple[str, ...]] = ("Brand", "Originality", "Relevance", "Accessibility", "Visual")


# ---- helpers ----------------------------------------------------------------


def _components(
    *,
    extrinsic: float = 0.20,
    swap_stability: float = 0.90,
    kappa_vs_golden: float = 0.80,
    chosen_axes: dict[str, float] | None = None,
    rejected_axes: dict[str, float] | None = None,
    outcome: dict[str, float] | None = None,
) -> RewardComponents:
    if chosen_axes is None:
        chosen_axes = dict.fromkeys(_AXES, 0.8)
    if rejected_axes is None:
        rejected_axes = dict.fromkeys(_AXES, 0.6)
    intrinsic = {a: {"chosen": chosen_axes[a], "rejected": rejected_axes[a]} for a in _AXES}
    return RewardComponents(
        extrinsic=extrinsic,
        intrinsic=intrinsic,
        outcome=outcome,
        swap_stability=swap_stability,
        kappa_vs_golden=kappa_vs_golden,
    )


# ---- happy path -------------------------------------------------------------


@pytest.mark.unit
def test_happy_path_passes_all_four_predicates() -> None:
    engine = AndGateRewardEngine()
    d = engine.evaluate(_components())
    assert d.dpo_eligible is True
    assert d.failed_checks == ()


# ---- single-predicate failures (4 cases) ------------------------------------


@pytest.mark.unit
def test_fails_when_extrinsic_below_floor() -> None:
    engine = AndGateRewardEngine()
    d = engine.evaluate(_components(extrinsic=EXTRINSIC_MARGIN_FLOOR - 0.001))
    assert d.dpo_eligible is False
    assert d.failed_checks == ("extrinsic_margin",)


@pytest.mark.unit
def test_fails_when_swap_stability_below_floor() -> None:
    engine = AndGateRewardEngine()
    d = engine.evaluate(_components(swap_stability=SWAP_STABILITY_FLOOR - 0.01))
    assert d.dpo_eligible is False
    assert d.failed_checks == ("swap_stability",)


@pytest.mark.unit
def test_fails_when_an_axis_regresses() -> None:
    engine = AndGateRewardEngine()
    # Originality: rejected 0.56 vs chosen 0.50 → delta 0.06 > MAX_AXIS_REGRESSION(0.05)
    chosen = dict.fromkeys(_AXES, 0.8)
    chosen["Originality"] = 0.50
    rejected = dict.fromkeys(_AXES, 0.6)
    rejected["Originality"] = 0.56  # rejected is 0.06 higher than chosen
    d = engine.evaluate(_components(chosen_axes=chosen, rejected_axes=rejected))
    assert d.dpo_eligible is False
    assert d.failed_checks == ("axis_regression:Originality",)


@pytest.mark.unit
def test_fails_when_kappa_below_floor() -> None:
    engine = AndGateRewardEngine()
    d = engine.evaluate(_components(kappa_vs_golden=KAPPA_VS_GOLDEN_FLOOR - 0.01))
    assert d.dpo_eligible is False
    assert d.failed_checks == ("kappa_vs_golden",)


# ---- two-predicate failures (6 of C(4,2)=6 combinations) -------------------


@pytest.mark.unit
def test_fails_extrinsic_and_swap() -> None:
    engine = AndGateRewardEngine()
    d = engine.evaluate(_components(extrinsic=0.10, swap_stability=0.70))
    assert d.dpo_eligible is False
    assert set(d.failed_checks) == {"extrinsic_margin", "swap_stability"}


@pytest.mark.unit
def test_fails_extrinsic_and_axis_regression() -> None:
    engine = AndGateRewardEngine()
    chosen = dict.fromkeys(_AXES, 0.8)
    chosen["Visual"] = 0.50
    rejected = dict.fromkeys(_AXES, 0.6)
    rejected["Visual"] = 0.70
    d = engine.evaluate(_components(extrinsic=0.10, chosen_axes=chosen, rejected_axes=rejected))
    assert d.dpo_eligible is False
    assert set(d.failed_checks) == {"extrinsic_margin", "axis_regression:Visual"}


@pytest.mark.unit
def test_fails_extrinsic_and_kappa() -> None:
    engine = AndGateRewardEngine()
    d = engine.evaluate(_components(extrinsic=0.10, kappa_vs_golden=0.60))
    assert d.dpo_eligible is False
    assert set(d.failed_checks) == {"extrinsic_margin", "kappa_vs_golden"}


@pytest.mark.unit
def test_fails_swap_and_axis_regression() -> None:
    engine = AndGateRewardEngine()
    chosen = dict.fromkeys(_AXES, 0.8)
    chosen["Brand"] = 0.50
    rejected = dict.fromkeys(_AXES, 0.6)
    rejected["Brand"] = 0.70
    d = engine.evaluate(
        _components(swap_stability=0.70, chosen_axes=chosen, rejected_axes=rejected)
    )
    assert d.dpo_eligible is False
    assert set(d.failed_checks) == {"swap_stability", "axis_regression:Brand"}


@pytest.mark.unit
def test_fails_swap_and_kappa() -> None:
    engine = AndGateRewardEngine()
    d = engine.evaluate(_components(swap_stability=0.70, kappa_vs_golden=0.60))
    assert d.dpo_eligible is False
    assert set(d.failed_checks) == {"swap_stability", "kappa_vs_golden"}


@pytest.mark.unit
def test_fails_axis_regression_and_kappa() -> None:
    engine = AndGateRewardEngine()
    chosen = dict.fromkeys(_AXES, 0.8)
    chosen["Accessibility"] = 0.50
    rejected = dict.fromkeys(_AXES, 0.6)
    rejected["Accessibility"] = 0.70
    d = engine.evaluate(
        _components(kappa_vs_golden=0.60, chosen_axes=chosen, rejected_axes=rejected)
    )
    assert d.dpo_eligible is False
    assert set(d.failed_checks) == {"axis_regression:Accessibility", "kappa_vs_golden"}


# ---- three-predicate failures (3 of C(4,3)=4) -------------------------------


@pytest.mark.unit
def test_fails_extrinsic_swap_kappa() -> None:
    engine = AndGateRewardEngine()
    d = engine.evaluate(_components(extrinsic=0.10, swap_stability=0.70, kappa_vs_golden=0.60))
    assert d.dpo_eligible is False
    assert set(d.failed_checks) == {"extrinsic_margin", "swap_stability", "kappa_vs_golden"}


@pytest.mark.unit
def test_fails_extrinsic_swap_axis() -> None:
    engine = AndGateRewardEngine()
    chosen = dict.fromkeys(_AXES, 0.8)
    chosen["Originality"] = 0.50
    rejected = dict.fromkeys(_AXES, 0.6)
    rejected["Originality"] = 0.70
    d = engine.evaluate(
        _components(
            extrinsic=0.10,
            swap_stability=0.70,
            chosen_axes=chosen,
            rejected_axes=rejected,
        )
    )
    assert d.dpo_eligible is False
    assert set(d.failed_checks) == {
        "extrinsic_margin",
        "swap_stability",
        "axis_regression:Originality",
    }


@pytest.mark.unit
def test_fails_swap_kappa_axis() -> None:
    engine = AndGateRewardEngine()
    chosen = dict.fromkeys(_AXES, 0.8)
    chosen["Brand"] = 0.50
    rejected = dict.fromkeys(_AXES, 0.6)
    rejected["Brand"] = 0.70
    d = engine.evaluate(
        _components(
            swap_stability=0.70,
            kappa_vs_golden=0.60,
            chosen_axes=chosen,
            rejected_axes=rejected,
        )
    )
    assert d.dpo_eligible is False
    assert set(d.failed_checks) == {
        "swap_stability",
        "kappa_vs_golden",
        "axis_regression:Brand",
    }


# ---- all-four failure --------------------------------------------------------


@pytest.mark.unit
def test_fails_all_four_predicates() -> None:
    """All scalar predicates fail AND all 5 axes regress → ≥8 entries in failed_checks.

    The spec requires len ≥ 4; we assert ≥ 8 because the AND-gate collects
    all failures (fail-all, not fail-first), so the diagnostic is richer.
    """
    engine = AndGateRewardEngine()
    chosen = dict.fromkeys(_AXES, 0.5)
    rejected = dict.fromkeys(_AXES, 0.7)
    d = engine.evaluate(
        _components(
            extrinsic=0.05,
            swap_stability=0.50,
            kappa_vs_golden=0.40,
            chosen_axes=chosen,
            rejected_axes=rejected,
        )
    )
    assert d.dpo_eligible is False
    assert len(d.failed_checks) >= 4  # spec floor
    assert len(d.failed_checks) >= 8  # actual: 3 scalar + 5 axis regressions


# ---- boundary cases (exactly at threshold passes) ---------------------------


@pytest.mark.unit
def test_extrinsic_exactly_at_floor_passes() -> None:
    engine = AndGateRewardEngine()
    d = engine.evaluate(_components(extrinsic=EXTRINSIC_MARGIN_FLOOR))
    assert d.dpo_eligible is True


@pytest.mark.unit
def test_swap_stability_exactly_at_floor_passes() -> None:
    engine = AndGateRewardEngine()
    d = engine.evaluate(_components(swap_stability=SWAP_STABILITY_FLOOR))
    assert d.dpo_eligible is True


@pytest.mark.unit
def test_kappa_exactly_at_floor_passes() -> None:
    engine = AndGateRewardEngine()
    d = engine.evaluate(_components(kappa_vs_golden=KAPPA_VS_GOLDEN_FLOOR))
    assert d.dpo_eligible is True


@pytest.mark.unit
def test_axis_regression_exactly_at_max_passes() -> None:
    """Regression of exactly MAX_AXIS_REGRESSION passes; only STRICTLY GREATER fails.

    Tested via `chosen = 0.0, rejected = MAX_AXIS_REGRESSION` so that the
    computed difference is `MAX_AXIS_REGRESSION - 0.0 = MAX_AXIS_REGRESSION`
    exactly (subtraction by 0 is lossless in IEEE-754). This avoids the
    floating-point ambiguity of constructions like `0.65 - 0.60 = 0.050...044 > 0.05`.
    """
    engine = AndGateRewardEngine()
    chosen = dict.fromkeys(_AXES, 0.8)
    chosen["Relevance"] = 0.0
    rejected = dict.fromkeys(_AXES, 0.6)
    rejected["Relevance"] = MAX_AXIS_REGRESSION  # diff = MAX - 0 = MAX, not > MAX
    d = engine.evaluate(_components(chosen_axes=chosen, rejected_axes=rejected))
    assert d.dpo_eligible is True


# ---- outcome data presence ---------------------------------------------------


@pytest.mark.unit
def test_outcome_data_present_does_not_change_decision() -> None:
    """outcome data is for post-deployment narrative (§21.3 docstring);
    it MUST NOT influence the DPO-eligibility gate decision.
    """
    engine = AndGateRewardEngine()
    d_with = engine.evaluate(_components(outcome={"ctr_delta": 0.03, "conversion_lift": 0.012}))
    d_without = engine.evaluate(_components(outcome=None))
    assert d_with.dpo_eligible == d_without.dpo_eligible
    assert d_with.failed_checks == d_without.failed_checks


@pytest.mark.unit
def test_outcome_data_absent_does_not_crash() -> None:
    engine = AndGateRewardEngine()
    d = engine.evaluate(_components(outcome=None))
    assert d.dpo_eligible is True


# ---- composite score sanity --------------------------------------------------


@pytest.mark.unit
def test_composite_score_is_mean_of_chosen_axes() -> None:
    """composite_score = mean of chosen-side intrinsic scores.

    The spec comment says 'sum of normalized axes'; the plan's test + this
    test pin the semantics: it is the arithmetic MEAN, not the raw sum.
    With 5 axes all at 0.80, mean = 0.80 exactly (4.0/5 is exact in float64).
    """
    engine = AndGateRewardEngine()
    chosen = dict.fromkeys(_AXES, 0.8)
    rejected = dict.fromkeys(_AXES, 0.6)
    d = engine.evaluate(_components(chosen_axes=chosen, rejected_axes=rejected))
    assert abs(d.composite_score - 0.80) < 1e-9


@pytest.mark.unit
def test_composite_score_is_zero_when_all_chosen_axes_are_zero() -> None:
    engine = AndGateRewardEngine()
    chosen = dict.fromkeys(_AXES, 0.0)
    rejected = dict.fromkeys(_AXES, 0.0)
    d = engine.evaluate(_components(chosen_axes=chosen, rejected_axes=rejected))
    assert d.composite_score == 0.0


@pytest.mark.unit
def test_composite_score_is_one_when_all_chosen_axes_are_one() -> None:
    engine = AndGateRewardEngine()
    chosen = dict.fromkeys(_AXES, 1.0)
    rejected = dict.fromkeys(_AXES, 0.0)
    d = engine.evaluate(_components(chosen_axes=chosen, rejected_axes=rejected))
    assert abs(d.composite_score - 1.0) < 1e-9


# ---- RewardDecision structural invariants ------------------------------------


@pytest.mark.unit
def test_reward_decision_is_hashable() -> None:
    """Unlike RouteDecision (which has a mutable span_attrs dict), RewardDecision
    contains only hashable fields — the AND-gate decision CAN be used as a
    cache key or put in a set for de-duplication.
    """
    engine = AndGateRewardEngine()
    d: RewardDecision = engine.evaluate(_components())
    h = hash(d)
    assert isinstance(h, int)
    # Two evaluations of the same input must produce equal AND same-hash objects.
    assert d == engine.evaluate(_components())
    assert hash(d) == hash(engine.evaluate(_components()))


@pytest.mark.unit
def test_reward_decision_failed_checks_is_tuple() -> None:
    """failed_checks is a tuple (immutable) — not a list — so it's hashable
    and its ordering is deterministic for trace-replay diffing.
    """
    engine = AndGateRewardEngine()
    d = engine.evaluate(_components(extrinsic=0.10))
    assert isinstance(d.failed_checks, tuple)


# ---- rationale + explain_to_judge -------------------------------------------


@pytest.mark.unit
def test_rationale_includes_each_failed_check_name() -> None:
    engine = AndGateRewardEngine()
    d = engine.evaluate(_components(extrinsic=0.10, swap_stability=0.70))
    assert "extrinsic_margin" in d.rationale
    assert "swap_stability" in d.rationale


@pytest.mark.unit
def test_rationale_on_happy_path_mentions_eligible() -> None:
    engine = AndGateRewardEngine()
    d = engine.evaluate(_components())
    assert d.dpo_eligible is True
    assert "eligible" in d.rationale.lower()


@pytest.mark.unit
def test_explain_to_judge_is_multi_sentence_on_failure() -> None:
    engine = AndGateRewardEngine()
    d = engine.evaluate(_components(extrinsic=0.05))
    explanation = engine.explain_to_judge(d)
    # Multi-sentence: at least one period followed by a space (≥ 2 sentences).
    assert explanation.count(". ") >= 1


@pytest.mark.unit
def test_explain_to_judge_on_happy_path_is_non_empty() -> None:
    engine = AndGateRewardEngine()
    d = engine.evaluate(_components())
    assert len(engine.explain_to_judge(d)) > 0


# ---- hypothesis property tests (5) ------------------------------------------

_floats = st.floats(
    min_value=0.0,
    max_value=1.0,
    allow_nan=False,
    allow_infinity=False,
    width=32,  # float32 precision, matching NDArray[np.float32] callers
)


@given(extrinsic=_floats, swap=_floats, kappa=_floats)
@settings(max_examples=100, deadline=None)
def test_property_evaluate_is_deterministic_for_identical_inputs(
    extrinsic: float, swap: float, kappa: float
) -> None:
    """Pure function contract: same inputs MUST produce equal outputs every time.

    This is the critical correctness invariant for a reward engine — any
    non-determinism would corrupt the DPO dataset.
    """
    engine = AndGateRewardEngine()
    c = _components(extrinsic=extrinsic, swap_stability=swap, kappa_vs_golden=kappa)
    assert engine.evaluate(c) == engine.evaluate(c)


@given(extrinsic=_floats, swap=_floats, kappa=_floats)
@settings(max_examples=100, deadline=None)
def test_property_dpo_eligible_implies_all_floors_met(
    extrinsic: float, swap: float, kappa: float
) -> None:
    """If the AND-gate returns eligible=True, all three scalar floors MUST be met.

    This is the core Goodhart-resistance invariant: you cannot be eligible
    without meeting every independent predicate.
    """
    engine = AndGateRewardEngine()
    d = engine.evaluate(
        _components(extrinsic=extrinsic, swap_stability=swap, kappa_vs_golden=kappa)
    )
    if d.dpo_eligible:
        assert extrinsic >= EXTRINSIC_MARGIN_FLOOR
        assert swap >= SWAP_STABILITY_FLOOR
        assert kappa >= KAPPA_VS_GOLDEN_FLOOR


@given(extrinsic=_floats, swap=_floats, kappa=_floats)
@settings(max_examples=100, deadline=None)
def test_property_failed_checks_consistent_with_eligibility(
    extrinsic: float, swap: float, kappa: float
) -> None:
    """failed_checks and dpo_eligible must be consistent:
    empty failed_checks ↔ eligible. No half-states.
    """
    engine = AndGateRewardEngine()
    d = engine.evaluate(
        _components(extrinsic=extrinsic, swap_stability=swap, kappa_vs_golden=kappa)
    )
    assert d.dpo_eligible == (len(d.failed_checks) == 0)


@given(score=_floats)
@settings(max_examples=50, deadline=None)
def test_property_composite_score_in_unit_interval(score: float) -> None:
    """composite_score is a mean of values in [0, 1] — result must also be in [0, 1]."""
    engine = AndGateRewardEngine()
    chosen = dict.fromkeys(_AXES, score)
    rejected = dict.fromkeys(_AXES, 0.0)
    d = engine.evaluate(_components(chosen_axes=chosen, rejected_axes=rejected))
    assert 0.0 <= d.composite_score <= 1.0


@given(
    bumps=st.lists(
        st.tuples(
            st.sampled_from(_AXES),
            st.floats(
                min_value=0.0,
                max_value=MAX_AXIS_REGRESSION,
                allow_nan=False,
                allow_infinity=False,
            ),
        ),
        min_size=0,
        max_size=5,
    ),
)
@settings(max_examples=100, deadline=None)
def test_property_no_axis_regression_within_max_passes_axis_gate(
    bumps: list[tuple[str, float]],
) -> None:
    """For any per-axis regression ≤ MAX_AXIS_REGRESSION, axis gate MUST pass.

    Other gates held at happy-path values. This exercises all axis combinations
    including the degenerate case where multiple axes regress simultaneously but
    each stays within the allowed envelope.
    """
    engine = AndGateRewardEngine()
    chosen = dict.fromkeys(_AXES, 0.8)
    rejected = dict.fromkeys(_AXES, 0.6)
    for axis, delta in bumps:
        # Set chosen = 0.0, rejected = delta so computed diff = delta - 0.0 = delta
        # exactly (IEEE-754 subtraction by zero is lossless). Avoids the
        # float-addition rounding error of `(0.60 + delta) - 0.60 > delta`.
        chosen[axis] = 0.0
        rejected[axis] = delta
    d = engine.evaluate(_components(chosen_axes=chosen, rejected_axes=rejected))
    assert not any(c.startswith("axis_regression:") for c in d.failed_checks)
