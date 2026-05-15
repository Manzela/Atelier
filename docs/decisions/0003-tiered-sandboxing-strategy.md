# 0003. Tiered sandboxing strategy (5 tiers)

**Status:** Accepted
**Date:** 2026-05-14
**Decision-makers:** Daniel Manzela (+ Claude Opus 4.7 MAX as builder)

## Context

Atelier invokes a wide variety of tools. Some are safe (file reads, grep). Some are risky (model-generated CSS/JS executed against a sandbox). Some are very risky (LLM-generated arbitrary code in cloud sandboxes). A single sandbox tier is either too lax (security risk) or too restrictive (performance and capability cost).

Per AutonomousAgent ADR 0003 lineage — we adopt the same tiered model.

## Decision

We will route tool calls to one of five sandbox tiers based on risk class, defined in `atelier-deploy/config/toolsets.yaml`:

| Tier | Tools | Boundary |
|---|---|---|
| `in_process` | file reads, grep, ls, AST validation, token-fidelity grep | Runs in agent process; host FS read-only |
| `shell_sandbox` | shell, git, jq, semantic-HTML linter | Docker container, `--cap-drop=ALL`, `--network=none`, RO host FS, writable `/workspace` only, `--memory=1g --cpus=1.0 --pids-limit=200`, timeout per `limits.sandboxes.shell_timeout_s` |
| `browser_sandbox` | Playwright actions, Lighthouse, axe-core, visual-diff snapshots, responsive snapshots | Docker container, `--cap-drop=ALL --cap-add=SYS_ADMIN`, network allowlisted per call, `--memory=2g --cpus=2.0`, timeout per `limits.sandboxes.browser_timeout_s` (300s default) |
| `external_https` | Stitch MCP, GitHub MCP, Context7 MCP, design.md MCP | In-process httpx with egress allowlist enforcement, mTLS where avail, 60s timeout |
| `cloud_sandbox` | Arbitrary LLM-generated code (CSS/JS), Vertex AI tuning jobs, Vertex AI Endpoints (LoRA serving) | Modal/Daytona ephemeral microVM OR Vertex AI managed services; per-call network allowlist; max 10-min lifetime |

First-match wins; unknown tools fall through to `shell_sandbox` (default-deny).

## Consequences

### Positive

- Fast path for safe operations (file reads run in-process, no overhead)
- Strong isolation for risky operations (model-generated code never runs without microVM boundary)
- Routing is data, not code — adding new tools requires no code changes (just `toolsets.yaml` entry)
- Per-tier capability limits enforced at container boundary, not in app code
- Fail-loud at unknown tool (default-deny prevents silent escalation)

### Negative

- Five tiers to maintain instead of one (more compose services in dev, more configuration)
- Cloud sandbox tier requires external accounts (Modal/Daytona) — operational dependency
- Browser sandbox needs `SYS_ADMIN` cap for Playwright Chrome (less constrained than shell sandbox)

### Neutral

- Tier choice is observable in OTel spans (`atelier.sandbox_tier=...`)
- Model Armor + Cloud Armor + Apigee provide additional defense-in-depth at the network layer

## Alternatives considered

### Option A: Single Docker sandbox for everything

- Pros: Simpler; one boundary to reason about
- Cons: Slow path for safe reads; over-restrictive for browser; under-restrictive for arbitrary code (no microVM)
- Why rejected: Single tier optimizes neither performance nor security

### Option B: Cloud sandbox (Modal/Daytona) for everything

- Pros: Maximum isolation; physical separation
- Cons: Latency (every read goes through microVM cold-start); cost; outage of Modal/Daytona blocks all tools including safe reads
- Why rejected: Cost-prohibitive at always-on level; latency degrades user experience

### Option C: gVisor / firecracker for our own sandboxes

- Pros: More flexible than Docker; lighter than full VMs
- Cons: Operational complexity; immature ecosystem in May 2026; we're not VM operators
- Why rejected: Modal/Daytona already provides this as a managed service

## References

- [AutonomousAgent ADR 0003](file:///Users/danielmanzela/RX-Research%20Project/AutonomousAgent/docs/decisions/0003-tiered-sandboxing-strategy.md) — direct lineage
- [PRD §6.7 Tiered Sandboxing](../superpowers/specs/2026-05-14-atelier-prd.md)
- `atelier-deploy/config/toolsets.yaml` — tool → tier routing
- `atelier-core/src/atelier/shared/toolset_router.py` — runtime dispatcher
