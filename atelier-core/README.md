# Atelier

Atelier is an autonomous UI/UX design agent built on the Google Agent Development Kit (ADK) and Gen AI Platform. Given a natural-language design brief, Atelier generates production-ready, accessible UI components through a multi-stage pipeline of planning, ensemble generation, deterministic gating, and consensus evaluation.

## Architecture

The system is structured as a directed acyclic graph (DAG) of composable agent nodes. Each node is a discrete ADK `LlmAgent` or deterministic gate, orchestrated by a central `Runner`.

### Dynamic Planner

A `PlannerAgent` analyzes each incoming brief and emits a structured `PlanStep` that controls downstream execution:

| Parameter         | Purpose                                                                        |
| ----------------- | ------------------------------------------------------------------------------ |
| `should_run_wrai` | Conditionally activates Web Research Augmented Intake based on brief ambiguity |
| `ensemble_k`      | Scales the parallel generator count (1--3) proportional to task complexity     |
| `axis_weights`    | Adjusts D-O-R-A-V evaluation axis weights to match the brief's objective       |
| `constitution`    | Selects the brand constitution applied during generation                       |

### Pipeline Stages

```
Brief --> PlannerAgent --> WRAI (conditional) --> GeneratorEnsemble (K candidates)
      --> DeterministicGates (6 axes) --> ConsensusAgent (D-O-R-A-V) --> Result
```

1. **Intake** -- `BriefParserGate` validates input sanitization (XSS, SSTI, CSS injection) and `BriefParserAgent` extracts structured intent.
2. **Research** -- WRAI performs grounded web research via Google Search, with strict system-instruction boundaries to prevent prompt steering.
3. **Generation** -- An ADK `ParallelAgent` ensemble produces K candidates, each backed by Stitch MCP with direct-generation fallback.
4. **Gating** -- Six deterministic gates (accessibility, semantic HTML, performance, responsiveness, visual fidelity, brand alignment) filter candidates without LLM involvement.
5. **Evaluation** -- `ConsensusAgent` scores surviving candidates across five axes: Design fidelity, Originality, Relevance, Accessibility, and Visual clarity (D-O-R-A-V).

### Security

All LLM interactions are protected by Vertex AI [Model Armor](https://cloud.google.com/security/products/model-armor), configured via centralized enterprise templates. Tenant isolation is enforced through segment-boundary validation on all resource identifiers.

### Observability

OpenTelemetry instrumentation exports traces to Google Cloud Trace via `BatchSpanProcessor`. A PII scrubber runs on every span export path.

### Evaluation and Simulation

Vertex AI Gen AI Evaluation provides rubric-based scoring of generated candidates. An adversarial simulation library exercises the pipeline against injection attacks, multilingual inputs, boundary conditions, and high-complexity briefs.

### Interoperability

An A2A v1.0 JSON-RPC endpoint enables agent-to-agent communication. The agent card is served at `/.well-known/agent-card.json`.

## Quick Start

### Install

```bash
pip install -e ".[dev]"
```

### Run Tests

```bash
pytest tests/ -v
```

### Deploy

```bash
python -m atelier.agent_engine_deploy
```

This deploys the agent as a managed `AdkApp` on Vertex AI Agent Engine.

## Requirements

- Python 3.11+
- `google-adk >= 1.34.1`
- `google-genai >= 1.75.0`
- `pydantic >= 2.9.0`
- A Google Cloud project with Vertex AI and Model Armor enabled

## Documentation

- [Product Requirements Document](../docs/superpowers/specs/2026-05-14-atelier-prd.md)
- [Architecture Index](../docs/architecture/README.md)
- [Architecture Decision Records](../docs/decisions/)
