# Sprint Status

**Last updated**: 2026-05-21 D7 EOD UTC
**Current phase**: Phase 1 Foundation — mid-flight, executor-brief remediation active
**Active branch**: `phase/1` (7 commits)
**Active worktree**: `.worktrees/phase1-foundation/`
**Days to submission**: 13 (target 2026-06-03 noon, official deadline 2026-06-05)

---

## NEW SESSION? READ FIRST

1. **Executor brief**: [`audit/executor-brief.md`](../../audit/executor-brief.md) — 15 C-items to close before Phase 2 gate
2. **PRD**: [`docs/superpowers/specs/2026-05-14-atelier-prd.md`](../superpowers/specs/2026-05-14-atelier-prd.md) — 1100+ lines, the source of truth
3. **Sprint plan**: [`docs/superpowers/plans/2026-05-14-atelier-sprint-plan.md`](../superpages/plans/2026-05-14-atelier-sprint-plan.md)
4. **CLAUDE.md** at repo root — auto-loaded sprint invariants
5. **DECISIONS.md** at repo root — 13 locked decisions (0001-0013)

Then run the 90-second restoration ritual (in CLAUDE.md), then pick the next unblocked feature from `features.json`:

```bash
cat features.json | jq '.features[] | select(.passes == false) | {id, name, day}' | head -10
```

---

## D1-D7 Sprint Progress (2026-05-15 to 2026-05-21)

### What shipped (7 commits on phase/1)

| Commit                                     | SHA       | Features Closed                                     |
| ------------------------------------------ | --------- | --------------------------------------------------- |
| Foundation data contracts + API + Governor | `2720f71` | F0001a, F0001b, F0003, F0004, F0005, FA-001, FA-002 |
| Model registry + A2A + OTel spans          | `71a1c7e` | F0002, FA-005, FA-006, FA-007, FA-016               |
| Terraform IaC + BigQuery schema            | `cf396bb` | F0006, FA-008, FA-015                               |
| Stitch MCP wrapper                         | `a967567` | FA-003, FA-009, FA-010                              |
| 6 det gates + generator + axis weights     | `fe7fd96` | F0009, F0010, F0011, FA-018, FA-019                 |
| Trajectory recorder + DPO extraction       | `7b52e0f` | FA-011 (partial)                                    |
| Sprint research artifacts                  | `9b70317` | docs only                                           |

### Test suite

- **Baseline (D0)**: 0 tests
- **Current (D7)**: 177 tests passing (0.27s)
- **Coverage**: data contracts, brief spec, governor, model registry, OTel spans, stitch MCP, gates, generator, axis weights, constitution registry, trajectory

### What's blocked

- C1-C15 remediation items from executor-brief.md (audit gap closure)
- Phase 2 gated on executor-brief DONE token

### GCP infrastructure live

- BigQuery: 4 tables in `i-for-ai.atelier_trajectories` (trajectory_records, dpo_preference_pairs, calibration_metrics, cost_ledger)
- Terraform: IaC skeleton for 18 GCP APIs, 2 SAs, Artifact Registry, Cloud Run, KMS

---

## Phase progress

- [/] Phase 1: Foundation (W1, May 15-21) — 7/7 commits, 177 tests, remediation in progress
- [ ] Phase 2: 10x Mechanisms (W2, May 22-28) — not started
- [ ] Phase 3: Production Polish (W3, May 29 - Jun 4) — not started

## Active blockers

See [BLOCKERS.md](BLOCKERS.md) for current blockers (updated 2026-05-21).

## Cost at D7

- Estimated: ~$200 of $5K (4.0%)
- Cache-hit-rate: data not available (no prefix-cache instrumentation in place)
- D7 daily: ~$40 estimated (Opus subagent + Antigravity IDE)

## Next session first task

F0023 — N3d ConsensusAgent skeleton (depends on C3 axis_weights + C4 research-trust YAML being closed first)

Suggested model tier: implementer-novel
Dependencies satisfied: yes (after C-item remediation)
