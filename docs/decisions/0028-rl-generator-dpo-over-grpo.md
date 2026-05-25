# 0028. RL Generator: DPO Over GRPO

**Status:** Accepted
**Date:** 2026-05-21
**Decision-makers:** Daniel Manzela (Principal Architect), Atelier sprint

## Context

Spec §19 calls for an RL-driven generator that closes the data flywheel:
K=6 candidate generations → multi-axis composite judging → preference-pair
mining → tuning → promotion. The RL algorithm choice gates the entire §9 + §19
pipeline and must be made before any tuning infrastructure is written.

Three constraints narrow the choice:

1. The reward signal is **preference-based** (ranked pairs), not numerically
   verifiable — there is no ground-truth scalar reward for "is this surface
   design good."
2. Vertex AI exposes `TuningMethod.PREFERENCE_TUNING` (DPO) as a GA surface.
   GRPO and PPO are not available through the Vertex tuning API.
3. Lightman et al. 2023 ("Let's Verify Step by Step") shows process reward models
   (PRM) outperform outcome reward models (ORM). Atelier's 8-node DAG emits
   per-node scores — each node IS a process-level reward signal, making DPO
   the natural fit.

## Decision

Adopt **DPO** (`TuningMethod.PREFERENCE_TUNING`) as the generator tuning
algorithm via `google.genai`.

Source model: `gemini-2.5-flash-001` (lockfile-pinned).

Hyperparameters (`Final`, change requires ADR amendment):

| Parameter              | Value | Rationale                                       |
| ---------------------- | ----- | ----------------------------------------------- |
| β (KL regulariser)     | 0.1   | Standard DPO default; prevents reward hacking   |
| epochCount             | 3     | Small dataset (< 1 000 pairs) — 3 epochs avoids |
|                        |       | overfitting while allowing convergence          |
| adapterSize            | 4     | LoRA rank 4; minimal parameter footprint        |
| learningRateMultiplier | 1.0   | Platform default; revisit if eval degrades      |

**Pair eligibility gate:** the §21 AND-gate composite reward (ADR 0030). Only
pairs that clear all four predicates are fed to the tuning job. This prevents
garbage-in on the DPO dataset.

**Promotion gate:** `evaluate_and_promote()` in `GeneratorTuner` re-runs the
WebGen-Bench calibration subset after each tuning job and only promotes if the
tuned model improves the golden-set pass rate (§19.4).

## Consequences

### Positive

- Direct alignment with Vertex's GA tuning surface — no custom training infra.
- PRM-style per-step preference supervision matches composite-judge granularity;
  the §21 reward carries richer signal than a scalar.
- Re-uses the §9.1 BigQuery dataset format unchanged.

### Negative

- DPO is known to overfit on small datasets. Mitigation: `mine_pairs()` raises
  `InsufficientDataError` if fewer than 50 pairs are available; the AND-gate
  composite reward rejects low-confidence pairs before they enter the dataset.
- Locked to Vertex tuning (no on-prem fallback). Accepted: ADR 0001
  (wrap-don't-fork) keeps us platform-coupled by design.
- Source model is flash-001. A different base model requires a fresh dataset
  (pairs are model-specific).

### Neutral

- Three-way binding adaptation in `dpo_tuning_job.py` allows the `google.genai`
  surface to evolve within the 1.x major version without breaking the call sites.

## Alternatives considered

**Option A: GRPO.**
Pros: SOTA per DeepSeek-R1 (2025). Cons: Vertex does not expose GRPO; using
it would require forking the training loop — forbidden per ADR 0001.
**Rejected — out of scope per ADR 0001.**

**Option B: PPO with a learned reward model.**
Pros: well-understood. Cons: requires training a separate reward model first
(chicken-and-egg), doubles the §9 pipeline, and Vertex does not expose PPO.
**Rejected — too much new infrastructure for the sprint window.**

**Option C: Pure SFT (no preference signal).**
Pros: simplest. Cons: discards the rejected-side of every preference pair;
the data flywheel becomes one-directional; the §21 composite judge's
discriminative power is wasted. **Rejected — signal loss is unacceptable.**

## References

- Lightman et al. 2023, "Let's Verify Step by Step" — PRM > ORM
- `TuningMethod.PREFERENCE_TUNING` — google-genai 1.75.0 (verified 2026-05-21)
- Spec: §9 (dataset), §19 (generator/tuner), §21 (AND-gate reward)
- Plan: Task 6 (DPO migration), Task 7 (mine_pairs), Task 14 (tune + promote)
- ADR 0030: AND-gate composite reward (eligibility gate for DPO pairs)
