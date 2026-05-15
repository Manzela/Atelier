# 0010. A2UI v0.9 as canonical output protocol

**Status:** Accepted
**Date:** 2026-05-14
**Decision-makers:** Daniel Manzela (+ Claude Opus 4.7 MAX as builder)

## Context

Generated UI must land somewhere. Options for the output protocol:

1. **Plain HTML/CSS/JS** — lowest common denominator; works everywhere
2. **Framework-specific output** — generate React JSX, Vue SFCs, Flutter widgets, etc., one at a time
3. **A2UI v0.9** (Google, released Apr 17, 2026) — framework-agnostic protocol for agents to render into existing component catalogs (renderers shipped for React, Flutter, Lit, Angular)

A2UI's pitch: agent emits a single declarative payload; A2UI renderers turn it into framework-native components in any of the supported frameworks. Designed for the emerging "generative UI" pattern (per Google Research's [generative UI blog post](https://research.google/blog/generative-ui-a-rich-custom-visual-interactive-user-experience-for-any-prompt/)).

As of May 2026, A2UI is **brand-new** (~1 month old). No commercial autonomous design agent has built on it.

## Decision

**Atelier renders to A2UI v0.9 by default.** Output drops into any React / Flutter / Lit / Angular host without translation. Atelier ships all 4 renderers as part of MVP.

Output flow:

```
Final Validator (N4) →
  A2UI Renderer →
    {ReactRenderer, FlutterRenderer, LitRenderer, AngularRenderer}
    each produces framework-native code in the project's stack
```

For projects whose stack is NOT one of the 4 (e.g., Sage 10 PHP, vanilla HTML, Astro), Atelier:

- Renders to A2UI internally for in-agent consistency
- Then transpiles A2UI to the project's target framework via an additional renderer (vanilla HTML renderer ships in Phase 1.5; Astro / Svelte / Sage in Phase 2+ as community contributions)

## Consequences

### Positive

- Constitutes novel contribution **N7** — first autonomous design agent built A2UI-native from day one
- Direct alignment with Google's emerging A2UI strategy — Atelier becomes the reference implementation for non-trivial agents on A2UI
- "Use of Google Cloud" judging criterion — A2UI is a Google protocol
- Multi-framework output from a single agent design = visceral demo moment (12 surfaces rendered simultaneously in React + Flutter + Lit + Angular)
- A2UI evolves; we get framework-renderer improvements for free
- Future-proof: as Google adds more A2UI renderers (Solid, Qwik, Vue?), we get them automatically

### Negative

- A2UI is brand-new (released Apr 17 2026); no production-grade examples to learn from; we're effectively the first significant adopter
- Renderer output may not match hand-written framework code idiomatically — could feel "AI-generated"
- A2UI v0.9 is alpha; breaking changes likely; lockfile-pinned to specific version (per ADR 0001 wrap-don't-fork principle)
- For projects using non-A2UI-supported frameworks, we have an additional translation step

### Neutral

- For users on supported frameworks, A2UI output is a feature (consistent design system across frameworks); for users on unsupported frameworks, it's transparent (we transpile)

## Alternatives considered

### Option A: Render directly to React only (the most common framework)

- Pros: Native idiomatic React output; well-trodden path
- Cons: Loses "first A2UI-native" novelty; loses multi-framework demo; locks Atelier into React-only ecosystem
- Why rejected: A2UI is on-rubric (Google) and gives us multi-framework as a side effect

### Option B: Render to plain HTML/CSS/JS only

- Pros: Lowest common denominator; works in every project
- Cons: Modern projects use frameworks; HTML output requires re-transpilation; loses A2UI alignment
- Why rejected: Lose-lose — neither idiomatic for framework users nor on-rubric

### Option C: Multi-framework output via direct emission per framework

- Pros: Idiomatic per framework; no protocol layer
- Cons: 4× generation cost (each framework gets its own LLM call); divergence between framework outputs (React version uses pattern X, Flutter version uses pattern Y); loses A2UI alignment
- Why rejected: A2UI normalizes the design intent into a single canonical representation; renderers are deterministic transpilers; cheaper + more consistent

## References

- [A2UI v0.9 announcement](https://developers.googleblog.com/a2ui-v0-9-generative-ui/) (Apr 17, 2026)
- [Google Research: Generative UI](https://research.google/blog/generative-ui-a-rich-custom-visual-interactive-user-experience-for-any-prompt/)
- [PRD §6.3 N4 Final Validator + A2UI Renderer](../superpowers/specs/2026-05-14-atelier-prd.md)
- `atelier-core/src/atelier/render/` — renderer implementations
