# Sprint Roadmap

> Day-by-day for week 1, week-by-week for weeks 2-3. Mirrors and elaborates the top-level [ROADMAP.md](../../ROADMAP.md).

For the comprehensive sprint plan with feature decomposition, see `docs/superpowers/plans/2026-05-14-atelier-sprint-plan.md` (output of writing-plans skill, generated D1).

---

## Sprint window: 2026-05-15 → 2026-06-04

**Submission target**: 2026-06-03 noon (2 days early)
**Official deadline**: 2026-06-05

---

## Week 1: Foundation (May 15-21)

| Day    | Date       | Worktree  | Focus                                                                                                                                           | Gate                                                                     |
| ------ | ---------- | --------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| **D1** | Wed May 15 | `phase/1` | Repo bootstrap, GCP + quota requests, first 3 ADRs in worktree, CI green on first phase commit                                                  | CI green                                                                 |
| **D2** | Thu May 16 | `phase/1` | Terraform foundation; Identity Platform + Apigee + Cloud Run + Vertex AI + Memory Bank + Vector Search + BigQuery + KMS + Monitoring modules    | `terraform plan` clean in staging                                        |
| **D3** | Fri May 17 | `phase/1` | Port `agent-dag-pipeline` ADK plumbing (lockfile-pinned, NEVER modify upstream); 8 GateAgent unit tests pass                                    | `pytest tests/unit/adk/` 8/8                                             |
| **D4** | Sat May 18 | `phase/1` | N1 Brief Parser + N2 Source Resolver + Pydantic v2 frozen data contracts                                                                        | N1 + N2 nodes pass acceptance criteria                                   |
| **D5** | Sun May 19 | `phase/1` | N3a Generator (Stitch MCP via MCPToolset) + Apigee cost router                                                                                  | Generation success ≥ 95% on 20 fixture briefs                            |
| **D6** | Mon May 20 | `phase/1` | N3c Deterministic Gate (parallel × 6 axes) + EvoDesign skeleton K=3                                                                             | Gate runs all 6 axes in parallel                                         |
| **D7** | Tue May 21 | `phase/1` | **Phase 1 Gate**: 1-surface end-to-end on `pipeline-observatory/index.html`; Cloud Run staging deploy; OTel + Cloud Trace + BigQuery functional | Phase 1 acceptance protocol passes; tag `phase1-accepted`; merge to main |

---

## Week 2: 10× Mechanisms (May 22-28)

| Days                  | Worktree  | Focus                                                                                                                                                                                               |
| --------------------- | --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **May 22-23** Wed-Thu | `phase/2` | N3b CSC-D + EvoDesign full (K=6, 6 mutation operators) + N3e Fixer/Hebbian via `adk optimize` (GEPA)                                                                                                |
| **May 24-25** Fri-Sat | `phase/2` | N3d ConsensusAgent + 5 specialized judges + DEMAS-D Provenance Matrix                                                                                                                               |
| **May 26** Sun        | `phase/2` | N12 Campaign Orchestrator + Surface Manifest + Cross-Surface Coherence Validator + Cloud Scheduler + Cloud Tasks                                                                                    |
| **May 27** Mon        | `phase/2` | N13 PIP + 13-question catalog + BriefSpec immutability + skip-path resolver                                                                                                                         |
| **May 28** Tue        | `phase/2` | **Phase 2 Gate**: 12-surface autonomous campaign on `pipeline-observatory`; WebGen-Bench full eval ≥ 51; calibration dashboard live; 5 beta tenants signed in; tag `phase2-accepted`; merge to main |

---

## Week 3: Production Polish + 10× Validation (May 29 - Jun 4)

| Days                  | Worktree  | Focus                                                                                                                                          |
| --------------------- | --------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **May 29-30** Wed-Thu | `phase/3` | DPO + LoRA pipeline wired (Vertex AI Tuning + Endpoints + Multi-Tuning + Gemma 4 26B-A4B-it base); first-project LoRA fine-tuned as demo proof |
| **May 31** Fri        | `phase/3` | N9 Open Eval Adapters (≥3 of 5 benchmarks) + N10 Convergence Spec RFC v0.1 + N11 Public scoreboard live                                        |
| **Jun 1** Sat         | `phase/3` | Atelier Skills Pack (6 skills) + atelier-action published to GitHub Marketplace + Figma plugin + Chrome extension + npm constitution package   |
| **Jun 2** Sun         | `phase/3` | Marketing site + waitlist (≥500 signups) + Loom walkthrough + arXiv preprint draft + designer-in-residence testimonials (≥3)                   |
| **Jun 3** Mon         | `phase/3` | **Phase 3 Gate / v1.0.0 release / G4S submission filed early at noon**                                                                         |
| **Jun 4** Tue         | `main`    | Final eval run + final smoke test + CHANGELOG updated; release `v1.0.0` tagged + pushed                                                        |
| **Jun 5** Wed         | —         | Official deadline — submission already filed; available for live demo office hours via Calendly                                                |

---

## Cost milestones

| Milestone | Cumulative target    | Actual |
| --------- | -------------------- | ------ |
| End W1    | $1,200 of $5K (24%)  | TBD    |
| End W2    | $2,500 of $5K (50%)  | TBD    |
| End W3    | $5,000 of $5K (100%) | TBD    |

---

## Phase acceptance tags

| Tag               | When                | Evidence                                                                                   |
| ----------------- | ------------------- | ------------------------------------------------------------------------------------------ |
| `phase1-accepted` | end of D7 (May 21)  | 1-surface end-to-end + CI green + staging deploy                                           |
| `phase2-accepted` | end of D14 (May 28) | 12-surface campaign + WebGen-Bench ≥ 51 + 5 beta tenants                                   |
| `v1.0.0`          | end of D20 (Jun 3)  | All 13 novel contributions evidenced + 32 pre-launch artifacts live + G4S submission filed |
