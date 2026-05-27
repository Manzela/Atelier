# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

Releases are managed via [release-please](https://github.com/googleapis/release-please) — Conventional Commits in `main` are parsed to generate release notes automatically. Do not edit released sections by hand; edits go to `[Unreleased]`.

---

## [0.2.0-alpha](https://github.com/Manzela/Atelier/compare/v0.1.2-alpha...v0.2.0-alpha) (2026-05-25)


### Features

* **intake,observability:** R9-A — Brief Parser + OTel span schema ([5888370](https://github.com/Manzela/Atelier/commit/5888370b41934cf67a16c98e3433957bf5885272))
* **memory:** T8 — BigQueryEpisodicBackend implements write_episodic() ([c4b9577](https://github.com/Manzela/Atelier/commit/c4b9577a1cce6f772636a6a8f8c749948acf5d0d))
* **nodes:** ConsensusAgent Phase 2 LLM judge integration ([8b965f7](https://github.com/Manzela/Atelier/commit/8b965f745f408804a2d4754bde4a4d09c09ff21e))
* **optimize:** T14 — GeneratorTuner.tune() + evaluate_and_promote() ([2bcd93a](https://github.com/Manzela/Atelier/commit/2bcd93afa2ff9262e16e96895e83566358e33002))
* **optimize:** T6 — DPO tuning job migration to google-genai PREFERENCE_TUNING ([f1a2628](https://github.com/Manzela/Atelier/commit/f1a262806e1df7bb1841cb6899cb74f5c630555e))
* **optimize:** T7 — GeneratorTunerProtocol + BigQueryPairMiner.mine_pairs() ([128a9e6](https://github.com/Manzela/Atelier/commit/128a9e6887e54a57d5d2b8fee2caf40e40060cb7))
* **orchestrator:** Implement generator ensemble and pipeline integration (R9-C) ([bc736db](https://github.com/Manzela/Atelier/commit/bc736db78bad67cb75dffc65878bf6fc65093909))
* **phase2:** Phase 1 Gate — SOTA Protocol surfaces + N1→N3a pipeline ([#26](https://github.com/Manzela/Atelier/issues/26)) ([bd57e3c](https://github.com/Manzela/Atelier/commit/bd57e3cbd4db55f681bb6995f7b5587c2bfd6e96))
* **router:** T13 — EpsilonGreedyBandit v1 PhaseAwareMoERouter ([8d10cd8](https://github.com/Manzela/Atelier/commit/8d10cd8361e2b711147922985c41a9aabf058c4d))


### Bug Fixes

* **ci:** Expand mypy overrides for Antigravity ADK-dependent modules ([bd34071](https://github.com/Manzela/Atelier/commit/bd340711f17a4a8c0a86f9e2eac24c119c241050))
* **ci:** Resolve mypy errors blocking CI after R9-B pull ([b92e1f1](https://github.com/Manzela/Atelier/commit/b92e1f1630e3c7242157fa2db1bf1b48be87ac82))
* **deps:** Add google-adk and google-cloud-secret-manager to runtime deps ([598b7d5](https://github.com/Manzela/Atelier/commit/598b7d514a28c808ddcf8e399bcd6899c4124568))
* **deps:** Align .nvmrc with node 22.20.0 pin (R4-04) ([ca1dd74](https://github.com/Manzela/Atelier/commit/ca1dd745bc9d40735ca088ff28dd063cf0a69fba))
* **features:** Correct F0006 evidence_tests (R4-01) ([261fcbf](https://github.com/Manzela/Atelier/commit/261fcbfff59854cf5bcbfc9888432d195549d246))
* **features:** Correct FA-009 evidence_tests (R4-02) ([cb9abd3](https://github.com/Manzela/Atelier/commit/cb9abd3baa646c3bff46efdf668102d5b891fae4))
* **features:** Correct FA-010 evidence_tests (R4-03) ([129a7d4](https://github.com/Manzela/Atelier/commit/129a7d47f4ceddac76ba108134e374c2470c168b))
* **governor,dpo,spans,runner:** R9-B audit — unblock test suite + lint sweep + spec compliance ([ffc6060](https://github.com/Manzela/Atelier/commit/ffc606010f7c365621010dcbbfbe0ee7bd68f124))
* **security,edge-cases:** Parallel audit findings — 5 bugs + 3 WARNs fixed ([bb78d4b](https://github.com/Manzela/Atelier/commit/bb78d4b731089dfe0c68f42a69ee4386e64f1b4e))
* **tests:** Correct async markers and config file paths in integration/security tests ([d9bd9f0](https://github.com/Manzela/Atelier/commit/d9bd9f0a67129f40a27be8737412143fb60b631a))


### Security

* Harden public repo — CodeQL, Scorecard, dep review, action pinning ([23d80aa](https://github.com/Manzela/Atelier/commit/23d80aa2dd3b984c974f39959f8b44aa2a50ca8a))


### Documentation

* **audit:** Disclose R3 bulk-commit drift + push reconciliation (R4-05, R4-06) ([a221d9d](https://github.com/Manzela/Atelier/commit/a221d9d4d8b9353b85593886e4a8961dc7d4f796))
* **audit:** R4 handoff (R4-handoff) ([87e3342](https://github.com/Manzela/Atelier/commit/87e33427e03365cce32712503482d9c43557ee64))
* **audit:** R9 executor brief — N1 Brief Parser, OTel, Governor, DPO pipeline ([a893ff7](https://github.com/Manzela/Atelier/commit/a893ff72816d6ff0ec04eb5b882556746fb76c1a))
* **audit:** Round-3 verdict + Round-4 remediation brief ([abac444](https://github.com/Manzela/Atelier/commit/abac444658ccf2bee72c2d2da7256a68735b3234))
* **audit:** Round-4 verdict (APPROVE close-out) + Round-5 hygiene brief ([0549469](https://github.com/Manzela/Atelier/commit/0549469ad4d9112c8e1ac2b597e23e6b490add1e))
* **plan,brief:** Apply verification findings F1-F8 (F9 retracted) ([ef4c9b2](https://github.com/Manzela/Atelier/commit/ef4c9b2fe99289fdda69a51a717e374134ec496e))
* **plan,sprint:** Verification pass — F5 contradiction + test fix record ([db40f73](https://github.com/Manzela/Atelier/commit/db40f73b0cca82f5d4af57a66ba1c511b689df02))
* **plan:** T6-T14 SOTA Protocol implementation plan ([09d2a3e](https://github.com/Manzela/Atelier/commit/09d2a3e3e26e062b1725b422ab1383ee87e57fa2))
* **spec:** Add Days 11-21 parallel execution design ([1051dec](https://github.com/Manzela/Atelier/commit/1051decdf42ce3e26e726fa3dd7f7d3d789f6e51))
* **spec:** Post-R4 strategic roadmap design (§0-§24) — SOTA arch + R4 reconciliation + GCP migration ([0e1c3b1](https://github.com/Manzela/Atelier/commit/0e1c3b1b7823eddb05439a63995a1aa0b51a1c8f))
* **sprint:** D14 actions — record completed GCP deployment + remove UIBench gate ([7038186](https://github.com/Manzela/Atelier/commit/7038186140864d76b2eae5c24b430597d1fe42dc))

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
