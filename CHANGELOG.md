# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

Releases are managed via [release-please](https://github.com/googleapis/release-please) — Conventional Commits in `main` are parsed to generate release notes automatically. Do not edit released sections by hand; edits go to `[Unreleased]`.

---

## [0.1.2-alpha](https://github.com/Manzela/Atelier/compare/v0.1.1-alpha...v0.1.2-alpha) (2026-05-20)


### Documentation

* **research:** Add sprint recovery research & audit artifacts ([9b70317](https://github.com/Manzela/Atelier/commit/9b70317d7834179cb09bd7f0c41b7a79bf326dd5))

## [0.1.1-alpha](https://github.com/Manzela/atelier/compare/v0.1.0-alpha...v0.1.1-alpha) (2026-05-15)


### Bug Fixes

* **ci:** Generate package-lock + trim workspaces + loosen Python pin + relax local hooks ([6c2fe1a](https://github.com/Manzela/atelier/commit/6c2fe1a4e288f96a422b40e6a7fa37e60cfd2831))


### Documentation

* **adr:** Absorb audit approvals — ADRs 0011-0013 ratified, +22 features queued ([c909dbf](https://github.com/Manzela/atelier/commit/c909dbf9a4541bc136b9f22de87aa41df94ac491))
* **adr:** Add ADR 0011 Web-Research-Augmented Intake (N14) + N15 MJG ([8022ec2](https://github.com/Manzela/atelier/commit/8022ec281daedf65e206534b714bd598bd06fbaf))
* Correct feature count from 198/~194 to verified 183 across all docs ([cb8425a](https://github.com/Manzela/atelier/commit/cb8425a57183d5ee6c180760e28cf51608ef39a2))
* **plan:** Add 21-day sprint implementation plan + populate features.json ([861d592](https://github.com/Manzela/atelier/commit/861d59242bf5ecba282160b931fd6699004a87d3))
* **secrets:** Document GCP Secret Manager pattern + add deny-by-default gitignore ([f85c68a](https://github.com/Manzela/atelier/commit/f85c68aff37fee21f6ad0add550fa7f05e88920c))
* **spec:** Add SESSION-COMPLETE handoff for context-loss-safe sprint resumption ([783f6e5](https://github.com/Manzela/atelier/commit/783f6e581ac3aa70aa85d3b33a42f2ee6bf327af))
* **sprint:** Add compact session insights for D1 startup ([5b85320](https://github.com/Manzela/atelier/commit/5b8532013db16ddb831e060286ff954266d8cc6f))
* **sprint:** Log P2 blocker for vite security PRs [#21](https://github.com/Manzela/atelier/issues/21)/[#22](https://github.com/Manzela/atelier/issues/22) ([3ac9b4d](https://github.com/Manzela/atelier/commit/3ac9b4d4650e5c4679e93ffed2e5700de6910a1f))


### Continuous Integration

* Bulk pre-commit fixes + relax markdownlint + add Research Knowledge Base ([19dcbcf](https://github.com/Manzela/atelier/commit/19dcbcf73bb02808d254198d06a9cc3183b82e62))
* Minimize workflow credit usage across GitHub Pro quota ([d692bdd](https://github.com/Manzela/atelier/commit/d692bdddeb1344c41c15849b86c1fe3f200ae18a))

## [0.2.0-beta](https://github.com/Manzela/Atelier/compare/v0.1.2-alpha...v0.2.0-beta) (2026-05-25)

Phase 2: 10× Mechanisms — consensus pipeline, trajectory recording, DPO flywheel, production infrastructure.

### Added

- **Full DAG pipeline**: N3c deterministic gates + N3d multi-judge consensus + N4 best-pick selection
- **POST `/v1/generate` endpoint** with trajectory recorder wiring and structured error responses
- **Bench data publisher** (`generate_bench_data.py`): BQ → `bench-schema.json` pipeline with fail-soft DEMO fallback
- **CI workflow** (`bench-publish.yml`): daily cron + push-on-`phase/2`, Workload Identity Federation, Firebase deploy
- **Trajectory fixture corpus**: 30-record JSONL golden dataset with exact score distributions
- **5 parametric unit tests** for DPO builder: completeness, tenant isolation, outcome distribution, judge votes, pair extraction
- **A2A Agent Card** (`.well-known/agent.json`): Atelier registered as A2A-discoverable agent
- **agents-cli scaffold** (`examples/agents-cli-scaffold/`): round-trip demo with `agent.yaml`, `agent.py`, README
- **Optimize pillar README** (`docs/architecture/optimize-pillar.md`): "Observe → Simulate → Verify" DPO flywheel documentation
- **Govern pillar README** (`docs/architecture/govern-pillar.md`): Registry/Identity/Gateway/Policy/Security/Audit mapping
- **`latency_ms` computed property** on `TrajectoryRecord`: derived from `started_at`/`ended_at`, emitted in `to_bq_row()`, resolves P1-7 latency gap

### Changed

- **CORS**: multi-origin support via comma-separated `ATELIER_DASHBOARD_ORIGIN` env var (was single-origin)
- **Terraform**: added `ATELIER_DASHBOARD_ORIGIN` env block to Cloud Run container definition
- **`firebase.json`**: replaced `__ATELIER_API_SERVICE_ID__` placeholder → `atelier-api-staging`; added `!.well-known` ignore override

### Fixed

- **AG-04 safety sweep**: all `LlmAgent` declarations use `generate_content_config.safety_settings` (not deprecated `safety_settings` param)
- **AG-06 Stitch degradation**: `stitch_degraded` flag only reflects Stitch MCP unavailability (not governor budget exhaustion)
- **AG-07 BigQuerySessionBackend**: implements `SessionBackend` protocol with correct `create_session`/`get_session` signatures
- **AG-10 PII scrubber**: `PiiScrubSpanProcessor` redacts email/phone/JWT from OTel spans before export
- **AG-01/02/03 Terraform**: project ID deduplication, IAP-protected ingress, DNS wildcard certificate
- **Bench data**: SQL injection defense via GCP project ID regex validation
- **Test fixture**: `test_replay_api.py` app_client fixture `yield` instead of `return` (BYPASS_AUTH context exit)

### Security

- Removed `allUsers` IAM binding from Cloud Run — all traffic through IAP
- KMS per-tenant encryption with 90-day key rotation
- `detect-secrets` pre-commit hook enabled
- CSP headers on all Firebase Hosting responses

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
