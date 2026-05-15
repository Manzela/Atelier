# 0005. Recursive Long-Running Discipline (RLRD)

**Status:** Accepted
**Date:** 2026-05-14
**Decision-makers:** Daniel Manzela (+ Claude Opus 4.7 MAX as builder)

## Context

Anthropic's Nov 26 2025 post "Effective harnesses for long-running agents" prescribes a **two-prompt harness** pattern (initializer agent + coding agent + JSON ledger + spec-anchored decisions + REJECTED memory + Ralph Loop "DONE" token + cache-breakpoint architecture) for autonomous coding sprints that span multiple sessions.

We adopt this pattern for our own build sprint (per Strategy v2). But we also realize: **Atelier's users will have the same problem.** Real users will say:

- "Redesign all 50 pages of my SaaS dashboard to match the new brand"
- "Build a complete SaaS UI from scratch — auth + settings + dashboard + entity views"
- "Audit and fix every page of my 200-page docs site for a11y, brand consistency, and motion"
- "Take this English-locale design and produce coherent ES/PT/HE variants"

These are **multi-day, multi-session, hundreds-of-iterations campaigns** that fail in exactly the same ways the research documents. **Every commercial design agent in our market map (Stitch, v0, Subframe, Lovable, Bolt, Replit Agent, Devin, Builder.io, Tempo Labs) breaks on this scope.** None ships long-running discipline.

## Decision

**We will ship the same long-running-agent harness pattern that we use to build Atelier as a first-class user-facing capability** — the **Campaign Orchestrator** layer (Layer 2). Atelier eats its own dogfood.

The Campaign Orchestrator wraps the atomic 8-node DAG (Layer 1) with:

- **CampaignBrief Parser** → decomposes a multi-surface user request into a Surface Manifest with dependency graph
- **Surface Manifest (`surfaces.json`)** → JSON ledger, schema-versioned, agent-edited not rewritten (per Anthropic's "JSON not Markdown" finding)
- **Campaign Picker** → picks next unblocked surface honoring the dependency graph; Cloud Scheduler + Cloud Tasks orchestrate per-campaign worker
- **Cross-Surface Coherence Validator** → on each surface convergence: token use validation, pattern reuse ≥30% threshold, DECISIONS.md compliance check, regression check on prior-converged surfaces
- **Campaign Checkpoint Writer** → updates `surfaces.json` + `campaign-progress.txt` + RESUME-HERE markers + DECISIONS.md + REJECTED.md; commits + pushes to git (or proposes PR)

Per-user-project persistent state mirrors our own sprint state:

```
<user-project>/.atelier/
├── campaign.json
├── surfaces.json
├── campaign-progress.txt
├── DECISIONS.md
├── REJECTED.md
├── design-system.lock.md
├── cost-ledger.json
├── checkpoints/
└── trajectories/
```

User can pause a campaign mid-flight, ship to staging, review converged surfaces, then resume — agent picks up exactly where it left off.

## Consequences

### Positive

- Constitutes novel contribution **N12** — Atelier is the first commercial autonomous design agent to ship Anthropic's long-running-agent harness for end users
- Visible long-running session that doesn't fail when every competitor would — visceral demo gold
- Direct alignment with G4S "Use of Google Cloud" judging criterion (uses Cloud Scheduler + Cloud Tasks + Memory Bank + BigQuery — every layer Google-native)
- Strategically defensible: even if a competitor copies one Atelier feature, replicating the recursive discipline + multi-surface campaign management at production grade is months of work
- Internal-discipline ↔ external-product symmetry creates narrative coherence: "the same patterns we use to build it, we ship to you"

### Negative

- Significant additional code (Campaign Orchestrator + Cross-Surface Coherence Validator + per-campaign state persistence) — adds ~2K LOC to Atelier-original code
- Demo complexity: showing a 12-surface campaign in a 4-min video requires careful pacing
- Cloud Scheduler + Cloud Tasks add two more managed services to the deployment

### Neutral

- The atomic 8-node DAG (Layer 1) remains UNCHANGED as the inner per-surface engine — N12 only adds the outer harness
- Single-surface ("atomic") tasks bypass the Campaign Orchestrator entirely

## Alternatives considered

### Option A: Single-surface only; users orchestrate multi-surface campaigns themselves

- Pros: Smaller scope; faster to ship
- Cons: Loses N12 (one of our 13 novel contributions); leaves the most valuable user use case (full platform redesigns) on the table; competitors don't ship this either, so we hand them the lane
- Why rejected: Multi-surface campaigns ARE the high-value use case; not shipping them is a strategic mistake

### Option B: Multi-surface campaigns via batch orchestration (run N atomic sessions sequentially)

- Pros: Reuses atomic DAG without an outer harness
- Cons: No cross-surface coherence enforcement; no shared design system lock; no dependency graph; no resume across sessions
- Why rejected: This is what commercial tools effectively offer today, and it's what users complain about ("Stitch generates inconsistent screens")

## References

- [PRD §6.2 Campaign Orchestrator](../superpowers/specs/2026-05-14-atelier-prd.md)
- [Anthropic: Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) (Nov 26 2025)
- [Anthropic: Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) (Sep 29 2025)
- Columbia DAPLab — 9 Critical Failure Patterns of Coding Agents (Jan 2026)
