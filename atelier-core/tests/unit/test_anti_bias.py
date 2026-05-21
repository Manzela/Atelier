"""Tests for the N3d ConsensusAgent anti-bias mechanism.

Covers every public symbol in :mod:`atelier.nodes.anti_bias`:

    * :func:`shuffle_evaluation_order` -- seeded determinism, permutation
      completeness, custom axis pools, and entropy-driven randomization.
    * :func:`detect_dominance` -- balanced-weights "no dominance" path,
      single-axis dominance flagging, and the
      :data:`DOMINANCE_THRESHOLD` boundary behavior.
    * :func:`build_anti_bias_report` -- composition of the two helpers
      into an :class:`AntiBiasReport`.

The tests use module-level constants instead of magic numbers to keep
ruff PLR2004 quiet and mirror the style of :mod:`tests.unit.test_gates`.
"""

import pytest
from atelier.models.axis_weights import AxisWeights
from atelier.nodes.anti_bias import (
    DEFAULT_AXIS_ORDER,
    DOMINANCE_THRESHOLD,
    AntiBiasReport,
    build_anti_bias_report,
    detect_dominance,
    shuffle_evaluation_order,
)

# ---------------------------------------------------------------------------
# Expected counts and seeds -- module-level so PLR2004 stays quiet.
# ---------------------------------------------------------------------------

EXPECTED_AXIS_COUNT = 5
DETERMINISTIC_SEED_A = 42
DETERMINISTIC_SEED_B = 1337
SHUFFLE_TRIAL_COUNT = 20


# ---------------------------------------------------------------------------
# shuffle_evaluation_order
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestShuffleEvaluationOrder:
    """:func:`shuffle_evaluation_order` randomizes the D-O-R-A-V axis order."""

    def test_default_pool_returns_full_permutation(self) -> None:
        order = shuffle_evaluation_order(seed=DETERMINISTIC_SEED_A)
        assert len(order) == EXPECTED_AXIS_COUNT
        assert set(order) == set(DEFAULT_AXIS_ORDER)

    def test_same_seed_yields_same_order(self) -> None:
        first = shuffle_evaluation_order(seed=DETERMINISTIC_SEED_A)
        second = shuffle_evaluation_order(seed=DETERMINISTIC_SEED_A)
        assert first == second

    def test_different_seeds_can_diverge(self) -> None:
        # Two unrelated seeds should usually produce different permutations.
        # With 5! = 120 permutations and two random seeds, collision is rare
        # enough that a single comparison is a meaningful smoke check.
        first = shuffle_evaluation_order(seed=DETERMINISTIC_SEED_A)
        second = shuffle_evaluation_order(seed=DETERMINISTIC_SEED_B)
        assert first != second

    def test_no_seed_yields_varied_orders(self) -> None:
        # With no seed we expect not every call to land on the same order.
        # 20 trials over 120 permutations makes a constant outcome
        # astronomically unlikely (probability < 1 / 120**19).
        orders = {shuffle_evaluation_order() for _ in range(SHUFFLE_TRIAL_COUNT)}
        assert len(orders) > 1

    def test_returned_tuple_is_immutable(self) -> None:
        order = shuffle_evaluation_order(seed=DETERMINISTIC_SEED_A)
        assert isinstance(order, tuple)

    def test_custom_axis_pool_preserved(self) -> None:
        axes = ("brand", "relevance", "accessibility")
        order = shuffle_evaluation_order(seed=DETERMINISTIC_SEED_A, axes=axes)
        assert set(order) == set(axes)
        assert len(order) == len(axes)

    def test_default_input_not_mutated(self) -> None:
        snapshot = tuple(DEFAULT_AXIS_ORDER)
        shuffle_evaluation_order(seed=DETERMINISTIC_SEED_A)
        assert snapshot == DEFAULT_AXIS_ORDER


# ---------------------------------------------------------------------------
# detect_dominance
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDetectDominance:
    """:func:`detect_dominance` flags axes that exceed the threshold."""

    def test_default_balanced_weights_have_no_dominance(self) -> None:
        dominant, warning = detect_dominance(AxisWeights())
        assert dominant is None
        assert warning is None

    def test_zero_weights_fallback_has_no_dominance(self) -> None:
        weights = AxisWeights(
            brand=0.0,
            originality=0.0,
            relevance=0.0,
            accessibility=0.0,
            visual_clarity=0.0,
        )
        dominant, warning = detect_dominance(weights)
        assert dominant is None
        assert warning is None

    def test_single_dominating_axis_flagged(self) -> None:
        weights = AxisWeights(
            brand=10.0,
            originality=0.1,
            relevance=0.1,
            accessibility=0.1,
            visual_clarity=0.1,
        )
        dominant, warning = detect_dominance(weights)
        assert dominant == "brand"
        assert warning is not None
        assert "brand" in warning
        assert f"{DOMINANCE_THRESHOLD:.2f}" in warning

    def test_moderate_skew_under_threshold_not_flagged(self) -> None:
        # brand normalized weight = 1.5 / 5.5 ≈ 0.273 -- under 0.40.
        weights = AxisWeights(
            brand=1.5,
            originality=1.0,
            relevance=1.0,
            accessibility=1.0,
            visual_clarity=1.0,
        )
        dominant, warning = detect_dominance(weights)
        assert dominant is None
        assert warning is None

    def test_just_above_threshold_flagged(self) -> None:
        # Drive brand's normalized share strictly above 0.40 so the
        # threshold check fires; the others remain equal.
        weights = AxisWeights(
            brand=4.0,
            originality=1.0,
            relevance=1.0,
            accessibility=1.0,
            visual_clarity=1.0,
        )
        dominant, warning = detect_dominance(weights)
        assert dominant == "brand"
        assert warning is not None

    def test_dominance_returns_axis_with_max_weight(self) -> None:
        # When two axes are very high, the *max* one wins (deterministic
        # via dict.items + max).
        weights = AxisWeights(
            brand=4.0,
            originality=5.0,
            relevance=0.1,
            accessibility=0.1,
            visual_clarity=0.1,
        )
        dominant, warning = detect_dominance(weights)
        assert dominant == "originality"
        assert warning is not None
        assert "originality" in warning


# ---------------------------------------------------------------------------
# build_anti_bias_report
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildAntiBiasReport:
    """:func:`build_anti_bias_report` composes shuffle + dominance."""

    def test_balanced_weights_no_warning(self) -> None:
        report = build_anti_bias_report(AxisWeights(), seed=DETERMINISTIC_SEED_A)
        assert isinstance(report, AntiBiasReport)
        assert report.dominant_axis is None
        assert report.bias_warning is None
        assert set(report.evaluation_order) == set(DEFAULT_AXIS_ORDER)

    def test_overweighted_axis_surfaces_warning(self) -> None:
        weights = AxisWeights(
            brand=10.0,
            originality=0.1,
            relevance=0.1,
            accessibility=0.1,
            visual_clarity=0.1,
        )
        report = build_anti_bias_report(weights, seed=DETERMINISTIC_SEED_A)
        assert report.dominant_axis == "brand"
        assert report.bias_warning is not None
        assert "brand" in report.bias_warning

    def test_seeded_report_order_is_deterministic(self) -> None:
        first = build_anti_bias_report(AxisWeights(), seed=DETERMINISTIC_SEED_A)
        second = build_anti_bias_report(AxisWeights(), seed=DETERMINISTIC_SEED_A)
        assert first.evaluation_order == second.evaluation_order

    def test_custom_axis_pool_forwarded(self) -> None:
        axes = ("brand", "relevance")
        report = build_anti_bias_report(
            AxisWeights(),
            seed=DETERMINISTIC_SEED_A,
            axes=axes,
        )
        assert set(report.evaluation_order) == set(axes)

    def test_report_is_frozen(self) -> None:
        report = build_anti_bias_report(AxisWeights(), seed=DETERMINISTIC_SEED_A)
        with pytest.raises((AttributeError, TypeError)):
            report.dominant_axis = "brand"  # type: ignore[misc]
