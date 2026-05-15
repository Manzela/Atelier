# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

Releases are managed via [release-please](https://github.com/googleapis/release-please) — Conventional Commits in `main` are parsed to generate release notes automatically. Do not edit released sections by hand; edits go to `[Unreleased]`.

---

## [Unreleased]

### Added

- Initial repository scaffold with full SDLC + CI/CD infrastructure
- PRD: Atelier autonomous design agent (831 lines, 13 novel contributions, 5 quantified 10× axes, full Google-native production stack)
- 10 Architecture Decision Records (MADR format) covering wrap-don't-fork inheritance, Cloud Run not Agent Engine for runtime, tiered sandboxing, PIP layer, RLRD, Google-native stack, EvoDesign K-candidate search, multi-judge Bayesian consensus, public calibration dashboard, A2UI-native output
- Full SDLC documentation: README, CHANGELOG, ROADMAP, SECURITY, CONTRIBUTING, CODE_OF_CONDUCT, GOVERNANCE, NOTICE
- Sprint discipline scaffold: `CLAUDE.md`, `DECISIONS.md`, `REJECTED.md`, `features.json` (Anthropic harness JSON ledger), `claude-progress.txt`, `init.sh`
- GitHub Actions workflows: CI (lint + typecheck + unit + integration + security + build), eval (nightly WebGen-Bench + Design2Code), CodeQL security scanning, release (release-please), docs (mkdocs to Firebase Hosting), stale issue management
- Pre-commit hooks: ruff format/check, mypy strict, pytest fast subset, commitlint, detect-secrets, markdownlint
- Issue templates (bug, feature, eval-failure, docs) + PR template + CODEOWNERS + Dependabot config
- Project conventions: commit messages (Conventional Commits 1.0.0), branching (worktree-per-phase per ADR 0007), code style (Python ruff + TypeScript strict + shell strict mode), logging (structured JSON, OTel GenAI semconv)
- Operational runbooks: recovery, on-call, deployment, incident response, customer support
- Three-subfolder repo split: `atelier-core/` (engine), `atelier-eval/` (suite + benchmarks), `atelier-deploy/` (infra)
- Plus: `atelier-dashboard/` (live observability), `atelier-action/` (GitHub Marketplace), `atelier-figma-plugin/`, `atelier-chrome-extension/`

### Notes

- This `[Unreleased]` section accumulates work intended for the first tagged release `v0.1.0-alpha` (target: 2026-05-21, Phase 1 acceptance gate).
- Phases 2 and 3 of the sprint will produce `v0.2.0-beta` (2026-05-28) and `v1.0.0` (2026-06-03 — submission day) respectively.

---

## Release tagging plan

| Tag | Date | What it represents |
|---|---|---|
| `v0.1.0-alpha` | 2026-05-21 | Phase 1 Foundation gate passed — single-surface end-to-end working on Cloud Run staging |
| `v0.2.0-beta` | 2026-05-28 | Phase 2 10× Mechanisms gate passed — 12-surface autonomous campaign converges + WebGen-Bench ≥ 51 + 5 beta tenants |
| `v1.0.0` | 2026-06-03 | Public launch + G4S submission filed |
| `v1.1.0` | TBD | Post-launch features (multiplayer dashboard, voice input, Discord community) |
| `v2.0.0` | TBD | SOC 2 Type 2 + per-tenant CMEK + HIPAA tier |

[Unreleased]: https://github.com/Manzela/atelier/compare/v0.0.0...HEAD
