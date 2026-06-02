# 0024. Governed A2UI — control-layer adoption + catalog export

**Status:** Accepted (2026-06-02) — P0 scope approved by operator. Additive to PRD v2.2; does **NOT** revive A2UI-as-output (ADR-0010, superseded).
**Date:** 2026-06-02
**Decision-makers:** Daniel Manzela (operator) + Claude Opus 4.8 (1M, ultracode) as builder
**Relates to:** complements ADR-0001 (wrap-don't-fork), ADR-0007 (worktree-per-phase); supersedes nothing; explicitly distinct from ADR-0010 (A2UI-as-output, superseded by PRD v2.2 §3.4/§10).

## Context and problem statement

A2UI standardizes **how** an agent describes a UI; it says **nothing about whether that UI is good** — accessible, on-brand, within budget. That gap is Atelier's existing moat (deterministic gates, D-O-R-A-V judge, zero-tolerance token enforcement, token cap).

ADR-0010 once made A2UI the **design output** protocol (render the deliverable to A2UI for React/Flutter/Lit/Angular). PRD v2.2 (2026-05-31) **dropped that** in favor of DTCG tokens + self-contained portable HTML. The code-grounding verification (`audit/governed-a2ui-gap-verification.md`) confirmed A2UI is today **scaffolded only**: `CandidateUI.a2ui_payload` is hardwired `None` (`nodes/generator.py:279`), the `complete` SSE event ships `best_html`, and the Studio chrome is hand-built React on a bespoke SSE vocabulary. The README even claimed "A2UI-Native Output | Shipped" — corrected this session (commit `6515d77`).

The question: how to adopt A2UI **credibly and honestly** for the hackathon without (a) reviving the dropped output decision, (b) forking upstream, or (c) taking CopilotKit runtime/cloud lock-in.

## Decision drivers

- Four equally-weighted DevPost axes: Design / Technological Implementation / Quality of Idea / Potential Impact.
- Honest-claim boundary — no "conformant"/"native"/"shipped" without substantiation (a live overclaim was just corrected).
- PRD v2.2 §3.4/§10: the design **output** stays DTCG + portable HTML. Do not convert the deliverable.
- `<wrap_dont_fork>` (ADR-0001); `<lockfile_only_installs>`; supply-chain hardening (Snyk).
- Deadline: DevPost 2026-06-05; the `google/A2UI` GitHub repo **moves orgs 2026-06-03** (pin by commit before then).

## Decision

Adopt **Governed A2UI** scoped to the **Studio chrome / control layer + a catalog export** — never the design deliverable.

1. **Emit Studio surfaces as A2UI.** The agent-driven Studio surfaces (P0: the AT-044 design-system panel, already `FlatToken[]`-driven) are emitted as A2UI (v0.10 wire schema: `createSurface` / `updateComponents` / `updateDataModel`) and rendered via `@a2ui/react`, **behind a feature flag**, with the hand-built React kept as the **fail-soft fallback**.
2. **Fail-closed governance gate on emission.** Every emitted surface passes Atelier's existing deterministic gates (axe/contrast/structure) + D-O-R-A-V judge + token enforcement **before render**. Off-brand/inaccessible → `REJECT` (or auto-correct) + a `CUSTOM` governance event. Trust by enforcement, not convention.
3. **Consume AG-UI headless.** `@ag-ui/client` `HttpAgent` against the existing FastAPI with Firebase-token middleware. **No** `CopilotRuntime` Node proxy, **no** CopilotKit Cloud — Atelier already owns auth (Firebase), persistence (Firestore), observability, and serving (ADK/Vertex/Cloud Run).
4. **The design OUTPUT iframe stays portable HTML** (AT-040/AT-050) — unchanged, PRD-v2.2-compliant. A2UI never touches the deliverable.
5. **(P2) Catalog export.** DTCG → A2UI Fixed-Schema + Zod catalog as an additional AT-050 handoff target; the D-O-R-A-V gate validates each agent emission against the locked catalog.

### Verified dependency pins (captured 2026-06-02, before the org move)

All coordinates verified against live registries this session (`npm view` / `gh`), per `<no_unverified_apis>`.

| Package                     | Pinned version                                                 | Role                                                            | Verified                                              |
| --------------------------- | -------------------------------------------------------------- | --------------------------------------------------------------- | ----------------------------------------------------- |
| `@a2ui/react`               | `0.10.0`                                                       | A2UI React renderer (`A2uiSurface` + `MessageProcessor`, /v0_9) | npm ✓                                                 |
| `@a2ui/web_core`            | `0.10.0`                                                       | core renderer/types                                             | npm ✓                                                 |
| `@ag-ui/core`               | `0.0.54`                                                       | AG-UI typed events/encoder (zero-dep)                           | npm ✓                                                 |
| `@ag-ui/client`             | `0.0.54`                                                       | `HttpAgent` — headless stream consume                           | npm ✓                                                 |
| `@copilotkit/a2ui-renderer` | `1.59.2`                                                       | CopilotKit A2UI renderer                                        | npm ✓ — **NOT adopted** (CONVERT: no runtime lock-in) |
| `google/A2UI` (GitHub)      | commit `0fde624719c500133c526f49df5b007d0392f3cb` / tag `v0.9` | spec + conformance suite (`agent_sdks/conformance/`)            | gh ✓                                                  |

**Pin by commit, not just tag:** `google/A2UI` (Apache-2.0, 15.1k★, pushed 2026-06-01) moves GitHub orgs on 2026-06-03, so the commit SHA `0fde6247…` is the durable reference; the `v0.9` tag may follow the repo.

**Version skew (recorded):** the renderer SDK is at the **v0.10** wire schema (`createSurface`/`updateComponents`/`updateDataModel`/`version`/`callFunction`) while the repo's latest **tag is v0.9**. Target the v0.10 schema (what `@a2ui/react@0.10.0` renders); the G-34 conformance signal runs against the suite's supported version. Public claim: **"A2UI v0.9/v0.10-pattern aligned"**, never "certified".

**Python side (P1, deferred):** `a2ui-agent-sdk` / `ag_ui_adk` (wrap the existing ADK) — must verify `google-adk` pin compatibility before adding; tracked as an ADR addendum, not authorized by this ADR.

## Transport decision (SSE over AG-UI/A2A)

A2UI is **transport-agnostic** — the v0.9 server-to-client message list
(`createSurface` / `updateComponents` / `updateDataModel`) is a JSON payload that
can be carried over any duplex or server-push channel. Atelier therefore carries
the emitted A2UI surface over its **existing server-to-client SSE stream** (the
`POST /v1/generate` event stream that already ships pipeline progress + the
`complete` event), **not** over an AG-UI/CopilotKit runtime nor an A2A task
channel. This is spec-compliant: A2UI prescribes the _message schema_, not the
wire.

**Why SSE, not AG-UI runtime:**

- **No new heavy dependency, no lock-in.** A `CopilotRuntime` Node proxy or
  CopilotKit Cloud would add a server-side runtime Atelier does not need —
  Atelier already owns auth (Firebase token middleware), persistence (Firestore),
  observability (OTel), and serving (ADK / Vertex / Cloud Run). SSE reuses the
  transport already wired and tested, so the A2UI surface inherits the existing
  trusted boundary for free. (See Decision driver #3 and Alternative A.)
- **Server-to-client is the whole job here.** The Governed A2UI scope is
  agent-driven Studio _chrome_ — the agent pushes surfaces, the client renders
  them. That is a strictly server→client flow, exactly what SSE does natively.
  The pinned `@ag-ui/client` `HttpAgent` (ADR table) is the **optional headless
  consume path** for the same stream; it is not a runtime and adds no proxy.
- **Lower attack + supply-chain surface.** Fewer packages on the render path
  (`<lockfile_only_installs>` + Snyk), consistent with the honest-claim posture.

**Revisit trigger:** adopt a bidirectional channel (AG-UI duplex events or A2A
`message/stream`) **only if** we need client-to-agent **`userAction` steering** —
i.e., the rendered A2UI surface itself originates agent control intents (button
clicks driving the pipeline mid-run), which the current server→push design-system
panel does not require. Until then, SSE is the deliberate, sufficient choice.

## Consequences

### Positive

- Turns "agent-driven UI" from a claim into a demonstrable fact on Google's own A2UI + ADK + Vertex stack (Tech + Idea axes).
- "Governed A2UI" is genuinely novel — no AG-UI/CopilotKit consumer ships gate-enforced, on-brand, on-budget A2UI emission (Impact axis, AT-098 narrative).
- Keeps the design deliverable portable HTML — no regression to AT-040 byte-equality / AT-050 handoff.

### Negative

- New supply-chain surface (4 npm packages + 1 GitHub-sourced reference) — mitigated by exact pins + lockfile + Snyk.
- v0.10-SDK vs v0.9-tag skew adds a compatibility watch item.
- A2UI is young (≈14 months); breaking changes likely — lockfile-pinned per ADR-0001.

### Neutral

- The flag keeps the hand-built React path live; A2UI is opt-in until proven, then promoted.

## Feature-flag lifecycle

The Governed A2UI render path ships behind a single build-time flag. The operator-facing canonical record is [`atelier-dashboard/.env.example`](../../atelier-dashboard/.env.example); this table is the governance record. CI exercises **both** flag states via the `dashboard-e2e` matrix (`a2ui_flag: [off, on]`) in [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml).

| Flag                      | Owner          | Introduced | Default   | Flip-on criteria                                                                                                     | Removal criteria                                                                                                         |
| ------------------------- | -------------- | ---------- | --------- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `NEXT_PUBLIC_A2UI_RENDER` | Daniel Manzela | 2026-06-02 | `0` (off) | G2 fail-closed gate-before-emit green **and** G3 a11y/axe-in-CI green **and** the `a2ui-render` flag-ON CI leg green | A2UI promoted to the default render path with the hand-built `DesignSystemPanel` retained only as the fail-soft fallback |

**Build-time-inline caveat:** Next.js statically inlines `NEXT_PUBLIC_*` at build time, so flipping the default requires a rebuild, not a restart. The dependency bridge the render path relies on (`@a2ui/web_core` 0.9.2 + 0.10.0) is machine-guarded by `scripts/ci/check-a2ui-skew.mjs` (the `a2ui-skew` CI job).

## Alternatives considered

- **A — Adopt CopilotKit runtime + Cloud.** Rejected: vendor/runtime lock-in, not Google-native; Atelier already owns the trusted boundary + persistence + serving.
- **B — Revive A2UI as the design OUTPUT (ADR-0010).** Rejected: PRD v2.2 dropped it; the deliverable stays DTCG + portable HTML.
- **C — Keep bespoke SSE, no A2UI.** Rejected: forfeits the Tech/Idea standards signal for a Google-judged hackathon.
- **D — Hand-roll an A2UI renderer.** Rejected per `<wrap_dont_fork>` (ADR-0001): consume via pinned deps.

## Honest-claim boundary

Until a real `surfaceUpdate`/`createSurface` is emitted and rendered (and, ideally, the conformance suite passes): **"A2UI-aligned, on Google's A2UI v0.9/v0.10 pattern."** Never "we built A2UI 2.0" / "conformant" / "native" without substantiation. Once the G-34 conformance signal runs in CI, claim **"A2UI vX-compatible (Y%)"**, never "certified". Every public claim cites what is actually wired.

## Governance note (branch divergence)

This build branch (`feature/studio-design-pass`) currently **lacks** `docs/decisions/0001-0010` and `DECISIONS.md` that exist on `origin/main` (the two lines diverged at `9b70317`; the app source lives only on this branch). This ADR continues the **canonical** numbering (`0011`) regardless. Reconciling the governance scaffold between the build branch and `origin/main` is a tracked follow-up, deferred per the operator's "build here, reconcile later" decision.

## References

- `audit/governed-a2ui-architecture.md` — the Governed A2UI build spec.
- `audit/governed-a2ui-gap-verification.md` — the code-grounding verification (34 gaps; this ADR closes the "no decision record" precondition for P0).
- ADR-0010 (superseded) — A2UI-as-output, dropped by PRD v2.2.
- ADR-0001 (wrap-don't-fork), ADR-0007 (worktree-per-phase).
- `docs/superpowers/specs/2026-05-31-atelier-prd-v2.2.md` §3.4/§10 — output protocol decision (HTML, not A2UI).
- A2UI v0.9 announcement: <https://developers.googleblog.com/a2ui-v0-9-generative-ui/>; AG-UI docs: <https://docs.ag-ui.com>.
