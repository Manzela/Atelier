"""Anti-bias mechanism for the N3d ConsensusAgent.

LLM-as-judge ensembles exhibit two well-documented bias modes:

    1. **Position bias** -- a judge invoked first (or last) carries
       disproportionate influence on the final composite. Randomizing the
       evaluation order per candidate dilutes this effect.
    2. **Weight dominance** -- if a single axis carries more than 40% of the
       composite weight, the composite degenerates into a proxy for that one
       axis. The remaining four judges become rubber stamps.

This module provides two pure helpers and a single aggregating builder:

    * :func:`shuffle_evaluation_order` -- produces a (seedable) randomized
      permutation of the D-O-R-A-V axes.
    * :func:`detect_dominance` -- scans an :class:`AxisWeights` and reports
      the dominant axis (if any) plus a human-readable warning.
    * :func:`build_anti_bias_report` -- composes both into a single
      :class:`AntiBiasReport`.

Everything here is pure-function and side-effect-free; the
:class:`ConsensusAgent` (N3d) consumes the report at evaluation time but the
two concerns stay decoupled so each can be unit-tested in isolation.

PRD Reference: §6.3 N3d (ConsensusAgent), F0211 (anti-bias)
"""

import random
from dataclasses import dataclass
from operator import itemgetter

from atelier.models.axis_weights import AxisWeights

# ---------------------------------------------------------------------------
# Tunable thresholds and defaults -- kept module-level so tests can assert
# against them and external callers can introspect the contract.
# ---------------------------------------------------------------------------

#: Maximum normalized weight any single axis may carry before it is flagged
#: as dominating the composite. Set to 0.40 because five axes balanced
#: equally would each carry 0.20; 0.40 is a 2x deviation, large enough to
#: meaningfully bias the composite while not so tight that every reasonable
#: AxisWeights configuration trips the warning.
DOMINANCE_THRESHOLD: float = 0.40

#: Canonical D-O-R-A-V axis ordering used by :func:`shuffle_evaluation_order`
#: when no caller-provided ``axes`` tuple is supplied. The string identifiers
#: match the keys used by :data:`atelier.models.model_registry.JUDGE_MODEL_CONFIG`
#: and the field names on :class:`AxisWeights`.
DEFAULT_AXIS_ORDER: tuple[str, ...] = (
    "brand",
    "originality",
    "relevance",
    "accessibility",
    "visual_clarity",
)


# ---------------------------------------------------------------------------
# Report container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AntiBiasReport:
    """Position-bias diagnostic for a single multi-judge evaluation.

    The report is emitted alongside (not embedded inside) the
    :class:`atelier.nodes.consensus.ConsensusEvaluation` so its three fields
    can be consumed by trajectory loggers, calibration dashboards, or tests
    without re-deriving them.

    Attributes:
        evaluation_order: The order in which judges were invoked for this
            candidate. A tuple of axis-name strings drawn from
            :data:`DEFAULT_AXIS_ORDER`. Order matters because LLM judges
            may share KV-cache prefixes -- the order is logged so
            cache-affinity regressions are debuggable.
        dominant_axis: The axis whose normalized weight exceeds
            :data:`DOMINANCE_THRESHOLD`, or ``None`` if the weights are
            balanced enough. At most one axis can dominate (the max).
        bias_warning: Human-readable warning string when ``dominant_axis`` is
            set; ``None`` otherwise. Suitable for inclusion in trajectory
            diagnostics or stderr logs.
    """

    evaluation_order: tuple[str, ...]
    dominant_axis: str | None
    bias_warning: str | None


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def shuffle_evaluation_order(
    *,
    seed: int | None = None,
    axes: tuple[str, ...] = DEFAULT_AXIS_ORDER,
) -> tuple[str, ...]:
    """Return a randomized permutation of ``axes`` for judge evaluation.

    When ``seed`` is supplied the order is deterministic (tests use this);
    when ``seed`` is ``None`` a fresh :class:`random.Random` is constructed
    with system entropy so every call yields a different order.

    Args:
        seed: Optional integer seed. Pass an explicit seed in tests for
            reproducibility; pass ``None`` in production for genuine
            randomization across candidates.
        axes: The pool to permute. Defaults to :data:`DEFAULT_AXIS_ORDER`
            but callers can pass a subset to evaluate only a few axes.

    Returns:
        A tuple containing every element of ``axes`` exactly once in a
        randomized order. Pure -- never mutates the input tuple.

    Examples:
        >>> shuffle_evaluation_order(seed=42)  # doctest: +SKIP
        ('relevance', 'brand', 'visual_clarity', 'accessibility', 'originality')
    """
    # NOTE: random is fine here -- we use it for fairness, not cryptography.
    rng = random.Random(seed)  # noqa: S311
    order = list(axes)
    rng.shuffle(order)
    return tuple(order)


def detect_dominance(weights: AxisWeights) -> tuple[str | None, str | None]:
    """Detect whether any single axis dominates the normalized composite.

    Normalizes ``weights`` via :meth:`AxisWeights.normalized`, picks the axis
    with the maximum normalized weight, and flags it when that weight exceeds
    :data:`DOMINANCE_THRESHOLD`.

    Args:
        weights: The :class:`AxisWeights` to inspect.

    Returns:
        A two-tuple ``(dominant_axis, warning_message)``. Both are ``None``
        when no axis dominates; both are populated when the maximum
        normalized weight crosses :data:`DOMINANCE_THRESHOLD`.

    Examples:
        >>> from atelier.models.axis_weights import AxisWeights
        >>> detect_dominance(AxisWeights())  # equal weights -> no dominance
        (None, None)
        >>> name, warn = detect_dominance(
        ...     AxisWeights(
        ...         brand=10.0,
        ...         originality=0.1,
        ...         relevance=0.1,
        ...         accessibility=0.1,
        ...         visual_clarity=0.1,
        ...     )
        ... )
        >>> name
        'brand'
    """
    normalized = weights.normalized()
    name, weight = max(normalized.items(), key=itemgetter(1))
    if weight > DOMINANCE_THRESHOLD:
        warning = (
            f"Axis '{name}' carries normalized weight {weight:.2f} "
            f"(> {DOMINANCE_THRESHOLD:.2f}); consider rebalancing AxisWeights "
            "so no single judge dominates the composite."
        )
        return name, warning
    return None, None


def build_anti_bias_report(
    weights: AxisWeights,
    *,
    seed: int | None = None,
    axes: tuple[str, ...] = DEFAULT_AXIS_ORDER,
) -> AntiBiasReport:
    """Compose :func:`shuffle_evaluation_order` and :func:`detect_dominance`.

    The single entry point that :func:`atelier.nodes.consensus.evaluate_candidate`
    calls per evaluation. Returning an immutable
    :class:`AntiBiasReport` keeps the two concerns -- order randomization and
    weight inspection -- bundled for downstream consumers (trajectory loggers,
    dashboards) without coupling either helper to the other.

    Args:
        weights: The :class:`AxisWeights` driving composite computation.
        seed: Optional seed forwarded to :func:`shuffle_evaluation_order`.
        axes: Axis pool forwarded to :func:`shuffle_evaluation_order`.

    Returns:
        An :class:`AntiBiasReport` populated with the chosen evaluation order
        plus the dominance diagnosis.
    """
    order = shuffle_evaluation_order(seed=seed, axes=axes)
    dominant, warning = detect_dominance(weights)
    return AntiBiasReport(
        evaluation_order=order,
        dominant_axis=dominant,
        bias_warning=warning,
    )
