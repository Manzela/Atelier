# 0014. Model Registry Pins Gemini 2.5 Flash (Not 3.0 Flash)

**Status:** Accepted
**Date:** 2026-05-21
**Decision-makers:** Daniel Manzela (+ Claude Opus 4.7 MAX as builder, Antigravity as executor)

## Context

The PRD (`docs/superpowers/specs/2026-05-14-atelier-prd.md`) section 6.3 (Node Specifications) and section 7 (FA-016: Model Selection Registry) reference `gemini-3-flash` as the primary model for the generator and most judge nodes.

At the time of D1 implementation (2026-05-15), `gemini-3-flash` is not yet generally available on Vertex AI. The highest-capability stable variant available is `gemini-2.5-flash-preview-05-20`, which shipped as a preview release on 2026-05-20 with significant improvements over the 2.5 Flash baseline:

- Improved code generation quality (critical for HTML/CSS output)
- Better structured output compliance (critical for JSON schema conformance in judge votes)
- Longer context window utilization (relevant for multi-document prompts)

The model registry (`atelier-core/src/atelier/models/model_registry.py:L84`) pins all generator and judge nodes to `gemini-2.5-flash-preview-05-20`, except the Visual Clarity judge which uses `gemini-2.5-pro-preview-05-06` for its higher visual reasoning capability.

This is a substantive deviation from the PRD that touches every node's behavior. Per `CLAUDE.md` invariant `<no_speculation>` and the requirement that "mid-sprint changes to the PRD require an explicit ADR commit, not silent drift," this ADR documents the deviation formally.

## Decision

**Pin all pipeline nodes to `gemini-2.5-flash-preview-05-20` (generator, 4 of 5 judges) and `gemini-2.5-pro-preview-05-06` (Visual Clarity judge) for the duration of Phase 1.**

The model registry is architected as a lookup table keyed by `(node_role, judge_axis)` tuples, enabling drop-in model swaps without code changes. When `gemini-3-flash` reaches GA on Vertex AI, the swap is a single YAML/config change — no code modification required.

## Consequences

### Positive

- Immediate availability: no blocking dependency on an unreleased model
- Stable API surface: preview-05-20 has a fixed API contract for the Phase 1 sprint window
- Drop-in swap readiness: `ModelRegistry.resolve()` returns `ModelConfig` objects that abstract the model ID — downstream code never references the literal string
- Cost predictability: 2.5 Flash pricing is known and budgeted

### Negative

- Capability gap: if `gemini-3-flash` has materially better design generation, Phase 1 calibration baselines will need recalibration on swap
- Preview stability: `preview-05-20` may receive breaking changes (mitigated by pinning the exact version string, not using `latest`)
- Audit trail: this deviation must be tracked so the swap is not forgotten

### Migration plan

The registry will be re-pinned to `gemini-3-flash` when **all three** conditions are met:

1. `gemini-3-flash` reaches GA status on Vertex AI in `us-central1` (the primary region)
2. The calibration golden set (10 surfaces with human-graded scores) is re-run on both models
3. Pass rate on the golden set is within 2 percentage points of the 2.5 Flash baseline

If condition 3 fails (3.0 is worse on the golden set), the pin remains on 2.5 Flash and this ADR is updated with the finding.

## Alternatives Considered

1. **Wait for `gemini-3-flash` GA.** Rejected: blocks all Phase 1 work on an external timeline outside our control.
2. **Use `gemini-2.0-flash` (stable GA).** Rejected: significantly lower code generation quality observed in early testing, particularly for semantic HTML output.
3. **Use `gemini-2.5-pro` for all nodes.** Rejected: 10x cost increase per token; budget would exhaust before Phase 2. Pro is reserved for the Visual Clarity judge only, where visual reasoning quality justifies the premium.
4. **Use a non-Gemini model (Claude, GPT-4o).** Rejected: Atelier is a Google-native system per the hackathon rules and PRD section 2.1. Cross-vendor routing adds latency, cost unpredictability, and compliance complexity.

## Status

Accepted — 2026-05-21. Will be superseded when `gemini-3-flash` GA migration is completed.
