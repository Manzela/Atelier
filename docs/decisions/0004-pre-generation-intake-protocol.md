# 0004. Pre-Generation Intake Protocol (PIP) as first-class layer

**Status:** Accepted
**Date:** 2026-05-14
**Decision-makers:** Daniel Manzela (+ Claude Opus 4.7 MAX as builder)

## Context

The Columbia DAPLab "9 Critical Failure Patterns of Coding Agents" (Jan 2026, tested across Claude Sonnet 4.5, Cline, Cursor, V0, Replit) identifies the dominant failure mode as **agents prioritizing runnable over correct, with bugs being silent rather than loud**. The root cause across most patterns: the agent starts generating before it has a complete, validated understanding of the user's intent, design system, stack, and acceptance criteria.

Every commercial autonomous design tool today (Stitch, Vercel v0, Subframe, Lovable.dev, Bolt.new, Replit Agent, Devin, Builder.io Fusion, Tempo Labs) accepts a free-form prompt and immediately generates. **None ships structured pre-generation intake.** First-shot convergence rate across these tools is estimated at ~5–15% (commercial baseline).

DesignPref (Nov 2025, 12k pairwise UI judgments by 20 professional designers) further establishes that designer disagreement is intrinsic (Krippendorff's α = 0.25), making personalized intake scientifically required — yet no shipped tool personalizes the intake itself.

## Decision

We will introduce **Layer 3 — PIP (Pre-Generation Intake Protocol)** as a first-class layer above the Campaign Orchestrator. PIP runs **before any generation** and produces an **immutable BriefSpec** the agent commits to for the duration of the project.

PIP characteristics:

1. **Adaptive depth** — atomic 2-3 questions / small campaign 5-7 / large campaign 10-12 / greenfield 12-15
2. **DAPLab-pattern-mapped** — each of 9 failure patterns has a preempting question; the catalog is documented in `atelier-core/src/atelier/intake/question_catalog.py`
3. **Visual options for design questions** — when content IS visual ("what visual feel?"), 4 mockup thumbnails replace text descriptions
4. **Skip-when-answered** — descriptor file (`.atelier.yaml`) + Memory Bank prior answers + brief-parsed answers all eliminate redundant questions
5. **Immutable post-approval** — BriefSpec.json is frozen at user approval; spec changes require explicit "amend BriefSpec" command + re-approval
6. **Initializes DECISIONS.md + design-system.lock.md** — locks the design system token-set for the duration of the project

## Consequences

### Positive

- Drives first-shot convergence rate from ~5-15% (commercial baseline) to ≥40% (MVP target with PIP)
- Closes silent-error-suppression and business-logic-mismatch failure modes (DAPLab patterns 9 + 3)
- Becomes a demo moment ("watch how Atelier sets itself up for success — 5 questions, 90 seconds, immutable spec") that builds visceral trust
- Constitutes novel contribution **N13** — publishable on its own (CHI workshop or HCI venue)
- Per-project personalization without requiring full DPO+LoRA training upfront (skip paths use Memory Bank for prior projects)

### Negative

- Adds 30-90 seconds of intake time before generation begins (offset by reducing iterations later)
- Visual options require ~30 reference thumbnails bundled in the repo (~3MB Git LFS)
- Adaptive depth requires logic to assess scope from the brief — failure mode if assessment is wrong (mitigated: user can always request fewer/more questions)

### Neutral

- PIP is opt-out via `atelier run --skip-intake` for power users who know exactly what they want
- The intake transcript itself becomes part of the BriefSpec for traceability

## Alternatives considered

### Option A: Skip PIP entirely; rely on free-form prompt + Reviewer feedback loop

- Pros: Minimum friction at the start
- Cons: Inherits the entire DAPLab failure-pattern map; first-shot convergence stays at commercial baseline (~5-15%); high frustration when iterations don't converge
- Why rejected: Defeats the point of the autonomous design agent — we want convergence, not iteration churn

### Option B: Required descriptor file (`.atelier.yaml`) for every project

- Pros: Maximum predictability
- Cons: Friction for new projects (must author descriptor before first use); conflicts with the "agnostic, non-biased" goal of PADI
- Why rejected: PADI requires zero-config new-project support; PIP achieves the same outcome with adaptive intake instead

### Option C: PIP enabled but invisible (intake happens via inferred questions in the agent's chain-of-thought)

- Pros: No UI friction
- Cons: User can't see/edit the inferred answers; can't approve the immutable BriefSpec; loses the trust-building demo moment
- Why rejected: Transparency + immutability are load-bearing for the convergence guarantee

## References

- [PRD §6.1 PIP Layer](../superpowers/specs/2026-05-14-atelier-prd.md)
- Columbia DAPLab — 9 Critical Failure Patterns of Coding Agents (Jan 2026)
- DesignPref (Nov 2025) — designer disagreement is intrinsic
- Anthropic two-prompt harness pattern (Nov 2025) — recursive influence
- `atelier-core/src/atelier/intake/` — implementation
