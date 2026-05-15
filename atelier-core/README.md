# atelier-core

The Atelier engine — agent runtime, judges, deterministic gates, intake, campaign orchestrator, and ADK integration wrappers.

## Subpackages

```
src/atelier/
├── intake/           # N13 PIP — Pre-Generation Intake Protocol
├── campaign/         # N12 RLRD — Campaign Orchestrator + Surface Manifest
├── dag/              # 8-node atomic DAG (per-surface engine)
│   ├── nodes/        # N1-N4 node implementations
│   ├── evolutionary/ # N5 EvoDesign K-candidate search + mutation operators
│   └── gates/        # N1 DGF-D2C deterministic gates (Lighthouse, axe, etc.)
├── judges/           # N2 DEMAS-D + N3 PerJudge + N6 CSC-D + ConsensusAgent
├── flywheel/         # 3-tier DPO + Hebbian mutator + LoRA training
├── adk/              # ADK 2.0 Beta integration wrappers
├── tools/            # MCP wrappers (Stitch, design.md, GitHub, Playwright)
├── render/           # N7 A2UI renderers (React, Flutter, Lit, Angular)
├── memory/           # Memory Bank + Vector Search 2.0 client
├── shared/           # Pydantic v2 frozen data contracts + observability + cost router
└── skills/           # N9 Atelier Skills Pack (case-study, dashboard, etc.)
```

## Status

**Phase 0** — repo scaffold complete; source code is a Phase 1 deliverable (D3+, May 17 onwards).

`pyproject.toml` is populated; `src/atelier/__init__.py` is a placeholder.

## Quick start (post-Phase-1)

```bash
pip install -e ".[dev]"
pytest tests/unit/ -v
mypy --strict src
```

## See also

- [Atelier PRD](../docs/superpowers/specs/2026-05-14-atelier-prd.md)
- [Architecture index](../docs/architecture/README.md)
- [ADRs](../docs/decisions/)
