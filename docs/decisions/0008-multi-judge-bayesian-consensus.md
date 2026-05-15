# 0008. Multi-judge Bayesian-weighted consensus + DEMAS-D Provenance per axis

**Status:** Accepted
**Date:** 2026-05-14
**Decision-makers:** Daniel Manzela (+ Claude Opus 4.7 MAX as builder)

## Context

After deterministic gates (Lighthouse, axe, visual-diff, token-fidelity, semantic-HTML, responsive snapshot) pass, we need an LLM-based judge to score subjective design axes (brand fidelity, copy voice, motion correctness, token coherence, cross-screen coherence).

Two key research findings constrain the judge design:

1. **DesignPref (Nov 2025)** — 12k pairwise UI judgments by 20 professional designers. Krippendorff's α = 0.25. **Designer disagreement is intrinsic.** A single global judge is provably wrong on subjective axes; personalized judges win with 20× fewer examples than aggregated baselines.

2. **DEMAS Provenance Matrix** (from agent-dag-pipeline) — sending an LLM judge the full DOM context for every axis causes attention dilution; the judge's per-axis accuracy degrades because it can't focus.

Three options:

1. Single LLM judge scores all axes from full context
2. K specialized judges, each scoring one axis from full context, simple-average vote
3. K specialized judges, each scoring one axis from **only its axis-relevant ground-truth variables** (DEMAS-D Provenance), Bayesian-weighted vote

## Decision

We will use **K = 5 specialized rubric judges in a Bayesian-weighted consensus, with per-axis DEMAS-D Provenance Matrix**.

The 5 judges:

- **Brand-judge** — scores adherence to `DESIGN_PRINCIPLES_APPLE.md` (or project's own constitution). Provenance: rendered DOM + DESIGN.md tokens + principles document.
- **Copy-judge** — scores voice rubric (no marketing voice, peer-level depth, on-brief). Provenance: text content + voice rubric.
- **Motion-judge** — scores motion correctness (`prefers-reduced-motion` alternate exists, reveals fire once, not decorative). Provenance: animation rules + JS event listeners + `prefers-reduced-motion` media query results.
- **Token-fidelity-judge** — scores adherence to `design-system.lock.md`. Provenance: rendered hex/rgb/font/spacing values + DESIGN.md token set.
- **Cross-screen-coherence-judge** — scores reuse of patterns from prior-converged surfaces in the same campaign. Provenance: this surface + top-5-most-similar prior surfaces + DECISIONS.md.

Each judge implements the ADK `rubric_based_final_response_quality_v1` evaluator with its axis-specific rubric. Judges run in parallel (ADK `ParallelAgent`).

The **ConsensusAgent** then computes a **Bayesian-weighted vote**:

- Each judge returns `(score, confidence_interval)`
- Weights are derived from per-axis priorities in the BriefSpec (e.g., a brand-heavy project weights brand-judge higher; an a11y-critical project weights a11y deterministic gate higher with lower trust budget for any single LLM judge)
- Composite score = `Σ(weight_i × score_i × confidence_i) / Σ(weight_i × confidence_i)`
- Decision: `CONVERGED` if composite ≥ floor AND every axis ≥ axis-floor; `RETRY` otherwise; `DEFER_HUMAN` if any judge confidence-interval is too wide

In Phase 1 MVP, all judges use Gemini 3 Flash with prompt-only personalization. In Phase 2+, per-project DPO + LoRA fine-tuning replaces the prompt-only judges via Vertex AI Endpoints with Multi-Tuning (per-project LoRA serving via S-LoRA).

## Consequences

### Positive

- Constitutes core of novel contribution **N2 (DEMAS-D)** + supporting structure for **N3 (PerJudge)**
- Addresses DesignPref α=0.25 finding head-on — personalization scientifically required, we ship it from MVP via prompt-tuning, then upgrade to LoRA in Phase 2
- DEMAS-D Provenance Matrix prevents judge attention dilution — each judge sees ~5-15 ground-truth variables for its axis, not 500+ DOM nodes
- Bayesian weighting enables transparent per-project priorities ("our project cares more about brand than performance")
- Confidence intervals enable escalation to human approval (Layer 3 of the layered oracle) when judges disagree

### Negative

- Five parallel LLM calls per consensus = higher token cost than a single judge (~5× cost). Mitigated by Apigee model routing (use Flash, not Pro, for judges) and per-session cost cap.
- ADK's `rubric_based_*_v1` runs serially today (open issue google/adk-python#3958). For K=5 in MVP this is fine; for K=8+ in Phase 2 we may need to fork or wait for upstream.
- Calibration is harder with K judges than with 1 — each judge needs its own calibration golden set

### Neutral

- ConsensusAgent is custom code (~300 LOC) since ADK doesn't ship a Bayesian-vote primitive — but it's a small, well-tested component

## Alternatives considered

### Option A: Single LLM judge scores all axes from full DOM context

- Pros: Simpler; one model call per consensus
- Cons: Suffers attention dilution (DEMAS-D would not apply); single global judge contradicts DesignPref α=0.25; can't personalize per axis
- Why rejected: Loses the two key insights from research

### Option B: K judges, simple-average vote, no DEMAS-D Provenance

- Pros: Mid-complexity
- Cons: Suffers attention dilution per judge (each gets full DOM); average treats all judges equal regardless of confidence
- Why rejected: Loses DEMAS-D's accuracy improvement and Bayesian weighting's per-project flexibility

## References

- [DesignPref paper](https://arxiv.org/abs/2511.20513) (Nov 2025) — α=0.25 finding
- [agent-dag-pipeline DEMAS Provenance Matrix](https://github.com/Manzela/agent-dag-pipeline) — direct port
- [PRD §6.4 D-O-R-A-V Design Rubric + §6.5 Layered Oracle](../superpowers/specs/2026-05-14-atelier-prd.md)
- [adk-python issue #3958](https://github.com/google/adk-python/issues/3958) — parallel LLM-as-judge tracking
- `atelier-core/src/atelier/judges/consensus.py` — ConsensusAgent implementation
- `atelier-core/src/atelier/judges/demas_provenance.py` — per-axis Provenance Matrix
