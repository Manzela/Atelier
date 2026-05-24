# ADR 0016: axis_weights_heuristic.yaml as Phase-1 Planning Artifact

**Status:** Accepted
**Date:** 2026-05-21
**Audit:** Run 2 P1-2 deferral

## Context

`consensus/axis_weights_heuristic.yaml` uses a `surface_types` taxonomy
(`landing_page`, `pricing`, `checkout`, `onboarding`, `dashboard`,
`marketing_email`, `default`).

`atelier-core/src/atelier/models/axis_weights.py` uses the legacy
`visual_register` taxonomy (`corporate`, `luxury`, `playful`, `technical`,
`editorial`, `default`).

These are conceptually different categorizations, not just different keys:

- `surface_types` categorizes by **page purpose** (what the user is doing)
- `visual_register` categorizes by **brand aesthetic** (how it should look)

Both are valid design dimensions. The question is which should drive
judge weighting in the ConsensusAgent (N3d).

## Decision

For Phase 1, retain BOTH:

- `axis_weights_heuristic.yaml` stays as a documented planning artifact for
  Phase-2 ConsensusAgent (N3d) integration
- `axis_weights.py` keeps hardcoded `_WEIGHT_PRESETS` keyed on
  `visual_register` for Phase-1 runtime
- Reconciliation deferred to F0025 at N3d integration time

## Consequences

- **Pro**: No schema risk for Phase-1 demo; existing 249 tests pass unchanged
- **Pro**: Phase-2 has a designed-for-purpose taxonomy ready with differentiated
  weights per surface type
- **Con**: Dual schemas to maintain until reconciliation
- **Con**: Confusion risk for new contributors — mitigated by this ADR +
  YAML header comment added per R3-03

## Alternatives Considered

- **Refactor now**: Rejected — `surface_types` vs `visual_register` requires a
  design call (which taxonomy wins? or do we merge into a 2D matrix?). That
  decision is out of scope for D7 remediation.
- **Delete the YAML**: Rejected — it IS the right Phase-2 taxonomy; deleting
  forces redesign in Phase 2.
- **Convert `visual_register` → `surface_types` now**: Rejected — breaks 30+
  existing tests that pass `visual_register` values to `AxisWeights`.

## Status

Accepted 2026-05-21 per audit Run 2 P1-2.
Tracked for unification: F0221 (open at N3d integration).
