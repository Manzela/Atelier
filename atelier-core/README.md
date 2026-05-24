# atelier-core

The Atelier engine — agent runtime, multi-axis judges, deterministic gates, intake protocol, campaign orchestrator, and Google ADK integration.

## Packages

```
src/atelier/
├── intake/      # N13 PIP — Pre-Generation Intake Protocol
├── campaign/    # N12 RLRD — Campaign Orchestrator + Surface Manifest
├── dag/         # 8-node atomic DAG (per-surface engine)
│   ├── nodes/        # N1–N4 node implementations
│   ├── evolutionary/ # N5 EvoDesign K-candidate search + mutation operators
│   └── gates/        # N1 DGF-D2C deterministic gates (Lighthouse, axe, etc.)
├── judges/      # N2 DEMAS-D + N3 PerJudge + N6 CSC-D + ConsensusAgent
├── flywheel/    # 3-tier DPO + Hebbian mutator + LoRA promotion pipeline
├── adk/         # Google ADK 2.0 integration wrappers
├── tools/       # MCP toolsets (Stitch, design.md, GitHub, Playwright)
├── render/      # N7 A2UI renderers (React, Flutter, Lit, Angular)
├── memory/      # Hierarchical Memory: episodic (BigQuery), semantic + procedural (Vertex Memory Bank)
├── router/      # Phase-Aware MoE Router: Phase 1 static table, Phase 2 ε-greedy bandit
├── reward/      # AND-Gate Composite Reward Engine (DPO eligibility gate)
└── shared/      # Pydantic v2 data contracts, OTel observability, cost router
```

## Status

The engine scaffold, typed Protocol surfaces, and CI/CD infrastructure are complete and passing. Full end-to-end pipeline integration (ConsensusAgent, Campaign Orchestrator, DPO flywheel) ships in Milestone 2. See [ROADMAP.md](../ROADMAP.md) for the delivery plan.

## Quick start

```bash
pip install -e ".[dev]"
pytest tests/unit/ -v
mypy --strict src
```

## See also

- [Architecture index](../docs/architecture/README.md)
- [Architecture Decision Records](../docs/decisions/)
- [Evaluation methodology](../docs/eval/methodology.md)
