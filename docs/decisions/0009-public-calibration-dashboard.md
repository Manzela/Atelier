# 0009. Public calibration dashboard at TBD

**Status:** Accepted
**Date:** 2026-05-14
**Decision-makers:** Daniel Manzela (+ Claude Opus 4.7 MAX as builder)

## Context

Galileo's "Why LLM-as-a-Judge Fails" report (May 2026) documents that **93% of teams hit judge calibration drift in production** — the same trace scores 91 on Monday and 64 on Wednesday. No commercial LLM-judge product ships a drift-detection mechanism, let alone a public-facing one.

For Atelier, calibration drift is critical. Our 5 specialized rubric judges (Brand / Copy / Motion / Token-fidelity / Coherence) each contribute to convergence decisions. If any drifts, downstream effects compound: bad design diffs land in DPO training, then the per-project LoRA learns from drifted ground-truth, then the next session's judge is even worse.

Three options:

1. Don't track drift (assume it doesn't happen)
2. Track drift internally; alert on threshold breach; never publicize
3. Track drift internally + publish externally as a transparency commitment

## Decision

We will publish judge calibration drift externally at **`TBD`** as a continuously-updated public dashboard. Per Anthropic's published guidance, defended by:

- **Frozen golden set**: 100 hand-graded designs per judge axis (500 total), curated pre-launch, never changed without an ADR
- **Weekly recalibration cron** (Mon 03:17 UTC, matching `limits.calibration.recalibration_cron`): every judge re-scores the frozen golden set; correlation vs. canonical-human-rating is computed
- **Drift alert** when correlation drops > 0.05 week-over-week
- **Transparent re-calibration history**: every recalibration event is logged with `(date, judge_axis, correlation, drift_pct, action_taken)` and shown publicly
- **Defense pattern** per Anthropic guidance: binary judges (where applicable) + multi-judge majority + ChainPoll + frozen golden set

Architecture:

- Eval workflow runs the calibration suite weekly
- Results land in `atelier-eval/data/results/calibration_*.json`
- A small Cloud Function pushes the latest results to Firebase Hosting at `TBD`
- Dashboard is a static React + Tailwind page (matches `pipeline-observatory` aesthetic)

## Consequences

### Positive

- Constitutes novel contribution **N8** — first commercial autonomous design agent to publish judge calibration externally
- Builds visceral trust with users + judges (G4S panel) — transparency is the strongest credibility signal
- Self-disciplining: knowing the dashboard is public motivates rigorous calibration maintenance
- Enables external validation by researchers; could become cited evidence in future papers
- Defends against the calibration-drift problem 93% of teams hit silently
- Operational defense + research artifact + competitive moat in one

### Negative

- Public dashboard means failures are public — when calibration drifts, everyone sees it
- Maintenance burden: golden set must be hand-curated initially (~10 hours of designer time per axis × 5 axes = 50 hours)
- Frozen golden set risk: if it stops being representative of real-world distributions, drift signal becomes noisy

### Neutral

- The dashboard becomes a recruiting/marketing asset (third-party validators + design-research community can cite us)

## Alternatives considered

### Option A: Don't track calibration drift

- Pros: No work
- Cons: Joins the 93% of teams who hit silent drift in production; downstream LoRA training poisoning; bad designs ship; users lose trust over time
- Why rejected: Existential — autonomous design agents that don't track judge drift will fail

### Option B: Track internally; never publish

- Pros: Internal-only ops discipline; no public failure mode
- Cons: Loses N8 (one of 13 novel contributions); loses the trust-building public commitment; every other team also tracks internally — no differentiation
- Why rejected: We need the differentiation that public publication provides

## References

- [Galileo: Why LLM-as-a-Judge Fails](https://galileo.ai/blog/why-llm-as-a-judge-fails) (May 2026) — 93% statistic
- [PRD §11 Strategy v2 + §6.5 Layered Oracle calibration check](../superpowers/specs/2026-05-14-atelier-prd.md)
- `atelier-eval/src/atelier_eval/calibration_dashboard.py` — implementation
- `TBD` — public dashboard URL
