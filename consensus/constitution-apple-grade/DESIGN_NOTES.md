# Apple-Grade Constitution — Technical Design Notes

## Purpose

This document explains the design philosophy, scoring methodology, and
integration mechanics behind the `apple-grade` constitution.

## Format Reconciliation (M3)

Two complementary representations exist:

- **`consensus/constitutions/apple-grade.yaml`** — Compact YAML with 7
  principles, numeric weights, and scoring thresholds. Consumed by the
  ConsensusAgent scoring algorithm for automated quality gating.
- **`consensus/constitution-apple-grade/`** (this directory) — Rich
  Markdown files with per-principle do/don't examples, edge cases, and
  HIG citations. Injected into the Brand judge prompt as grounding context.

Both formats are canonical. The YAML drives automated scoring; the MD
directory provides the detailed reasoning the judge uses to evaluate
candidates. Neither supersedes the other.

The `index.json` in this directory maps principle IDs to files and
weights that align with the YAML's scoring weights.

## Constitution Selector Component (CSC-D)

The CSC-D (Constitution Selector Component — Design) automatically selects
this constitution when the `BriefSpec.visual_register` matches any of:

- `luxury`
- `corporate`
- `saas`

The constitution is loaded into the `ConsensusAgent` (N3d) as a soft
penalty system that reduces the composite D-O-R-A-V score when quality
falls below the `scoring.target` threshold.

## Principle Summary

| ID | Name | Weight | Key Gate |
|----|------|--------|----------|
| P1 | Pixel-Perfect Precision | 1.5 | 8px grid, no fractional px |
| P2 | Restrained Color Palette | 1.2 | ≤5 colors, neutrals dominate |
| P3 | Typography Hierarchy | 1.3 | ≤3 font sizes visible |
| P4 | Generous Whitespace | 1.4 | ≥24px padding, ≥48px sections |
| P5 | Micro-Interactions | 0.8 | 200-300ms ease-out transitions |
| P6 | Accessibility as Design | 1.0 | WCAG AA contrast ratios |
| P7 | Progressive Disclosure | 1.1 | Primary CTA immediately visible |

## Scoring Thresholds

| Threshold | Score | Meaning |
|-----------|-------|---------|
| `minimum_pass` | 0.70 | Below this → rejected outright |
| `target` | 0.85 | Below this → soft penalty applied |
| `exceptional` | 0.95 | At or above → flagged as "gold" |

## Penalty Mechanics

When the composite D-O-R-A-V score falls below `target` (0.85), the
`_apply_constitution()` function applies a graded penalty:

```
gap = target - composite
penalty_multiplier = max(1.0 - gap, CONSTITUTION_FLOOR)
penalized_score = composite * penalty_multiplier
```

The `CONSTITUTION_FLOOR` (0.50) prevents the multiplier from dropping
below 50%, ensuring even poor candidates retain some signal for the
fixer loop.

## Integration Path

```
BriefSpec.visual_register == "luxury"
    → CSC-D selects apple-grade.yaml
    → ConsensusAgent loads 7 principles
    → Each judge scores against principle weights
    → Composite score checked against target
    → Penalty applied if below 0.85
    → ConsensusEvaluation emitted with constitution_name="apple-grade"
```

## PRD Reference

- §6.3 N6 (CSC-D — Constitution Selector)
- §6.3 N3d (ConsensusAgent)

## ADR Reference

- ADR-0012: Constitution enforcement as soft penalty
