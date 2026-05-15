# Sprint Cost Ledger

> Per Strategy v2: daily check. Updated end-of-session. Cache-hit-rate watch column flags prefix drift.

**Budget**: $5,000 Claude Opus 4.7 MAX via Vertex AI
**Sprint window**: 2026-05-15 → 2026-06-04 (21 days)
**Linear daily target**: $238/day
**2× spike days allowed; not sustained**

---

## Daily ledger

| Date       | Tokens In | Tokens Out | Cost USD | Cumulative | Burn vs $5K | Cache-Hit % | Notes                                              |
| ---------- | --------- | ---------- | -------- | ---------- | ----------- | ----------- | -------------------------------------------------- |
| 2026-05-14 | ~1.5M     | ~150K      | ~$50     | $50        | 1.0%        | n/a         | Pre-sprint PRD + scaffold (no subagents yet)       |
| 2026-05-15 | TBD       | TBD        | TBD      | TBD        | TBD         | TBD         | D1: GCP setup, push to GitHub, file quota requests |

(Future days appended D1+.)

---

## Phase summaries (updated at each phase gate)

### Phase 1 Foundation (W1, May 15-21) target: $1,200

| Metric                      | Target    | Actual |
| --------------------------- | --------- | ------ |
| Total cost                  | ≤ $1,200  | TBD    |
| Cache-hit-rate              | ≥ 85%     | TBD    |
| Subagent dispatches         | ~50       | TBD    |
| Opus / Sonnet / Haiku ratio | 30/50/20% | TBD    |

### Phase 2 10× Mechanisms (W2, May 22-28) target: $2,500 cumulative

(Filled at end of W2.)

### Phase 3 Production Polish (W3, May 29 - Jun 4) target: $5,000 cumulative

(Filled at end of W3.)

---

## Triggered cost actions

### Cache-hit-rate < 85% → investigate prefix drift

If cache-hit-rate drops below 85% for any day, the cached prefix is drifting. Common causes:

- A per-request value (timestamp, session ID) crept into the cached block
- ADRs grew faster than DECISIONS.md was updated
- New PRD section added without re-tagging the cache breakpoint

Action: locate the drift, restore the stable prefix, re-verify with the next subagent dispatch.

### Daily burn > $400 sustained → reduce subagent dispatch volume

If three consecutive days exceed $400 (>2× linear target), pause. Triage:

1. Which subagent class is over-budget?
2. Can it move from Opus → Sonnet → Haiku for routine work?
3. Is the prefix cached on every dispatch?
4. Is any subagent stuck in a loop?

Action: downgrade routine work to Sonnet; extend cache TTL; tighten subagent token budget.

### Vertex AI 429 rate (5min) > 20% → check quota + Provisioned Throughput

If Vertex AI is throttling > 20% of calls in any 5-minute window, hit quota ceiling.

Action: file Provisioned Throughput request; switch high-stakes calls to alternate region (europe-west4 fallback); for low-stakes work, route to Sonnet 4.6 (separate quota pool).
