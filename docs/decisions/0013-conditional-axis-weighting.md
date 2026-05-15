# 0013. BriefSpec-Conditional Axis Weighting (N15 MJG)

**Status:** Accepted (approved 2026-05-15)
**Date:** 2026-05-15
**Decision-makers:** Daniel Manzela (+ Claude Opus 4.7 MAX as builder)
**Related:** ADR 0011 (WRAI), ADR 0012 (Anchor Discipline)
**Promotes:** Audit P1-5 → PRD §5 N15 (Metastrategic Judging Gap)

## Context

Audit `audit/findings.md` Gap 1 surfaced a fundamental design issue: Atelier's 5-judge ConsensusAgent + Det Gate use **fixed per-axis floors** regardless of project type. A data-viz dashboard ships with the same brand-fidelity floor (0.7) as a marketing landing page, even though the user's intent + visual register clearly demand different weights:

- A **dense-data dashboard** should weight a11y + visual-clarity higher (0.85+) and brand-fidelity lower (0.6) — information density beats decorative consistency
- A **brutalist marketing site** should weight originality higher (0.85) and brand-fidelity lower (0.5) — memorability beats restraint
- An **editorial publication** should weight visual-clarity higher (0.8) and originality moderate (0.7) — readability beats novelty

Pass 2 reference enrichment (cf. `audit/findings.md` §"Pass 2 — DAPLab scan") confirmed that **DAPLab's 9 failure patterns do not document this failure mode** — the patterns are all implementation failures, not metastrategic evaluation failures. Closing this gap is therefore a **novel contribution** (N15 MJG — Metastrategic Judging Gap).

No commercial autonomous design agent in our market map (Stitch, v0, Subframe, Lovable, Bolt, Replit Agent, Devin, Builder.io, Tempo Labs, Galileo AI, Locofy) ships per-project judge weighting. This is competitively unowned ground.

## Decision

We will introduce a **`compute_axis_weights(brief: BriefSpec) → AxisWeights`** function that derives per-axis floors and weights from `BriefSpec.visual_register × BriefSpec.compliance_level × BriefSpec.convergence_bar`. The ConsensusAgent applies these as per-axis floors; the Det Gate applies them as threshold modifiers. WRAI's `suggested_overrides` (per ADR 0011) can amend the heuristic per-project.

### Initial heuristic table — `visual_register` axis

| visual_register | brand_fidelity | originality | relevance | accessibility | visual_clarity |
| --------------- | -------------- | ----------- | --------- | ------------- | -------------- |
| editorial       | 0.7            | 0.7         | 0.7       | 0.7           | 0.8            |
| dense-data      | 0.6            | 0.5         | 0.8       | 0.85          | 0.85           |
| playful         | 0.6            | 0.8         | 0.7       | 0.7           | 0.65           |
| brutalist       | 0.5            | 0.85        | 0.7       | 0.7           | 0.5            |
| custom          | 0.7            | 0.7         | 0.7       | 0.7           | 0.7 (defaults) |

### `compliance_level` modifier (additive to accessibility floor)

| compliance_level | accessibility floor adjustment |
| ---------------- | ------------------------------ |
| none             | -0.1 (warn-only)               |
| AA               | 0 (default)                    |
| AAA              | +0.05                          |
| regulatory       | +0.10 (cap at 1.0)             |

### `convergence_bar` modifier (multiplicative to all floors)

| convergence_bar | multiplier            |
| --------------- | --------------------- |
| ship-it         | 0.85 (≥85% threshold) |
| production      | 1.00 (≥95% threshold) |
| perfectionist   | 1.05 (cap at 1.0)     |

### Composition

```python
def compute_axis_weights(brief: BriefSpec) -> AxisWeights:
    base = REGISTER_TABLE[brief.visual_register]
    a11y_adj = COMPLIANCE_ADJ[brief.compliance_level]
    bar_mult = CONVERGENCE_MULT[brief.convergence_bar]

    weights = {
        axis: min(1.0, max(0.0, (base[axis] + (a11y_adj if axis == "accessibility" else 0)) * bar_mult))
        for axis in AXES
    }

    # WRAI suggested_overrides applied last (with provenance)
    if brief.research_findings:
        for override in brief.research_findings.suggested_overrides:
            if override.user_accepted and override.target_field.startswith("axis_weights."):
                axis = override.target_field.split(".")[1]
                weights[axis] = float(override.suggested_value)

    return AxisWeights(weights=weights, provenance=...)
```

### Pydantic data contract

```python
class AxisWeights(BaseModel, frozen=True):
    weights: dict[Axis, float]  # all 5 axes; floor for that axis
    provenance: dict[Axis, WeightSource]  # where each weight came from (heuristic / WRAI / user-override)
    schema_version: int = 1

class WeightSource(BaseModel, frozen=True):
    method: WeightSourceMethod  # REGISTER_TABLE | COMPLIANCE_ADJ | CONVERGENCE_MULT | WRAI_OVERRIDE | USER_OVERRIDE
    cited_in: str  # ADR id, citation URL, or "user input"
    schema_version: int = 1
```

`AxisWeights` is computed once at BriefSpec lock + cached in per-project state at `<user-project>/.atelier/axis_weights.json`. Re-computed only on BriefSpec amendment (per ADR 0012 Rule 3).

## Consequences

### Positive

- Closes audit Gap 1 (user-flagged) — BriefSpec.visual_register now actually drives downstream behavior
- Constitutes novel contribution **N15** — first commercial autonomous design agent to ship per-project judge weighting. Publishable as standalone CHI workshop paper.
- Deterministic and inspectable — `provenance` field shows exactly why each weight has its value
- Composable with WRAI — research findings can override heuristic defaults with cited rationale
- Composable with PADI (P2-9) — PADI's tech-stack inference can extend the heuristic table later (e.g., React-with-server-components → boost performance axis)

### Negative

- Heuristic table requires calibration. Initial table is informed but not validated.
- More complex demo: "watch how Atelier scores the same candidate UI differently for editorial vs. brutalist" requires running 2 fixtures side-by-side
- Custom register falls back to defaults; documented limitation

### Neutral

- Weights cap at 0.0–1.0 to prevent invalid floor configurations
- The heuristic table is itself a versioned config file (`config/axis_weights_heuristic.yaml`) — changes require an ADR (defends against silent drift)

## Calibration plan

Phase 2 D10-D11 ships 20 calibration runs:

- 5 fixture briefs × 4 visual_registers (skipping `custom`) = 20 unique configurations
- Each runs the full pipeline end-to-end on a known-good candidate set
- Compare ConsensusAgent decision (CONVERGED / RETRY / DEFER_HUMAN) against expert human rating
- Adjust heuristic table if 2+ fixtures show systematic mis-weighting
- Final table committed in `config/axis_weights_heuristic.yaml` with calibration evidence in `atelier-eval/data/axis_weights_calibration_2026-05-29.jsonl`

## Alternatives considered

### Option A: Fixed weights (status quo)

- Pros: Predictable, simple, no calibration needed
- Cons: Cannot deliver "dynamic per project" intent — the user's exact ask
- Why rejected: User-flagged failure mode

### Option B: Fully learned weights (DPO-tuned per project)

- Pros: Maximally personalized
- Cons: Requires accumulated trajectory data per project before weights stabilize; cold-start fails for new projects; opaque (no inspection)
- Why rejected: Cold-start is fatal for the "agnostic, non-biased" claim. Heuristic table provides instant good-default; DPO can refine later (Phase 4+)

### Option C: User-specified weights (manual axis-weight UI in PIP)

- Pros: Maximum user control
- Cons: Demands user knowledge they don't have ("what should brand-fidelity be for my use case?"); cognitive overload; defeats the "agent does the thinking" promise
- Why rejected: PIP is meant to free the user from technical config decisions

### Option D: Heuristic table + user override (chosen)

- Best of all: instant good defaults, inspectable, composable with WRAI overrides, calibrate-able with data over time
- This is the chosen approach

## References

- [audit/findings.md Gap 1](../../audit/findings.md)
- [audit/audit-plan.md P1-5 → N15](../../audit/audit-plan.md)
- [PRD §5 N15](../superpowers/specs/2026-05-14-atelier-prd.md) — formal contribution declaration
- [PRD §6.4 D-O-R-A-V Design Rubric](../superpowers/specs/2026-05-14-atelier-prd.md) — fixed-floors table this ADR replaces
- [ADR 0011 — WRAI](0011-web-research-augmented-intake.md) — `suggested_overrides` source
- [ADR 0012 — Anchor Discipline](0012-anchor-discipline-briefspec-everywhere.md) — versioning binding
- DesignPref (Nov 2025, α=0.25) — designer disagreement is intrinsic, motivating per-project weighting
