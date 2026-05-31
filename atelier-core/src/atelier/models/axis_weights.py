"""Axis Weighting — BriefSpec-conditional D-O-R-A-V score weighting.

Implements the Multi-Judge Governor (MJG) weighting logic per PRD §6.3 N15.
Each judge axis (Design, Originality, Relevance, Accessibility, Visual Clarity)
receives a weight based on the BriefSpec's ``visual_register``, ``compliance_level``,
and ``convergence_bar``.

The composite score is:
    score = sum(weight_i * judge_score_i) / sum(weight_i)

This module is consumed by the ConsensusAgent (N3d) to compute final scores.

PRD Reference: §6.3 (N15 MJG), F0209-F0210
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AxisWeights:
    """Weights for D-O-R-A-V judge axes.

    All weights are positive floats. They are normalized at scoring time
    so they don't need to sum to 1.0.

    Attributes:
        brand: Weight for brand/design alignment axis.
        originality: Weight for creative novelty axis.
        relevance: Weight for content relevance/accuracy axis.
        accessibility: Weight for WCAG/a11y compliance axis.
        visual_clarity: Weight for visual hierarchy/clarity axis.
    """

    brand: float = 1.0
    originality: float = 1.0
    relevance: float = 1.0
    accessibility: float = 1.0
    visual_clarity: float = 1.0

    def normalized(self) -> dict[str, float]:
        """Return weights normalized to sum to 1.0.

        Returns:
            Dictionary mapping axis name to normalized weight.
        """
        total = (
            self.brand
            + self.originality
            + self.relevance
            + self.accessibility
            + self.visual_clarity
        )
        if total == 0:
            equal = 0.2
            return {
                "brand": equal,
                "originality": equal,
                "relevance": equal,
                "accessibility": equal,
                "visual_clarity": equal,
            }
        return {
            "brand": self.brand / total,
            "originality": self.originality / total,
            "relevance": self.relevance / total,
            "accessibility": self.accessibility / total,
            "visual_clarity": self.visual_clarity / total,
        }

    def compute_composite(self, scores: dict[str, float]) -> float:
        """Compute weighted composite score from per-axis scores.

        Args:
            scores: Dictionary mapping axis name to score (0.0-1.0).
                Must contain all D-O-R-A-V axes.

        Returns:
            Weighted composite score (0.0-1.0).

        Raises:
            ValueError: If any required axis is missing from scores,
                or if any score is outside [0.0, 1.0].
        """
        weights = self.normalized()

        # M-2: Fail-loud on missing axes — silently defaulting to 0.0
        # hides cases where a judge didn't produce a score.
        missing = set(weights.keys()) - set(scores.keys())
        if missing:
            msg = f"Missing axis scores for compute_composite: {sorted(missing)}"
            raise ValueError(msg)

        composite = 0.0
        for axis, weight in weights.items():
            score = scores[axis]
            if not 0.0 <= score <= 1.0:
                msg = f"Score for axis '{axis}' must be in [0.0, 1.0], got {score}"
                raise ValueError(msg)
            composite += weight * score
        return round(composite, 4)


# ---------------------------------------------------------------------------
# Default weight presets per visual_register x compliance_level matrix
# ---------------------------------------------------------------------------
# These defaults come from axis_weights_heuristic.yaml (FA-019).
# They can be overridden per-BriefSpec.

_WEIGHT_PRESETS: dict[str, AxisWeights] = {
    # Corporate: balanced, slightly favor accessibility
    "corporate": AxisWeights(
        brand=1.2,
        originality=0.8,
        relevance=1.0,
        accessibility=1.5,
        visual_clarity=1.0,
    ),
    # Luxury: heavy on brand + visual, lower accessibility tolerance
    "luxury": AxisWeights(
        brand=1.8,
        originality=1.2,
        relevance=0.8,
        accessibility=0.8,
        visual_clarity=1.5,
    ),
    # Startup: balanced with slight originality boost
    "startup": AxisWeights(
        brand=1.0,
        originality=1.5,
        relevance=1.0,
        accessibility=1.0,
        visual_clarity=1.2,
    ),
    # Editorial: content-heavy, relevance matters most
    "editorial": AxisWeights(
        brand=0.8,
        originality=1.0,
        relevance=1.8,
        accessibility=1.2,
        visual_clarity=1.0,
    ),
    # SaaS: usability-focused, accessibility is critical
    "saas": AxisWeights(
        brand=1.0,
        originality=0.8,
        relevance=1.2,
        accessibility=1.8,
        visual_clarity=1.2,
    ),
    # Brutalist: originality is king, accessibility takes a backseat
    "brutalist": AxisWeights(
        brand=1.0,
        originality=2.0,
        relevance=0.5,
        accessibility=0.5,
        visual_clarity=1.0,
    ),
    # Playful: balanced with visual boost
    "playful": AxisWeights(
        brand=1.0,
        originality=1.5,
        relevance=0.8,
        accessibility=1.0,
        visual_clarity=1.5,
    ),
}

# Compliance level multipliers for accessibility axis
_COMPLIANCE_MULTIPLIERS: dict[str, float] = {
    "wcag_aa": 1.5,
    "wcag_aaa": 2.0,
    "section_508": 1.8,
    "none": 0.8,
}

# Convergence bar multipliers — higher bar = stricter scoring
_CONVERGENCE_MULTIPLIERS: dict[str, float] = {
    "production": 1.0,
    "draft": 0.7,
    "prototype": 0.5,
}


def compute_axis_weights(
    visual_register: str,
    *,
    compliance_level: str = "wcag_aa",
    convergence_bar: str = "production",
) -> AxisWeights:
    """Compute axis weights from BriefSpec parameters.

    Looks up the base weights for the visual register, then applies
    compliance and convergence multipliers.

    Args:
        visual_register: Design register (e.g., ``"luxury"``, ``"saas"``).
        compliance_level: Accessibility compliance level.
        convergence_bar: How strict the convergence criteria should be.

    Returns:
        AxisWeights tuned for the given brief parameters.
    """
    base = _WEIGHT_PRESETS.get(
        visual_register.lower().strip(),
        AxisWeights(),
    )

    # Apply compliance multiplier to accessibility axis
    compliance_mult = _COMPLIANCE_MULTIPLIERS.get(
        compliance_level.lower().strip(),
        1.0,
    )

    # Apply convergence multiplier to all axes (scales importance)
    convergence_mult = _CONVERGENCE_MULTIPLIERS.get(
        convergence_bar.lower().strip(),
        1.0,
    )

    return AxisWeights(
        brand=base.brand * convergence_mult,
        originality=base.originality * convergence_mult,
        relevance=base.relevance * convergence_mult,
        accessibility=base.accessibility * compliance_mult * convergence_mult,
        visual_clarity=base.visual_clarity * convergence_mult,
    )
