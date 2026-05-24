# Atelier

> **The first autonomous design agent that asks the right questions, converges on flawless UI/UX across multi-axis judged criteria, and gets sharper with every iteration. Stitch generates. Atelier asks, converges, learns.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Node 20.11+](https://img.shields.io/badge/node-20.11+-green.svg)](https://nodejs.org/)
[![Google ADK 2.0 Beta](https://img.shields.io/badge/Google_ADK-2.0_Beta-4285F4?logo=google)](https://adk.dev/2.0/)
[![Vertex AI](https://img.shields.io/badge/Vertex_AI-Deployable-34A853?logo=googlecloud)](https://cloud.google.com/vertex-ai)
[![A2UI v0.9](https://img.shields.io/badge/A2UI-v0.9-FF9800)](https://developers.googleblog.com/a2ui-v0-9-generative-ui/)
[![Conventional Commits](https://img.shields.io/badge/Conventional%20Commits-1.0.0-yellow.svg)](https://www.conventionalcommits.org/)

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│ Layer 3: PIP — Pre-Generation Intake Protocol  (N13)     │
│   Adaptive Q&A · visual options · skip-when-answered     │
│   → immutable BriefSpec.json + DECISIONS.md initialized  │
└──────────────────┬───────────────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 2: Campaign Orchestrator  (N12 RLRD)               │
│   Surface Manifest · Cross-Surface Coherence · Cloud     │
│   Scheduler + Cloud Tasks for multi-session orchestration│
└──────────────────┬───────────────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────────┐
│ Layer 1: Atomic 8-node DAG  (per-surface engine)         │
│  N1 Brief Parser → N2 Source Resolver →                  │
│  N3 EvoDesign LoopAgent (max_iter=N):                    │
│    N3a Generator (ParallelAgent K=6, Stitch MCP)         │
│    N3b CSC-D (Constitutional Self-Critique)              │
│    N3c Deterministic Gate (parallel × 6 axes)            │
│    N3d ConsensusAgent (5 specialized rubric judges +     │
│        DEMAS-D Provenance Matrix)                        │
│    N3e Fixer (Hebbian via adk optimize / GEPA)           │
│  → N4 Final Validator + A2UI Renderer                    │
└──────────────────────────────────────────────────────────┘
```

## What this is

Atelier is a self-improving autonomous design agent that **converges UI/UX work to flawless across multi-axis criteria** instead of generating one-shot output and stopping. Built on Google ADK 2.0 Beta + Vertex AI + Stitch MCP + A2UI v0.9, with architecture inspired by the production-validated 7-node Gate-Agent DAG in [`agent-dag-pipeline`](https://github.com/Manzela/agent-dag-pipeline) and the long-running-agent harness pattern from [Anthropic's published guidance](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) (Nov 2025).

Where every shipped autonomous-design tool today (Stitch, Vercel v0, Subframe, Lovable.dev, Replit Agent, Devin, Builder.io Fusion, Tempo Labs) terminates at _generation_ — Google's own Antigravity codelab calls the verification step **"Vibe Check"** (manual eyeballing) — Atelier:

1. **Asks the right questions** (PIP) — adaptive intake mapped 1:1 to the 9 documented coding-agent failure patterns, producing an immutable BriefSpec the agent commits to.
2. **Converges autonomously** (8-node DAG + EvoDesign + multi-judge consensus) — Lighthouse / axe / visual-diff / token-fidelity / responsive gates run _before_ any judge, then a 5-judge Bayesian-weighted consensus with per-axis Provenance Matrix evaluates the surviving candidates.
3. **Learns each project's preferences** (PerJudge + 3-tier DPO flywheel) — fine-tunes a per-project judge on accumulated accept/reject signals via Vertex AI Endpoints with Multi-Tuning.
4. **Handles multi-surface campaigns** (Campaign Orchestrator + RLRD) — redesign 50 pages, build a complete SaaS UI from scratch, audit a 200-page docs site — across multiple sessions with checkpoint resume.
5. **Renders to any framework** (A2UI-native) — same converged design output simultaneously in React, Flutter, Lit, Angular hosts.

## Key differentiators (13 novel contributions)

| #       | Contribution                                                                    | Defense                                                                                                                                                                                                                      |
| ------- | ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **N1**  | **DGF-D2C** — Deterministic-Gate-First Design-to-Convergence                    | Improves on WebGen-Agent (NeurIPS 2025 SOTA at 51.9%) by adding deterministic preconditions before any judge call. Eliminates judge attention dilution.                                                                      |
| **N2**  | **DEMAS-D** — Per-axis Provenance Matrix Design Judge                           | Each axis (a11y, brand, motion, copy, semantics, tokens) sees only its relevant ground-truth variables — never the full DOM.                                                                                                 |
| **N3**  | **PerJudge** — Per-Project DPO Judge with Hebbian Mutator + Few-Shot Cold-Start | Addresses DesignPref's α=0.25 finding (designer disagreement is intrinsic). Personalized judges win with 20× fewer examples.                                                                                                 |
| **N4**  | **PADI** — Project-Agnostic Descriptor Inference                                | Adapts to any tech stack with optional `.atelier.yaml` descriptor; full inference from path + intent.                                                                                                                        |
| **N5**  | **EvoDesign** — AlphaEvolve-Inspired Evolutionary K-Candidate Search            | First transfer of DeepMind's AlphaEvolve methodology to UI generation. K=6 candidates × 8 mutation operators per iteration.                                                                                                  |
| **N6**  | **CSC-D** — Constitutional Self-Critique for Design                             | Self-grades each candidate against the 12-principle Apple-Grade constitution before deterministic gate fires.                                                                                                                |
| **N7**  | **A2UI-Native Output**                                                          | First autonomous design agent built on Google's A2UI v0.9 protocol from day one. Renders to React + Flutter + Lit + Angular simultaneously.                                                                                  |
| **N8**  | **Public Judge Calibration Dashboard**                                          | First commercial autonomous design agent to publish judge calibration externally as a transparency commitment. Defends against the calibration-drift problem 93% of teams hit.                                               |
| **N9**  | **Open Eval Adapters Library**                                                  | Apache-2.0 PRs to `google/adk-python` for WebGen-Bench, Design2Code, Web2Code, ScreenSpot, FrontendBench. Makes ADK the canonical evaluation runtime for the field.                                                          |
| **N10** | **Convergence Spec RFC**                                                        | Open standard: how an autonomous design agent declares convergence criteria, emits trajectories, reports calibration drift. Atelier is the reference implementation.                                                         |
| **N11** | **Public Eval Harness**                                                         | `bench.atelier.dev` accepts agent submissions from any vendor. Atelier becomes the standard evaluation surface for the entire UI-generation field.                                                                           |
| **N12** | **RLRD** — Recursive Long-Running Discipline                                    | Atelier-as-reference-implementation of Anthropic's published long-running agent harness for a domain-specific agent. The same patterns we use to build Atelier, we ship to users running multi-day, multi-surface campaigns. |
| **N13** | **PIP** — Pre-Generation Intake Protocol                                        | Adaptive-depth, DAPLab-pattern-mapped, visual-option-driven, skip-when-answered intake. First commercial autonomous design agent to ship structured pre-generation intake.                                                   |

## 10× thesis (5 quantified axes)

| #   | Axis                                       | Atelier MVP target                                                                              | Best commercial baseline                                       |
| --- | ------------------------------------------ | ----------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| 1   | Convergence quality at first declared-done | ≥ 95% (Lighthouse Perf/A11y/BP ≥ 90 · axe = 0 · visual-diff ≤ 2% · responsive on 4 breakpoints) | ~0% formal (no commercial tool gates)                          |
| 2   | Iterations to convergence                  | ≤ 3 autonomous loops                                                                            | Reflexion typical 5–10; commercial requires ~80+ human-bounded |
| 3   | Human-in-loop time                         | ≤ 60 sec to gate-passing output                                                                 | Subframe / v0 / Stitch: ~5–15 min per page                     |
| 4   | Cross-session pattern reuse                | ≥ 60% reuse rate after 100 sessions                                                             | 0% across commercial tools (no learning)                       |
| 5   | WebGen-Bench (NeurIPS 2025)                | ≥ +25 pts vs Claude-3.5 baseline (26.4 → ≥ 51); stretch ≥ 77 with first-project LoRA            | SOTA WebGen-Agent: 51.9%                                       |

Plus surfaced by N12 + N13: **multi-surface campaign success ≥ 85% on 12-surface campaign** + **first-shot convergence rate ≥ 40% with PIP** (vs ~5–15% commercial baseline).

## Quick start

```bash
git clone https://github.com/Manzela/atelier.git
cd atelier

./init.sh                     # one-time bootstrap
pip install -r requirements.lock
npm ci
pre-commit install

# Verify environment
./atelier-deploy/scripts/verify-prereqs.sh

# Run the test suite
cd atelier-core && pytest tests/unit/ -v
```

> The `atelier run` and `atelier intake` CLI commands ship in Milestone 2 (see [ROADMAP.md](ROADMAP.md)). The current release delivers the engine, evaluation suite, and infrastructure foundation.

## Project layout

```
atelier/
├── docs/                    # Architecture decision records (ADRs), runbooks, and conventions
├── atelier-core/            # Engine: DAG nodes, judges, gates, intake, campaign orchestrator
├── atelier-eval/            # Evaluation suite, benchmark adapters, and calibration golden sets
├── atelier-deploy/          # Terraform IaC, Docker, Cloud Build, and deployment scripts
├── atelier-dashboard/       # Observability dashboard with time-machine replay (React)
├── atelier-action/          # GitHub Marketplace Action
├── atelier-figma-plugin/    # Figma Community plugin
├── atelier-chrome-extension/# Chrome Web Store extension
├── .github/                 # CI/CD workflows, issue templates, and PR templates
├── DECISIONS.md             # Locked architectural decisions (injected into agent context)
└── init.sh                  # One-time environment bootstrap
```

## Origin

Atelier was created for the [Google for Startups AI Agents Challenge 2026](https://startup.google.com/programs/agents-challenge). It is production-grade software and is developed openly as an Apache-2.0 project independent of the competition.

## Live demos & artifacts

- **Live agent**: [atelier.dev](https://atelier.dev)
- **Documentation**: [docs.atelier.dev](https://docs.atelier.dev)
- **Public benchmark scoreboard**: [bench.atelier.dev](https://bench.atelier.dev)
- **Public calibration drift dashboard**: [calibration.atelier.dev](https://calibration.atelier.dev)
- **Status page**: [status.atelier.dev](https://status.atelier.dev)
- **Demo video** (4-min): linked from atelier.dev
- **arXiv preprint** (4-page workshop): linked from docs.atelier.dev/research

## Pricing

- **Freemium** — 3 sessions/month, watermarked output
- **Pro** $20/month — 50 sessions, no watermark
- **Team** $50/seat/month — shared workspace, project-history sync, shared judge LoRA across team
- **Enterprise** usage-based — BYO Cloud KMS keys, VPC-SC perimeter, dedicated tenant pool, custom judge axes

## Inheritance (wrap-don't-fork — see [ADR 0001](docs/decisions/0001-wrap-dont-fork-inheritance-model.md))

Atelier consumes upstream code via lockfile-pinned dependencies and wraps it with our own deployment / configuration / security / observability layers. We do **NOT** fork upstream internals.

| Source                                                                                                                    | Consumption mode                    | What we use                                                                                                                         |
| ------------------------------------------------------------------------------------------------------------------------- | ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| [`agent-dag-pipeline`](https://github.com/Manzela/agent-dag-pipeline) (Apache-2.0)                                        | `pip install` lockfile-pinned       | Gate-Agent ABC pattern, DEMAS Provenance Matrix, 3-tier DPO flywheel, Hebbian mutator, ADK integration wrappers                     |
| [`google-adk`](https://github.com/google/adk-python) v2.0 Beta (Apache-2.0)                                               | `pip install --pre` lockfile-pinned | SequentialAgent, ParallelAgent, LoopAgent, MCPToolset, rubric*based*\*\_v1, Skills for Agents, adk optimize (GEPA), adk conformance |
| [`hermes-agent`](https://github.com/NousResearch/hermes-agent) (MIT)                                                      | Pattern inheritance only            | Skills system, MEMORY/SOUL files, sandboxing tier model, panic/resume primitives, Atropos GRPO+LoRA training pattern                |
| [Stitch MCP](https://stitch.googleapis.com/mcp) (Google Labs)                                                             | HTTP MCP via ADK `MCPToolset`       | UI generation primitive (`generate_screen_from_text`, `generate_variants`, `apply_design_system`)                                   |
| [Anthropic two-prompt harness](https://github.com/anthropics/claude-quickstarts/tree/main/autonomous-coding) (Apache-2.0) | Pattern adoption                    | Initializer + coding agent + JSON ledger + end-to-end test before next feature (build sprint discipline)                            |

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full milestone plan. The three development milestones are:

- **Milestone 1: Foundation** (complete) — engine scaffold, ADK integration, single-surface end-to-end pipeline, Cloud Run staging deployment
- **Milestone 2: 10× Mechanisms** (in progress) — EvoDesign, ConsensusAgent, Campaign Orchestrator, PIP, WebGen-Bench ≥ 51, beta tenants
- **Milestone 3: Production Polish** (planned) — per-project judge LoRA, Open Eval Adapters, public scoreboard, marketing site

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, branching strategy ([worktree-per-phase, ADR 0007](docs/decisions/0007-worktree-per-phase-branching.md)), commit conventions ([Conventional Commits 1.0.0](docs/conventions/commit-messages.md)), PR process, and testing requirements.

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting and the responsible disclosure policy.

## License

Apache License 2.0 — see [LICENSE](LICENSE) for details. Built on patterns from [agent-dag-pipeline](https://github.com/Manzela/agent-dag-pipeline) (Apache-2.0), [hermes-agent](https://github.com/NousResearch/hermes-agent) (MIT), and [google-adk](https://github.com/google/adk-python) (Apache-2.0). See [NOTICE](NOTICE) for full attribution.
