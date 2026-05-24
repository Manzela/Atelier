# Roadmap

This document describes Atelier's planned milestones, feature releases, and long-term direction.

---

## Current status

Atelier is in active development. The engine, evaluation suite, and infrastructure scaffold are complete. End-to-end pipeline integration, the full ConsensusAgent, and the Campaign Orchestrator are in progress.

---

## Milestone 1 — Foundation (complete)

Establishes the core infrastructure: repository, CI/CD, ADK integration, single-surface end-to-end pipeline, and Cloud Run staging deployment.

**Delivered:**

- 8-node atomic DAG runtime (Brief Parser → Source Resolver → EvoDesign loop → Final Validator)
- N1 DGF-D2C: Deterministic-Gate-First pipeline with parallel Lighthouse, axe-core, visual-diff, and token-fidelity gates
- Google ADK 2.0 integration with Stitch MCP toolset
- BigQuery trajectory store and OTel observability
- Cloud Run staging deployment with Terraform IaC
- Typed Protocol surfaces for Phase-Aware MoE Router (§18), RL Generator Agent (§19), Hierarchical Memory (§20), and AND-Gate Composite Reward (§21)
- Pre-commit CI/CD with mypy strict, ruff, markdownlint, shellcheck, detect-secrets, CodeQL
- SDLC documentation, 13 Architecture Decision Records (ADR 0001–0031)

---

## Milestone 2 — 10× Mechanisms (in progress)

Delivers the core quality mechanisms that make Atelier self-improving.

**In progress:**

- N5 EvoDesign — K=6 candidates × 8 mutation operators per iteration; AlphaEvolve-inspired evolutionary search
- N3d ConsensusAgent — 5 specialized rubric judges (Brand, Copy, Motion, Token-fidelity, Cross-screen-coherence) with DEMAS-D Provenance Matrix and Bayesian-weighted consensus
- N12 Campaign Orchestrator — multi-surface campaigns with Surface Manifest and Cross-Surface Coherence Validator
- N13 PIP — Pre-Generation Intake Protocol with 13-question adaptive catalog and immutable BriefSpec
- 3-tier DPO flywheel — BigQuery episodic memory → Vertex AI Tuning → per-project LoRA promotion
- ε-Greedy Bandit Router (v1) — online learning phase-to-model routing
- WebGen-Bench integration — 50-task CI subset + full 484-task nightly evaluation

**Acceptance criteria:**

- 12-surface autonomous campaign converges end-to-end without human intervention
- WebGen-Bench full evaluation at or above NeurIPS 2025 SOTA (51.9%)
- Calibration dashboard live at [TBD](TBD)
- All four A2UI renderers operational (React, Flutter, Lit, Angular)

---

## Milestone 3 — Production Polish + Public Launch

Completes the per-project learning loop, open ecosystem artifacts, and production infrastructure.

**Planned:**

- Per-project judge LoRA — fine-tuned judge per tenant using accumulated accept/reject signals; 20× lower sample requirement vs generic judge
- N9 Open Eval Adapters — Apache-2.0 adapters to `google/adk-python` for WebGen-Bench, Design2Code, Web2Code, ScreenSpot, and FrontendBench
- N10 Convergence Spec RFC v0.1 — open standard for how autonomous design agents declare convergence, emit trajectories, and report calibration drift
- N11 Public benchmark scoreboard — `TBD` accepts agent submissions from any vendor
- Atelier Skills Pack — 6 reusable skills for common design patterns
- Ecosystem integrations — GitHub Marketplace Action, Figma Community plugin, Chrome extension
- Marketing site — [TBD](TBD) with freemium sign-up

---

## Post-launch versions

| Version  | Focus                                                                                                       |
| -------- | ----------------------------------------------------------------------------------------------------------- |
| `v1.1.0` | Multiplayer dashboard annotation; voice input parity via Stitch; Discord community launch                   |
| `v1.2.0` | Full N9 adapter suite (all 5 benchmarks); Convergence Spec RFC v0.2 (community-reviewed); additional skills |
| `v1.3.0` | Sketch-to-UI upload; multi-region active-active failover (US + EU); additional A2UI renderers               |
| `v2.0.0` | SOC 2 Type 2 certification; per-tenant CMEK on Cloud Run; HIPAA tier; ISO 27001 evidence collection         |
| `v3.0.0` | Federated learning across tenants with differential privacy; cross-project pattern transfer at scale        |

---

## Long-term vision

Atelier aims to become:

1. **The standard evaluation surface for UI-generation** — `TBD` as the canonical public benchmark for autonomous design agents, with the eval-set adapters adopted by independent research teams.

2. **The reference implementation of the Convergence Spec** — a community-driven open standard for how any autonomous design agent declares convergence, emits trajectories, and reports calibration drift.

3. **A compounding data moat** — trajectory data accumulated across tenants drives continuous improvement of the router, the judges, and the generator. Agent core remains Apache-2.0 and freely forkable; the trajectory dataset is proprietary.

**2026 targets:**

- 10,000+ active projects on the platform
- 100,000+ design trajectories collected
- 3+ third-party benchmarks adopting Atelier's eval-set adapters
- 1+ published research paper (NeurIPS D&B, ICLR, or CHI) drawing on Atelier's trajectory data
- 5+ Atelier Skills published by community contributors
- 1+ Google Cloud case study featuring Atelier as a production multi-agent system

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to contribute to Atelier's development. Feature requests and roadmap discussion happen in [GitHub Issues](https://github.com/Manzela/Atelier/issues).
