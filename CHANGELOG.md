# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

Releases are managed via [release-please](https://github.com/googleapis/release-please) — Conventional Commits in `main` are parsed to generate release notes automatically. Do not edit released sections by hand; edits go to `[Unreleased]`.

---

## [0.2.1-alpha](https://github.com/Manzela/Atelier/compare/v0.2.0-alpha...v0.2.1-alpha) (2026-05-28)


### Bug Fixes

* **audit:** HANDOFF-R12 remediation — 25 production blockers + security hardening ([#29](https://github.com/Manzela/Atelier/issues/29)) ([7e652d0](https://github.com/Manzela/Atelier/commit/7e652d02b131790e254ada7b8868ad3d665c8497))

## [0.2.0-phase-2-gate] — 2026-05-25

Phase 2: consensus pipeline, trajectory recording, DPO flywheel, production infrastructure, evaluation framework.

### Added

**Core Pipeline (N1→N4 full 8-node DAG)**

- `POST /v1/generate` — authenticated endpoint running the full design pipeline
- N3c deterministic gates (6 gates: semantic HTML, CSS validity, token fidelity, Lighthouse heuristic, axe a11y, visual-diff structural similarity)
- N3d D-O-R-A-V consensus evaluation (5-axis Bayesian-weighted scoring)
- N4 convergence decision with κ=0.70 threshold and best-candidate selection
- N14 WRAI (Web-Research-Augmented Intake) via Vertex AI Search Grounding

**Self-Improving DPO Flywheel**

- `TrajectoryRecorder` streaming trajectory data to BigQuery `atelier_trajectories.trajectory_records`
- `BigQueryPairMiner.mine_pairs()` — tenant-isolated DPO pair extraction from accepted/rejected candidates
- `DpoTuningJob` — Vertex AI PREFERENCE_TUNING via `google.genai` SDK (β=0.1, epochs=3, adapter=4)
- `GeneratorTuner.tune()` + `evaluate_and_promote()` — κ-gated model promotion pipeline

**Session Architecture**

- `BigQuerySessionBackend` — ADK `BaseSessionService` implementation with BQ persistence
- ADK `Runner(session_service=...)` injection — no more `InMemoryRunner` in production
- Session state cross-device resumption via BQ + in-memory fallback

**Security & Governance**

- Firebase Authentication (Google SSO) wired end-to-end: auth page → API → BigQuery
- IAP-protected Cloud Run ingress (allUsers binding removed)
- PII scrubber on all OTel span attributes (`PiiScrubSpanProcessor`)
- §20.5 tenant isolation enforced at data layer (WHERE tenant_id = @tenant_id)
- GovernorBudgetExceeded → HTTP 402 with user-readable response

**Infrastructure**

- Firebase Hosting: bench + replay + auth dashboards at `atelier-build-2026.web.app`
- A2A Agent Card at `/.well-known/agent.json` — A2A protocol discoverable
- Cloudflare DNS: all `*.atelier.autonomous-agent.dev` subdomains live
- Terraform: project migrated from `i-for-ai` to `atelier-build-2026`
- Multi-origin CORS via comma-separated `ATELIER_DASHBOARD_ORIGIN` env var

**Observability**

- 15-attribute OTel span schema (PRD §7.3) wired through scrubbed `set_atelier_span_attrs()`
- `latency_ms` computed property on `TrajectoryRecord` (derived from started_at/ended_at)
- Bench data publisher: BQ → `bench-schema.json` with nightly CI publish
- `bench-publish.yml` CI workflow: daily cron + push-on-phase/2, Workload Identity Federation

**Evaluation**

- ADK golden evaluation set: 5 canonical design briefs in `EvalSet` format (`tests/eval/golden_set.json`)
- Trajectory fixture corpus: 30-record JSONL golden dataset with exact score distributions
- 5 parametric unit tests for DPO builder: completeness, tenant isolation, outcome distribution

**Architecture Documentation**

- `docs/architecture/optimize-pillar.md` — DPO flywheel Observe → Simulate → Verify
- `docs/architecture/govern-pillar.md` — six-layer governance stack
- agents-cli scaffold example (`examples/agents-cli-scaffold/`)

### Fixed

- AG-06: `stitch_degraded=False` when governor fail-softs (not conflated with Stitch MCP availability)
- AG-07: `BigQuerySessionBackend` fully implements `BaseSessionService` protocol
- IDOR: BQ queries filter by `tenant_id` at data layer (defense-in-depth)
- CORS: multi-origin support for production + staging domains
- Null latency schema validation: omit `avg_latency_ms`/`p99_latency_ms` when no data (prevents JSON null → type:number failure)
- Firebase Hosting ignore: replaced unsupported glob negation with specific dotfile excludes

### Security

- All endpoints require Firebase Auth except `/health` and `/auth/signin`
- Ownership verification on session replay (`/v1/replay/{session_id}`)
- `firebase-admin==7.4.0` (Apache-2.0, local JWT verification, sub-1ms cached key lookup)
- CSP headers on all Firebase Hosting responses
- SQL injection defense via GCP project ID regex validation in bench publisher
- `detect-secrets` pre-commit hook enabled
- KMS per-tenant encryption with 90-day key rotation

[0.2.0-phase-2-gate]: https://github.com/Manzela/atelier/compare/v0.1.2-alpha...v0.2.0-phase-2-gate

---

## [0.1.2-alpha](https://github.com/Manzela/Atelier/compare/v0.1.1-alpha...v0.1.2-alpha) (2026-05-20)

### Documentation

- **research:** Add sprint recovery research & audit artifacts ([9b70317](https://github.com/Manzela/Atelier/commit/9b70317d7834179cb09bd7f0c41b7a79bf326dd5))

## [0.1.1-alpha](https://github.com/Manzela/atelier/compare/v0.1.0-alpha...v0.1.1-alpha) (2026-05-15)

### Bug Fixes

- **ci:** Generate package-lock + trim workspaces + loosen Python pin + relax local hooks ([6c2fe1a](https://github.com/Manzela/atelier/commit/6c2fe1a4e288f96a422b40e6a7fa37e60cfd2831))

### Documentation

- **adr:** Absorb audit approvals — ADRs 0011-0013 ratified, +22 features queued ([c909dbf](https://github.com/Manzela/atelier/commit/c909dbf9a4541bc136b9f22de87aa41df94ac491))
- **adr:** Add ADR 0011 Web-Research-Augmented Intake (N14) + N15 MJG ([8022ec2](https://github.com/Manzela/atelier/commit/8022ec281daedf65e206534b714bd598bd06fbaf))
- Correct feature count from 198/~194 to verified 183 across all docs ([cb8425a](https://github.com/Manzela/atelier/commit/cb8425a57183d5ee6c180760e28cf51608ef39a2))
- **plan:** Add 21-day sprint implementation plan + populate features.json ([861d592](https://github.com/Manzela/atelier/commit/861d59242bf5ecba282160b931fd6699004a87d3))
- **secrets:** Document GCP Secret Manager pattern + add deny-by-default gitignore ([f85c68a](https://github.com/Manzela/atelier/commit/f85c68aff37fee21f6ad0add550fa7f05e88920c))
- **spec:** Add SESSION-COMPLETE handoff for context-loss-safe sprint resumption ([783f6e5](https://github.com/Manzela/atelier/commit/783f6e581ac3aa70aa85d3b33a42f2ee6bf327af))
- **sprint:** Add compact session insights for D1 startup ([5b85320](https://github.com/Manzela/atelier/commit/5b8532013db16ddb831e060286ff954266d8cc6f))
- **sprint:** Log P2 blocker for vite security PRs [#21](https://github.com/Manzela/atelier/issues/21)/[#22](https://github.com/Manzela/atelier/issues/22) ([3ac9b4d](https://github.com/Manzela/atelier/commit/3ac9b4d4650e5c4679e93ffed2e5700de6910a1f))

### Continuous Integration

- Bulk pre-commit fixes + relax markdownlint + add Research Knowledge Base ([19dcbcf](https://github.com/Manzela/atelier/commit/19dcbcf73bb02808d254198d06a9cc3183b82e62))
- Minimize workflow credit usage across GitHub Pro quota ([d692bdd](https://github.com/Manzela/atelier/commit/d692bdddeb1344c41c15849b86c1fe3f200ae18a))

---

## [Unreleased]

### Added

- Initial repository scaffold with full SDLC + CI/CD infrastructure
- PRD: Atelier autonomous design agent (831 lines, 13 novel contributions, 5 quantified 10× axes, full Google-native production stack)
- 10 Architecture Decision Records (MADR format) covering wrap-don't-fork inheritance, Cloud Run not Agent Engine for runtime, tiered sandboxing, PIP layer, RLRD, Google-native stack, EvoDesign K-candidate search, multi-judge Bayesian consensus, public calibration dashboard, A2UI-native output
- Full SDLC documentation: README, CHANGELOG, ROADMAP, SECURITY, CONTRIBUTING, CODE_OF_CONDUCT, GOVERNANCE, NOTICE
- Repo discipline: locked-decisions index (`DECISIONS.md`), rejected-approaches log (`REJECTED.md`), one-time bootstrap (`init.sh`)
- GitHub Actions workflows: CI (lint + typecheck + unit + integration + security + build), eval (nightly WebGen-Bench + Design2Code), CodeQL security scanning, release (release-please), docs (mkdocs to Firebase Hosting), stale issue management
- Pre-commit hooks: ruff format/check, mypy strict, pytest fast subset, commitlint, detect-secrets, markdownlint
- Issue templates (bug, feature, eval-failure, docs) + PR template + CODEOWNERS + Dependabot config
- Project conventions: commit messages (Conventional Commits 1.0.0), branching (worktree-per-phase per ADR 0007), code style (Python ruff + TypeScript strict + shell strict mode), logging (structured JSON, OTel GenAI semconv)
- Operational runbooks: recovery, on-call, deployment, incident response, customer support
- Three-subfolder repo split: `atelier-core/` (engine), `atelier-eval/` (suite + benchmarks), `atelier-deploy/` (infra)
- Plus: `atelier-dashboard/` (live observability), `atelier-action/` (GitHub Marketplace), `atelier-figma-plugin/`, `atelier-chrome-extension/`

### Notes

- This `[Unreleased]` section accumulates work intended for the first tagged release `v0.1.0-alpha` (Phase 1 acceptance gate).
- Phases 2 and 3 will produce `v0.2.0-beta` and `v1.0.0` (public launch) respectively.

---

## Release tagging plan

| Tag            | Date       | What it represents                                                                                                              |
| -------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `v0.1.0-alpha` | 2026-05-21 | Phase 1 Foundation gate passed — single-surface end-to-end working on Cloud Run staging                                         |
| `v0.2.0-beta`  | 2026-05-28 | Phase 2 10× Mechanisms gate passed — 12-surface autonomous campaign converges + WebGen-Bench ≥ 51 + beta tenant cohort onboarded |
| `v1.0.0`       | 2026-06-03 | Public launch + Google for Startups AI Agents Challenge submission filed                                                        |
| `v1.1.0`       | TBD        | Post-launch features (multiplayer dashboard, voice input, Discord community)                                                    |
| `v2.0.0`       | TBD        | SOC 2 Type 2 + per-tenant CMEK + HIPAA tier                                                                                     |

[Unreleased]: https://github.com/Manzela/atelier/compare/v0.0.0...HEAD
