# 0030. AND-Gate Composite Reward Engine

**Status:** Accepted
**Date:** 2026-05-21
**Decision-makers:** Daniel Manzela (Principal Architect), Atelier sprint

## Context

The §9.1 DPO dataset builder and the §19 generator-pair miner both need a
predicate that answers: "is this candidate pair good enough to train on?"

The naive composite-reward shape — `R = Σ w_i × axis_i(y)` — is
Goodhart-vulnerable: the generator learns to pump the highest-weight axis at
the expense of all others. Eisenstein 2023 ("Helping or Herding?") shows that
even reward-model ensembles reduce but cannot eliminate this attack surface.

Zheng 2023 (MT-Bench) showed that LLM judges flip preferences ~35% of the
time (GPT-4) to ~76% (Claude) when the answer order is swapped — a pure
position-bias artifact that a weighted sum cannot detect.

A single-predicate quality threshold (e.g. "extrinsic margin ≥ 0.15") is
insufficient because it ignores: (a) position bias, (b) per-axis regressions
in the chosen candidate, and (c) judge calibration quality.

## Decision

Replace the weighted-sum composite reward with a **conjunctive AND-gate** over
four independent predicates. A pair passes if and only if **all four** hold:

| Predicate          | Threshold | Constant                 | Rationale                                                                                 |
| ------------------ | --------- | ------------------------ | ----------------------------------------------------------------------------------------- |
| Extrinsic margin   | ≥ 0.15    | `EXTRINSIC_MARGIN_FLOOR` | Composite-judge score difference must be meaningful (matches §9.1 `MIN_MARGIN`)           |
| Swap stability     | ≥ 0.80    | `SWAP_STABILITY_FLOOR`   | Position-swap test (§7 FA-017) confirms the win is not a position-bias artifact           |
| No axis regression | Δ ≤ 0.05  | `MAX_AXIS_REGRESSION`    | Chosen does not score > 0.05 below rejected on any individual axis (strict-greater check) |
| Kappa vs golden    | ≥ 0.70    | `KAPPA_VS_GOLDEN_FLOOR`  | Judge agreement with the calibration golden set on this brief type is at the RR-13 floor  |

Failing any ONE predicate rejects the pair. Thresholds are `Final` — changes
require an ADR amendment (not a config flip) to prevent silent threshold drift.

Implementation: `atelier.reward.composite.AndGateRewardEngine`. Pure function,
no I/O, deterministic by construction. The `CompositeRewardEngine` Protocol
allows alternative implementations (e.g. a learned gate) without changing
callers.

**composite_score** (soft score, not the gate): arithmetic mean of chosen-side
axis scores. Used for ranking within the eligible set only.

**explain_to_judge()**: returns multi-sentence human-readable explanation
naming each failed predicate and quantifying the gap. Used in the reward_engine
audit artifact and the DevPost demo §11.3 narrative.

## Consequences

### Positive

- Goodhart-resistant: no single axis can dominate — all four independent signals
  must pass. This is the claim in the DevPost Optimize-pillar narrative.
- Two callers, one predicate: §9.1 dataset builder and §19 pair miner both use
  the identical eligibility check — no drift between where pairs are mined and
  where they are consumed.
- Exhaustive failure collection (not fail-first): every failing predicate is
  reported in `failed_checks`, enabling targeted calibration improvements.
- `RewardDecision` is hashable — all fields are primitives. Can be used as a
  cache key or placed in a set for de-duplication.

### Negative

- Conjunctive gate is conservative — it rejects more pairs than a soft threshold
  would. Mitigation: `mine_pairs()` expands the candidate pool (K=6 per intent)
  to compensate.
- Threshold calibration is fixed until an ADR amendment. Mitigation: the weekly
  `reward_engine_audit` artifact aggregates the `failed_checks` distribution
  across the calibration golden set — skewed distributions (e.g. swap_stability
  failing > 30%) trigger an ADR-amendment proposal.

### Neutral

- `MAX_AXIS_REGRESSION = 0.05` uses a strict-greater check (`>`). Exact-equality
  at the boundary is IEEE-754 implementation-defined; tests construct the boundary
  case as `chosen=0.0, rejected=0.05` (subtraction from zero is lossless) to
  avoid floating-point ambiguity. This is documented in the constant's docstring.

## Alternatives considered

**Option A: Weighted sum with high minimum weights.**
Pros: smooth, differentiable signal. Cons: one high-weight axis can always
dominate; Goodhart-vulnerable by construction. **Rejected.**

**Option B: Soft constraints via penalty terms.**
Pros: flexible. Cons: penalty weights become hyperparameters subject to Goodhart;
no sharp rejection boundary makes the dataset quality indeterminate. **Rejected.**

**Option C: Learned reward model (separate from the composite judge).**
Pros: end-to-end learned. Cons: chicken-and-egg with the DPO dataset it is
trained on; Phase 1 has no labelled data to train from. **Deferred to Phase 3.**

## Anti-bias research basis (spec §21.2)

| Defense                         | Source          | Implementation                                    |
| ------------------------------- | --------------- | ------------------------------------------------- |
| Swap stability floor            | Zheng 2023      | `SWAP_STABILITY_FLOOR = 0.80`                     |
| Pretrain-diverse judge ensemble | Eisenstein 2023 | §7 JUDGE_MODEL_CONFIG: 5 different model families |
| Center-rewards regulariser      | Eisenstein 2023 | §19 `GeneratorTuningConfig.center_rewards=1e-2`   |
| PRM over ORM                    | Lightman 2023   | 8-node DAG emits per-node scores                  |
| AND-gate gate                   | This ADR        | `AndGateRewardEngine.evaluate()`                  |

## References

- Eisenstein 2023, "Helping or Herding? Reward Model Ensembles..."
- Zheng 2023, MT-Bench: "Judging LLM-as-a-Judge with MT-Bench"
- Lightman 2023, "Let's Verify Step by Step"
- Spec: `docs/superpowers/specs/2026-05-21-post-r4-strategic-roadmap-design.md` §21
- Plan: Task 5 (T5), Task 14 (promote gate)
- Implementation: `atelier-core/src/atelier/reward/composite.py`
- ADR 0028: DPO algorithm (primary consumer of the eligibility gate)
