# DECISIONS.md — Locked architectural decisions (auto-injected)

> This file is auto-injected into every Claude Code session and every subagent dispatch's prompt prefix. It lists every locked architectural decision with a one-line rationale + ADR pointer. **Subagent prompts include: "You may not propose alternatives to anything in DECISIONS.md without first surfacing it to the orchestrator."** Re-litigation of locked decisions is prevented at the prompt level.

For full ADR text and tradeoffs, see [`docs/decisions/`](docs/decisions/).

---

## Locked decisions

| #   | Decision                                                                                         | One-line rationale                                                                                                                                                                                                                                                                                                   | ADR                                                                   |
| --- | ------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| 1   | **Wrap-don't-fork inheritance from `agent-dag-pipeline` + `google-adk` + `hermes-agent`**        | Lockfile-pinned dependencies + wrap with our deployment/config/security/observability. Never modify upstream internals. Preserves upgrade paths.                                                                                                                                                                     | [0001](docs/decisions/0001-wrap-dont-fork-inheritance-model.md)       |
| 2   | **Cloud Run jobs for runtime, not Agent Engine**                                                 | Atelier convergence loops run minutes-to-hours; Agent Engine's per-request runtime model + Sessions billing dominance ($43K/mo at modest scale) is wrong fit. Use Cloud Run jobs + call Agent Engine for Sessions/Memory Bank/A2A as services.                                                                       | [0002](docs/decisions/0002-cloud-run-not-agent-engine-for-runtime.md) |
| 3   | **Tiered sandboxing strategy (5 tiers)**                                                         | `in_process` / `shell_sandbox` / `browser_sandbox` / `external_https` / `cloud_sandbox`. Risk-appropriate isolation per tool class. Routing data not code.                                                                                                                                                           | [0003](docs/decisions/0003-tiered-sandboxing-strategy.md)             |
| 4   | **Pre-Generation Intake Protocol (PIP) as first-class layer above Campaign Orchestrator**        | Adaptive Q&A mapped 1:1 to DAPLab's 9 failure patterns; produces immutable BriefSpec before any generation. Drives ≥40% first-shot convergence vs ~5-15% commercial baseline.                                                                                                                                        | [0004](docs/decisions/0004-pre-generation-intake-protocol.md)         |
| 5   | **Recursive Long-Running Discipline (RLRD)**                                                     | The same long-running-agent harness pattern (Anthropic Nov 2025) we use to build Atelier, we ship as a first-class user capability for multi-surface campaigns. Atelier eats its own dogfood.                                                                                                                        | [0005](docs/decisions/0005-recursive-long-running-discipline.md)      |
| 6   | **Google-native stack — no Langfuse, no Statsig, no PostHog, no GKE for S-LoRA, no LiteLLM**     | OTel + Cloud Trace + Cloud Monitoring + Vertex AI Studio Tracing covers Langfuse. Firebase Remote Config covers Statsig. Firebase Analytics + GA4 + BigQuery Export covers PostHog. Vertex AI Endpoints + Multi-Tuning covers GKE S-LoRA. Apigee covers LiteLLM. Two non-Google components total: Stripe + Telegram. | [0006](docs/decisions/0006-google-native-stack-no-langfuse.md)        |
| 7   | **Worktree-per-phase branching**                                                                 | `main` holds only accepted-and-tagged work. Each sprint phase gets a long-running branch in `.worktrees/`. Acceptance: `git merge --no-ff phase/N + tag phaseN-accepted`.                                                                                                                                            | [0007](docs/decisions/0007-worktree-per-phase-branching.md)           |
| 8   | **Multi-judge Bayesian-weighted consensus (5 specialized judges + DEMAS-D Provenance per axis)** | Brand / Copy / Motion / Token-fidelity / Cross-screen-coherence judges run in parallel. Each judge sees ONLY its axis-relevant ground-truth variables. Bayesian-weighted vote with confidence interval. Addresses DesignPref α=0.25 finding.                                                                         | [0008](docs/decisions/0008-multi-judge-bayesian-consensus.md)         |
| 9   | **Public calibration dashboard at `calibration.atelier.dev` as transparency commitment**         | First commercial autonomous design agent to publish judge calibration externally. Defends against the calibration-drift problem 93% of teams hit (Galileo report). Operational defense + research artifact + competitive moat in one.                                                                                | [0009](docs/decisions/0009-public-calibration-dashboard.md)           |
| 10  | **A2UI v0.9 as canonical output protocol**                                                       | First autonomous design agent built A2UI-native from day one. Renders to React + Flutter + Lit + Angular simultaneously. Direct alignment with Google's A2UI strategy launched Apr 2026.                                                                                                                             | [0010](docs/decisions/0010-a2ui-native-output-protocol.md)            |
| 11  | **Web-Research-Augmented Intake (WRAI) for relevance grounding**                                 | N14 node fetches web references during intake, scored by domain trust lattice. Prevents hallucinated design citations and grounds relevance judge in verifiable sources.                                                                                                                                             | [0011](docs/decisions/0011-web-research-augmented-intake.md)          |
| 12  | **Design Constitution System (CSC-D) for brand judge anchoring**                                 | Brand judge scores against a constitution document (e.g., Apple HIG distillation). Constitutions are YAML configs, not code. Enables multi-tenant brand standards without code changes.                                                                                                                              | [0012](docs/decisions/0012-design-constitution-system.md)             |
| 13  | **Conditional Axis Weighting per surface type**                                                  | D-O-R-A-V axis weights vary by surface type (checkout emphasizes accessibility; landing page emphasizes brand). Prevents one-size-fits-all scoring that penalizes surface-appropriate tradeoffs.                                                                                                                     | [0013](docs/decisions/0013-conditional-axis-weighting.md)             |
| 14  | **Model registry pins Gemini 2.5 Flash (not 3.0 Flash)**                                        | `gemini-3-flash` not yet GA on Vertex AI at D1. Pin to `gemini-2.5-flash-preview-05-20` with drop-in swap readiness. Migration plan: re-pin when GA + golden set pass rate within 2pp of baseline.                                                                                                                  | [0014](docs/decisions/0014-model-registry-gemini-2-5-flash-pin.md)    |

---

## Subagent prompt prefix (auto-injected)

> The above 10 decisions are LOCKED. Do not propose alternatives without first surfacing the proposal to the orchestrator (main Claude Code session). The orchestrator will decide whether to escalate to Daniel for an ADR amendment. Treat these as constants for the duration of the sprint.

---

## How to amend a locked decision

If implementation reveals a locked decision is wrong:

1. Stop relevant work.
2. Open a GitHub Issue tagged `adr-amendment` describing the conflict.
3. Discuss with Daniel (the maintainer).
4. If approved, open a PR that:
   - Updates the affected ADR's status to `Superseded by [NNNN](NNNN-other.md)`
   - Adds a new ADR with the replacement decision
   - Updates this `DECISIONS.md`
   - Updates the PRD section that references the decision
   - Adds an entry to `docs/sprint/DEVIATIONS.md`
5. Commit as `docs(adr): amend NNNN — <reason>`.

This is a heavy process by design. We want the friction to discourage casual changes.
