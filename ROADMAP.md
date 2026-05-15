# Roadmap

> **Three-week sprint to public launch on 2026-06-03 + Google for Startups AI Agents Challenge 2026 submission.**

## Sprint window

**Start**: 2026-05-15 (Wed)
**Internal target**: 2026-06-03 (Mon) noon — submission filed early
**Official deadline**: 2026-06-05 (Wed)
**Build budget**: $5K Claude Opus 4.7 MAX capacity via Vertex AI

---

## Phase 1: Foundation (W1, May 15-21)

Repo bootstrap, ADK plumbing, single-surface end-to-end, Cloud Run staging deploy.

**Worktree**: `.worktrees/phase1-foundation/` on branch `phase/1`.

| Day               | Deliverable                                                                                      |
| ----------------- | ------------------------------------------------------------------------------------------------ |
| **D1** Wed May 15 | Repo bootstrap, full SDLC docs, first 3 ADRs, CI green on first commit                           |
| **D2** Thu May 16 | GCP project + Terraform foundation; quota requests filed                                         |
| **D3** Fri May 17 | Port `agent-dag-pipeline` ADK plumbing (lockfile-pinned consume, not fork)                       |
| **D4** Sat May 18 | N1 Brief Parser + N2 Source Resolver + Pydantic v2 frozen data contracts                         |
| **D5** Sun May 19 | N3a Generator (Stitch MCP) + Apigee cost router                                                  |
| **D6** Mon May 20 | N3c Deterministic Gate (parallel × 6 axes) + EvoDesign skeleton K=3                              |
| **D7** Tue May 21 | **Phase 1 Gate**: end-to-end on `pipeline-observatory/index.html`; CI green; deployed to staging |

**Acceptance criteria** (all must pass to tag `phase1-accepted`):

- 1 surface converges end-to-end (PIP → 5 questions → BriefSpec → Generator → Gate → stub Judge → Final Validator → A2UI React render)
- Cloud Run deployment of API + Agent jobs working
- OTel + Cloud Trace functional
- BigQuery trajectory ingest working
- 50/484 WebGen-Bench task subset passing in CI
- README + ROADMAP + first 5 ADRs complete

**Cost target**: $1,200 of $5K (24%).

---

## Phase 2: 10× Mechanisms (W2, May 22-28)

EvoDesign + ConsensusAgent + Campaign Orchestrator + PIP + 12-surface autonomous campaign.

**Worktree**: `.worktrees/phase2-10x-mechanisms/` on branch `phase/2` (created when phase/1 accepted).

| Days                  | Focus                                                                                                                                                  |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **May 22-23** Wed-Thu | N3b CSC-D + EvoDesign full (K=6, 6 mutation operators) + N3e Fixer/Hebbian via `adk optimize`                                                          |
| **May 24-25** Fri-Sat | N3d ConsensusAgent + 5 specialized judges + DEMAS-D Provenance Matrix                                                                                  |
| **May 26** Sun        | N12 Campaign Orchestrator + Surface Manifest + Cross-Surface Coherence Validator                                                                       |
| **May 27** Mon        | N13 PIP + 13-question catalog + BriefSpec immutability + skip-path resolver                                                                            |
| **May 28** Tue        | **Phase 2 Gate**: closed beta (5 invited tenants), full 484-task WebGen-Bench eval published, 12-surface autonomous campaign on `pipeline-observatory` |

**Acceptance criteria** (all must pass to tag `phase2-accepted`):

- 12-surface autonomous campaign converges end-to-end without human intervention
- WebGen-Bench full eval ≥ 51 (matching SOTA)
- Calibration dashboard live at calibration.atelier.dev with first-week data
- All 4 A2UI renderers working (React + Flutter + Lit + Angular)
- Telegram + CLI + web UI all working
- 5 beta tenants signed in via Identity Platform
- Privacy policy + ToS published (legal-template draft)
- Status page live
- Documentation 90% complete

**Cost target**: $2,500 of $5K cumulative (50%).

---

## Phase 3: Production Polish + 10× Validation (W3, May 29 - Jun 4)

Per-project judge LoRA fine-tune, Open Eval Adapters, Skills Pack, marketing site, arXiv preprint, demo recording, submission package.

**Worktree**: `.worktrees/phase3-production-polish/` on branch `phase/3` (created when phase/2 accepted).

| Days                  | Focus                                                                                                                                          |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **May 29-30** Wed-Thu | DPO + LoRA pipeline wired (Vertex AI Tuning + Endpoints + Multi-Tuning + Gemma 4 26B-A4B-it base); first-project LoRA fine-tuned as demo proof |
| **May 31** Fri        | N9 Open Eval Adapters (5 benchmarks) + N10 Convergence Spec RFC v0.1 + N11 Public scoreboard                                                   |
| **Jun 1** Sat         | Atelier Skills Pack (6 skills) + atelier-action (GitHub Marketplace) + Figma plugin + Chrome extension + npm constitution package              |
| **Jun 2** Sun         | Marketing site + waitlist (target ≥500 signups) + Loom walkthrough + arXiv preprint + designer-in-residence testimonials (target ≥3)           |
| **Jun 3** Mon         | **Phase 3 Gate / v1.0.0 release / G4S submission filed early**                                                                                 |
| **Jun 4** Tue         | Final eval run + final smoke test on staging + prod; CHANGELOG updated; release v1.0.0 tagged                                                  |
| **Jun 5** Wed         | Official deadline — already submitted, available for live office hours                                                                         |

**Acceptance criteria** (all must pass to tag `v1.0.0`):

- WebGen-Bench full eval published (target ≥ 60, stretch ≥ 77 with first-project LoRA)
- All 13 novel contributions have evidence in `atelier-eval/data/results/`
- All 32 pre-launch artifacts live (see [Pre-Launch Checklist](docs/superpowers/specs/2026-05-14-atelier-prelaunch-checklist.md))
- Public sign-up live, freemium tier active
- 4-min demo video + 2-min backup + 60-sec elevator pitch recorded
- arXiv preprint draft submitted
- ≥3 designer-in-residence testimonials captured
- ≥500 waitlist signups
- Co-marketing 1-pager sent to Google Cloud DA
- G4S submission package filed by Jun 3 noon

**Cost target**: $5K of $5K cumulative (100%).

---

## Post-launch (Jun 5+)

| Version  | Target        | What it adds                                                                                                        |
| -------- | ------------- | ------------------------------------------------------------------------------------------------------------------- |
| `v1.1.0` | Jun 12        | Multiplayer dashboard annotation, voice input parity (Stitch "vibe design"), Discord community launch               |
| `v1.2.0` | Jul           | Full N9 adapter suite (all 5 benchmarks), Convergence Spec RFC v0.2 (community-reviewed), additional Atelier Skills |
| `v1.3.0` | Aug           | Sketch-to-UI dedicated upload, multi-region active-active failover (US + EU), additional A2UI renderers             |
| `v2.0.0` | Dec (month 6) | SOC 2 Type 2 certification, per-tenant CMEK on Cloud Run path, HIPAA tier, ISO 27001 evidence collection            |
| `v3.0.0` | TBD           | Federated learning across tenants with differential privacy, cross-project pattern transfer at scale                |

---

## Long-term vision

Atelier becomes the **standard evaluation surface for the entire UI-generation field** (`bench.atelier.dev`), the **reference implementation of the Convergence Spec** (community-driven RFC), and the **canonical example of Anthropic's long-running-agent harness applied to a domain-specific autonomous agent**. Trajectory data is the compounding moat — never open-sourced; agent core is Apache-2.0 and freely forkable.

By end of 2026:

- 10K+ active projects on the platform
- 100K+ trajectories collected
- ≥3 third-party benchmarks adopt Atelier's eval-set adapters
- ≥1 published paper (NeurIPS D&B or ICLR or CHI) drawing on Atelier's data
- ≥5 Atelier Skills published by community contributors
- ≥1 Google Cloud case study featuring Atelier
