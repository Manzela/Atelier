"""Intrinsic Outcome-Driven Reward Engine (ADR 0030, spec §21).

Replaces the naive weighted-sum composite reward with an AND-gate over four
independent signals. Goodhart-resistant: no single axis can dominate because
the gate is conjunctive — one failed predicate rejects the entire pair.

The pair-eligibility check is called from two places:

  §9.1 DPO dataset builder  — writes dpo_eligible to BigQuery
  §19  generator-pair miner  — filters pairs before BigQuery mine_pairs

Both use the same predicate so eligibility semantics are identical, preventing
drift between where pairs are mined and where they are consumed.

Anti-bias research basis (§21.2):
  - Eisenstein 2023: pretrain-diverse ensembles + center-rewards regulariser
  - Zheng 2023 (MT-Bench): position-swap pairwise (SWAP_STABILITY_FLOOR)
  - PRM-over-ORM: Atelier's 8-node DAG emits per-node scores (§21.2 table)

Threshold constants are Final; changes require an ADR amendment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol

# ---------------------------------------------------------------------------
# Thresholds — locked, must move only via ADR amendment (spec §21.3).
# ---------------------------------------------------------------------------

EXTRINSIC_MARGIN_FLOOR: Final[float] = 0.15
"""Composite-judge score margin floor: composite_judge(chosen) - composite_judge(rejected) ≥ 0.15.

Matches the MIN_MARGIN constant in §9.1 DPO dataset builder.
"""

SWAP_STABILITY_FLOOR: Final[float] = 0.8
"""Position-swap consistency floor (§7 FA-017 pairwise pattern).

swap_stability = 0.5 * (score_ab + (1 - score_ba)) per Zheng 2023.
Values below 0.8 indicate the preference is a position-bias artifact, not a
genuine quality signal.
"""

MAX_AXIS_REGRESSION: Final[float] = 0.05
"""Per-axis regression ceiling: rejected axis score MUST NOT exceed chosen by > 0.05.

Prevents the generator from trading quality on one axis for gains elsewhere.
Evaluated per axis; any axis exceeding this threshold rejects the pair.
The check is STRICT-GREATER: delta == 0.05 passes, delta > 0.05 fails.

IEEE-754 note: constructions like `(0.60 + 0.05) - 0.60` return
`0.050000000000000044` (> 0.05) due to float rounding, making exact-boundary
comparisons unreliable. Tests that probe the boundary should compute the
delta directly as `rejected = MAX_AXIS_REGRESSION, chosen = 0.0` so the
subtraction `MAX_AXIS_REGRESSION - 0.0 = MAX_AXIS_REGRESSION` is lossless.
"""

KAPPA_VS_GOLDEN_FLOOR: Final[float] = 0.7
"""Judge-golden-set agreement floor (RR-13 calibration threshold).

Pairs where the judge's agreement with the calibration golden set on this
brief is < 0.7 are excluded — the judge was miscalibrated for this brief
type, so its preference signal is unreliable.
"""


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RewardComponents:
    """All inputs to the AND-gate. Computed from a candidate-vs-candidate comparison.

    `extrinsic` is the composite-judge score margin (chosen - rejected).
    Positive values mean chosen outscored rejected; zero or negative are
    automatically rejected by the AND-gate floor.

    `intrinsic` is a dict keyed by axis name (Brand / Originality / Relevance /
    Accessibility / Visual) where each value is `{"chosen": s, "rejected": s}`
    with s ∈ [0.0, 1.0]. The engine iterates this dict in sorted order for
    deterministic evaluation.

    `outcome` holds post-deployment outcome data (CTR, conversion lift) when
    available. It is `None` during in-loop DPO mining and populated only by the
    post-deployment hook for narrative purposes. It MUST NOT influence the
    DPO-eligibility gate.

    `swap_stability` and `kappa_vs_golden` are pre-computed by the caller:
    the engine treats them as opaque scalars.

    Note: `intrinsic` and `outcome` are mutable dicts. `frozen=True` prevents
    attribute reassignment but not mutation of the dict's contents. Callers
    MUST NOT mutate these after construction — the engine reads them without
    defensive copying for performance.
    """

    extrinsic: float
    intrinsic: dict[str, dict[str, float]]
    outcome: dict[str, float] | None
    swap_stability: float
    kappa_vs_golden: float


@dataclass(frozen=True, slots=True)
class RewardDecision:
    """Output of the AND-gate evaluation.

    `dpo_eligible` is the primary gate output.

    `composite_score` is the arithmetic mean of chosen-side axis scores,
    used for ranking within the eligible set — NOT for the eligibility gate.
    Note: the spec comment says "sum of normalized axes"; this implementation
    uses mean (sum / count) for range-preservation — values stay in [0, 1].

    `failed_checks` is an immutable tuple of predicate names that failed.
    Axis-regression failures carry the axis name: "axis_regression:Brand".
    Non-axis failures use fixed tokens: "extrinsic_margin", "swap_stability",
    "kappa_vs_golden". The tuple preserves evaluation order (scalar predicates
    first, then axes in sorted order) for deterministic trace-replay diffing.
    Empty tuple ↔ dpo_eligible is True; non-empty ↔ dpo_eligible is False.

    `rationale` is a human-readable string emitted as an OTel span attribute.

    Unlike RouteDecision (which has a mutable span_attrs dict), RewardDecision
    contains only hashable fields — it IS hashable and can be used as a cache
    key or placed in a set for de-duplication across runs.
    """

    dpo_eligible: bool
    composite_score: float
    failed_checks: tuple[str, ...]
    rationale: str


# ---------------------------------------------------------------------------
# Protocol surface
# ---------------------------------------------------------------------------


class CompositeRewardEngine(Protocol):
    """Evaluate a candidate pair against the 4-predicate AND-gate.

    Implementations MUST be pure functions (no I/O, no side effects) and
    MUST be deterministic: same inputs → same outputs every time. The test
    suite in tests/unit/test_reward_engine.py asserts this property.

    The only shipped implementation is AndGateRewardEngine. Future variants
    (e.g. a learned reward model that wraps the AND-gate) must satisfy this
    same Protocol — the DPO pipeline is agnostic to which implementation
    is wired in.
    """

    def evaluate(self, components: RewardComponents) -> RewardDecision:
        """Return the gate decision for a single candidate pair.

        MUST be sub-5ms p99 — this is called inside the EvoDesign trajectory
        ingest pipeline on every candidate pair, often thousands per session.
        The current implementation is O(|axes|) with no I/O.
        """
        ...

    def explain_to_judge(self, decision: RewardDecision) -> str:
        """Return a multi-sentence human-readable explanation.

        Used in the §11.3 DevPost demo narrative and in the weekly
        reward_engine_audit artifact. Must name each failed predicate and
        quantify the gap. Returns a positive affirmation on eligible pairs.
        """
        ...


# ---------------------------------------------------------------------------
# Default implementation
# ---------------------------------------------------------------------------


class AndGateRewardEngine:
    """Default AND-gate implementation. Pure function — no I/O.

    Deterministic by construction: all branches are pure arithmetic over
    the input values; no random state, no I/O, no mutable class state.
    The hypothesis property tests in test_reward_engine.py verify this.

    Evaluation order (determines failed_checks tuple ordering):
      1. extrinsic_margin
      2. swap_stability
      3. per-axis regression, in sorted(intrinsic.keys()) order
      4. kappa_vs_golden

    All failures are collected before returning — the gate does NOT short-
    circuit on the first failure. This gives operators a complete picture of
    why a pair was rejected, enabling targeted calibration improvements.
    """

    def evaluate(self, components: RewardComponents) -> RewardDecision:
        """Return the AND-gate decision for a candidate pair."""
        failed: list[str] = []

        # Predicate 1: extrinsic margin
        if components.extrinsic < EXTRINSIC_MARGIN_FLOOR:
            failed.append("extrinsic_margin")

        # Predicate 2: swap stability
        if components.swap_stability < SWAP_STABILITY_FLOOR:
            failed.append("swap_stability")

        # Predicate 3: per-axis regression.
        # Sorted key iteration guarantees deterministic failed_checks ordering
        # across Python versions (dicts preserve insertion order as of 3.7,
        # but callers may construct the dict in arbitrary order).
        for axis in sorted(components.intrinsic.keys()):
            scores = components.intrinsic[axis]
            chosen_score = scores["chosen"]
            rejected_score = scores["rejected"]
            # Strict-greater: delta == MAX_AXIS_REGRESSION passes.
            if rejected_score - chosen_score > MAX_AXIS_REGRESSION:
                failed.append(f"axis_regression:{axis}")

        # Predicate 4: kappa vs golden-set calibration
        if components.kappa_vs_golden < KAPPA_VS_GOLDEN_FLOOR:
            failed.append("kappa_vs_golden")

        # Composite score: arithmetic mean of chosen-side axis scores.
        # Used for ranking within the eligible set; does NOT gate eligibility.
        # Range-preserved in [0, 1] because each axis score is in [0, 1].
        chosen_scores = [s["chosen"] for s in components.intrinsic.values()]
        composite_score = sum(chosen_scores) / len(chosen_scores) if chosen_scores else 0.0

        eligible = len(failed) == 0
        if eligible:
            rationale = (
                f"DPO-eligible: all 4 predicates passed "
                f"(extrinsic={components.extrinsic:.3f} ≥ {EXTRINSIC_MARGIN_FLOOR}, "
                f"swap_stability={components.swap_stability:.3f} ≥ {SWAP_STABILITY_FLOOR}, "
                f"no axis regressed by > {MAX_AXIS_REGRESSION}, "
                f"kappa={components.kappa_vs_golden:.3f} ≥ {KAPPA_VS_GOLDEN_FLOOR})"
            )
        else:
            rationale = f"REJECTED: {len(failed)} predicate(s) failed: {', '.join(failed)}"

        return RewardDecision(
            dpo_eligible=eligible,
            composite_score=composite_score,
            failed_checks=tuple(failed),
            rationale=rationale,
        )

    def explain_to_judge(self, decision: RewardDecision) -> str:
        """Return a multi-sentence explanation suitable for audit artifacts.

        Named the predicate(s) that failed, quantifies the gap (actual vs
        threshold), and gives a disposition: REJECTED or DPO-eligible.
        """
        if decision.dpo_eligible:
            return (
                f"This pair is DPO-eligible. "
                f"Composite score {decision.composite_score:.3f}. "
                f"All four AND-gate predicates passed; the pair is safe to include in "
                f"the §9 DPO dataset builder."
            )
        gap_descriptions: list[str] = []
        for check in decision.failed_checks:
            if check == "extrinsic_margin":
                gap_descriptions.append(
                    f"the composite-judge margin failed to clear the {EXTRINSIC_MARGIN_FLOOR} floor"
                )
            elif check == "swap_stability":
                gap_descriptions.append(
                    f"swap-stability fell below the {SWAP_STABILITY_FLOOR} floor, "
                    f"indicating a likely position-bias artifact per Zheng 2023"
                )
            elif check.startswith("axis_regression:"):
                axis = check.split(":", 1)[1]
                gap_descriptions.append(
                    f"the {axis!r} axis regressed by more than {MAX_AXIS_REGRESSION}"
                )
            elif check == "kappa_vs_golden":
                gap_descriptions.append(
                    f"judge agreement with the golden set fell below the "
                    f"{KAPPA_VS_GOLDEN_FLOOR} calibration floor (RR-13)"
                )
        return (
            f"This pair was REJECTED by the AND-gate. "
            f"{len(decision.failed_checks)} predicate(s) failed. "
            f"Specifically: {'; '.join(gap_descriptions)}. "
            f"The pair will NOT be included in the DPO dataset."
        )
