# Architecture

The full architectural design lives in [`../superpowers/specs/2026-05-14-atelier-prd.md`](../superpowers/specs/2026-05-14-atelier-prd.md). This directory provides reading order + indexes.

## Reading order

1. **[Atelier PRD](../superpowers/specs/2026-05-14-atelier-prd.md)** — single source of truth. Read sections 1-5 for the goal + 10× thesis + 13 novel contributions; sections 6-10 for the architecture + data contracts + inheritance map; section 11 for Strategy v2 sprint discipline; sections 12-19 for MVP scope + sprint plan + 10× checklist + risk register; sections 20-29 for designed-for-deferred items, governance sections, glossary, and the comprehensive `limits.yaml` schema.
2. **[ADRs](../decisions/)** — 10 point-in-time architectural decisions with full Context / Decision / Consequences / Alternatives. Read in numerical order (0001 → 0010).
3. **[Conventions](../conventions/)** — commit messages, branching, code style, logging.
4. **[Runbooks](../runbooks/)** — operational procedures (filled out as Phase 1+ ships them).

## Key concepts

| Concept                                                                 | Where to read                               |
| ----------------------------------------------------------------------- | ------------------------------------------- |
| 3-layer stacked architecture (PIP / Campaign Orchestrator / 8-node DAG) | PRD §6                                      |
| 13 novel contributions (N1-N13)                                         | PRD §5                                      |
| Inheritance from agent-dag-pipeline + hermes-agent + ADK                | PRD §10, ADR 0001                           |
| Cloud Run vs Agent Engine                                               | PRD §6 + §8, ADR 0002                       |
| Tiered sandboxing                                                       | PRD §6.7, ADR 0003                          |
| Pre-Generation Intake Protocol                                          | PRD §6.1, ADR 0004                          |
| Recursive Long-Running Discipline                                       | PRD §6.2, ADR 0005                          |
| Google-native stack                                                     | PRD §8, ADR 0006                            |
| Worktree-per-phase branching                                            | PRD §28, ADR 0007, conventions/branching.md |
| Multi-judge consensus + DEMAS-D Provenance                              | PRD §6.3-§6.4, ADR 0008                     |
| Public calibration dashboard                                            | PRD §16, ADR 0009                           |
| A2UI v0.9 native output                                                 | PRD §6.3 N4 + §6.7 ADR 0010                 |
| `limits.yaml` single source of truth                                    | PRD §27                                     |
| Sprint plan + acceptance gates                                          | PRD §15, ROADMAP.md, docs/sprint/ROADMAP.md |
| Strategy v2 execution discipline                                        | PRD §11, CLAUDE.md                          |
| Failure-handling trichotomy (fail-loud / fail-soft / self-heal)         | PRD §21                                     |
| Panic + Resume CLI primitives                                           | PRD §22                                     |

## Subpackage architecture

- **[atelier-core](../../atelier-core/README.md)** — engine: nodes, judges, intake, campaign, ADK wrappers
- **[atelier-eval](../../atelier-eval/README.md)** — eval suite, benchmark adapters, golden sets, scoreboard
- **[atelier-deploy](../../atelier-deploy/README.md)** — Terraform, Docker, Cloud Build, scripts
- **[atelier-dashboard](../../atelier-dashboard/README.md)** — live observability + time-machine UI
- **[atelier-action](../../atelier-action/README.md)** — GitHub Marketplace action
- **[atelier-figma-plugin](../../atelier-figma-plugin/README.md)** — Figma Community plugin
- **[atelier-chrome-extension](../../atelier-chrome-extension/README.md)** — Chrome Web Store extension
