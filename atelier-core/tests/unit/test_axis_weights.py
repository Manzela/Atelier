"""Tests for axis weighting system (FA-018/FA-019)."""

from __future__ import annotations

import pytest
from atelier.models.axis_weights import (
    AxisWeights,
    compute_axis_weights,
)


@pytest.mark.unit
class TestAxisWeights:
    """Verify AxisWeights construction and computation."""

    def test_default_equal_weights(self) -> None:
        w = AxisWeights()
        normalized = w.normalized()
        assert len(normalized) == 5
        for v in normalized.values():
            assert abs(v - 0.2) < 1e-6

    def test_normalized_sums_to_one(self) -> None:
        w = AxisWeights(
            brand=2.0, originality=1.0, relevance=1.0, accessibility=3.0, visual_clarity=1.0
        )
        normalized = w.normalized()
        total = sum(normalized.values())
        assert abs(total - 1.0) < 1e-6

    def test_zero_weights_fallback(self) -> None:
        w = AxisWeights(brand=0, originality=0, relevance=0, accessibility=0, visual_clarity=0)
        normalized = w.normalized()
        for v in normalized.values():
            assert abs(v - 0.2) < 1e-6

    def test_compute_composite_perfect(self) -> None:
        w = AxisWeights()
        scores = {
            "brand": 1.0,
            "originality": 1.0,
            "relevance": 1.0,
            "accessibility": 1.0,
            "visual_clarity": 1.0,
        }
        assert w.compute_composite(scores) == 1.0

    def test_compute_composite_weighted(self) -> None:
        w = AxisWeights(
            brand=2.0, originality=0.0, relevance=0.0, accessibility=0.0, visual_clarity=0.0
        )
        scores = {
            "brand": 0.8,
            "originality": 0.0,
            "relevance": 0.0,
            "accessibility": 0.0,
            "visual_clarity": 0.0,
        }
        # brand has all the weight, score = 0.8
        assert w.compute_composite(scores) == 0.8

    def test_compute_composite_invalid_score(self) -> None:
        w = AxisWeights()
        scores = {
            "brand": 1.5,
            "originality": 0.5,
            "relevance": 0.5,
            "accessibility": 0.5,
            "visual_clarity": 0.5,
        }
        with pytest.raises(ValueError, match="must be in"):
            w.compute_composite(scores)

    def test_compute_composite_missing_axes(self) -> None:
        w = AxisWeights()
        scores = {"brand": 0.8}
        with pytest.raises(ValueError, match="Missing axis scores"):
            w.compute_composite(scores)

    def test_frozen(self) -> None:
        w = AxisWeights()
        with pytest.raises(AttributeError):
            w.brand = 2.0  # type: ignore[misc]


@pytest.mark.unit
class TestComputeAxisWeights:
    """Verify BriefSpec → axis weights computation."""

    def test_corporate_favors_accessibility(self) -> None:
        w = compute_axis_weights("corporate")
        assert w.accessibility > w.originality

    def test_luxury_favors_brand(self) -> None:
        w = compute_axis_weights("luxury")
        assert w.brand > w.relevance

    def test_brutalist_favors_originality(self) -> None:
        w = compute_axis_weights("brutalist")
        assert w.originality > w.brand

    def test_wcag_aaa_boosts_accessibility(self) -> None:
        w_aa = compute_axis_weights("corporate", compliance_level="wcag_aa")
        w_aaa = compute_axis_weights("corporate", compliance_level="wcag_aaa")
        assert w_aaa.accessibility > w_aa.accessibility

    def test_draft_convergence_reduces_all(self) -> None:
        w_prod = compute_axis_weights("corporate", convergence_bar="production")
        w_draft = compute_axis_weights("corporate", convergence_bar="draft")
        assert w_draft.brand < w_prod.brand
        assert w_draft.originality < w_prod.originality

    def test_unknown_register_uses_defaults(self) -> None:
        w = compute_axis_weights("unknown_style")
        assert w.brand == 1.0  # default AxisWeights

    def test_case_insensitive(self) -> None:
        w1 = compute_axis_weights("LUXURY")
        w2 = compute_axis_weights("luxury")
        assert w1.brand == w2.brand
