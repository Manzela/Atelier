# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

Releases are managed via [release-please](https://github.com/googleapis/release-please) — Conventional Commits in `main` are parsed to generate release notes automatically. Do not edit released sections by hand; edits go to `[Unreleased]`.

---

## [0.3.0-alpha](https://github.com/Manzela/Atelier/compare/v0.2.0-alpha...v0.3.0-alpha) (2026-06-11)


### Features

* **api:** SSE streaming pipeline + multi-surface plan (phase/2 WIP) ([67d1a5b](https://github.com/Manzela/Atelier/commit/67d1a5b7043c1d0383655db84ac5ebe7ff319be1))
* **api:** Surface best_html + D-O-R-A-V + Nielsen on the SSE complete event (AT-040) ([7b22411](https://github.com/Manzela/Atelier/commit/7b2241149c6b4490c949d1419a7b4de66fc89553))
* **AT-020b:** Board task-doc emitter — drive one task doc through the exact 6-column lane ([e9b7ac4](https://github.com/Manzela/Atelier/commit/e9b7ac4151a1fbce5724d997d111811b41f5698d))
* **AT-025:** WRAI grounded research — Model Armor, applicable standards, reference seeding ([7fda768](https://github.com/Manzela/Atelier/commit/7fda768befdd45b383886618eb59775a46e0267e))
* **AT-026:** Agentic legibility / accountability layer over SSE + replay ([76bba7a](https://github.com/Manzela/Atelier/commit/76bba7afe23ed5b0dd50c9a5c3f0422ef0e04574))
* **AT-027:** Surface Optimize assets (simulation / MoE route / DPO) read-only ([b19ff08](https://github.com/Manzela/Atelier/commit/b19ff08d46b966f46c93ed0aa72db383f0587bde))
* **AT-030:** Clarify gate — uncertainty-gated, event-driven, extends PlanStep ([eb76889](https://github.com/Manzela/Atelier/commit/eb768890f79a11f158537fa0c0a2416f8300eca4))
* **AT-041:** Kanban board /board — live 6-column reader of the AT-020b task docs ([ff2f8c2](https://github.com/Manzela/Atelier/commit/ff2f8c2ff5fc82a5361612a3705e3e1ad52f8296))
* **AT-042:** ApprovalCard — push-free sign-off over Firestore onSnapshot ([583aa70](https://github.com/Manzela/Atelier/commit/583aa707d17a684b6c5296dc9920f20a601b13fe))
* **AT-053:** Persistent per-tenant design-system memory, enforced by AT-012 gate ([0084634](https://github.com/Manzela/Atelier/commit/0084634006d5cfa6c90ae29c896c93532d850e3a))
* **AT-094:** Acknowledged-degradation surfacing (R9) in the Studio UI ([3d9f37a](https://github.com/Manzela/Atelier/commit/3d9f37a5a6f6bdd0bb73d2d90d5fe9eabaf48d16))
* **ci:** AT-102 reviewer DONE-evidence gate (envelope re-run, not a vibe-string) ([52d32d5](https://github.com/Manzela/Atelier/commit/52d32d514d72040b8a6fa190211048d0824b475a))
* **ci:** Repo hygiene gate + sanitize emoji/AI-tells + docs/STYLE.md (AT-099) ([fe6b10c](https://github.com/Manzela/Atelier/commit/fe6b10c268544edbf95792cd50e5b4b7cc7f937d))
* **ci:** Repo hygiene gate + sanitize emoji/AI-tells + docs/STYLE.md (AT-099) ([cd300ee](https://github.com/Manzela/Atelier/commit/cd300eed917ed536fd1e5cea62fddf723f1233fa))
* Complete SDLC audit, fix A2UI conformance, and harden FinOps controls ([d019cd3](https://github.com/Manzela/Atelier/commit/d019cd31d0baf364d561c39258cb784848b49430))
* **dashboard:** AT-096 live token meter (used / 5,000,000) ([132fb75](https://github.com/Manzela/Atelier/commit/132fb75a74204765b214f6dc40c991421edb6eb5))
* **dashboard:** AT-096 live token meter (used / 5,000,000) ([d02b47f](https://github.com/Manzela/Atelier/commit/d02b47f556e8a407e36d7de232043b136f3e1f1d))
* **eval:** AT-100 deterministic offline eval gate (regression-sensitive) ([9b34850](https://github.com/Manzela/Atelier/commit/9b3485020b589fc3de365c0446d2993af8e4ccc5))
* **eval:** AT-100 deterministic offline eval gate (regression-sensitive) ([9bfe0e2](https://github.com/Manzela/Atelier/commit/9bfe0e23f4818644a6410ee985b9e6410230c2a5))
* **firestore:** AT-084 tenant-isolation rules + indexes + emulator test ([8bb0bf4](https://github.com/Manzela/Atelier/commit/8bb0bf451f48aeceb65da30d8cd90151b146788b))
* **firestore:** AT-084 tenant-isolation rules + indexes + emulator test ([b4b73b2](https://github.com/Manzela/Atelier/commit/b4b73b28ca0d019763bfdaf416f88c067de45837))
* **gates:** DTCG token-fidelity zero-tolerance gate (AT-012) ([440018d](https://github.com/Manzela/Atelier/commit/440018dabef66a6ed999d24ee9a302f06340e632))
* **gates:** Real axe-core a11y oracle, fail-closed on critical/serious (AT-011) ([84a3628](https://github.com/Manzela/Atelier/commit/84a362856db991c90a49a4c1b697d3dce16495ee))
* **gates:** WCAG 2.2 AA contrast oracle + Lighthouse lab config (AT-013) ([a1974e5](https://github.com/Manzela/Atelier/commit/a1974e5ddfb4043a256c3d63b5c00035eecdc75f))
* **governance:** Tiered model routing + per-tier token caps (AT-044 ext.) ([990ce65](https://github.com/Manzela/Atelier/commit/990ce6520a2070a7ee5f81037e61cdf1581b57ba))
* **governor:** AT-095 per-user lifetime 5M-token hard cap ([0512bae](https://github.com/Manzela/Atelier/commit/0512bae3dba8465bd79027a26d09f00bf0b8e514))
* **governor:** AT-095 per-user lifetime 5M-token hard cap ([822b7dc](https://github.com/Manzela/Atelier/commit/822b7dccecf2fdc69b3533f83866b91a64512bb5))
* **governor:** AT-097 token-abuse / quota-DoS hardening — global circuit-breaker + N3d judge-token threading ([32140c7](https://github.com/Manzela/Atelier/commit/32140c71bbbe467f143a14452bbd9c04a541be37))
* **governor:** AT-097 token-abuse / quota-DoS hardening — global circuit-breaker + N3d judge-token threading ([91ec810](https://github.com/Manzela/Atelier/commit/91ec810f8fa7c4597fabbeccccdc795b5c1bf501))
* Implement mobile responsiveness for StudioClientShell and StitchClientShell sidebars and prompt card ([532433f](https://github.com/Manzela/Atelier/commit/532433f9de50d5c5adfcc4bdcb17d0e0b65bdde6))
* **models:** InteractionSpec schema + parser for AT-023; specialist emits structured JSON ([4dc5df8](https://github.com/Manzela/Atelier/commit/4dc5df84f1fdd33456357a568c7a844dc4b72f7d))
* **models:** Pin served Gemini model id to gemini-2.5-pro (AT-024) ([628b1a5](https://github.com/Manzela/Atelier/commit/628b1a55cf14bc66228463b15e167f860cf1ebc9))
* **nodes:** AT-021 QA critique panel + gate-floor synthesizer (anti-inverted-gate) ([5acc05d](https://github.com/Manzela/Atelier/commit/5acc05d3fb34e9c768dcc590e8d7e419879c6d1a))
* **nodes:** AT-021 QA critique panel + gate-floor synthesizer (anti-inverted-gate) ([7c1c08e](https://github.com/Manzela/Atelier/commit/7c1c08e17f52a4c086bfc79681d934a7fd53310e))
* **nodes:** AT-022 Nielsen-10 usability presence oracle (&gt;=2/3 vote, presence-only) ([b3f036c](https://github.com/Manzela/Atelier/commit/b3f036c655ebde9b9a65a5a2249069419fc33ebd))
* **nodes:** AT-022 Nielsen-10 usability presence oracle (≥2/3 vote, presence-only) ([0e7f9f2](https://github.com/Manzela/Atelier/commit/0e7f9f23063bc62799dd140dfd0b78a7f64ad285))
* **oracle:** Run-completion oracle verify_run over ACCEPTANCE.json (AT-007) ([130111c](https://github.com/Manzela/Atelier/commit/130111c32d78e6cc117770dbce30dc0983726678))
* **orchestrator:** AT-020 DDLC role-specialist SequentialAgent (replace K=3 ensemble) ([4af1707](https://github.com/Manzela/Atelier/commit/4af17071f45df53773f0d0c085b5d8d8a603d86d))
* **orchestrator:** AT-020 DDLC role-specialist SequentialAgent (replace K=3 ensemble) ([1d4e746](https://github.com/Manzela/Atelier/commit/1d4e74660f1f6d30a6b84376e80b22bdbee3ae64))
* **orchestrator:** AT-031 fail-closed HITL sign-off gate (durable, idempotent resume) ([67b82d2](https://github.com/Manzela/Atelier/commit/67b82d22a443547ef81de2a540fb07d1f9b3a382))
* **orchestrator:** AT-031 fail-closed HITL sign-off gate (durable, idempotent resume) ([ac7f8d8](https://github.com/Manzela/Atelier/commit/ac7f8d894b02e2374948f5ac508e58115df951fd))
* **orchestrator:** R4 anchor re-injection in the bounded loop (AT-005) ([030f543](https://github.com/Manzela/Atelier/commit/030f543a7a35b49b2864ee793de57b0e52dc015b))
* **orchestrator:** Stop-reason enum + strict precedence (AT-005 R1 core) ([2069a40](https://github.com/Manzela/Atelier/commit/2069a401ae05627e36bf4d06045449f683e453d3))
* **orchestrator:** Wire stop-reason precedence into the runner loop (AT-005 R1) ([2545ee9](https://github.com/Manzela/Atelier/commit/2545ee931dafc5688cdd1d4619609e1e76b8c5a7))
* **pipeline:** Implement N3 convergence loop; sanitize audit footprints ([94fe746](https://github.com/Manzela/Atelier/commit/94fe7467a07f4f4fb8382b3c653aa4009ea4f297))
* **platform:** Agent Platform backend — registry, read-only /v1/platform API, per-agent A2A cards ([ba56c35](https://github.com/Manzela/Atelier/commit/ba56c357d8051c094c52c386339dedbb648f4c4c))
* **platform:** Agent Platform frontend — four pillars, data-driven topology, typed client ([0ef4c90](https://github.com/Manzela/Atelier/commit/0ef4c90f430dadab20474c8231b4673a20b741cc))
* **platform:** Real-time agent-state sync, token revocation on spend routes, Build/Scale pillar docs ([3ec973f](https://github.com/Manzela/Atelier/commit/3ec973f56c9d42fefb154c31b975d84bbf5114b8))
* **studio:** Adopt Next.js Studio dashboard onto trunk (AT-040 substrate) ([c70ab83](https://github.com/Manzela/Atelier/commit/c70ab83d85e407362eb23420acc48bba5106e910))
* **studio:** Adopt Next.js Studio dashboard onto trunk + CI gate (AT-040 substrate) ([eacc4c8](https://github.com/Manzela/Atelier/commit/eacc4c8a80bbbe97f4b8a09bb07f753ece1607ef))
* **studio:** AT-023 Interaction Designer — interaction_spec schema + Playwright interaction acceptance ([7112214](https://github.com/Manzela/Atelier/commit/711221432a1859672148d3c9d328048e3c9b2ffd))
* **studio:** AT-040 device-frame toggle + Playwright acceptance suite + CI e2e ([c8c3989](https://github.com/Manzela/Atelier/commit/c8c3989f08dc28a6974447db9aad5ff663575e53))
* **studio:** AT-043 designed states (empty/loading/degraded/error/cap-reached) + axe e2e ([d225b3d](https://github.com/Manzela/Atelier/commit/d225b3d6539848a3b287e9b15c6fe3e31aea8809))
* **studio:** AT-043 designed states (empty/loading/degraded/error/cap-reached) + axe e2e ([c4cd6b2](https://github.com/Manzela/Atelier/commit/c4cd6b2ad330c5f3740efdb6836b1a8cb6df8cc1))
* **studio:** AT-044 design-system panel + agent-generated controls ([cf729d0](https://github.com/Manzela/Atelier/commit/cf729d0cf1b19f400de842846120fbdc629e6ec2))
* **studio:** AT-044 design-system panel + agent-generated controls ([6923adb](https://github.com/Manzela/Atelier/commit/6923adb3fdd2e772605926b1efe1e14d7e7dae13))
* **studio:** AT-090 competitor-contrast beat (README + Studio panel) ([1d7f134](https://github.com/Manzela/Atelier/commit/1d7f134e2e20cdf1548520a82d88e03416cb5b83))
* **studio:** AT-090 competitor-contrast beat (README + Studio panel) ([49d5a66](https://github.com/Manzela/Atelier/commit/49d5a66cbe8507026a6f7280300b657009bb1712))
* **studio:** AT-093 animated converging D-O-R-A-V scorecard (real per-iteration SSE) ([f6d8e90](https://github.com/Manzela/Atelier/commit/f6d8e90cef2a5e6fd9eae6ec63ef4c818dfe368d))
* **studio:** AT-093 animated converging D-O-R-A-V scorecard (real per-iteration SSE) ([bb84a42](https://github.com/Manzela/Atelier/commit/bb84a42d5ef909087fadae42ca88b8ae89f4654d))
* **studio:** Device-frame toggle + AT-040 Playwright acceptance suite + CI e2e job ([238481f](https://github.com/Manzela/Atelier/commit/238481fbb1829597fb68a69474c0b1754736c7f1))
* **studio:** Live canvas + D-O-R-A-V/Nielsen scorecard render real output (AT-040 Increment 2) ([8ddc38b](https://github.com/Manzela/Atelier/commit/8ddc38bfe2270fb0a7d3c84029962f1887b5455f))
* **studio:** Render converged best_html in sandboxed iframe + live D-O-R-A-V/Nielsen scorecard (AT-040) ([40a4306](https://github.com/Manzela/Atelier/commit/40a4306bf388992171bdfde7f2af138e9874632f))
* **tokens:** AT-052 token round-trip proof (code surfaces + Studio iframe) ([5555198](https://github.com/Manzela/Atelier/commit/55551983a20f9017ceecffbe315107d430eb9fcf))
* **tokens:** AT-052 token round-trip proof (code surfaces + Studio iframe) ([d0017f9](https://github.com/Manzela/Atelier/commit/d0017f93c6ad3641096cdf40ad5f2865232517bb))
* **tokens:** DTCG token source + Style Dictionary v4 fan-out (AT-050) ([0907d51](https://github.com/Manzela/Atelier/commit/0907d513fb8b7e443f3cb55607b55e40bcbe08b3))
* **v1:** Go-Live E8 — Vertex Session/Memory Bank (AT-080) + Model Armor callbacks (AT-081) ([#68](https://github.com/Manzela/Atelier/issues/68)) ([cc04e94](https://github.com/Manzela/Atelier/commit/cc04e9401a8f73fc42e73d63f0b518a7ef42df9c))
* **v1:** Staging live — dashboard on Cloud Run, AT-101b CI, zod fix, Firebase auth-domains ([#69](https://github.com/Manzela/Atelier/issues/69)) ([6196f1b](https://github.com/Manzela/Atelier/commit/6196f1bbd1ed74fa7921417113106f4998cbd97b))


### Bug Fixes

* **AT-083:** Resolve openapi smoke-gate vs S9 prod-gating (ADR-0026) ([ec0d95f](https://github.com/Manzela/Atelier/commit/ec0d95f7621f7b90491aac144e7fef45e937d53f))
* **audit:** HANDOFF-R12 remediation — 22 items (5C + 7H + 11M) ([b631103](https://github.com/Manzela/Atelier/commit/b631103e10363867b79d1360022577a9e7115507))
* **audit:** HANDOFF-R12 remediation — 25 production blockers + security hardening ([#29](https://github.com/Manzela/Atelier/issues/29)) ([7e652d0](https://github.com/Manzela/Atelier/commit/7e652d02b131790e254ada7b8868ad3d665c8497))
* **audit:** Resolve go-live checklist audit findings and add launch readiness governance ([050b641](https://github.com/Manzela/Atelier/commit/050b641b5b1838fe5137de69f6c7ba654ed5d365))
* **audit:** Self-review hardening — 3 findings from red-team ([3ca7b07](https://github.com/Manzela/Atelier/commit/3ca7b079fc220299232aeafeb6cda51eaff14ec1))
* **ci,security:** Resolve mypy errors, CodeQL alerts, bench-publish workflow ([f8c54ab](https://github.com/Manzela/Atelier/commit/f8c54abab684bda4a3196693f253232735bfec56))
* **ci:** Add SCAN_EXEMPT to hygiene gate — exempt gate, test, style-guide (AT-099) ([596c2c7](https://github.com/Manzela/Atelier/commit/596c2c7d95f2546b40779729c43ca14da7ee74d3))
* **ci:** AT-102 DONE-must-pass + non-empty files (close fabrication escape) ([650ccd7](https://github.com/Manzela/Atelier/commit/650ccd78972755711d916c800b2e105c3e1e7a94))
* **ci:** AT-102 DONE-must-pass + non-empty files (close fabrication escape) ([e284b0a](https://github.com/Manzela/Atelier/commit/e284b0a7692abc8aa9ed068425b4ae55fd9cdd57))
* **ci:** Break planner↔clarify cyclic import, validate stop session_id, drop unused lexorank globals, make dreaming seed-path container-safe ([5fbd1a5](https://github.com/Manzela/Atelier/commit/5fbd1a575bcbdf7734358a51857235afe35c2a05))
* **ci:** Browser UA in canonical smoke probe ([#98](https://github.com/Manzela/Atelier/issues/98)) ([f622f08](https://github.com/Manzela/Atelier/commit/f622f08d6fe043ca8d55444ec6e96293b4f4af30))
* **ci:** Clear semgrep gate (1 real fix + 6 triaged) and regenerate reviewer envelope ([08d19db](https://github.com/Manzela/Atelier/commit/08d19db206af70ce37b336fc8d463464c85f9b96))
* **ci:** Define job-level env for secrets to resolve workflow parse error ([61807a7](https://github.com/Manzela/Atelier/commit/61807a7a2384c81ad87eb91d0b4e82cb22a16665))
* **ci:** Production smoke probes live Cloud Run URLs directly ([#99](https://github.com/Manzela/Atelier/issues/99)) ([2900f57](https://github.com/Manzela/Atelier/commit/2900f5799f01c592f999e5797517d051c554e1af))
* **ci:** Regenerate secrets baseline with proper plugins ([58d99b5](https://github.com/Manzela/Atelier/commit/58d99b55007e059f4b5e97de37d0653c7f72f83a))
* **ci:** Repin trivy-action v0.33.1 -&gt; v0.36.0 to clear GHSA-69fq-xp46-6x23 + GHSA-9p44-j4g5-cfx5 ([91b3ddc](https://github.com/Manzela/Atelier/commit/91b3ddc135e81aa4034586b2652c76eb3316617a))
* **ci:** Resolve [#79](https://github.com/Manzela/Atelier/issues/79) job failures — bandit MD5, stale e2e assertions, eval coverage ([a057a72](https://github.com/Manzela/Atelier/commit/a057a7275393bfdac4c5c2a1b026379dac45fb46))
* **ci:** Resolve pipeline failures, enforce lockfiles, skip deploy on no secrets, and add competitor beat ([c1614c2](https://github.com/Manzela/Atelier/commit/c1614c2b0db5585f192080d80d2f16095d2e5db9))
* **ci:** Resolve the firebase CLI via --package firebase-tools on a clean runner ([#94](https://github.com/Manzela/Atelier/issues/94)) ([69d42c3](https://github.com/Manzela/Atelier/commit/69d42c3a389091b118a8943349cd87a1d610329f))
* **ci:** Split GCP auth steps, fix types, and update reviewer envelope ([6edd597](https://github.com/Manzela/Atelier/commit/6edd5975fe5c1acf755bc98f3c6265d79d8e893f))
* **ci:** Store AT-040 screenshot reference as binary, not Git LFS ([e682c53](https://github.com/Manzela/Atelier/commit/e682c533f33f564ac3b191d04a179f2804acd280))
* **ci:** Suppress false-positive semgrep in useAgentActivity and regenerate envelope ([8051251](https://github.com/Manzela/Atelier/commit/80512516f8ee43e7cf87e304e1e2766e56d2ea43))
* **ci:** Update reviewer-envelope SHA for runner.py after audit-findings fix ([53a2cc0](https://github.com/Manzela/Atelier/commit/53a2cc04bcab519830a4e36bee7578b56a39f3af))
* **convergence:** Keep FIXER on Flash — restores convergence ([#97](https://github.com/Manzela/Atelier/issues/97)) ([613269b](https://github.com/Manzela/Atelier/commit/613269bc7b02a1bfd43b6cee08893cccef1de911))
* **correctness:** Failure_trichotomy async support + RouteDecision.phase + bandit arm scoping ([2d161eb](https://github.com/Manzela/Atelier/commit/2d161eb4ded4d1078cf54717973e1892b3a9fe3e))
* **dashboard:** Allow Google/Firebase auth domains in CSP so sign-in works ([#74](https://github.com/Manzela/Atelier/issues/74)) ([9fbfe64](https://github.com/Manzela/Atelier/commit/9fbfe64e5c03257c2bb13dccf1e829833f66d9ae))
* **deploy:** Resolve staging/production gaps, CSP connect-src, and test mock signatures ([21d6970](https://github.com/Manzela/Atelier/commit/21d697053e76e12e49daa518ce378113ec1d1480))
* **deploy:** Route /health and agent card through Firebase Hosting to apex domain ([ef6c563](https://github.com/Manzela/Atelier/commit/ef6c5632e4c424ed4cde67acf44350b6348c8d6b))
* **deploy:** Update custom domain routing and fallback auth logic to resolve redirects to /bench ([58ddf89](https://github.com/Manzela/Atelier/commit/58ddf89d79629054321d0c0b44dead8d2d11b725))
* **deploy:** Update firebase.json hosting rewrites mapping to active cloud run serviceId ([80a1319](https://github.com/Manzela/Atelier/commit/80a1319c6ce71f82e6f2586dab72d650d7ba6390))
* **deploy:** Use correct GCP WIF secrets names from repository ([77faaf1](https://github.com/Manzela/Atelier/commit/77faaf15d3e66c17147645debe6bda4f27490154))
* **e2e:** Update studio assertions, conditionalize sidebars, and fix deploy credentials check ([4a5885d](https://github.com/Manzela/Atelier/commit/4a5885d18653eb613aa836ecfaabcf6ba53c03b7))
* **eval:** Scope mypy --strict overrides for untyped playwright + skimage boundaries ([4b0393b](https://github.com/Manzela/Atelier/commit/4b0393bb70d5fe119945f0ee254c9ffc2d38eb02))
* **gates:** Reject empty/skeleton HTML instead of passing it (AT-010) ([aa584e9](https://github.com/Manzela/Atelier/commit/aa584e954f0e5c7d8aaaecb6ea0a8047ba577ff7))
* **gates:** Scan SVG presentation attributes for off-token colors (AT-012 review) ([6a18796](https://github.com/Manzela/Atelier/commit/6a18796396cee5cea7eb1c4ebdb7fbeed666ffa3))
* **gates:** Treat script/style-only pages as skeletons (AT-010 review nit) ([1ce3708](https://github.com/Manzela/Atelier/commit/1ce3708323da8e49c3c297779eda801e9643dd54))
* **governance:** Address audit findings — exceeded_tier SSE + silent tier drop + coverage gaps ([548d28a](https://github.com/Manzela/Atelier/commit/548d28a914adebb9785abd22a99aa93dd1c10d7f))
* **governor:** AT-095 hardening + USD dead-code sweep ([3adef91](https://github.com/Manzela/Atelier/commit/3adef918a9fe6bcbf508f108e12ed5a8a3c16c2e))
* **governor:** AT-095 hardening + USD dead-code sweep ([fdeceb4](https://github.com/Manzela/Atelier/commit/fdeceb4596c2adbd003e9b4bcb8f960c2601ee44))
* **lint:** Bypass set-state-in-effect warning on mounted state ([9eaa591](https://github.com/Manzela/Atelier/commit/9eaa5915db1b2e0e386a8e0cb7f08d7a77ced713))
* **lint:** Resolve full-src ruff debt surfaced by CI on PR [#31](https://github.com/Manzela/Atelier/issues/31) ([c959fc6](https://github.com/Manzela/Atelier/commit/c959fc67463433ff36426416865b526a3e129eb9))
* **pipeline:** Join candidates to scores by id, killing DPO direction-inversion ([#70](https://github.com/Manzela/Atelier/issues/70)) ([61b7af6](https://github.com/Manzela/Atelier/commit/61b7af623ffaa72433a1b182c20d79157d7f03da))
* **security:** AT-095 make the token-cap counter server-write-only ([956627f](https://github.com/Manzela/Atelier/commit/956627ffdd058a38f7f6511917829880ad727f8e))
* **security:** Close 6 P0 ship-blockers from the 2026-06-09 audit ([5d44c78](https://github.com/Manzela/Atelier/commit/5d44c7896e50f23e1fa32970e7736e0e3808b7db))
* **security:** Sanitize remaining user-controlled log values (CWE-117) ([8e59951](https://github.com/Manzela/Atelier/commit/8e59951a10ff15fbbd05c88bc2d820983385c88d))
* Stream complete-event crash, /v1/a2a auth bypass, and agent-card stub ([#75](https://github.com/Manzela/Atelier/issues/75)) ([d7f7aa4](https://github.com/Manzela/Atelier/commit/d7f7aa48a25467a1c23b95348224e5677f6d4a8e))
* **studio:** Drop @lhci/cli dev-dep (kills tmp/postcss transitive vulns) ([1184182](https://github.com/Manzela/Atelier/commit/11841827e30b7874525f8570df74c62517b899a5))
* **studio:** Pin viewport + device for deterministic AT-040 screenshot size ([0d7494e](https://github.com/Manzela/Atelier/commit/0d7494e9e218f65bf4656c12957ce64f3cd6aeef))
* **studio:** Regenerate dashboard lockfile cleanly (npm-ci consistent) ([1aa171d](https://github.com/Manzela/Atelier/commit/1aa171d717c239c38c6e8d1cea6890a425dca3c0))
* **studio:** Retarget AT-040 screenshot to the iframe + wait for content paint ([87846f0](https://github.com/Manzela/Atelier/commit/87846f0fa85d4061e65c1c815c36516a01f23a53))
* **submission:** Pre-submission remediation — multi-surface delivery, plan-seeded oracle, credibility fixes ([#95](https://github.com/Manzela/Atelier/issues/95)) ([55b94bf](https://github.com/Manzela/Atelier/commit/55b94bfeedab6d4b8a2bdbbf747f1c3df1fe081a))


### Security

* Untrack .mcp.json (contained a live token) and gitignore it ([3c8bbc5](https://github.com/Manzela/Atelier/commit/3c8bbc54704ac802c424cd57508ebfff38c7c0b1))


### Documentation

* **go-live:** Add operator runbook, tfvars example, and latency ADR ([#71](https://github.com/Manzela/Atelier/issues/71)) ([6313d7c](https://github.com/Manzela/Atelier/commit/6313d7c1e08ac9f1fdb46a2a4e19a6e34cfbd8cf))
* **nodes:** Correct Workflow deprecation rationale + document skeleton exclusion (review) ([1a3847e](https://github.com/Manzela/Atelier/commit/1a3847e46dab4617772bb785b7601ae81d86ae2a))
* **runbooks:** AT-086 rollback runbook (cert/DNS/deploy recovery) ([1cdf975](https://github.com/Manzela/Atelier/commit/1cdf9753ac6918adcefce2b6e700821ffe5de158))
* **runbooks:** AT-086 rollback runbook (cert/DNS/deploy recovery) ([965009c](https://github.com/Manzela/Atelier/commit/965009c1bc15da766484b1106d7ddb2e2a9bbdff))
* **studio:** AT-090 mark Kanban board as deploy-wave (anti-overclaim) ([147e9cb](https://github.com/Manzela/Atelier/commit/147e9cb4da374550a80a08b732cf4fd9ba295fc5))
* **submission:** Correct Google Cloud claims to the running system ([#72](https://github.com/Manzela/Atelier/issues/72)) ([7ef1b68](https://github.com/Manzela/Atelier/commit/7ef1b6839e8ef21939b5d9c36c14ea19a1778cda))


### Code Refactoring

* **nodes:** Tighten H2 machine-token voter (review NIT) + regression test ([ffd6f57](https://github.com/Manzela/Atelier/commit/ffd6f57f3391343948f913cee176a90a7c9f8b08))


### Tests

* **firestore:** Align AT-095 counter test doc-id to production (usage/lifetime) ([9a36cef](https://github.com/Manzela/Atelier/commit/9a36cefde87c00071f9134570921a772d5d66066))
* **harness:** Record/replay determinism harness (AT-003) ([e3545a6](https://github.com/Manzela/Atelier/commit/e3545a677dd067ab7cdce9aa8b031d9bb56b7403))
* **studio:** Add Linux iframe screenshot reference for AT-040 (CI-generated) ([5161868](https://github.com/Manzela/Atelier/commit/5161868e100b519d06f94e8b24f0874117f49e42))
* **studio:** Add Linux screenshot reference for AT-040 canvas (CI-generated) ([17ff926](https://github.com/Manzela/Atelier/commit/17ff9268bac6419ecb366fafba8705378278d597))
* **studio:** AT-023 Playwright interaction-state acceptance (hover/focus) ([46b0802](https://github.com/Manzela/Atelier/commit/46b0802b28d2a60db7b38e414f1ac2a97e690093))
* **studio:** Fix idle smoke test to assert state-empty testid (AT-043 review) ([3c0a04a](https://github.com/Manzela/Atelier/commit/3c0a04a52e1566b205bfe94ed04f62406714d574))
* **studio:** Regenerate AT-040 Linux iframe reference (fixed viewport/device) ([7fb99c4](https://github.com/Manzela/Atelier/commit/7fb99c44c9bd6ba84b9fbdb058240bc25eb1bda7))


### Build System

* Add Makefile verify|preflight|replay lanes (AT-004) ([ceef83c](https://github.com/Manzela/Atelier/commit/ceef83c045a5396271c7df9bed0359d370d83d4b))
* **deps:** Bump google-adk 1.34.1 -&gt; latest stable 2.1.0 (AT-002) ([5273559](https://github.com/Manzela/Atelier/commit/5273559840dcba52e930b8edbdb670cae2963f7f))
* **deps:** Pin google-adk==1.34.1 across all sources (AT-002) ([b5b9005](https://github.com/Manzela/Atelier/commit/b5b90051bc43d35c403a0e656cc030d722f08c32))


### Continuous Integration

* Add Dashboard (Next.js Studio) typecheck + lint + build gate ([8434a56](https://github.com/Manzela/Atelier/commit/8434a56e3b22f46b39e0a680e48ca46ffd4a7464))
* Bump NODE_VERSION 20.11.1 -&gt; 22.13.0 (dashboard toolchain needs &gt;=20.19) ([a76eeaf](https://github.com/Manzela/Atelier/commit/a76eeaf2602aab73679dec670ab463b4a8437613))
* **deploy:** Tier-1 staging → approval → production pipeline (keyless WIF) ([#93](https://github.com/Manzela/Atelier/issues/93)) ([cbfe58f](https://github.com/Manzela/Atelier/commit/cbfe58f4d28a8a70ec407be248fbdf63178e08e2))
* **lint:** Ruff-format + C901 suppression for CI parity ([7d68064](https://github.com/Manzela/Atelier/commit/7d68064e5dcdfec9653dc558083d4cb6cf81fa0e))
* **safety:** Gate bench-publish + pin scorecard action (AT-101a) ([7ba21e2](https://github.com/Manzela/Atelier/commit/7ba21e2f800e1023c63ffd6bd41c6761e672e7aa))
* Track deploy.yml workflow to trigger cloud run and firebase deploys ([c54c80d](https://github.com/Manzela/Atelier/commit/c54c80def230ec8a85bb6148f581c3ed8549946c))

## [Unreleased]

### Fixed

- **Per-candidate score join.** Every consumer of N3d consensus results — DPO mid-flight pair extraction, BigQuery trajectory recording, the `/v1/generate` per-candidate breakdown, and the N3e FixerAgent input — now joins each candidate to its D-O-R-A-V score by `candidate_id` through a canonical `scored_candidates` structure, rather than positionally pairing the generation-order candidate/gate lists against the score-descending evaluations. The previous positional pairing attached the wrong score to the wrong candidate whenever generation order differed from score order: it inverted the chosen/rejected labels on DPO preference pairs written to BigQuery (reversed training signal), mispaired per-candidate scores in trajectory records, and fed the FixerAgent one candidate's consensus scores with another candidate's gate outcomes.
- Removed a `convergence_result["converged"]` hard subscript that raised `KeyError` on a first-iteration early break of the final surface (token-cap stop, governor halt, or N3a fail-soft).

### Changed

- `POST /v1/generate` — the `candidates[]` array now enumerates gradeable (gate-reaching) candidates instead of every raw model emission, so non-HTML specialist outputs no longer appear as phantom zero-score rows. `candidate_index` numbers the gradeable candidates in order.

---

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
- **adr:** Add ADR 0024 Web-Research-Augmented Intake (N14) + N15 MJG ([8022ec2](https://github.com/Manzela/atelier/commit/8022ec281daedf65e206534b714bd598bd06fbaf))
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
- 10 Architecture Decision Records (MADR format) covering wrap-don't-fork inheritance, Cloud Run not Agent Engine for runtime, tiered sandboxing, PIP layer, RLRD, Google-native stack, EvoDesign K-candidate search, multi-judge Bayesian consensus, public calibration dashboard, A2UI-native output (ADR-0010, since superseded by PRD v2.2 — A2UI is now the Studio chrome layer, ADR-0024)
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

| Tag            | Date       | What it represents                                                                                                               |
| -------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `v0.1.0-alpha` | 2026-05-21 | Phase 1 Foundation gate passed — single-surface end-to-end working on Cloud Run staging                                          |
| `v0.2.0-beta`  | 2026-05-28 | Phase 2 10× Mechanisms gate passed — 12-surface autonomous campaign converges + WebGen-Bench ≥ 51 + beta tenant cohort onboarded |
| `v1.0.0`       | 2026-06-03 | Public launch + Google for Startups AI Agents Challenge submission filed                                                         |
| `v1.1.0`       | TBD        | Post-launch features (multiplayer dashboard, voice input, Discord community)                                                     |
| `v2.0.0`       | TBD        | SOC 2 Type 2 + per-tenant CMEK + HIPAA tier                                                                                      |

[Unreleased]: https://github.com/Manzela/atelier/compare/v0.0.0...HEAD
