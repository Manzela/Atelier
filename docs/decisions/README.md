# Architecture Decision Records

This directory holds [MADR](https://adr.github.io/madr/) — Markdown Architecture Decision Records — that document point-in-time decisions on this project.

## When to write an ADR

Write one whenever you make a decision that:

- Locks in a tradeoff (chose X over Y)
- Affects code that's hard to unwind
- Future-you would want to know the reasoning
- Constrains a future implementation choice

Don't write one for purely cosmetic choices or short-lived implementation details.

## How to write one

1. Open a GitHub Issue tagged `adr-proposal` describing the problem
2. Discuss for ≥ 7 days (longer for major architectural changes)
3. Copy [`template.md`](template.md) to `<NNNN>-<short-kebab-name>.md` where NNNN is the next zero-padded number
4. Fill in: Status, Context, Decision, Consequences, Alternatives, References
5. Open a PR titled `docs(adr): <NNNN> <title>`
6. Maintainer reviews + accepts/rejects
7. On acceptance: status changes to `Accepted`, ADR is merged, this index is updated

## Amending a locked ADR

A locked ADR is hard to change by design. To amend:

1. Stop relevant work
2. Open a new ADR with status `Proposed` that supersedes the original
3. Update the original's status to `Superseded by [NNNN](NNNN-other.md)`
4. Update [`DECISIONS.md`](../../DECISIONS.md) at the repo root
5. Update the PRD section that references the decision
6. Add an entry to `docs/sprint/DEVIATIONS.md`

## Index

| # | Title | Status |
|---|---|---|
| 0001 | [Wrap-don't-fork inheritance model](0001-wrap-dont-fork-inheritance-model.md) | Accepted |
| 0002 | [Cloud Run jobs for runtime, not Agent Engine](0002-cloud-run-not-agent-engine-for-runtime.md) | Accepted |
| 0003 | [Tiered sandboxing strategy (5 tiers)](0003-tiered-sandboxing-strategy.md) | Accepted |
| 0004 | [Pre-Generation Intake Protocol (PIP) layer](0004-pre-generation-intake-protocol.md) | Accepted |
| 0005 | [Recursive Long-Running Discipline (RLRD)](0005-recursive-long-running-discipline.md) | Accepted |
| 0006 | [Google-native stack (no Langfuse, Statsig, PostHog, GKE-S-LoRA, LiteLLM)](0006-google-native-stack-no-langfuse.md) | Accepted |
| 0007 | [Worktree-per-phase branching](0007-worktree-per-phase-branching.md) | Accepted |
| 0008 | [Multi-judge Bayesian-weighted consensus + DEMAS-D Provenance per axis](0008-multi-judge-bayesian-consensus.md) | Accepted |
| 0009 | [Public calibration dashboard at calibration.atelier.dev](0009-public-calibration-dashboard.md) | Accepted |
| 0010 | [A2UI v0.9 as canonical output protocol](0010-a2ui-native-output-protocol.md) | Accepted |
