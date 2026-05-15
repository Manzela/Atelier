---
title: Atelier — Autonomous Design Agent (PRD)
date: 2026-05-14
status: approved
author: Daniel Manzela (strategy) + Claude Opus 4.7 MAX (architecture + builder)
project_dir: /Users/danielmanzela/Professional Profile/atelier
submission_target: Google for Startups AI Agents Challenge 2026
submission_deadline: 2026-06-05
internal_target_deadline: 2026-06-03
sprint_window: 2026-05-15 → 2026-06-04
build_budget_usd: 5000 # Claude Opus 4.7 MAX capacity via Vertex AI
license: Apache-2.0
related_specs:
  - /Users/danielmanzela/Professional Profile/agent-dag-pipeline (architectural reference, ~75% ADK reuse)
  - /Users/danielmanzela/RX-Research Project/AutonomousAgent (hermes-agent fork, harness inspiration)
  - /Users/danielmanzela/Professional Profile/DESIGN_PRINCIPLES_APPLE.md (CSC-D constitution)
  - /Users/danielmanzela/Professional Profile/design.md/examples/apple-grade/DESIGN.md (canonical token sheet)
upstream_inheritance:
  - github.com/Manzela/agent-dag-pipeline (Apache-2.0; Gate-Agent ABC, DEMAS, 3-tier flywheel, ADK wrappers)
  - github.com/NousResearch/hermes-agent (MIT; skills, MEMORY/SOUL, sandboxing, GRPO+LoRA)
  - github.com/google/adk-python v2.0 Beta (Apache-2.0; LoopAgent, ParallelAgent, MCPToolset, eval primitives)
  - github.com/anthropics/claude-quickstarts/tree/main/autonomous-coding (two-prompt harness pattern)
---

# Atelier — Autonomous Design Agent

> **The first autonomous design agent that asks the right questions, converges on flawless UI/UX across multi-axis judged criteria, and gets sharper with every iteration. Stitch generates. Atelier asks, converges, learns.**

---

## 1. Goal

Build a production-grade, public-launch autonomous design agent — **Atelier** — that wins the Google for Startups AI Agents Challenge 2026 by 10×-ing every shipped autonomous design tool in the market across **13 falsifiable novel contributions** and **5 quantified 10× axes**, anchored in Anthropic's published long-running-agent harness pattern, Google's ADK 2.0 Beta + Vertex AI Agent Engine + Memory Bank + A2UI v0.9, and Daniel Manzela's production-validated 7-node Gate-Agent DAG architecture.

The 21-day sprint window is **2026-05-15 → 2026-06-04** with submission filed **2026-06-03 noon** (2 days before the official 2026-06-05 deadline). Build budget is **$5K of Claude Opus 4.7 MAX capacity via Vertex AI**, leveraged ~10× by aggressive prompt caching ($0.50/MTok effective rate on cache hits with 1h TTL breakpoints).

---

## 2. Submission target

**Google for Startups AI Agents Challenge 2026** — open category, $90K prize pool, mentorship from Google DeepMind + Google Labs. Deadline 2026-06-05; we file 2026-06-03 noon. Judging criteria (inferred from 2025 rubric): **technical novelty, agentic depth, real-world impact, demo quality, Use of Google Cloud**. The PRD is structured to score on every one.

---

## 3. Problem statement

Every shipped autonomous-design tool in May 2026 — Stitch, Vercel v0, Subframe, Lovable.dev, Bolt.new, Replit Agent v2, Devin, Builder.io Fusion, Tempo Labs — terminates at _generation_, not at _convergence_. The verification step in Google's own Antigravity codelab is literally called **"Vibe Check"** — manual human eyeballing. None auto-runs Lighthouse, axe-core, visual-regression, or responsive-snapshot gates and re-generates until pass. None ships a multi-axis design judge. None fine-tunes on user-specific accept/reject signals. None mirrors the deterministic-gate-first DAG architecture validated in production codegen agents.

Meanwhile, **WebGen-Bench (NeurIPS 2025)** establishes that even the strongest current agent (WebGen-Agent at 51.9%) leaves nearly half of generated sites failing automated quality criteria, and **DesignPref (Nov 2025, 12k pairwise UI judgments by 20 professional designers)** proves that designer disagreement is intrinsic (Krippendorff's α = 0.25), making **personalized judges scientifically required** — yet no shipped agent personalizes.

The whitespace is not "better generation." The whitespace is **closed-loop convergence + per-project personalization + offline RL on captured trajectories + multi-surface campaign discipline + pre-generation intake**.

---

## 4. The 10× thesis (5 quantified axes)

Atelier delivers 10× over the strongest commercial baseline (Subframe + Devin + v0 stack) along **5 simultaneous axes**, every one falsifiable:

| #   | Axis                                                   | MVP target                                                                                   | Baseline                                                              | 10× evidence                               |
| --- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------ |
| 1   | **Convergence quality at first declared-done**         | ≥ 95% (Lighthouse Perf/A11y/BP ≥ 90, axe = 0, visual-diff ≤ 2%, responsive on 4 breakpoints) | Today: ~0% formal across commercial tools (no tool gates)             | Quantified vs zero                         |
| 2   | **Iterations to convergence**                          | ≤ 3 autonomous loops                                                                         | Reflexion typical 5–10; commercial requires ~80+ human-bounded cycles | Beats published research                   |
| 3   | **Human-in-loop time**                                 | ≤ 60 sec to gate-passing output                                                              | Subframe / v0 / Stitch: ~5–15 min per page                            | Order of magnitude                         |
| 4   | **Cross-session pattern reuse** (compounding learning) | ≥ 60% reuse rate after 100 sessions                                                          | Today: 0% across commercial tools                                     | Compounding moat                           |
| 5   | **WebGen-Bench (published benchmark)**                 | ≥ +25 pts vs Claude-3.5 baseline (26.4 → ≥ 51.4); stretch ≥ 77 with first-project LoRA       | SOTA WebGen-Agent: 51.9%                                              | Beats published SOTA by ≥ 25 pts (stretch) |

Plus a **6th axis surfaced by N13 PIP**: **first-shot convergence rate ≥ 40%** (vs ≤ 25% without PIP, vs ~5–15% commercial baseline) and a **7th axis surfaced by N12 RLRD**: **multi-surface campaign success ≥ 85% on 12-surface campaign, ≥ 70% on 50-surface** (vs ~0% commercial — none handle campaigns autonomously).

---

## 5. Novel contributions (15)

Each contribution is independently defensible against peer review and competitively unowned at the commercial level.

**N1. DGF-D2C — Deterministic-Gate-First Design-to-Convergence.** Process supervision with deterministic preconditions: every node fires a zero-LLM, O(1) gate before any probabilistic agent. Lighthouse / axe / token-fidelity / semantic-HTML / visual-diff / responsive gates run _before_ the design judge sees anything, eliminating attention dilution and judge oscillation. WebGen-Agent uses VLM scorer + Step-GRPO but no deterministic pre-gate. **Publishable at NeurIPS D&B or ICLR.**

**N2. DEMAS-D — Per-axis Provenance Matrix Design Judge.** Each design axis (a11y, brand, motion, copy, semantics, tokens) receives **only** its relevant ground-truth variables, never the full DOM. Solves the "judge overwhelmed by full page context when scoring just contrast" problem that Stitch/v0/Lovable architectures all suffer from. Direct port of agent-dag-pipeline's DEMAS Provenance Matrix retargeted to UI.

**N3. PerJudge — Per-Project DPO Judge with Hebbian Prompt Mutator + Few-Shot Cold-Start.** A 3-tier dataset flywheel (production-baseline → quality-approved → failure-cases) generates DPO preference pairs per project. LoRA fine-tunes the judge on each project's accumulated diffs via S-LoRA on Vertex AI Endpoints. Hebbian mutator wraps `adk optimize` (GEPA) for fast prompt patches between full retraining cycles. **Addresses DesignPref's α=0.25 finding directly** — first commercial-grade autonomous design agent to ship personalization.

**N4. PADI — Project-Agnostic Descriptor Inference.** Hybrid input contract — optional `.atelier.yaml` descriptor for control, full inference from path + intent for new projects. Adapts to any tech stack (React, Vue, Astro, Sage 10 PHP, vanilla HTML, Next.js, etc.) without per-stack hardcoding.

**N5. EvoDesign — AlphaEvolve-Inspired Evolutionary K-Candidate Search.** K=6 parallel hypotheses per iteration → judge-mediated selection → mutation (8 explicit operators) + crossover → repeat. Diversity prevents local minima. **First transfer of AlphaEvolve methodology to UI generation.**

**N6. CSC-D — Constitutional Self-Critique for Design.** Agent self-grades each candidate against the 12-principle Apple-Grade constitution (`@atelier/constitution-apple-grade`) **before** the deterministic gate fires. Cuts iteration count by killing obviously broken candidates pre-flight. Direct transfer of Anthropic CAI methodology to design.

**N7. A2UI-Native Output.** Atelier renders to Google's A2UI v0.9 protocol by default. Output drops into any React / Flutter / Lit / Angular host without translation. **First autonomous design agent built A2UI-native from day one.**

**N8. Public Judge Calibration Dashboard.** `calibration.atelier.dev` shows per-judge agreement on a frozen golden set over time, drift alerts when correlation drops below 0.8, transparent re-calibration history. **First commercial autonomous design agent to publish judge calibration externally as a transparency commitment.** Defends against the judge-calibration-drift problem 93% of teams hit (Galileo report).

**N9. Open Eval Adapters Library.** Apache-2.0 PRs to `google/adk-python` for **WebGen-Bench, Design2Code, Web2Code, ScreenSpot, FrontendBench**. Makes ADK the canonical evaluation runtime for the entire UI-generation research field. Atelier as the reference implementation.

**N10. Convergence Spec RFC.** Open standard: how an autonomous design agent declares convergence criteria, emits trajectories, reports calibration drift, integrates with eval benchmarks. Atelier ships the reference implementation. Other agents implement the spec. Atelier becomes the standard-setter, not the niche tool.

**N11. Atelier Open Eval Harness.** `bench.atelier.dev` accepts agent submissions from any vendor (Vercel v0, Lovable.dev, Replit Agent, even Stitch). Public leaderboard. Atelier becomes the **standard evaluation surface** for the entire UI-generation field. Ecosystem-defining move.

**N12. RLRD — Recursive Long-Running Discipline.** Atelier-as-reference-implementation of Anthropic's published long-running agent harness for a domain-specific agent. Initializer + coding agent, JSON ledger (`surfaces.json`), spec-anchored decisions (`DECISIONS.md`), `REJECTED.md` long-term memory of failed approaches, Ralph Loop "DONE" token, cache-breakpoint architecture, multi-tier subagent orchestration. **Atelier eats its own dogfood**: the same discipline we use to build it, we ship to users running multi-day, multi-surface campaigns.

**N13. PIP — Pre-Generation Intake Protocol.** Adaptive-depth (atomic 2-3 / small 5-7 / large 10-12 / greenfield 12-15 questions), DAPLab-pattern-mapped (each of 9 failure patterns has a preempting question), visual-option-driven (4 mockup thumbnails for "what visual feel?"), skip-when-answered (descriptor / Memory Bank / brief-parsed) intake before any generation. Produces an **immutable BriefSpec** the agent commits to. **First commercial autonomous design agent to ship structured pre-generation intake** — directly closes silent-error-suppression and business-logic-mismatch failure modes.

**N14. WRAI — Web-Research-Augmented Intake.** Between PIP Q&A completion and BriefSpec lock, the agent dispatches 5-8 parallel Vertex AI Search Grounding queries derived from the draft BriefSpec (industry best practices, current compliance standards, stack-specific patterns, visual-register references, competitor analysis, failure-mode warnings). Findings synthesized into structured `ResearchFindings` (applied_standards, inspirations, suggested_overrides, risk_warnings, citations) with per-source trust scores and one-shot user review before lock. Domain whitelist + Apigee Model Armor sanitization + per-tenant 7-day cache. **First commercial autonomous design agent to ship web-research-augmented intake** — anchors aren't bounded by user knowledge; agent surfaces what the user doesn't know they don't know (e.g., WCAG 2.2 added rule 2.4.11) before BriefSpec is locked. See ADR 0011.

**N15. MJG — Metastrategic Judging Gap closure (BriefSpec-conditional axis weighting).** Per-axis floors and weights for the 5-judge ConsensusAgent + Det Gate are derived from `BriefSpec.visual_register × compliance_level × convergence_bar`, not constants. A data-viz dashboard weights a11y + visual-clarity higher; a marketing landing page weights brand-fidelity + originality higher; a brutalist register downgrades brand-fidelity floor in service of memorability. **Closes a failure mode that DAPLab's 9 patterns do not document** (the patterns are implementation failures; this is a metastrategic evaluation failure). First commercial autonomous design agent to ship per-project judge weighting. Audit trail in `audit/findings.md` Gap 1.

**Combined defense:**

- N1+N2+N5 = methodology paper ("Process Supervision with Deterministic Preconditions and Evolutionary Search for Personalized Autonomous Design Convergence")
- N3+N6+N13+N14 = personalization + intake + research-augmented intake paper
- N4+N7 = product moat (broad deployment)
- N8+N9+N10+N11 = ecosystem moat (transparency, standards, community)
- N12 = recursive discipline (the same patterns we use, we ship)
- N15 = metastrategic-judging-gap closure (publishable as standalone — first paper to formalize the gap and ship a closure)

---

## 6. System architecture

Atelier is a **three-layer stacked architecture**:

```
┌──────────────────────────────────────────────────────────┐
│ Layer 3: PIP (Pre-Generation Intake Protocol) — N13      │
│   Adaptive Q&A, visual options, skip-when-answered       │
│   Output: immutable BriefSpec.json + initialized         │
│   DECISIONS.md + design-system.lock.md                   │
└──────────────────┬───────────────────────────────────────┘
                   │ BriefSpec.json (immutable)
                   ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 2: Campaign Orchestrator (N12 RLRD)                │
│   CampaignBrief Parser → Surface Manifest (surfaces.json │
│   JSON ledger) → Campaign Picker (dependency-graph aware)│
│   → Cross-Surface Coherence Validator → Checkpoint       │
│   Writer. Cloud Scheduler + Cloud Tasks for multi-       │
│   session orchestration. Per-campaign DECISIONS.md +     │
│   REJECTED.md + design-system.lock.md.                   │
└──────────────────┬───────────────────────────────────────┘
                   │ One surface job per Cloud Run invocation
                   ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 1: Atomic 8-node DAG (per-surface engine)          │
│   N1 Brief Parser → N2 Source Resolver →                 │
│   N3 EvoDesign LoopAgent (max_iter=N):                   │
│     N3a Generator (ParallelAgent K=6, Stitch MCP) →      │
│     N3b CSC-D (constitutional self-critique) →           │
│     N3c Deterministic Gate (parallel, 6 axes) →          │
│     N3d ConsensusAgent (5 specialized rubric judges,     │
│         Bayesian-weighted vote, DEMAS-D Provenance) →    │
│     N3e Fixer (Hebbian via adk optimize/GEPA)            │
│   → N4 Final Validator + A2UI Renderer                   │
└──────────────────────────────────────────────────────────┘
```

### 6.1 PIP Layer (Pre-Generation Intake)

**Architecture:**

```
PIP Router (assesses scope: atomic/small/large/greenfield)
  → Skip-Path Resolver (descriptor + Memory Bank + brief-parsed)
    → Adaptive Question Sequencer (one Q at a time, visual options
      for design questions)
      → WRAI: Web-Research-Augmented Intake (N14) — Vertex AI Search
        Grounding × 5-8 parallel queries derived from draft BriefSpec
        → Trust Scorer (whitelist/PageRank/denylist; 0-1 per source)
        → Apigee Model Armor sanitization
        → Findings Synthesizer (Gemini 3 Flash → ResearchFindings:
          applied_standards, inspirations, suggested_overrides,
          risk_warnings, citations)
        → User Review (one-shot summary; per-finding accept/skip;
          --no-research opt-out for power users)
      → BriefSpec Synthesizer (immutable JSON with research_findings
        embedded, user-approved, initializes DECISIONS.md +
        design-system.lock.md)
```

**Question catalog (13 questions, mapped 1:1 to DAPLab patterns):**

| Q#  | Question                                                                   | Visual options                                                     | DAPLab pattern preempted      |
| --- | -------------------------------------------------------------------------- | ------------------------------------------------------------------ | ----------------------------- |
| 1   | "Reference images / live URL / Figma file? If no, what's the visual feel?" | 4 mockup thumbnails (editorial / dense-data / playful / brutalist) | 1 — UI grounding mismatch     |
| 2   | "Multi-surface project? One shared design system or federated?"            | Single-system vs federated diagram                                 | 2 — State management failures |
| 3   | "In ONE sentence: what's the single thing this should make easier?"        | (text only)                                                        | 3 — Business-logic mismatch   |
| 4   | "Existing DESIGN.md / tokens / brand guide?"                               | Color-palette swatch grid                                          | 4 — Schema errors             |
| 5   | "Output stack?"                                                            | Stack logos (React, Vue, Svelte, vanilla HTML, etc.)               | 5 — API integration failures  |
| 6   | "Compliance level?" (WCAG AA default / AAA / regulatory / none)            | (text only)                                                        | 6 — Security vulnerabilities  |
| 7   | "Existing component library to reuse?"                                     | (text only)                                                        | 7 — Repeated code             |
| 8   | "Process surfaces sequentially or parallel?"                               | Sequential vs parallel diagram                                     | 8 — Codebase awareness loss   |
| 9   | "Convergence bar?" (Ship-it ≥85% / Production ≥95% / Perfectionist 100%)   | (text only)                                                        | 9 — Silent error suppression  |
| 10  | (Campaign only) "Timeline?" Today / week / multi-week                      | (text only)                                                        | —                             |
| 11  | (Campaign only) "Budget cap per session / per campaign?"                   | (text only)                                                        | —                             |
| 12  | (Campaign only) "Failure policy?" Skip / ask for help / best-effort + flag | (text only)                                                        | —                             |
| 13  | (Greenfield only) "Brand-from-scratch? Primary user? Business goal?"       | (text only)                                                        | —                             |

**Adaptive depth:**

- Atomic single-surface task: questions 1, 3, 5 (= 3 questions)
- Small campaign (5-15 surfaces): adds 2, 4, 9 (= 6 questions)
- Large campaign (50+ surfaces): adds 6, 7, 8, 10, 11, 12 (= 12 questions)
- Greenfield (no existing project): adds 13 (= 13 questions)

**BriefSpec is immutable post-approval.** Spec changes require explicit "amend BriefSpec" command + re-approval; no silent drift.

### 6.2 Campaign Orchestrator (RLRD)

**Per-campaign persistent state** in user's project:

```
<user-project>/.atelier/
├── campaign.json                  # campaign brief, frozen at start
├── surfaces.json                  # JSON ledger, agent-edited not rewritten
├── campaign-progress.txt          # append-only narrative across sessions
├── DECISIONS.md                   # locked decisions, auto-injected
├── REJECTED.md                    # failed approaches with rationale
├── design-system.lock.md          # frozen DESIGN.md token-set
├── cost-ledger.json               # token spend per session per surface
├── checkpoints/
│   └── 2026-05-15T14:30Z.json    # full state per session-end
└── trajectories/                  # captured for cross-session learning
    └── *.jsonl
```

**Cross-Surface Coherence Validator** runs after each surface converges:

- Token use matches `design-system.lock.md`
- Pattern reuse with prior surfaces ≥ 30% threshold
- No DECISIONS.md contradictions
- No regression on prior-converged surfaces (visual-diff top 5 most-similar)

**Fail-loud, fail-closed**: any coherence violation surfaces explicit non-convergence response, never silent acceptance.

### 6.3 Atomic 8-node DAG (per-surface engine)

Mirrors agent-dag-pipeline's Gate-Agent pattern: every node = deterministic gate (zero-LLM, O(1)) → probabilistic agent (LLM-powered, only fires if gate passes).

```
Phase 1 — ParallelAgent
  N1 Brief Parser ────┐
  N2 Source Resolver ─┤
                      │
Phase 2 — Sequential  │
                      ▼
  N3 EvoDesign LoopAgent (max_iter=N)
    Per iteration:
    ┌─ N3a Generator (ParallelAgent K=6 candidates) ────────────┐
    │   K parallel Stitch MCP / frontend-design / direct calls   │
    │   Mutation operators (iter > 0):                           │
    │   token-swap / layout-swap / typography-swap / motion-swap │
    │   density-shift / asymmetry / hierarchy / copy-voice       │
    └────────────────┬───────────────────────────────────────────┘
                     │
    ┌─ N3b CSC-D (Constitutional Self-Critique) ───────────────┐
    │   Score each candidate against 12-principle constitution │
    │   Eliminate obvious failures pre-flight                  │
    │   Calibration: κ ≥ 0.7 vs human rubric per 100 calls     │
    └────────────────┬─────────────────────────────────────────┘
                     │
    ┌─ N3c Deterministic Gate (parallel, 6 axes) ──────────────┐
    │   Lighthouse a11y/perf │ axe │ token-fidelity grep        │
    │   semantic-HTML linter │ Playwright visual-diff │         │
    │   responsive snapshot at 375/768/1280/1920                │
    │   Pass = ALL green per candidate                          │
    └────────────────┬─────────────────────────────────────────┘
                     │
    ┌─ N3d ConsensusAgent (5 specialized rubric judges) ───────┐
    │   Brand / Copy / Motion / Token-fidelity / Coherence     │
    │   DEMAS-D Provenance Matrix per axis (each judge sees    │
    │   ONLY its relevant ground-truth variables)              │
    │   Bayesian-weighted vote with confidence interval        │
    │   Returns: aggregate score + per-axis breakdown +        │
    │   selected best candidate                                │
    └────────────────┬─────────────────────────────────────────┘
                     │
    ┌─ N3e Fixer (Hebbian Mutator via adk optimize/GEPA) ──────┐
    │   Reads gate failures + judge low-axis scores            │
    │   Failure-pattern → mutation:                            │
    │     A11Y_FAIL → APPEND_CONSTRAINT                        │
    │     TOKEN_DRIFT → APPEND_CONSTRAINT                      │
    │     BRAND_INCONSIST → BOOST_EXAMPLE                      │
    │     LOW_ORIGINALITY → ADJUST_TEMPERATURE                 │
    │     MOTION_NO_REDUCED → APPEND_CONSTRAINT                │
    │   Generator prompt mutated; loop re-enters N3a           │
    └──────────────────────────────────────────────────────────┘

    exit_loop conditions:
      converged: judge ≥ floor AND all axes pass
      timeout: max_iterations hit
      budget: per-tenant cost cap reached
      panic: human override
                     │
                     ▼
  N4 Final Validator + A2UI Renderer
    Gate: convergence reason ∈ {converged, timeout w/ partial}
    Agent: optional Telegram approval (per limits.approval rules)
    Render to A2UI v0.9 (React/Flutter/Lit/Angular targets)
    Emit PR diff or commit
    Append trajectory to BigQuery
    Extract pattern recipe to Memory Bank + Vector Search 2.0
    On non-convergence: explicit non-convergence response
    (iteration counter, partial artifacts, axes that converged
    vs didn't, "request human help" CTA)
```

**Loop discipline:**

| Loop                                             | Where                 | Exit                                                     | Iter cap                                 |
| ------------------------------------------------ | --------------------- | -------------------------------------------------------- | ---------------------------------------- |
| EvoDesign K-candidate                            | N3a                   | All K candidates generated                               | K from `limits.evodesign.k` (MVP K=6)    |
| Generator↔Fixer (deterministic gate convergence) | N3a → N3c → N3e → N3a | All deterministic gates green for at least one candidate | `limits.det_loop_max_iter` (default 5)   |
| Judge↔Fixer (LLM judge convergence)              | N3d → N3e → N3a       | ConsensusResult.decision == CONVERGED                    | `limits.judge_loop_max_iter` (default 3) |

Hard outer cap: `limits.outer_loop_max_iter` (default 8).

### 6.4 D-O-R-A-V Design Rubric

Adapting agent-dag-pipeline's O-R-A-V to design:

| Axis               | What it measures                                                                   | Model tier                             | Threshold                          |
| ------------------ | ---------------------------------------------------------------------------------- | -------------------------------------- | ---------------------------------- |
| **Brand-fidelity** | Adherence to DESIGN_PRINCIPLES_APPLE.md + DESIGN.md tokens                         | Gemini 3 Flash + Brand-judge LoRA      | 0.7                                |
| **Originality**    | Distinctness from generic AI-slop / template repetition                            | Gemini 3 Flash                         | 0.6                                |
| **Relevance**      | Alignment between generated UI and BriefSpec                                       | Gemini 3 Flash + project-specific LoRA | 0.7                                |
| **Accessibility**  | Lighthouse a11y + axe + semantic-HTML (deterministic) + a11y-judge (probabilistic) | Det gate + Gemini 3 Flash              | Det: 0 errors / Probabilistic: 0.8 |
| **Visual-clarity** | Information hierarchy, scan-ability, cognitive load                                | Gemini 3 Flash + multimodal-embedding  | 0.7                                |

Composite: weighted vote (Bayesian-weighted by confidence interval), per-axis floors enforced (any axis < threshold = REJECT).

### 6.5 Layered Oracle

Three layers, each with explicit responsibility:

| Layer                                           | Responsibility                                                                                                                                                            | Tools                                                                                            |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **Layer 1: Deterministic gates** (must pass)    | Lighthouse Perf/A11y/BP ≥ 90, axe = 0 errors, token-fidelity grep clean, semantic-HTML linter clean, prefers-reduced-motion alternate exists, responsive on 4 breakpoints | Lighthouse CI, axe-core, custom grep, html-validate, Playwright                                  |
| **Layer 2: LLM design judge** (D-O-R-A-V)       | Brand / Copy / Motion / Token / Coherence axes via 5 specialized rubric judges; DEMAS-D Provenance Matrix per axis                                                        | ADK `rubric_based_final_response_quality_v1` + per-project LoRAs (S-LoRA on Vertex AI Endpoints) |
| **Layer 3: Optional human approval** (Telegram) | Final "ship it" for high-stakes pages per `limits.approval` rules                                                                                                         | Telegram inline-keyboard buttons (inherits hermes-agent pattern)                                 |

Phase 4 RL fine-tunes the LLM Design Judge (Layer 2) on accumulated trajectories.

### 6.6 Self-Improvement Loop

**Soft loop (Phase 1+, runs continuously, no GPU):**

| Nudge               | Trigger                                          | Action                                                                                                     | Tunable                                      |
| ------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| Pattern curator     | Every 6h                                         | Agent re-reads project Memory Bank, scores patterns for keep/promote/forget                                | `limits.nudges.pattern_curator_interval`     |
| Skill extractor     | After complex campaign (≥ 10 surfaces converged) | Reflect on trajectory; if reusable, write `/skills/<slug>/SKILL.md`                                        | `limits.nudges.skill_extractor_min_surfaces` |
| Vector consolidator | Nightly 03:17 UTC                                | Cluster Vector Search 2.0 embeddings, summarize via LiteLLM, promote to Memory Bank, prune low-score > 90d | `limits.nudges.vector_consolidator_cron`     |

**Hard loop (Phase 1.5 within MVP for first-project; Phase 2+ for all projects):**

```
Production traffic → trajectory-shipper (hourly) → BigQuery + GCS
DPO preference pairs (margin ≥ 0.15) → LoRA fine-tune on Gemma 4 26B-A4B-it base
Vertex AI Tuning Manager → Vertex AI Endpoints with Multi-Tuning → S-LoRA serving
First-project LoRA fine-tuned in MVP as demo proof
```

**3-tier dataset flywheel** (mirrors agent-dag-pipeline pattern):

```
Production traffic
      ↓
[T1: production-baseline] ← all sessions
      ↓ D-O-R-A-V ≥ 0.7 AND all det gates pass
[T2: quality-approved] ← chosen examples
      ↓ D-O-R-A-V < 0.5 OR any det gate fails
[T3: failure-cases] ← rejected examples
      ↓
DPO preference pairs → LoRA fine-tuning → improved per-project judge
```

### 6.7 Tiered Sandboxing (5 tiers, inherits hermes-agent + agent-dag-pipeline)

| Tier              | Tools                                                                                                           | Boundary                                                                               |
| ----------------- | --------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `in_process`      | file reads, grep, ls, AST validation                                                                            | runs in agent process; host FS read-only                                               |
| `shell_sandbox`   | shell, git, jq                                                                                                  | Docker container, --cap-drop=ALL, --network=none, RO host FS, writable /workspace only |
| `browser_sandbox` | Playwright actions, Lighthouse, axe-core                                                                        | Docker container, network allowlisted per call, --memory=2g --cpus=2.0                 |
| `external_https`  | Stitch MCP, GitHub MCP, Context7 MCP                                                                            | in-process httpx with egress allowlist enforcement                                     |
| `cloud_sandbox`   | arbitrary code execution (model-generated CSS/JS), Vertex AI Endpoints (LoRA serving), Vertex AI Tuning Manager | Modal/Daytona ephemeral microVM, network restricted, max 10-min lifetime               |

First-match wins; unknown tools fall through to `shell_sandbox` (default-deny).

### 6.8 Cross-Surface Coherence (Campaign-level)

When a surface converges, the Cross-Surface Coherence Validator runs:

1. **Token use validation**: every hex/rgb/font/spacing value in the generated artifact must be in `design-system.lock.md` OR be a documented exception with ADR-equivalent rationale in DECISIONS.md.
2. **Pattern reuse measurement**: components used in this surface must reuse ≥ 30% of components from prior-converged surfaces (per Surface Manifest dependency graph).
3. **DECISIONS.md compliance**: no contradiction with locked decisions (e.g., if prior surface locked "primary CTA = pill button," this surface cannot use rectangular CTA without explicit ADR).
4. **Regression check**: visual-diff against top 5 most-similar prior-converged surfaces; no regression > 2% pixel diff on shared regions (nav, footer, common components).

Any violation = explicit non-convergence response on this surface; surface marked `coherence_review: required` until resolved.

---

## 7. Production-grade SaaS layer (day-0 launch)

### 7.1 Multi-tenancy

`tenant_id` in JWT (issued by Identity Platform) → propagate via OTel baggage → enforce in Postgres RLS + BigQuery authorized views. **NOT tenant-per-deployment** (cost-prohibitive past 50–100 tenants). OWASP Multi-Tenant Cheat Sheet as control list. Per-session access control via **IAM Conditions on Vertex AI session resources** (Google's first-class multi-tenant primitive).

### 7.2 Cost model

**Per-session unit economics** (target):

- 50 LLM predictions × $0.20/1K (under 1M Agent Engine tier) = $0.01 platform cost
- Token costs: ~$0.10–0.50/session via Apigee model routing (Pro for Generator, Flash for judges, Flash-Lite for gate auxiliaries)
- **Total per-session cost: < $0.50 in MVP, < $0.10 with judge LoRA (Phase 2)**

**Sessions billing is the dominant non-LLM cost lever** ($0.25 per 1,000 stored events). Atelier caps session-event writes to node boundaries + final convergence state; pushes trajectory captures to **Firestore + BigQuery, not Sessions**.

**Cost ceiling**: per-tenant budget cap enforced at **Apigee AI Gateway** (not in our code). Surge protection: token-bucket per tenant in Redis + circuit-breaker that demotes runaway tenants to a "degraded" model pool (Flash-Lite only).

### 7.3 Observability

**OTel GenAI semconv** (`gen_ai.*` spans/events) → **Cloud Trace** + **Cloud Monitoring** + **Cloud Logging** + **Vertex AI Studio Tracing UI** + **Atelier Dashboard** (custom UX layer). **No Langfuse** (Google-native covers ~95%, Langfuse adds sprawl + conflicts with "Use of Google Cloud" judging criterion).

**Every span carries:**

- `gen_ai.system` = "atelier"
- `gen_ai.operation.name` = `generate_candidate` | `judge_axis` | `gate_check` | `mutator_apply` | `consensus_vote` | `final_render` | `pip_question` | `coherence_check`
- `gen_ai.request.model` = e.g., `gemini-3-1-pro`, `atelier-judge-brand-v3-loraN`
- `gen_ai.usage.input_tokens` / `output_tokens` / `cost_usd`
- `atelier.tenant_id`, `atelier.project_id`, `atelier.session_id`, `atelier.campaign_id`, `atelier.surface_id`
- `atelier.node`, `atelier.iteration`, `atelier.candidate_id`
- `atelier.axis` (for axis-scoped spans)
- `atelier.decision`, `atelier.score`, `atelier.confidence_interval`

### 7.4 Day-0 SLOs

Set in `limits.yaml` from sprint week 1, enforced by Cloud Monitoring alerts → Telegram + email:

- `agent_success_rate ≥ 95%` (gate-pass + judge-pass on declared-done)
- `p95_turn_latency ≤ 8s` (single judge call)
- `p95_session_latency ≤ 4 minutes` (full convergence cycle on a single surface)
- `judge_pass_rate ≥ 65%` (after 3 iterations)
- `cost_per_session ≤ tenant_budget_remaining` (hard enforcement at LiteLLM/Apigee)
- `first_shot_convergence_rate ≥ 40%` (with PIP active)
- `campaign_surface_convergence_rate ≥ 85%` (on 12-surface campaigns)

#### 7.5 Trust + safety + network egress allowlist

**Egress allowlist (enumerated, enforced at Apigee + Cloud Armor + VPC firewall):**

Atelier agent processes can ONLY reach these external endpoints. Every other outbound is blocked at the network layer.

| Endpoint                                                                           | Purpose                                                                           |
| ---------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `*.aiplatform.googleapis.com`                                                      | Vertex AI (Gemini, Memory Bank, Vector Search, Tuning, Endpoints)                 |
| `stitch.googleapis.com`                                                            | Stitch MCP for UI generation                                                      |
| `api.github.com`                                                                   | GitHub MCP (PR creation, repo metadata)                                           |
| `api.context7.com`                                                                 | Context7 MCP (library docs verification)                                          |
| `*.firebaseio.com`, `firestore.googleapis.com`                                     | Firestore for hot UI state                                                        |
| `bigquery.googleapis.com`, `bigquerystorage.googleapis.com`                        | BigQuery for trajectory writes                                                    |
| `storage.googleapis.com`                                                           | GCS for trajectory cold storage + KMS key references                              |
| `secretmanager.googleapis.com`                                                     | Secret Manager for platform secrets                                               |
| `cloudkms.googleapis.com`                                                          | Cloud KMS for BYOK envelope encryption                                            |
| `cloudtrace.googleapis.com`, `monitoring.googleapis.com`, `logging.googleapis.com` | Observability                                                                     |
| `apigee.googleapis.com`                                                            | Apigee gateway control                                                            |
| `api.telegram.org`                                                                 | Telegram bot (async tasks + approval gates)                                       |
| `api.stripe.com`                                                                   | Stripe billing                                                                    |
| `*.run.app` (own services only)                                                    | Internal Cloud Run service-to-service                                             |
| Per-call Playwright targets                                                        | User-supplied URLs for visual-diff (per-session allowlist, expires after session) |

**No other endpoint is reachable.** Adding a new endpoint requires an ADR + explicit allowlist update.

### 7.5.1 Trust + safety

**Model Armor** (5 capabilities: prompt-injection/jailbreak, harmful content, sensitive data, RAI policies, malicious URL) wired through **Apigee `SanitizeUserPrompt` / `SanitizeModelResponse`** policies. Per-IP rate limits at **Cloud Armor**; per-user at **LiteLLM** (or Apigee). Output secret scrubber inherited from agent-dag-pipeline (regex patterns in `config/scrubber-patterns.yaml`).

### 7.6 Compliance roadmap

| Milestone                                  | Status                                         | Date              |
| ------------------------------------------ | ---------------------------------------------- | ----------------- |
| GDPR + EU AI Act limited-risk transparency | MVP launch                                     | 2026-06-05        |
| SOC 2 Type 2 (via Vanta or Drata)          | Evidence collection wired day-0; certification | 2026-12 (month 6) |
| ISO 27001                                  | When first enterprise contract demands         | TBD               |
| ISO 42001 (AI-specific governance)         | At scale, as differentiator                    | TBD               |

### 7.7 Pricing

- **Freemium**: 3 sessions/month, watermarked output ("designed by Atelier" footer)
- **Pro $20/month**: 50 sessions, no watermark
- **Team $50/seat/month**: shared workspace, project-history sync, shared judge LoRA across team
- **Enterprise usage-based**: BYO Cloud KMS keys, VPC-SC perimeter, dedicated tenant pool, custom judge axes

Target $/MAU = **15–25% of Cursor Pro** to undercut while differentiating on judge quality.

---

## 8. Tech stack (Google-native, sprawl-free)

```
Identity Platform (multi-tenant + Google/GitHub/email sign-in)
  ↓ JWT w/ tenant_id
Apigee AI Gateway (per-tenant rate limit, cost router, Model Armor)
  + Cloud Armor (per-IP)
  ↓
Atelier API (Cloud Run, FastAPI + OpenAPI 3.1 + Eventarc)
  ↓
Atelier Agent (Cloud Run jobs — NOT Agent Engine for runtime)
  ADK 2.0 Beta + LoopAgent + ParallelAgent + GateAgent ABC (from
  agent-dag-pipeline) + LiteLLM Proxy + Skills for Agents
  ↓
[Vertex Memory Bank — cross-session preferences + capped Sessions]
[Firestore — hot UI state]
[Vertex Vector Search 2.0 + multimodal-embedding — pattern recall]
[BigQuery + GCS coldline — trajectories, KMS-per-subject for GDPR]
[Vertex AI Tuning jobs — SFT + DPO]
[Vertex AI Endpoints + Multi-Tuning — per-project judge LoRA serving]
  ↓
Cloud Trace + Cloud Monitoring + Cloud Logging + Vertex AI Studio
Tracing + Atelier Dashboard
  ↓
Firebase Remote Config (feature flags + A/B tests + progressive rollout)
+ Firebase Hosting (atelier.dev, docs, bench, calibration, status)
+ Firebase Analytics + GA4 + BigQuery Export
  ↓
Stripe (only non-Google component — billing)
+ Telegram (hermes inheritance — async tasks + approval gates)
```

**Two non-Google components**: Stripe (no Google billing platform) + Telegram (already owned). Everything else Google-native.

---

## 9. Data contracts (Pydantic v2, frozen, schema-versioned)

```python
class TenantContext(BaseModel, frozen=True):
    tenant_id: str
    user_id: str
    project_id: str
    descriptor: AtelierDescriptor | None
    cost_budget_usd: Decimal
    cost_consumed_usd: Decimal
    schema_version: int = 1

class BriefSpec(BaseModel, frozen=True):
    spec_id: UUID
    tenant_id: str
    project_id: str
    intent: str  # the "ONE thing" answer
    visual_register: VisualRegister  # editorial / dense-data / playful / brutalist / custom
    stack: StackChoice
    design_system_source: str | None  # path to DESIGN.md or "infer"
    compliance_level: ComplianceLevel  # AA / AAA / regulatory / none
    convergence_bar: ConvergenceBar  # ship-it / production / perfectionist
    reference_artifacts: list[str]  # URLs / paths
    campaign_scope: CampaignScope | None  # None for atomic; populated for campaigns
    intake_transcript: list[IntakeAnswer]  # the Q&A that produced this spec
    schema_version: int = 1
    approved_at: datetime
    approved_by_user_id: str

class SurfaceManifest(BaseModel, frozen=True):
    campaign_id: UUID
    surfaces: list[SurfaceState]
    dependency_graph: dict[UUID, list[UUID]]  # surface_id → depends_on
    schema_version: int = 1

class SurfaceState(BaseModel, frozen=True):
    surface_id: UUID
    name: str  # e.g., "homepage-hero"
    type: SurfaceType  # page | component | template | screen
    brief: str
    axes_required: list[GateAxis]
    passes: bool = False
    iteration_count: int = 0
    human_approved: bool | None = None
    coherence_review_required: bool = False
    started_at: datetime | None = None
    completed_at: datetime | None = None
    schema_version: int = 1

class CandidateUI(BaseModel, frozen=True):
    candidate_id: UUID
    surface_id: UUID
    iteration: int
    parent_candidate_id: UUID | None  # for crossover
    mutation_op: MutationOp | None
    artifacts: dict[str, str]  # {"index.html": "...", "main.css": "..."}
    a2ui_payload: dict | None
    schema_version: int = 1

class GateOutcome(BaseModel, frozen=True):
    candidate_id: UUID
    axis: GateAxis  # LIGHTHOUSE_A11Y | LIGHTHOUSE_PERF | AXE | TOKEN_FIDELITY |
                    # SEMANTIC_HTML | VISUAL_DIFF | RESPONSIVE
    decision: GateDecision  # PASS | REJECT | DEFER
    score: float | None  # 0-100 for Lighthouse; null for binary axes
    diagnostic: str
    schema_version: int = 1

class JudgeVote(BaseModel, frozen=True):
    candidate_id: UUID
    judge_axis: JudgeAxis  # BRAND | COPY | MOTION | TOKEN | COHERENCE
    score: float  # 0.0 - 1.0
    confidence_interval: tuple[float, float]  # Bayesian CI
    reasoning: str  # for transparency dashboard
    provenance_vars: list[str]  # which DEMAS-D vars this judge saw
    judge_model: str  # e.g., "gemini-3-flash" or "atelier-judge-brand-v3-loraN"
    schema_version: int = 1

class ConsensusResult(BaseModel, frozen=True):
    selected_candidate_id: UUID
    composite_score: float
    per_axis_scores: dict[JudgeAxis, JudgeVote]
    decision: ConsensusDecision  # CONVERGED | RETRY | DEFER_HUMAN
    schema_version: int = 1

class CoherenceVerdict(BaseModel, frozen=True):
    surface_id: UUID
    token_use_valid: bool
    pattern_reuse_rate: float
    decisions_md_compliant: bool
    regression_check_passed: bool
    violations: list[str]
    schema_version: int = 1

class TrajectoryRecord(BaseModel, frozen=True):
    """Persisted to BigQuery, partitioned by DATE(ts) clustered by tenant_id."""
    trajectory_id: UUID
    tenant_id: str
    project_id: str
    campaign_id: UUID | None
    surface_id: UUID
    session_id: str
    ts: datetime
    node_name: str
    iteration: int
    candidates: list[CandidateUI]
    gate_outcomes: list[GateOutcome]
    judge_votes: list[JudgeVote]
    consensus: ConsensusResult | None
    coherence: CoherenceVerdict | None
    user_signal: UserSignal | None  # explicit accept/reject
    schema_version: int = 1
    encryption_key_id: str  # KMS key per subject — revoke for GDPR right-to-be-forgotten
```

All models frozen, schema-versioned (`schema_version` field never decreases, fields never dropped).

---

## 10. Inheritance map (wrap-don't-fork)

**Architectural principle (per AutonomousAgent ADR 0001 lineage)**: Atelier **consumes upstream code via lockfile-pinned dependencies and wraps it with our own deployment, configuration, security, and observability layers — we do NOT fork upstream internals.** Preserves upgrade paths, eliminates merge friction, keeps us aligned with upstream evolution.

Specifically:

- **`agent-dag-pipeline`** → consumed via `pip install agent-dag-pipeline==<pinned-version>` in `requirements.lock`. We import its ADK integration classes (`agent_dag.adk.gate_agent.GateAgent`, etc.) and subclass them. We never modify the package's source.
- **`google-adk`** v2.0 Beta → consumed via `pip install google-adk --pre` lockfile-pinned. We use its primitives (`SequentialAgent`, `ParallelAgent`, `LoopAgent`, `MCPToolset`, `rubric_based_*`, `MemoryService`). We never modify it.
- **`hermes-agent`** → **inheritance is pattern-only, not code-import.** We mirror its skills system, MEMORY/SOUL files, sandboxing tier model, panic/resume primitives, heartbeat, and Atropos GRPO+LoRA training pattern in our own code. We do not run hermes-agent as a process.
- **Stitch MCP** → consumed via the published HTTP MCP endpoint at `https://stitch.googleapis.com/mcp` through ADK's `MCPToolset`. No source-level dependency.
- **All other services** (Identity Platform, Apigee, Cloud Run, Memory Bank, Vector Search 2.0, BigQuery, KMS, Vertex AI Tuning + Endpoints) → managed Google services consumed via SDKs.

| Component                                                                                                                                                                                                                   | Source                                                                      | Consumption mode              | Atelier wrapping layer                              |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | ----------------------------- | --------------------------------------------------- |
| GateAgent ABC + GateDecision + GateResult                                                                                                                                                                                   | agent-dag-pipeline `agent_dag/adk/gate_agent.py` (215 LOC)                  | `pip install` lockfile-pinned | Subclass with Atelier-specific node implementations |
| Pipeline composition (Sequential + Parallel + Loop)                                                                                                                                                                         | agent-dag-pipeline `agent_dag/adk/pipeline.py` + ADK 2.0 `LoopAgent`        | 80%                           | Add `LoopAgent` for EvoDesign                       |
| Runner + SessionService                                                                                                                                                                                                     | agent-dag-pipeline `agent_dag/adk/runner.py` (70 LOC)                       | 100%                          | Direct reuse                                        |
| Lifecycle callbacks (integrity / flywheel / telemetry)                                                                                                                                                                      | agent-dag-pipeline `agent_dag/adk/callbacks.py` (114 LOC)                   | 90%                           | Adapt for design context                            |
| Eval framework                                                                                                                                                                                                              | agent-dag-pipeline `agent_dag/adk/eval.py` (132 LOC) + ADK `rubric_based_*` | 80%                           | Adapt to D-O-R-A-V rubric                           |
| Model Armor guardrails                                                                                                                                                                                                      | agent-dag-pipeline `agent_dag/adk/guardrails.py` (153 LOC)                  | 100%                          | Direct reuse                                        |
| Tool callbacks (sacred-label scrubber, prompt-injection regex)                                                                                                                                                              | agent-dag-pipeline `agent_dag/adk/tools.py` (118 LOC)                       | 90%                           | Adapt SACRED_LABELS for design                      |
| A2A Agent Card                                                                                                                                                                                                              | agent-dag-pipeline `agent_dag/adk/agent_card.py` (53 LOC)                   | 50%                           | New skills declared                                 |
| Vertex AI deployment                                                                                                                                                                                                        | agent-dag-pipeline `agent_dag/adk/deploy.py` (108 LOC)                      | 100%                          | Direct reuse, change requirements                   |
| 3-tier flywheel + DPO preference pairs + Hebbian mutator                                                                                                                                                                    | agent-dag-pipeline `agent_dag/flywheel/`                                    | 90%                           | Adapt scoring metrics to design                     |
| Telegram gateway + skills + MEMORY/SOUL + sandboxing tiers + panic + heartbeat                                                                                                                                              | hermes-agent                                                                | 70%                           | Domain-adapt for design                             |
| Atropos GRPO + LoRA training pipeline                                                                                                                                                                                       | hermes-agent                                                                | 100%                          | Direct reuse                                        |
| LoopAgent + ParallelAgent + Skills for Agents + MCPToolset + rubric*based*\*\_v1 + adk optimize (GEPA) + adk conformance                                                                                                    | ADK 2.0 Beta                                                                | 100%                          | Direct consume                                      |
| Vertex Memory Bank + Sessions + Vector Search 2.0 + Tuning jobs + Endpoints with Multi-Tuning                                                                                                                               | GEAP managed services                                                       | 100%                          | Direct consume                                      |
| Two-prompt harness (initializer + coding agent + JSON ledger)                                                                                                                                                               | Anthropic published pattern                                                 | 100%                          | Direct adopt                                        |
| Atelier-original code (8 nodes + EvoDesign + CSC-D + ConsensusAgent + 5 judges + 6 mutation operators + dashboard + A2UI renderers + WebContainer + bench adapters + PIP + Campaign Orchestrator + Cross-Surface Coherence) | new                                                                         | —                             | ~6,000–8,000 LOC                                    |
| Documentation, ADRs, runbooks, eval cases, terraform, CI/CD                                                                                                                                                                 | new                                                                         | —                             | ~10,000 LOC equivalent                              |

**Total Atelier-original: ~20,000 LOC** — achievable in 3 weeks with $5K Opus capacity.

---

## 11. Strategy v2 — sprint execution discipline

Full Strategy v2 in companion doc: `docs/superpowers/specs/2026-05-14-atelier-strategy-v2.md`. Summary:

- **Spec-Anchored Development**: this PRD is the source of truth; `DECISIONS.md` orchestrator-injected to prevent re-litigation; mid-sprint changes require explicit ADR commits.
- **Two-prompt harness (Anthropic Nov 2025)**: `init.sh` + `claude-progress.txt` + `features.json` JSON ledger (~200 entries marked `passes: false`); coding agent picks one feature at a time, runs end-to-end test before touching new feature.
- **JSON not Markdown for state files** (Anthropic finding: Claude less likely to silently rewrite JSON).
- **Aggressive prompt caching** with **single explicit cache breakpoint** at end of `[tools + system + PRD + DECISIONS]` block (~33K tokens, 1h TTL). Vertex AI does NOT support automatic caching.
- **4-tier subagent orchestration**: Orchestrator (Opus) → Planner (Opus) → Implementer (Sonnet, isolated worktree) → Reviewer (Opus + code-review-excellence) + Evaluator (general-purpose).
- **Anti-collision discipline**: every subagent dispatch includes orchestrator-injected `DECISIONS.md`; mandatory `gaps.md` section in every subagent return.
- **9 DAPLab failure-pattern counters** (1:1 mapped to sprint discipline + Atelier-product PIP questions).
- **Ralph Loop "DONE" token**: Reviewer subagent must emit strict "DONE" before any merge; no DONE = loop continues.
- **Compile-then-commit**: mypy strict + import-clean + pytest -x before any commit.
- **Lockfile-only installs**: `pip install -r requirements.lock`, no ad-hoc; defends against slopsquatting (LiteLLM Mar 2026 incident).
- **No `--no-verify` ever; no `force-push` / `reset --hard` / uninstrumented `rm` without explicit human approval.**
- **No silent error suppression**: bare `except:` and silent `pass` banned via Ruff E722 + custom AST check pre-commit.
- **Daily cost ledger** with cache-hit-rate tracking; if hit-rate < 85%, prefix is drifting — fix before continuing.
- **Three grader types** (code-based + model-based + human) per Anthropic Jan 2026 published taxonomy.
- **Eval-driven development**: 6 eval surfaces with explicit cadences; results published to `bench.atelier.dev` + `calibration.atelier.dev`.
- **Multi-session continuity**: 90-second session restoration ritual; `RESUME-HERE` markers in CHECKPOINTS.md.
- **Recursive discipline**: the same patterns we use to build Atelier, Atelier ships to users via N12 RLRD.

---

## 12. MVP scope (52 deliverables)

Full table in companion doc: `docs/superpowers/specs/2026-05-14-atelier-mvp-scope.md` (to be authored as first deliverable in writing-plans output). Summary by category:

- **Atomic 8-node DAG** (9 deliverables, all P0)
- **Outer Campaign Orchestrator** (6 deliverables, all P0)
- **Pre-Generation Intake Protocol** (5 deliverables, all P0; visual options behind feature flag for Phase 1.5)
- **Production-grade SaaS layer** (15 deliverables, all P0)
- **Public artifacts live by Jun 3** (17 deliverables: bench/calibration/docs/marketing/status sites + GitHub repo + arXiv preprint + 4-min demo + Loom walkthrough + 6 Atelier Skills + Convergence Spec RFC + npm package + GitHub Action + Figma plugin (P1) + Chrome extension (P1) + Privacy/ToS + bug bounty)

**Out-of-MVP (designed-for, deferred to Phase 2):** Per-tenant CMEK on Agent Engine, HIPAA tenants, Multiplayer dashboard annotation, Voice input, Sketch-to-UI dedicated upload, Multi-region active-active failover, Discord community, SOC 2 Type 2 certification.

---

## 13. Repository structure

Full tree in companion doc: `docs/superpowers/specs/2026-05-14-atelier-repo-structure.md`. Top-level summary:

Monorepo at `github.com/Manzela/atelier` (Apache-2.0). Three subfolders: `atelier-core/` (engine), `atelier-eval/` (eval suite + benchmarks), `atelier-deploy/` (infra-as-code + Docker + CI). Plus `atelier-dashboard/`, `atelier-action/`, `atelier-figma-plugin/`, `atelier-chrome-extension/`.

Full SDLC documentation: README + CHANGELOG + ROADMAP + SECURITY + CONTRIBUTING + CODE_OF_CONDUCT + GOVERNANCE + LICENSE + NOTICE + ADRs (10+) + runbooks + conventions + eval/data docs.

---

## 14. CI/CD (GitHub Actions)

| Workflow      | Trigger                   | Steps                                                                                                                                          | Gate                                                  |
| ------------- | ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| `ci.yml`      | every PR + push           | lint + typecheck + unit + integration + security (CodeQL, secret scan, license) + build                                                        | All green or PR blocked                               |
| `eval.yml`    | nightly + on-tag          | full WebGen-Bench (484) + Design2Code (484) + calibration golden set + adversarial set; results to bench.atelier.dev + calibration.atelier.dev | Nightly: alerts. On-tag: blocks release if regression |
| `deploy.yml`  | on-tag                    | Cloud Build → Artifact Registry → Workload Identity Federation → staging → smoke → manual approval → prod                                      | Manual approval before prod                           |
| `release.yml` | on push to main           | release-please: scan Conventional Commits → bump version → CHANGELOG → GitHub Release → publish npm                                            | Auto                                                  |
| `docs.yml`    | on push to main + docs PR | mkdocs build → Firebase Hosting deploy                                                                                                         | Auto                                                  |

Pre-commit hooks: ruff format + check, mypy strict, prettier + eslint, pytest fast subset, commitlint, detect-secrets, markdownlint.

---

## 15. 21-day sprint plan

Full day-by-day plan in companion doc: `docs/superpowers/plans/2026-05-14-atelier-sprint-plan.md` (output of writing-plans skill). Summary:

- **Week 1 (May 15-21)**: Foundation. Day-by-day deliverables. Gate: end-to-end on 1 surface, deployed to staging.
- **Week 2 (May 22-28)**: 10× mechanisms. EvoDesign + ConsensusAgent + Campaign Orchestrator + PIP. Gate: 12-surface autonomous campaign + WebGen-Bench ≥ 51 + 5 beta tenants.
- **Week 3 (May 29 - Jun 4)**: Production polish + 10× validation. Per-project judge LoRA fine-tune, Open Eval Adapters, Skills Pack, marketing site, arXiv preprint, demo recording, submission package.
- **Submission filed Jun 3 noon** (2 days early).

**Cost targets**: $1,200 by end W1; $2,500 by end W2; $5,000 by end W3.

---

## 16. 10× outcome checklist

Full table in companion doc: `docs/superpowers/specs/2026-05-14-atelier-10x-checklist.md`. 12 quantitative targets + 13 novel-contribution validations + submission completeness checklist. Each item has an evidence file path or URL — pass/fail is verifiable, not subjective.

---

## 17. Pre-launch checklist

Full list in companion doc: `docs/superpowers/specs/2026-05-14-atelier-prelaunch-checklist.md`. All items live by Jun 3 (32 artifacts: 5 public sites + GitHub repo + Identity Platform + Apigee + Cloud Run + Vertex AI tuning + Vertex AI Endpoints + BigQuery + Cloud KMS + Cloud Monitoring + Cloud Scheduler + Stripe + Telegram bot + CLI + Atelier Skills Pack + Convergence Spec RFC + npm constitution package + GitHub Action + Figma plugin + Chrome extension + arXiv preprint + 4-min demo + 90-sec Loom + Privacy/ToS + bug bounty + Co-marketing 1-pager + ≥3 designer testimonials + ≥500 waitlist signups).

---

## 18. Launch motion

Full timeline in companion doc: `docs/superpowers/specs/2026-05-14-atelier-launch-motion.md`. Sequence: Jun 3 noon submission filed early; Jun 3 PM Twitter announcement thread; Jun 4 AM Hacker News Show HN; Jun 4 PM Product Hunt scheduled; Jun 5 AM PT Product Hunt live + Calendly office hours bookable throughout; Jun 6-12 weekly newsletter to waitlist + outreach to Google Cloud DA + guest posts in AI/UI publications (Smashing Magazine, A List Apart, CSS Tricks, Vercel blog) + Discord community launch (post-launch +1).

---

## 19. Risk register

Full register in companion doc: `docs/superpowers/specs/2026-05-14-atelier-risk-register.md`. Highest risks summarized:

| Risk                                              | Probability | Impact   | Mitigation                                                                        |
| ------------------------------------------------- | ----------- | -------- | --------------------------------------------------------------------------------- |
| Vertex AI quota for Gemini 3.1 Pro denied/delayed | Medium      | High     | File request D2; fallback to Gemini 3.0 Flash for Generator until granted         |
| Stitch MCP rate-limited during live demo          | High        | Medium   | Pre-recorded backup demo segments; live Atelier with Gemini direct fallback       |
| WebGen-Bench score doesn't beat 51.9              | Medium      | High     | MVP target is ≥51 (matches SOTA); alternative pitch leans on 12 other 10× axes    |
| Daniel sick / unavailable on Jun 5                | Low         | Critical | Pre-record demo Jun 3; submission already filed Jun 3; Calendly bookable          |
| Critical Anthropic harness regression             | Low         | High     | Buffer 1 day per sprint week for diagnosis; suspect harness/cache before our code |
| Cost overrun on $5K Opus                          | Medium      | Medium   | Daily ledger check; downgrade routine work to Sonnet; cache-hit-rate watch        |
| G4S 2026 rules differ from 2025                   | Medium      | Medium   | Read 2026 rulebook D1; adjust within 24h if material shift                        |
| Live launch day Cloud Run / Vertex outage         | Low         | High     | Status page + Telegram alerts; backup region (europe-west4); manual fallback      |

---

## 20. Out of scope (this MVP)

- Per-tenant CMEK on Agent Engine (Cloud Run + KMS-encrypted Firestore path exists; activates with first regulated tenant)
- HIPAA / regulated tenants (waits for CMEK)
- Multiplayer real-time annotation on dashboard (single-user dashboard ships; multiplayer week-of-launch+1)
- Voice input parity with Stitch's "vibe design" (text + image + descriptor in MVP; voice via Gemini 3 audio in Phase 2)
- Sketch-to-UI dedicated upload (image input via Gemini 3 vision covers most use cases in MVP)
- Multi-region active-active failover (single-region per geography in MVP; multi-region Phase 2)
- Discord community (GitHub Discussions covers MVP; Discord post-launch)
- SOC 2 Type 2 certification (Vanta evidence collection scaffolded day-0; certification month 6)
- Stripe billing actually-charging users (scaffolded + tiers visible at launch; real billing month 6 with SOC 2)

---

## 21. Failure-handling trichotomy (explicit)

Per AutonomousAgent ADR pattern: every Atelier operation maps to exactly one of three failure modes. **Never invent a fourth.** User-facing rule: agent **always acknowledges degradation** — trust > apparent capability.

| Mode                                                | When to use                                                                                                    | Examples in Atelier                                                                                                                                                                                                                                                                                       |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Fail-loud** (alert + halt)                        | Security failures, budget breach, data corruption, training cost overruns, judge calibration drift > threshold | Scrubber blocked secret leak; Apigee budget cap hit; BigQuery KMS key missing; LoRA training cost overrun mid-run; calibration golden set drops > 3% correlation                                                                                                                                          |
| **Fail-soft** (degrade + log + acknowledge to user) | Tool errors, transient unavailability, snapshot failure, single trajectory drop                                | Stitch MCP rate-limited (fall back to direct Gemini); Memory Bank temporarily unreachable (operate without cross-session); Lighthouse timeout (use cached score); single judge axis times out (proceed with partial consensus + flag); A2UI renderer unavailable for one target (render others, note gap) |
| **Self-heal** (retry silently with bounded backoff) | Transient 429/503, rate limits, container restarts within frequency budget                                     | Vertex AI 429 → exponential backoff per `limits.retries.vertex_*`; Cloud Run cold-start; transient OTel collector unavailability                                                                                                                                                                          |

Hard cap: **3 self-heal retries per operation**, then escalate to fail-soft. **No silent suppression.** Bare `except:` and silent `pass` are banned via Ruff E722 + custom AST check pre-commit (per Strategy v2 invariants).

---

## 22. Panic + Resume CLI (production safety primitives)

Mirrors hermes-agent's panic/resume pattern. Production-grade autonomy requires both.

### `atelier panic` — halt all in-flight work

```bash
atelier panic [--teardown]
```

Effects:

- Halts all in-flight tool calls + pending convergence loops
- Drains queued nudges
- Refuses new requests at API layer (HTTP 503)
- Snapshots in-flight session state to GCS
- Posts status to Telegram
- `--teardown`: also stops Cloud Run jobs entirely (full stop)

Restricted to authenticated user_id matching tenant owner OR project admin role.

### `atelier resume` — restart after panic

```bash
atelier resume [--from-snapshot=<gcs-path>]
```

Effects:

- Re-enables API layer
- Restores in-flight session state from latest snapshot (or specified snapshot)
- Re-queues nudges with restored cron schedule
- Posts "resumed" status to Telegram

### Telegram-side panic

`/panic` via Telegram from authenticated user → same effect as CLI `atelier panic` (without `--teardown`).

`/resume` via Telegram → same effect as CLI `atelier resume`.

---

## 23. Pending user-manual actions (gate progression blockers)

Lists what blocks each phase gate from progressing. Updated as items resolve.

### Pre-Sprint (must complete by 2026-05-15 D1 of sprint)

| #   | Action                                                                                                                                                                         | Owner  | Blocking gate                     |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------ | --------------------------------- |
| P-1 | File Vertex AI quota request: Gemini 3.1 Pro provisioned throughput                                                                                                            | Daniel | Sprint D5 (Generator integration) |
| P-2 | File Agent Engine session-write quota increase (default 100/min/region → request 1000/min/region)                                                                              | Daniel | Sprint D7 (multi-tenant deploy)   |
| P-3 | Activate Tier 1 models in Vertex AI Model Garden: Haiku 4.5, Gemini 3.1 Pro, Gemini 3 Flash, Gemini 3 Flash-Lite, text-embedding-005, multimodal-embedding, Gemma 4 26B-A4B-it | Daniel | Sprint D5+                        |
| P-4 | Confirm Vertex AI Endpoints with Multi-Tuning is enabled                                                                                                                       | Daniel | Sprint W2 (LoRA serving)          |
| P-5 | Confirm Vertex AI Tuning Manager is enabled                                                                                                                                    | Daniel | Sprint W3 (DPO + LoRA fine-tune)  |
| P-6 | Read G4S 2026 official rulebook (publishes ~late May 2026)                                                                                                                     | Daniel | Sprint W3 (submission package)    |

### Pre-Beta (must complete by 2026-05-28 W2 gate)

| #   | Action                                                                               | Owner             |
| --- | ------------------------------------------------------------------------------------ | ----------------- |
| B-1 | Identity Platform tenant configuration + sign-in providers (Google + GitHub + email) | Daniel            |
| B-2 | Designer-in-residence outreach (target 5 designers, capture 3+ testimonials)         | Daniel            |
| B-3 | Privacy Policy + ToS legal-template review (Termly or iubenda)                       | Daniel + attorney |

### Pre-Launch (must complete by 2026-06-03 submission)

| #   | Action                                                                                    | Owner           |
| --- | ----------------------------------------------------------------------------------------- | --------------- |
| L-1 | Co-marketing 1-pager sent to Google Cloud DA (Steren Giannini, Romin Irani, or Allen Day) | Daniel          |
| L-2 | arXiv preprint draft submitted                                                            | Daniel + Claude |
| L-3 | 4-min demo video recorded (vertical + horizontal) + 2-min backup + 60-sec elevator pitch  | Daniel + Claude |
| L-4 | Twitter announcement thread drafted (12 tweets)                                           | Daniel + Claude |
| L-5 | Hacker News Show HN post drafted                                                          | Daniel + Claude |
| L-6 | Product Hunt launch scheduled                                                             | Daniel          |
| L-7 | Calendly office hours configured (Jun 5 throughout day)                                   | Daniel          |
| L-8 | ≥500 waitlist signups target (via build-in-public Twitter thread)                         | Daniel          |

---

## 24. How to resume after context loss

If you (future-you, or a new agent, or a new contributor) come to this project with no conversation history:

```bash
cd "/Users/danielmanzela/Professional Profile/atelier"

# 1. Read this PRD first (you're reading it now)
# 2. Read companion docs (in order):
#    - docs/superpowers/specs/2026-05-14-atelier-strategy-v2.md
#    - docs/superpowers/specs/2026-05-14-atelier-mvp-scope.md
#    - docs/superpowers/specs/2026-05-14-atelier-10x-checklist.md
#    - docs/superpowers/plans/2026-05-14-atelier-sprint-plan.md
# 3. Read all ADRs in numerical order: docs/decisions/0001 → 0010+

# 4. Read sprint state (current snapshot):
cat docs/sprint/STATUS.md            # what's happening right now
cat docs/sprint/BLOCKERS.md          # active escalations
tail -100 docs/sprint/CHECKPOINTS.md  # most recent checkpoint(s) with RESUME-HERE
tail -20 docs/sprint/REJECTED.md     # don't re-attempt these
tail -7 docs/sprint/COST_LEDGER.md   # last week's burn rate

# 5. Read Anthropic harness state:
cat features.json | jq '.[] | select(.passes == false) | .id' | head -10
tail -50 claude-progress.txt

# 6. Verify git state matches expectations:
git log --oneline -20
git status
git diff --stat
git worktree list  # confirm phase worktrees
git branch -a      # confirm phase/N branches

# 7. Verify CI green:
gh run list --limit 5

# 8. Verify tests pass:
cd atelier-core && pytest tests/unit/ -v --no-header
cd ../atelier-eval && pytest tests/ -v --no-header

# 9. Identify which Pending Actions (§23 above) remain open

# 10. Begin work — first commit of session updates STATUS.md
```

**If state files are missing or corrupted**: `git log --all --oneline` is the source of truth. Reconstruct STATUS.md from the most recent commits.

---

## 25. Implementation deviations log (template)

Track every faithful-to-intent deviation from the spec made during implementation. Spec stays canonical; deviations get explanations + rationale. **Pattern from AutonomousAgent SESSION-COMPLETE doc §7.4.**

```markdown
## Deviation log

### YYYY-MM-DD — <short title>

**Spec section affected**: §X.Y
**What the spec says**: <verbatim or summary>
**What was implemented**: <verbatim or summary>
**Why the deviation was necessary**: <root cause>
**Faithfulness justification**: <why this preserves the spec's intent>
**Action**: <update spec to match | leave deviation, document only | revert and find another path>
**Owner**: <who decides>
```

Live at `docs/sprint/DEVIATIONS.md`. Reviewed at every weekly checkpoint. Spec updates are committed as `docs(spec): update §X.Y to match deviation YYYY-MM-DD`.

---

## 26. Glossary

Project-specific terms defined here. **If a term appears in code or docs that isn't in this glossary, add it.**

| Term                      | Meaning                                                                                                                                                                                                               |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Atelier**               | This project — autonomous design agent for the Google for Startups AI Agents Challenge 2026                                                                                                                           |
| **A2UI v0.9**             | Google's framework-agnostic protocol for agents to render UI into existing React/Flutter/Lit/Angular component catalogs (released Apr 17, 2026)                                                                       |
| **ADK 2.0 Beta**          | Google Agent Development Kit v2.0 Beta (`pip install google-adk --pre`) — provides `SequentialAgent`, `ParallelAgent`, `LoopAgent`, `MCPToolset`, `rubric_based_*` evaluators                                         |
| **Apigee AI Gateway**     | Google's first-class ADK model integration layer; per-tenant rate limit + cost router + Sanitize policies (Model Armor)                                                                                               |
| **BriefSpec**             | Immutable JSON spec produced by PIP, frozen at user approval; what the agent commits to for the duration of the project                                                                                               |
| **Campaign**              | A multi-surface user request (e.g., "redesign 50-page SaaS dashboard") — distinct from atomic tasks; managed by Campaign Orchestrator                                                                                 |
| **Campaign Orchestrator** | Atelier's outer layer (N12 RLRD) that decomposes campaigns into Surface Manifest, picks unblocked surfaces, validates cross-surface coherence, persists state across sessions                                         |
| **CSC-D**                 | Constitutional Self-Critique for Design (N6) — agent self-grades each generated candidate against the 12-principle Apple-Grade constitution before deterministic gate                                                 |
| **D-O-R-A-V**             | Design rubric: Brand-fidelity, Originality, Relevance, Accessibility, Visual-clarity (analog to agent-dag-pipeline's O-R-A-V)                                                                                         |
| **DEMAS-D**               | Design Evaluation with Multi-Axis Provenance (N2) — per-axis Provenance Matrix preventing judge attention dilution                                                                                                    |
| **DGF-D2C**               | Deterministic-Gate-First Design-to-Convergence (N1) — process supervision with deterministic preconditions                                                                                                            |
| **EvoDesign**             | AlphaEvolve-inspired evolutionary K-candidate search (N5) inside the convergence loop                                                                                                                                 |
| **GEAP**                  | Gemini Enterprise Agent Platform — Google rebrand at Cloud Next '26 (Apr 23, 2026) of Vertex AI Agent surfaces                                                                                                        |
| **GEPA**                  | The prompt optimizer Google ships in `adk optimize`; we wrap it as the Hebbian Mutator backend                                                                                                                        |
| **Hebbian Mutator**       | Failure-pattern → mutation operator mapping for prompt patches between full LoRA retrainings (PerJudge component)                                                                                                     |
| **N1-N13**                | Atelier's 13 novel contributions; see §5                                                                                                                                                                              |
| **PADI**                  | Project-Agnostic Descriptor Inference (N4) — adapts to any tech stack with optional `.atelier.yaml` descriptor                                                                                                        |
| **PerJudge**              | Per-Project DPO Judge (N3) — LoRA fine-tunes the judge on each project's accumulated DPO preference pairs via Vertex AI Endpoints + Multi-Tuning                                                                      |
| **PIP**                   | Pre-Generation Intake Protocol (N13) — adaptive-depth, DAPLab-pattern-mapped, visual-option-driven, skip-when-answered intake before any generation                                                                   |
| **Provenance Matrix**     | Per-axis filter that gives each judge ONLY its relevant ground-truth variables (not the full DOM) — prevents attention dilution                                                                                       |
| **RLRD**                  | Recursive Long-Running Discipline (N12) — Atelier ships the same long-running-agent harness pattern (Anthropic Nov 2025) it uses to be built                                                                          |
| **Surface**               | A single page / component / template / screen — atomic unit of design work                                                                                                                                            |
| **Surface Manifest**      | JSON ledger of all surfaces in a campaign, with dependency graph                                                                                                                                                      |
| **Two-prompt harness**    | Anthropic's published long-running-agent pattern: initializer agent (one-time setup) + coding agent (per-session, one feature at a time, end-to-end test before next)                                                 |
| **Wrap-don't-fork**       | Architectural principle from AutonomousAgent ADR 0001: consume upstream via lockfile-pinned dependencies + wrap with our deployment/config/security/observability; never modify upstream internals                    |
| **Worktree-per-phase**    | Branching pattern from AutonomousAgent ADR 0007: `main` holds only accepted work; each phase gets a long-running branch in `.worktrees/phaseN/`; merged via `--no-ff` after acceptance gate; tagged `phaseN-accepted` |

---

## 27. limits.yaml — single source of truth for tunables

Mirroring hermes-agent's pattern. JSON-schema-validated at startup. Runtime-tunable. Lives at `atelier-deploy/config/limits.yaml`.

```yaml
budget:
  daily_usd_cap: 100 # platform-level cap, enforced at Apigee
  per_session_usd_cap: 0.50 # MVP target; 0.10 with judge LoRA (Phase 2)
  per_tenant_monthly_usd_cap: null # populated per tenant tier (Free=$0, Pro=$20, Team=$50/seat)
  alert_at_pct: 75

retries:
  vertex_max_attempts: 5
  vertex_initial_backoff_s: 1
  vertex_max_backoff_s: 60
  vertex_jitter_pct: 25
  stitch_mcp_max_attempts: 3
  stitch_mcp_fallback: gemini_direct # if Stitch fails N times, use direct Gemini call

agent:
  max_outer_loop_iterations: 8
  max_evodesign_k: 6
  max_det_loop_iterations: 5
  max_judge_loop_iterations: 3
  max_concurrent_surfaces_per_campaign: 3
  max_session_duration_s: 1800 # 30 min hard cap
  max_campaign_duration_h: 72 # 3 days hard cap

evodesign:
  k: 6 # K candidates per iteration
  mutation_operators: # all 8 named operators
    - token_swap
    - layout_swap
    - typography_swap
    - motion_swap
    - density_shift
    - asymmetry_injection
    - hierarchy_restructure
    - copy_voice_shift
  crossover_enabled: false # Phase 2

deterministic_gates:
  lighthouse_a11y_min: 90
  lighthouse_perf_min: 90
  lighthouse_bp_min: 90
  axe_max_violations: 0
  visual_diff_max_pct: 2.0
  responsive_breakpoints: [375, 768, 1280, 1920]
  semantic_html_strict: true
  token_fidelity_strict: true # any hex outside DESIGN.md = fail

judges:
  d_orav_score_floor: 0.7
  d_orav_axis_floor: # per-axis minimums (any below = REJECT)
    brand_fidelity: 0.7
    originality: 0.6
    relevance: 0.7
    accessibility: 0.8
    visual_clarity: 0.7
  consensus_confidence_min: 0.6 # Bayesian CI lower bound
  judge_models:
    brand: 'gemini-3-flash' # Phase 1; per-project LoRA in Phase 2
    copy: 'gemini-3-flash'
    motion: 'gemini-3-flash'
    token_fidelity: 'gemini-3-flash'
    coherence: 'gemini-3-flash'

csc_d:
  calibration_kappa_min: 0.7 # Cohen's κ vs human rubric
  calibration_check_every_n_calls: 100
  constitution_path: '@atelier/constitution-apple-grade' # npm package

intake:
  pip_enabled: true
  visual_options_enabled: false # Phase 1.5 feature flag
  skip_paths:
    - descriptor # .atelier.yaml
    - memory_bank # prior project answers
    - brief_parsed # answers in free-form brief
  question_catalog_version: 'v1'

campaign:
  max_surfaces: 200 # hard cap
  cross_surface_pattern_reuse_min: 0.30
  coherence_check_top_n_similar: 5
  fail_policy_default: 'best_effort_and_flag' # skip | ask_help | best_effort_and_flag

slos:
  agent_success_rate_min: 0.95
  p95_turn_latency_s_max: 8
  p95_session_latency_s_max: 240
  judge_pass_rate_min: 0.65
  first_shot_convergence_rate_min: 0.40 # PIP active
  campaign_surface_convergence_rate_min: 0.85
  cost_per_session_usd_max: 0.50

approval:
  always_ask_patterns:
    - 'rm -rf'
    - 'git push --force'
    - 'DROP TABLE'
    - 'DELETE FROM'
    - 'kubectl delete'
  never_ask_patterns:
    - 'ls *'
    - 'cat *'
    - 'git status'
    - 'git log*'
    - 'rg *'
  default_for_unknown: ask
  approval_timeout_s: 300

dpo_rewards:
  weights:
    user_explicit_accept: 1.0 # user clicked "ship it"
    user_implicit_accept: 0.3 # user didn't reject within 24h
    judge_self_consistency: 0.2 # generator agreement with judge across iterations
    convergence_completion: 0.5 # session reached convergence vs timeout
  reward_horizon_iterations: 8
  exclude_session_if_lt_iterations: 3

dpo_training:
  enabled: false # Phase 1 ships disabled; flipped at Phase 2 first-project LoRA
  trigger_check_cron: '0 12 * * *'
  preflight:
    min_dpo_pairs_per_project: 50
    min_mean_margin: 0.20
    min_days_since_last_run: 3
    require_eval_baseline_exists: true
    require_reward_sanity_score_min: 0.7
  approval:
    require_admin_approval: true
    approval_timeout_h: 12
  guardrails:
    max_runs_per_project_per_month: 4
    max_run_duration_h: 6
    base_model: 'gemma-4-26b-a4b-it'
    abort_if_eval_regresses_pct: 5
  post_training:
    auto_register_if_eval_improves_pct: 2
    auto_swap_in_endpoint_if_eval_improves_pct: null # null = always require admin

calibration:
  golden_set_size: 100 # frozen tasks
  recalibration_cron: '17 3 * * 1' # weekly Mon 03:17 UTC
  drift_alert_correlation_drop: 0.05 # alert if week-over-week corr drops > 5%

trajectories:
  bigquery_partition_by: 'DATE(ts)'
  bigquery_cluster_by: ['tenant_id', 'project_id']
  hot_retention_days: 90
  gcs_coldline_after_days: 90
  delete_after_days: 365
  per_subject_kms_key: true
  sample_pct_for_rl_training: 10

alerts:
  budget_pct_of_daily_cap: [50, 75, 90, 100]
  budget_pct_of_monthly_cap: [75, 90, 100]
  agent_heartbeat_missed_count: 3
  cloud_run_unreachable_min: 5
  vertex_error_rate_5min: 0.20
  apigee_error_rate_5min: 0.20
  scrubber_secret_leak_attempts_per_hour: 1
  judge_calibration_drift_pct: 5
  campaign_failure_rate_per_hour: 5

notify_channels:
  telegram_chat_id: null # set after Telegram bot creation
  cloud_monitoring_email: null
  pagerduty_routing_key: null # opt-in for enterprise tier

log_retention:
  cloud_logging_days: 30
  cloud_logging_to_gcs_coldline_after_days: 30
  cloud_logging_delete_after_days: 365
  trace_sampling:
    head_sample_rate: 1.0
    tail_sample_errors: true
    tail_sample_slow_p99: true

local_logs_dev:
  rotate_size_mb: 100
  keep_files: 5
```

JSON schema at `atelier-deploy/config/limits-schema.json`. Validator at `atelier-core/src/atelier/shared/limits_validator.py`. **Bad values fail-loud at startup** — Atelier refuses to start.

---

## 28. Worktree-per-phase branching (sprint discipline)

Per AutonomousAgent ADR 0007 lineage. Adapted for Atelier's 3-week phased sprint.

```
github.com/Manzela/atelier/                     ← branch: main (accepted-only)
├── .worktrees/                                 ← gitignored
│   ├── phase1-foundation/                      ← branch: phase/1
│   ├── phase2-10x-mechanisms/                  ← branch: phase/2 (created when phase/1 accepted)
│   └── phase3-production-polish/               ← branch: phase/3 (created when phase/2 accepted)
```

**Branching rules:**

- `main` holds **only accepted-and-tagged** work (`phase1-accepted`, `phase2-accepted`, `phase3-accepted`, `v1.0.0`)
- All phase work happens in `.worktrees/phaseN-<name>/` on branch `phase/N`
- After acceptance gate passes:

  ```bash
  git checkout main
  git merge --no-ff phase/N -m "Merge phase/N: <gate description>"
  git tag -a phaseN-accepted -m "Phase N accepted on $(date -u +%Y-%m-%d). All gate criteria passed."
  git push origin main --tags
  ```

- Hotfixes: branch from `main` as `hotfix/<short-desc>`, merge back to `main` + cherry-pick to active phase branch

**Why**: enforces phase isolation per ADR 0006 lineage; multiple phases can have concurrent worktrees if needed; `main` is always shippable; clean acceptance boundary.

---

## 29. Open items / will-evolve

- **G4S 2026 official judging rubric**: not yet published; assume 2025 criteria (technical novelty, agentic depth, real-world impact, demo quality, Use of Google Cloud) and adjust D1 of sprint when 2026 rules drop
- **Gemini 3.1 Pro Provisioned Throughput quota**: needs Google approval before public load; file D2
- **Agent Engine session-write quota**: default 100/min/region; file increase D2
- **Designer-in-residence outreach**: 3-5 testimonials targeted; outreach week 2
- **Co-marketing 1-pager to Google Cloud DA**: send week 1, follow-up week 2-3
- **arXiv preprint authorship**: Daniel as first author, Claude listed in acknowledgments per Anthropic guidance
- **N9 Open Eval Adapters**: target 5 benchmarks (WebGen-Bench, Design2Code, Web2Code, ScreenSpot, FrontendBench); MVP minimum is 3
- **Convergence Spec RFC v0.1**: drafted in repo; finalize as community W3C-style group post-launch

---

## Appendix A — ADR list (10+ initial ADRs)

1. ADR-0001: Fork agent-dag-pipeline ADK plumbing as base (~75% reuse)
2. ADR-0002: Cloud Run (not Agent Engine) for runtime; Agent Engine for Sessions + Memory Bank only
3. ADR-0003: Tiered sandboxing inherited from hermes-agent (5 tiers)
4. ADR-0004: Pre-Generation Intake Protocol (PIP) as first-class layer above Campaign Orchestrator
5. ADR-0005: Recursive Long-Running Discipline (RLRD) — Atelier ships the same patterns it consumes
6. ADR-0006: Google-native stack (no Langfuse, no Statsig, no PostHog, no GKE for S-LoRA)
7. ADR-0007: Evolutionary K-candidate search (K=6 MVP) inside LoopAgent
8. ADR-0008: Multi-judge Bayesian-weighted consensus (5 specialized judges + DEMAS-D Provenance per axis)
9. ADR-0009: Public calibration dashboard at calibration.atelier.dev as transparency commitment
10. ADR-0010: A2UI v0.9 as canonical output protocol (React + Flutter + Lit + Angular renderers)

---

## Appendix B — Demo gambit (4-minute video script)

| Time      | Action                                                                                                                                                                                                                                                                                                              |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0:00–0:30 | "Real designer brief: redesign all 12 pages of pipeline-observatory. We sent it to Stitch, Vercel v0, and Atelier."                                                                                                                                                                                                 |
| 0:30–1:30 | Stitch + v0 generate page 1 immediately (text-only one-shot, "Vibe Check" required). Atelier opens PIP — 5 questions, visual options, 90 seconds. User picks editorial register, Apple-Grade tokens (existing DESIGN.md detected), production convergence bar. BriefSpec rendered. User clicks Approve.             |
| 1:30–2:30 | Atelier dashboard live: 12-surface campaign in flight; surfaces 1-3 converged green; surface 4 in EvoDesign loop with K=6 candidates; Cross-Surface Coherence Validator highlights pattern reuse; Hebbian mutator fires on contrast failure. Time-machine view shows full iteration tree. All 12 surfaces converge. |
| 2:30–3:00 | Project-history view: "Atelier ran 17 sessions on this project. Watch the judge's preferences evolve." DPO loss curve, pattern-reuse rate climbing, time-to-convergence dropping iteration over iteration.                                                                                                          |
| 3:00–3:30 | A2UI render: same 12 converged surfaces simultaneously in React, Flutter, Lit, Angular hosts.                                                                                                                                                                                                                       |
| 3:30–4:00 | Scoreboard: Claude-3.5 26.4 / WebGen-Agent 51.9 / **Atelier ≥ 60 single-surface, ≥ 85% surface convergence on 12-surface campaign, ≥ 50% first-shot convergence rate**.                                                                                                                                             |

---

## Appendix C — Pitch lines

- **Tagline**: "Stitch generates. Atelier asks, converges, learns."
- **One-sentence**: "The first autonomous design agent that asks the right questions, converges on flawless UI/UX across multi-axis judged criteria, and gets sharper with every iteration."
- **Technical pitch**: "Process supervision with deterministic preconditions and per-project DPO judging — for autonomous UI/UX convergence at >2× SOTA — built on Google ADK 2.0 + Vertex AI + Stitch MCP + A2UI v0.9, with the architecture validated in production at 73.5M agent operations / cycle in the author's 7-node DAG pipeline."
- **For Googlers**: "Atelier is the reference implementation that proves Google's GEAP + ADK + Memory Bank + A2UI stack can ship a self-improving, domain-specialized, public-launch autonomous agent in 3 weeks."

---

## Appendix D — References

- Anthropic, _Effective harnesses for long-running agents_ (Nov 26, 2025)
- Anthropic, _Effective context engineering for AI agents_ (Sep 29, 2025)
- Anthropic, _Demystifying evals for AI agents_ (Jan 9, 2026)
- Anthropic, _2026 Agentic Coding Trends Report_
- Anthropic, Claude Code post-mortem (April 2026)
- Columbia DAPLab, _9 Critical Failure Patterns of Coding Agents_ (Jan 2026)
- Google ADK 2.0 Beta documentation, `adk.dev/2.0/`
- Google Cloud, _Gemini Enterprise Agent Platform_ (rebranded Apr 23, 2026)
- Google Labs, _Stitch_ (Mar 18, 2026 repositioning)
- Google, _A2UI v0.9_ (Apr 17, 2026)
- DeepMind, _AlphaEvolve_ (closest precedent for self-improving agents)
- Stanford SALT-NLP, _Design2Code_ (NAACL 2025)
- Luzimu et al., _WebGen-Bench_ (NeurIPS 2025)
- _DesignPref_ (Nov 2025 — α=0.25 personalization-over-aggregation finding)
- _DPO with LLM-Judge for Computer-Use Agents_ (arXiv 2506.03095)
- Nous Research, _Hermes Agent_ (https://hermes-agent.nousresearch.com)
- Nous Research, _Atropos GRPO + LoRA_
- Daniel Manzela, `agent-dag-pipeline` (Apache-2.0, github.com/Manzela/agent-dag-pipeline)
- Daniel Manzela, `pipeline-observatory` (live demo at manzela.github.io/pipeline-observatory/)
- Daniel Manzela, `Resume CV/00-GROUND-SOURCE-OF-TRUTH.md` (production scale: 11 retailers, 73.5M agent ops/cycle, $0.0006/PDP, top-100 retail-tech 2025)
- Galileo, _Why LLM-as-a-Judge Fails_ (judge calibration drift report)
- Replit DB-deletion incident (Lemkin/SaaStr, Jul 2025)
- OWASP Multi-Tenant Security Cheat Sheet
- W3C Design Tokens Format Module

---

**End of PRD.**
