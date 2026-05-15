# 0001. Wrap-don't-fork inheritance model

**Status:** Accepted
**Date:** 2026-05-14
**Decision-makers:** Daniel Manzela (+ Claude Opus 4.7 MAX as builder)

## Context

Atelier inherits architectural patterns and code from three upstream projects:

- [`agent-dag-pipeline`](https://github.com/Manzela/agent-dag-pipeline) (Apache-2.0) — production-validated 7-node Gate-Agent DAG with DEMAS Provenance Matrix, 3-tier DPO flywheel, ADK integration wrappers
- [`google-adk`](https://github.com/google/adk-python) v2.0 Beta (Apache-2.0) — `SequentialAgent`, `ParallelAgent`, `LoopAgent`, `MCPToolset`, `rubric_based_*_v1`, Skills for Agents, `adk optimize` (GEPA), `adk conformance`
- [`hermes-agent`](https://github.com/NousResearch/hermes-agent) (MIT) — skills system, MEMORY/SOUL files, sandboxing tier model, panic/resume primitives, Atropos GRPO+LoRA training pattern

Three options for relating to upstream:

1. Fork each repo and modify internals to fit our use case
2. Build everything from scratch on top of the Anthropic SDK (or similar low-level base)
3. Wrap upstream — consume via lockfile-pinned dependencies + add our own deployment / configuration / security / observability layers

## Decision

**We will wrap-don't-fork** — directly inheriting the principle from AutonomousAgent ADR 0001:

- `agent-dag-pipeline` → `pip install agent-dag-pipeline==<pinned-version>` in `requirements.lock`. We import its public APIs (`agent_dag.adk.gate_agent.GateAgent`, etc.) and subclass them. We never modify the package's source.
- `google-adk` → `pip install google-adk --pre` lockfile-pinned. We use its primitives. We never modify it.
- `hermes-agent` → **inheritance is pattern-only, not code-import.** We mirror its skills system, MEMORY/SOUL files, sandboxing tier model, panic/resume primitives, Atropos GRPO+LoRA training pattern in our own code. We do not run hermes-agent as a process or import its modules.
- Stitch MCP → consumed via the published HTTP MCP endpoint at `https://stitch.googleapis.com/mcp` through ADK's `MCPToolset`. No source-level dependency.

Atelier's job is to add the **wrapping layers**: deployment (Cloud Run jobs), configuration (`limits.yaml`), security (Apigee + Model Armor + IAM Conditions), observability (Cloud Trace + Cloud Monitoring + Atelier Dashboard), and the novel Atelier-specific code (PIP, Campaign Orchestrator, EvoDesign, ConsensusAgent, A2UI renderers, etc.).

## Consequences

### Positive

- Skip months of foundational agent-loop / skill / memory / RL development
- Inherit battle-tested production patterns from a Daniel-Manzela-shipped Apache-2.0 project (agent-dag-pipeline runs in 11 enterprise retailers at 73.5M agent ops/cycle per his portfolio)
- Preserve upstream upgrade paths — bumps are explicit, lockfile-controlled
- Aligns governance: contributors who improve the upstream packages benefit Atelier
- Compatible with the agentskills.io / Skills for Agents emerging standard
- Active community support via Anthropic + Google + Nous Research developer channels

### Negative

- Dependent on upstream release cadence and breaking changes
- Upstream upgrades require regression testing against our wrapper (caught by `eval-delta` CI gate)
- Custom modifications to agent internals are off the table; if we need different behavior, we wrap or contribute upstream — never fork inline

### Neutral

- We track upstream via lockfile-pinned versions; bumps are explicit, not automatic
- All three upstreams are Apache-2.0 or MIT — compatible with our Apache-2.0 license
- Dependabot opens weekly PRs for version bumps; CI eval-delta catches regressions

## Alternatives considered

### Option A: Fork agent-dag-pipeline + agent-loop hermes-agent

- Pros: Total control over internals
- Cons: Loses upstream improvements; merge friction; doubles maintenance burden; we're not the experts on the agent-loop internals; misaligns governance
- Why rejected: Effort vastly exceeds value of differentiation. We add value at the wrapping layer, not the engine layer.

### Option B: Build agent loop from scratch on top of Anthropic SDK

- Pros: Total control; no upstream dependencies
- Cons: Months of work; reinvents skill / memory / multi-axis judge / RL / sandboxing systems; precludes the 3-week sprint window
- Why rejected: Out of sprint scope; not differentiated.

### Option C: Use LangGraph / LlamaIndex / CrewAI as the agent runtime

- Pros: Production-ready frameworks
- Cons: None ship the closed self-improvement loop, RL trajectory pipeline, or A2UI native rendering out of the box; would still need significant assembly; not Google-native (conflicts with G4S "Use of Google Cloud" judging criterion)
- Why rejected: ADK 2.0 Beta is closer to our requirements with less assembly + on-rubric.

## References

- [`agent-dag-pipeline`](https://github.com/Manzela/agent-dag-pipeline) — Apache-2.0
- [`google-adk`](https://github.com/google/adk-python) — Apache-2.0, v2.0 Beta
- [`hermes-agent`](https://github.com/NousResearch/hermes-agent) — MIT
- AutonomousAgent ADR 0001 (the original wrap-don't-fork ADR for hermes-agent)
- [PRD §10 Inheritance map](../superpowers/specs/2026-05-14-atelier-prd.md#10-inheritance-map-wrap-dont-fork)
- [NOTICE](../../NOTICE) — full attribution
