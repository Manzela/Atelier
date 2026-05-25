# 0027. Phase-Aware Mixture-of-Experts Router

**Status:** Accepted
**Date:** 2026-05-21
**Decision-makers:** Daniel Manzela (Principal Architect), Atelier sprint

## Context

The 8-node DAG (Brief Parse → Intent Schema → Surface Plan → Generate Candidates
→ Judge Candidates → Select Winner → Polish → Emit) previously routed every node
to a single model. This wastes 30-50× cost on deterministic-gate phases
(BRIEF_PARSE, INTENT_SCHEMA, EMIT) where a flash-lite model meets the latency
and accuracy bar set by the §13.1 Phase 1 Gate.

Spec §18 mandates a Phase-Aware MoE Router so each DAG phase dispatches to the
cheapest expert meeting the per-phase quality floor. Without phase awareness the
§11.3 DevPost demo cannot credibly claim Optimize-pillar usage, because
cost-per-intent is dominated by avoidable Pro spend on non-reasoning phases.

## Decision

Adopt a three-version progression defined by a single `PhaseAwareMoERouter`
Protocol with two async methods:

```python
async def route(self, request: RouteRequest) -> RouteDecision: ...
async def observe_outcome(self, *, decision, achieved_score, ...) -> None: ...
```

**Phase 1 — `ManagedRoutingRouter` (static table, ships D9):**

| DAGPhase            | Expert                | Rationale                                          |
| ------------------- | --------------------- | -------------------------------------------------- |
| BRIEF_PARSE         | GEMINI_3_FLASH        | Deterministic JSON extraction; flash is sufficient |
| INTENT_SCHEMA       | GEMINI_3_1_FLASH_LITE | Schema validation; lightest model meets the bar    |
| SURFACE_PLAN        | GEMINI_3_FLASH        | Plan generation; flash meets quality floor         |
| GENERATE_CANDIDATES | budget-gated (below)  | K=6 candidates; budget-aware selection             |
| JUDGE_CANDIDATES    | GEMINI_2_5_PRO        | Multi-axis composite judge needs strong reasoning  |
| SELECT_WINNER       | GEMINI_3_1_FLASH_LITE | Argmax; deterministic                              |
| POLISH              | GEMINI_3_FLASH        | Surface revision; flash is sufficient              |
| EMIT                | GEMINI_3_1_FLASH_LITE | Final serialization; deterministic                 |

GENERATE_CANDIDATES budget gate:

- `cost_budget_remaining_usd < 0.50` → GEMINI_3_1_FLASH_LITE (cost-degraded tier)
- `cost_budget_remaining_usd ≥ 0.50` → GEMINI_3_FLASH

Cost map (USD per 1 000 input tokens, live pricing 2026-05-21, source-of-truth
in `infra/pricing/vertex-2026-05.json`, refreshed monthly):

| Expert                | Input/1K |
| --------------------- | -------- |
| GEMINI_3_PRO          | $0.00200 |
| GEMINI_3_FLASH        | $0.00050 |
| GEMINI_3_1_FLASH_LITE | $0.00025 |
| GEMINI_2_5_PRO        | $0.00125 |
| GEMINI_2_5_FLASH      | $0.00030 |

**Phase 2 — `BanditRoutingRouter` (ε-greedy MAB, Task 13):**
Arms = (phase, expert) pairs. BigQuery-backed posterior. ε-greedy
(ε_start=0.10, ε_floor=0.02, 7-day exponential decay). UCB1 fallback for
cold-start arms (< 10 pulls).

**Phase 2 stretch — `MatrixFactorizationRouter` (T14):**
RouteLLM-style matrix factorization trained on Atelier DPO pairs.

All three implementations satisfy the same Protocol; the DAG orchestrator is
agnostic to which router is wired in.

## Consequences

### Positive

- 30-50× cost reduction on the 6 non-judge phases vs. all-Pro baseline.
- Single Protocol seam: router swap is a one-line change in the DI binding.
- Phase 2 bandit learns from trajectory data without changing any DAG node.
- Demo narrative §11.3: "6 of 8 DAG phases route to flash or flash-lite;
  WebGen-Bench data shows zero accuracy regression on those phases."

### Negative

- Static table is brittle to model deprecations. Mitigation: cost map and
  routing table are `Final[dict]`; deprecation requires an ADR amendment.
- Bandit introduces routing non-determinism. Mitigation: all decisions logged
  to OTel + BigQuery for deterministic replay.

### Neutral

- Cost telemetry needs a per-phase pivot in BigQuery COST_LEDGER (already
  tracked in the cost-ledger schema as the `phase` column).

## Alternatives considered

**Option A: Single Pro model for all phases.**
Pros: simplest. Cons: 30-50× cost ceiling pushes past the $1,200 Phase 1
budget by D10. **Rejected — cost-prohibitive.**

**Option B: Vertex `GenerationConfigRoutingConfig` (managed).**
Pros: zero code. Cons: intent-level routing cannot express "JUDGE → Pro,
EMIT → Flash-Lite." **Rejected — wrong abstraction level.**

**Option C: RouteLLM matrix factorization for Phase 1.**
Pros: SOTA per RouteLLM 2024 paper. Cons: requires labeled (prompt, model-score)
training data we do not have in Phase 1. **Deferred to Phase 2 stretch (T14).**

## References

- Spec: `docs/superpowers/specs/2026-05-21-post-r4-strategic-roadmap-design.md` §18
- Plan: Task 3 (T3 Protocol), Task 13 (v1 Bandit)
- Protocol: `atelier-core/src/atelier/router/protocol.py`
- v0 implementation: `atelier-core/src/atelier/router/v0_managed.py`
- Pricing source: `infra/pricing/vertex-2026-05.json` (live 2026-05-21)
