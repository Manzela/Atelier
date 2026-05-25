# Sprint Status

**Last updated**: 2026-05-25 D14 UTC
**Current phase**: Phase 2 — 10x Mechanisms + GCP deployment complete
**Active branch**: `phase/2`
**Active worktree**: `.worktrees/phase2-consensus-agent/`
**Days to submission**: 9 (target 2026-06-03 noon, official deadline 2026-06-05)

---

## NEW SESSION? READ FIRST

1. **PRD**: [`docs/superpowers/specs/2026-05-14-atelier-prd.md`](../superpowers/specs/2026-05-14-atelier-prd.md) — 1100+ lines, the source of truth
2. **D14 Actions**: [`docs/sprint/D14-daniel-actions.md`](D14-daniel-actions.md) — GCP deployment completed
3. **CLAUDE.md** at repo root — auto-loaded sprint invariants
4. **DECISIONS.md** at repo root — 13 locked decisions (0001-0013)

Then run the 90-second restoration ritual (in CLAUDE.md), then pick the next unblocked feature from `features.json`:

```bash
cat features.json | jq '.features[] | select(.passes == false) | {id, name, day}' | head -10
```

---

## D14 Status — GCP Infrastructure Deployed

### Infrastructure live (atelier-build-2026)

| Resource                          | Status                                                                      |
| --------------------------------- | --------------------------------------------------------------------------- |
| Cloud Run (`atelier-api-staging`) | ✅ Serving — `https://atelier-api-staging-537337457799.us-central1.run.app` |
| `/health` endpoint                | ✅ HTTP 200 `{"status":"healthy"}`                                          |
| BigQuery (`atelier_trajectories`) | ✅ 4 tables provisioned                                                     |
| Secret Manager                    | ✅ `atelier-geap-api-key` migrated from `i-for-ai`                          |
| Artifact Registry                 | ✅ `atelier-images` repo with API image                                     |
| Service Accounts                  | ✅ `atelier-runtime@` + `atelier-api-sa@`                                   |
| Branch Protection                 | ✅ 7 required checks on `phase/1`                                           |

### Test suite

- **D7 (Phase 1)**: 249 tests
- **D11 (Phase 2)**: 504 tests (50 xfailed)
- **D14 (Current)**: 509 tests passing, 50 xfailed, 0 failures

### Commits on phase/2 (D11-D14)

| SHA       | Description                                          |
| --------- | ---------------------------------------------------- |
| `ffc6060` | R9-B audit: spans API + lint sweep + spec compliance |
| `7038186` | D14: GCP deployment record + UIBench gate removed    |
| `598b7d5` | deps: add google-adk and google-cloud-secret-manager |

---

## Phase progress

- [x] Phase 1: Foundation (W1, May 15-21) — 7 commits, 249 tests, executor-brief closed
- [/] Phase 2: 10x Mechanisms (W2, May 22-28) — GCP deployed, consensus agent active
- [ ] Phase 3: Production Polish (W3, May 29 - Jun 4) — not started

## Active blockers

See [BLOCKERS.md](BLOCKERS.md) for current blockers.

## Cost estimate

- Estimated: ~$400 of $5K (8.0%)
- Includes: Opus orchestrator + Antigravity IDE + Vertex AI inference

## Next session first task

Continue Phase 2 feature implementation — pick next unblocked feature from `features.json`.
