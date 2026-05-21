# Atelier — Full Locked Scope & Expected Production State

> Synthesized from: [PRD](file:///Users/danielmanzela/Professional%20Profile/Atelier/docs/superpowers/specs/2026-05-14-atelier-prd.md) · [features.json](file:///Users/danielmanzela/Professional%20Profile/Atelier/features.json) · [ROADMAP.md](file:///Users/danielmanzela/Professional%20Profile/Atelier/ROADMAP.md) · [DECISIONS.md](file:///Users/danielmanzela/Professional%20Profile/Atelier/DECISIONS.md) · [REJECTED.md](file:///Users/danielmanzela/Professional%20Profile/Atelier/REJECTED.md) · [Sprint docs](file:///Users/danielmanzela/Professional%20Profile/Atelier/docs/sprint)

---

## 1. What Atelier Is

**Atelier** is an autonomous design agent — the **first** that asks the right questions, converges on flawless UI/UX across multi-axis judged criteria, and gets sharper with every iteration. The tagline: **"Stitch generates. Atelier asks, converges, learns."**

**Target**: Google for Startups AI Agents Challenge 2026 ($90K prize pool)
**Sprint**: 2026-05-15 → 2026-06-04 (21 days, 3 phases)
**Submission**: 2026-06-03 noon (2 days early)
**Budget**: $5K Claude Opus 4.7 MAX via Vertex AI
**License**: Apache-2.0
**Repo**: `github.com/Manzela/atelier`

---

## 2. The End-Goal Vision

Atelier becomes:

1. The **standard evaluation surface** for the entire UI-generation field (`bench.atelier.dev`)
2. The **reference implementation** of the Convergence Spec (community-driven RFC)
3. The **canonical example** of Anthropic's long-running-agent harness applied to a domain-specific autonomous agent

**By end of 2026**: 10K+ active projects, 100K+ trajectories, ≥3 third-party benchmarks adopt Atelier's eval-set adapters, ≥1 published paper, ≥5 community-contributed Skills, ≥1 Google Cloud case study.

---

## 3. The 10× Thesis (7 Quantified Axes)

| #   | Axis                                           | MVP Target                                                    | Baseline (competitors)              |
| --- | ---------------------------------------------- | ------------------------------------------------------------- | ----------------------------------- |
| 1   | **Convergence quality at first declared-done** | ≥95% (Lighthouse ≥90, axe=0, visual-diff ≤2%, responsive 4bp) | ~0% (no tool gates)                 |
| 2   | **Iterations to convergence**                  | ≤3 autonomous loops                                           | 5-10 (Reflexion) / 80+ (commercial) |
| 3   | **Human-in-loop time**                         | ≤60 sec to gate-passing output                                | 5-15 min per page                   |
| 4   | **Cross-session pattern reuse**                | ≥60% after 100 sessions                                       | 0% (no competitor does this)        |
| 5   | **WebGen-Bench**                               | ≥51.4 (match SOTA); stretch ≥77 with LoRA                     | SOTA 51.9%                          |
| 6   | **First-shot convergence**                     | ≥40% (with PIP)                                               | ~5-15% commercial                   |
| 7   | **Campaign convergence**                       | ≥85% on 12-surface, ≥70% on 50-surface                        | ~0% (no competitor)                 |

---

## 4. The 15 Novel Contributions (Locked)

| #       | Name                      | What it is                                                                                               |
| ------- | ------------------------- | -------------------------------------------------------------------------------------------------------- |
| **N1**  | **DGF-D2C**               | Deterministic-Gate-First Design-to-Convergence — zero-LLM O(1) gates fire before any probabilistic agent |
| **N2**  | **DEMAS-D**               | Per-axis Provenance Matrix Design Judge — each axis sees ONLY its relevant ground-truth variables        |
| **N3**  | **PerJudge**              | Per-Project DPO Judge + Hebbian Prompt Mutator + Few-Shot Cold-Start — LoRA fine-tunes per project       |
| **N4**  | **PADI**                  | Project-Agnostic Descriptor Inference — adapts to any tech stack                                         |
| **N5**  | **EvoDesign**             | AlphaEvolve-inspired K=6 evolutionary candidate search                                                   |
| **N6**  | **CSC-D**                 | Constitutional Self-Critique for Design — 12-principle Apple-Grade constitution                          |
| **N7**  | **A2UI-Native**           | Renders to A2UI v0.9 natively (React + Flutter + Lit + Angular)                                          |
| **N8**  | **Calibration Dashboard** | `calibration.atelier.dev` — public judge calibration transparency                                        |
| **N9**  | **Open Eval Adapters**    | Apache-2.0 PRs to `google/adk-python` for 5 benchmarks                                                   |
| **N10** | **Convergence Spec RFC**  | Open standard for convergence criteria declaration                                                       |
| **N11** | **Open Eval Harness**     | `bench.atelier.dev` — public leaderboard accepting any agent                                             |
| **N12** | **RLRD**                  | Recursive Long-Running Discipline — ships what it uses to be built                                       |
| **N13** | **PIP**                   | Pre-Generation Intake Protocol — 13-question adaptive intake mapped to DAPLab's 9 failure patterns       |
| **N14** | **WRAI**                  | Web-Research-Augmented Intake — Vertex AI Search Grounding before BriefSpec lock                         |
| **N15** | **MJG**                   | Metastrategic Judging Gap — BriefSpec-conditional per-axis weighting                                     |

---

## 5. Three-Layer Architecture (Locked)

```
┌─────────────────────────────────────────────────────────┐
│ Layer 3: PIP (Pre-Generation Intake Protocol)            │
│   Adaptive Q&A (2-15 questions) → WRAI research →       │
│   Immutable BriefSpec.json                               │
└──────────────────┬──────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Layer 2: Campaign Orchestrator (RLRD)                    │
│   CampaignBrief → Surface Manifest → Picker →           │
│   Cross-Surface Coherence Validator → Checkpoint Writer  │
└──────────────────┬──────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────┐
│ Layer 1: Atomic 8-Node DAG (per-surface)                 │
│   N1 Brief Parser → N2 Source Resolver →                 │
│   N3 EvoDesign Loop:                                     │
│     N3a Generator (K=6, Stitch MCP) →                    │
│     N3b CSC-D (self-critique) →                          │
│     N3c Det Gate (6 axes parallel) →                     │
│     N3d ConsensusAgent (5 judges, Bayesian) →            │
│     N3e Fixer (Hebbian mutator)                          │
│   → N4 Final Validator + A2UI Renderer                   │
└─────────────────────────────────────────────────────────┘
```

### Deterministic Gate Axes (Layer 1, N3c)

1. Lighthouse a11y/perf/best-practices ≥ 90
2. axe-core WCAG2AA = 0 violations
3. Token-fidelity grep (hex/font/spacing within DESIGN.md)
4. Semantic-HTML linter (html-validate)
5. Playwright visual-diff ≤ 2%
6. Responsive snapshot at 375/768/1280/1920

### ConsensusAgent Judges (Layer 1, N3d)

1. **Brand** judge (rubric-based, LoRA upgradeable)
2. **Copy** judge (voice rubric)
3. **Motion** judge (prefers-reduced-motion)
4. **Token-fidelity** judge (DESIGN.md compliance)
5. **Cross-screen coherence** judge (pattern reuse)

### D-O-R-A-V Design Rubric

| Axis           | Floor | Model                      |
| -------------- | ----- | -------------------------- |
| Brand-fidelity | 0.7   | Gemini 3 Flash + LoRA      |
| Originality    | 0.6   | Gemini 3 Flash             |
| Relevance      | 0.7   | Gemini 3 Flash + LoRA      |
| Accessibility  | 0.8   | Det gate + Gemini 3 Flash  |
| Visual-clarity | 0.7   | Gemini 3 Flash + embedding |

---

## 6. 13 Locked Architectural Decisions (ADRs)

| #    | Decision                                          | Rationale                               |
| ---- | ------------------------------------------------- | --------------------------------------- |
| 0001 | Wrap-don't-fork (agent-dag-pipeline, ADK, hermes) | Preserve upgrade paths                  |
| 0002 | Cloud Run jobs, NOT Agent Engine for runtime      | Sessions billing $43K/mo at scale       |
| 0003 | 5-tier sandboxing                                 | Risk-appropriate isolation              |
| 0004 | PIP as first-class layer                          | ≥40% first-shot convergence             |
| 0005 | RLRD — ship what you use                          | Dogfood discipline                      |
| 0006 | Google-native stack only                          | No Langfuse/Statsig/PostHog/GKE/LiteLLM |
| 0007 | Worktree-per-phase branching                      | Phase isolation                         |
| 0008 | Multi-judge Bayesian consensus                    | 5 judges + DEMAS-D Provenance           |
| 0009 | Public calibration dashboard                      | Transparency commitment                 |
| 0010 | A2UI v0.9 as output protocol                      | React + Flutter + Lit + Angular         |
| 0011 | WRAI — research-augmented intake                  | N14                                     |
| 0012 | Anchor Discipline — BriefSpec everywhere          | Every subagent sees BriefSpec           |
| 0013 | Conditional axis weighting (MJG)                  | N15                                     |

---

## 7. Google-Native Tech Stack (Locked, No Sprawl)

```
Identity Platform → Apigee AI Gateway → Cloud Armor
    ↓
Atelier API (Cloud Run, FastAPI)
    ↓
Atelier Agent (Cloud Run jobs, ADK 2.0 Beta)
    ↓
├── Vertex Memory Bank (cross-session)
├── Firestore (hot UI state)
├── Vertex Vector Search 2.0 (pattern recall)
├── BigQuery + GCS (trajectories, KMS)
├── Vertex AI Tuning (SFT + DPO)
├── Vertex AI Endpoints + Multi-Tuning (LoRA serving)
├── Stitch MCP (UI generation)
├── Cloud Trace + Monitoring + Logging + Vertex AI Studio Tracing
├── Firebase (Remote Config, Hosting, Analytics, GA4)
├── Cloud Scheduler + Cloud Tasks
└── Cloud KMS (encryption)
    ↓
Stripe (billing) + Telegram (async tasks + approvals)
```

**Only 2 non-Google components**: Stripe + Telegram

---

## 8. Feature Inventory & Sprint Progress

### Totals

| Category             | Count        |
| -------------------- | ------------ |
| **Total features**   | 205          |
| **P0 (must ship)**   | 200          |
| **P1 (post-launch)** | 5            |
| **Completed**        | 1/205 (0.5%) |

### Per-Phase Breakdown

| Phase       | Description                            | Features | Completed | Status         |
| ----------- | -------------------------------------- | -------- | --------- | -------------- |
| **Phase 0** | Pre-Sprint Bootstrap                   | 1        | 1 ✅      | Complete       |
| **Phase 1** | Foundation (W1, May 15-21)             | 54       | 0         | ⚠️ Not started |
| **Phase 2** | 10× Mechanisms (W2, May 22-28)         | 87       | 0         | Blocked by P1  |
| **Phase 3** | Production Polish (W3, May 29 - Jun 4) | 60       | 0         | Blocked by P2  |
| **Phase 4** | Launch Day (Jun 5)                     | 3        | 0         | Blocked by P3  |

> [!IMPORTANT]
> As of 2026-05-20, Atelier is **6 days into the sprint** with only the pre-sprint bootstrap completed (1/205 features). The sprint plan assumed Phase 1 would complete by May 21. The project is significantly behind schedule — no phase/1 worktree has been created, no source code exists yet.

---

## 9. Phase Gate Acceptance Criteria (Locked)

### Phase 1 Gate (by May 21) — 7 criteria

- [ ] 1 surface converges end-to-end (PIP → BriefSpec → Generator → Gate → Judge → Validator → A2UI)
- [ ] Cloud Run deployment working
- [ ] OTel + Cloud Trace functional
- [ ] BigQuery trajectory ingest working
- [ ] 50/484 WebGen-Bench subset passing in CI
- [ ] README + ROADMAP + first 5 ADRs complete
- [ ] Cost ≤ $1,200 of $5K (24%)

### Phase 2 Gate (by May 28) — 9 criteria

- [ ] 12-surface autonomous campaign converges without human intervention
- [ ] WebGen-Bench full eval ≥ 51
- [ ] Calibration dashboard live at calibration.atelier.dev
- [ ] All 4 A2UI renderers working (React + Flutter + Lit + Angular)
- [ ] Telegram + CLI + web UI all working
- [ ] 5 beta tenants signed in via Identity Platform
- [ ] Privacy policy + ToS published
- [ ] Status page live
- [ ] Documentation 90% complete
- [ ] Cost ≤ $2,500 of $5K (50%)

### Phase 3 Gate / v1.0.0 Release (by Jun 3) — 11 criteria

- [ ] WebGen-Bench ≥ 60 (stretch ≥ 77 with LoRA)
- [ ] All 15 novel contributions evidenced in `atelier-eval/data/results/`
- [ ] All 32 pre-launch artifacts live
- [ ] Public sign-up live, freemium tier active
- [ ] 4-min demo video + 2-min backup + 60-sec elevator pitch
- [ ] arXiv preprint submitted
- [ ] ≥3 designer-in-residence testimonials
- [ ] ≥500 waitlist signups
- [ ] Co-marketing 1-pager sent to Google Cloud DA
- [ ] G4S submission package filed by Jun 3 noon
- [ ] Cost ≤ $5K

---

## 10. Expected Production State at v1.0.0

When Atelier ships, here is the complete picture of what "done" looks like:

### 10.1 Live Services & URLs

| URL                       | What                                             |
| ------------------------- | ------------------------------------------------ |
| `atelier.dev`             | Marketing site + sign-up + pricing               |
| `app.atelier.dev`         | Dashboard (React SPA)                            |
| `bench.atelier.dev`       | Public evaluation leaderboard + agent submission |
| `calibration.atelier.dev` | Public judge calibration dashboard               |
| `status.atelier.dev`      | Status page (Cloud Monitoring uptime checks)     |
| `docs.atelier.dev`        | Documentation                                    |
| Cloud Run API             | FastAPI with `/health`, `/docs`                  |
| Cloud Run jobs            | Agent runtime (convergence loops)                |

### 10.2 Deliverable Packages

| Package                             | Distribution       |
| ----------------------------------- | ------------------ |
| `atelier-core` (Python)             | pip (PyPI)         |
| `atelier-eval` (Python)             | pip (PyPI)         |
| `atelier-dashboard` (React)         | Firebase Hosting   |
| `atelier-action`                    | GitHub Marketplace |
| `@atelier/constitution-apple-grade` | npm                |
| `atelier-figma-plugin` (P1)         | Figma Community    |
| `atelier-chrome-extension` (P1)     | Chrome Web Store   |

### 10.3 Atelier Skills (6)

1. `case-study` — case study page generation
2. `dashboard` — analytics dashboard generation
3. `marketing-page` — landing page generation
4. `e-commerce` — e-commerce page generation
5. `portfolio` — portfolio site generation
6. `docs-site` — documentation site generation

### 10.4 Pricing Tiers (Live at v1.0.0)

| Tier       | Price          | Sessions                            |
| ---------- | -------------- | ----------------------------------- |
| Freemium   | Free           | 3/month, watermarked                |
| Pro        | $20/month      | 50/month, no watermark              |
| Team       | $50/seat/month | Shared workspace, shared judge LoRA |
| Enterprise | Usage-based    | BYO KMS, VPC-SC, custom judges      |

### 10.5 Self-Improvement Loop (Active at v1.0.0)

**Soft loop (continuous, no GPU):**

- Pattern curator: every 6h, curate Memory Bank patterns
- Skill extractor: after ≥10-surface campaigns, auto-write Skills
- Vector consolidator: nightly 03:17 UTC, cluster + prune

**Hard loop (DPO/LoRA — first-project demo proof at v1.0.0):**

- 3-tier dataset flywheel: T1 production → T2 quality-approved → T3 failure-cases
- DPO preference pairs (margin ≥ 0.15) → LoRA on Gemma 4 26B-A4B-it
- Vertex AI Tuning + Endpoints + Multi-Tuning for serving
- Auto-register if eval improves ≥ 2%

### 10.6 Day-0 SLOs (Enforced)

| SLO                    | Target             |
| ---------------------- | ------------------ |
| Agent success rate     | ≥ 95%              |
| p95 turn latency       | ≤ 8s               |
| p95 session latency    | ≤ 4 min            |
| Judge pass rate        | ≥ 65%              |
| Cost per session       | ≤ $0.50            |
| First-shot convergence | ≥ 40% (PIP active) |
| Campaign convergence   | ≥ 85% (12-surface) |

### 10.7 Observability (All OTel GenAI semconv)

Every span carries: `gen_ai.system=atelier`, tenant/project/session/campaign/surface IDs, node, iteration, candidate, axis, decision, score, confidence interval, token counts, cost USD.

Cloud Trace + Cloud Monitoring + Cloud Logging + Vertex AI Studio Tracing + Atelier Dashboard.

### 10.8 Security Posture at v1.0.0

- 5-tier sandboxing (in_process → shell_sandbox → browser_sandbox → external_https → cloud_sandbox)
- Explicit network egress allowlist (16 endpoint patterns, everything else blocked)
- Model Armor via Apigee (prompt injection, harmful content, sensitive data, RAI, malicious URL)
- Per-tenant cost caps at Apigee
- Cloud KMS per-subject encryption (GDPR)
- GDPR + EU AI Act limited-risk transparency
- SOC 2 Type 2 evidence collection scaffolded (certification month 6)

---

## 11. Rejected Approaches (7 Locked Rejections)

These are **permanently rejected** — do not re-attempt:

1. ❌ **Langfuse** for observability → Google-native only (ADR 0006)
2. ❌ **Agent Engine for runtime** → Cloud Run jobs (ADR 0002)
3. ❌ **Fork agent-dag-pipeline** → Wrap-don't-fork (ADR 0001)
4. ❌ **Statsig/GrowthBook** for feature flags → Firebase Remote Config (ADR 0006)
5. ❌ **PostHog** for analytics → Firebase Analytics + GA4 + BigQuery (ADR 0006)
6. ❌ **GKE for vLLM Multi-LoRA** → Vertex AI Endpoints + Multi-Tuning (ADR 0006)
7. ❌ **LiteLLM as production proxy** → Apigee AI Gateway (ADR 0006)

---

## 12. Explicitly Out of Scope for v1.0.0

| Feature                            | Deferred to          |
| ---------------------------------- | -------------------- |
| Voice input (Stitch "vibe design") | v1.1.0 (Jun 12)      |
| Multiplayer dashboard annotation   | v1.1.0               |
| Discord community                  | v1.1.0               |
| Additional A2UI renderers          | v1.3.0               |
| Sketch-to-UI dedicated upload      | v1.3.0               |
| Multi-region active-active         | v1.3.0               |
| SOC 2 Type 2 certification         | v2.0.0 (Dec)         |
| Per-tenant CMEK on Cloud Run       | v2.0.0               |
| HIPAA tier                         | v2.0.0               |
| ISO 27001 / ISO 42001              | v2.0.0+              |
| Federated learning across tenants  | v3.0.0               |
| Stripe actually charging users     | Month 6 (with SOC 2) |

---

## 13. Submission Package (32 Pre-Launch Artifacts)

The G4S submission (F0186) requires:

1. Project description ≤ 500 words
2. Demo video (4-min + 2-min backup + 60-sec elevator)
3. Repo URL (`github.com/Manzela/atelier`)
4. Live URL (`atelier.dev`)
5. Team info
6. "Built with Google" declaration
7. arXiv link
8. Benchmark results (WebGen-Bench ≥ 60)
9. Testimonials (≥ 3 designer-in-residence)
10. Calendly for live office hours

Plus: Twitter announcement, Hacker News Show HN, Product Hunt launch scheduled.

---

## 14. Current Sprint State (as of 2026-05-20)

| Property               | Value                                     |
| ---------------------- | ----------------------------------------- |
| **Days elapsed**       | 6 of 21                                   |
| **Features completed** | 1/205 (0.5%)                              |
| **Active branch**      | `main` (no phase worktree created)        |
| **Last commit**        | `c909dbf` — ADR audit absorptions         |
| **Active blockers**    | Vite security PRs #21/#22 failing CI (P2) |
| **Cost spent**         | ~$50 of $5,000 (1%)                       |
| **Phase 1 due**        | May 21 (tomorrow)                         |

> [!CAUTION]
> **The sprint is 6 days in with only the pre-sprint bootstrap feature completed.** The Phase 1 gate (54 features) was due May 21. No phase/1 worktree exists. No source code has been written. The project appears to have pivoted attention to the AutonomousAgent research project during this period (where 6 Claude Code sessions are actively running).

---

## 15. Key Configuration Files

| File                                 | Purpose                                                    | Path                                |
| ------------------------------------ | ---------------------------------------------------------- | ----------------------------------- |
| `limits.yaml`                        | All tunables (budget, retries, loops, gates, judges, SLOs) | `atelier-deploy/config/limits.yaml` |
| `features.json`                      | Atomic feature ledger (205 entries)                        | Repo root                           |
| `BriefSpec.json`                     | Immutable per-project spec (produced by PIP)               | `<project>/.atelier/`               |
| `surfaces.json`                      | Campaign surface manifest                                  | `<project>/.atelier/`               |
| `.atelier.yaml`                      | Optional project descriptor (PADI)                         | User's project root                 |
| `config/axis_weights_heuristic.yaml` | Per-register axis weight tables (N15)                      | `atelier-core/`                     |
| `config/research-trust.yaml`         | WRAI domain trust whitelist/denylist (N14)                 | `atelier-core/`                     |
| `config/scrubber-patterns.yaml`      | Output secret scrubber patterns                            | Inherited from agent-dag-pipeline   |
