# Audit Plan — Intent Locking Mechanism Hardening

**Audit target**: Close the spec/code gap so Atelier's BriefSpec actually drives downstream behavior dynamically per project (not just decoratively).
**Pass**: 1 of 2 (codebase-only).
**Status**: Draft for user approval. **Do not implement yet.**

---

## Priority bucketing

| Priority | Definition                                                              | Sprint window        |
| -------- | ----------------------------------------------------------------------- | -------------------- |
| **P0**   | Demo-day failure if not fixed; user-stated intent is undelivered        | Phase 1 (D1-D7)      |
| **P1**   | Demo works but intent locking is decorative; user notices on inspection | Phase 2 (W2 D8-D14)  |
| **P2**   | Long-tail correctness; first power user hits it                         | Phase 3 (W3 D15-D20) |

---

## P0 — Phase 1 fixes (must land before D7)

### P0-1. Wire BriefSpec into the cached prefix for every subagent (Gap 8)

- **What**: Add `BriefSpec` to the cached prefix block referenced in `atelier-prd.md:11`. Currently the breakpoint is `[tools + system + PRD + DECISIONS]`; add `[+ BriefSpec]` so every subagent's first call carries the anchor.
- **Why**: Without this, the RLRD discipline (anchors as North Star) is broken at the protocol level for shared-LLM concurrency.
- **Where**: `docs/superpowers/specs/2026-05-14-atelier-prd.md` §11 (Strategy v2 cache breakpoint section); subagent dispatch wrapper in `atelier-core/src/atelier/adk/` (when written).
- **Effort**: 1h spec change + ADR 0011 + 1d implementation in the dispatch wrapper (D2-D3).
- **Acceptance**: A unit test that asserts every subagent's first system message contains the serialized BriefSpec.

### P0-2. Make BriefSpec the single input to the Relevance judge (Gap 7)

- **What**: The Relevance judge prompt template must explicitly bind to `BriefSpec.intent` + `BriefSpec.visual_register` + selected `BriefSpec.intake_transcript` answers. Not the Brand/Copy/Motion/Token/Coherence judges (those stay rubric-anchored), but **Relevance is the single judge whose entire job is "score against the anchor."**
- **Why**: Today PRD §6.4 lists Relevance as a D-O-R-A-V axis but nowhere specifies what it grades against. Without this, Relevance becomes a synonym for Brand and the anchor doesn't bite.
- **Where**: PRD §6.4 (`atelier-prd.md:299-311`); future code in `atelier-core/src/atelier/judges/relevance.py`.
- **Effort**: 2h spec sharpening; integrated into F0085-F0092 (D10) judge implementation tasks.
- **Acceptance**: 5 unit tests on synthetic BriefSpecs — judge correctly demotes off-intent candidates that pass other axes.

### P0-3. Specify the "amend BriefSpec" protocol (Gap 2)

- **What**: Define the amendment protocol in ADR 0004. Pick option:
  - (a) New BriefSpec version (`brief_spec_v2.json`), prior version archived; Surface Manifest entries get `brief_spec_version` field; converged surfaces re-validated against the new spec.
  - (b) In-place "revision" with a separate revision-history file; converged surfaces grandfathered.
- **Why**: First user with a real campaign will hit this within day 1. Today it's a one-sentence assertion in PRD without operational detail.
- **Where**: `docs/decisions/0004-pre-generation-intake-protocol.md` (extend); `docs/superpowers/specs/2026-05-14-atelier-prd.md:187`.
- **Effort**: Half-day decision discussion + ADR update. **Recommend option (a)** — versioning matches the `frozen=True` Pydantic constraint and the rest of the schema-versioned data contracts.
- **Acceptance**: ADR explicitly answers: how is amendment triggered? does it re-run PIP? what happens to in-flight surfaces? what happens to converged surfaces?

## P1 — Phase 2 fixes (during W2 D8-D14)

### P1-4. Wire BriefSpec.compliance_level into Det Gate (Gap 9)

- **What**: Det Gate `LIGHTHOUSE_A11Y` threshold becomes a function of `BriefSpec.compliance_level`. Mapping:
  - `none`: ≥80 (warn-only)
  - `AA`: ≥90 (current default)
  - `AAA`: ≥95 + axe AAA ruleset + manual contrast verification
  - `regulatory`: ≥95 + axe AAA + Pa11y + accessibility statement output
- **Why**: Compliance is captured in BriefSpec but the gate that enforces it is hard-coded. Enterprise demo day will surface this immediately.
- **Where**: PRD §6.4 (`atelier-prd.md:303-309`); future `atelier-core/src/atelier/dag/gates/lighthouse.py`.
- **Effort**: 2 days, includes Pa11y integration for `regulatory` tier.
- **Acceptance**: 4 fixture briefs (one per compliance level) → gate produces 4 different threshold sets.

### P1-5. Implement axis weighting derived from BriefSpec (Gap 1 — user-flagged)

- **What**: New module `atelier-core/src/atelier/intake/axis_weighter.py` exposes `compute_axis_weights(brief: BriefSpec) → AxisWeights`. Initial heuristic table:

  | visual_register | brand_fid  | originality | relevance | a11y | visual_clarity |
  | --------------- | ---------- | ----------- | --------- | ---- | -------------- |
  | editorial       | 0.7        | 0.7         | 0.7       | 0.7  | 0.8            |
  | dense-data      | 0.6        | 0.5         | 0.8       | 0.85 | 0.85           |
  | playful         | 0.6        | 0.8         | 0.7       | 0.7  | 0.65           |
  | brutalist       | 0.5        | 0.85        | 0.7       | 0.7  | 0.5            |
  | custom          | (defaults) |             |           |      |                |

  Then ConsensusAgent applies these as per-axis floors instead of fixed values.

- **Why**: The user's exact ask. Without this, BriefSpec capture is decorative on the highest-leverage axis.
- **Where**: PRD §6.4 (`atelier-prd.md:299-311`); new code under `atelier-core/src/atelier/intake/axis_weighter.py`; consumed by `atelier-core/src/atelier/judges/consensus.py`.
- **Effort**: 3 days. Includes 20 calibration runs across visual_register × convergence_bar matrix.
- **Acceptance**: 5 fixture briefs with different visual_register → 5 different weight vectors → ConsensusAgent rejects/accepts differently per fixture.

### P1-6. Bind CSC-D constitution to BriefSpec.visual_register (Gap 5)

- **What**: Move from single `@atelier/constitution-apple-grade` to a constitution registry keyed by visual_register. Ship 2 constitutions for MVP: `apple-grade` (default) + `brutalist` (deliberate violation of restraint principles). `playful`/`dense-data`/`editorial` map to `apple-grade` for now.
- **Why**: Without this, a user who answers PIP "brutalist" gets a CSC-D that immediately rejects every brutalist candidate.
- **Where**: PRD §6.3 N3b (`atelier-prd.md:237`); future `atelier-core/src/atelier/judges/csc_d.py` + `atelier-core/assets/constitutions/{apple-grade,brutalist}.md`.
- **Effort**: 4 days. Includes authoring the brutalist constitution + calibration on 30 brutalist references.
- **Acceptance**: PIP fixture → "brutalist" → CSC-D scores brutalist candidates above apple-grade-rejecting baseline.

### P1-7. Define skip-path precedence in ADR 0004 (Gap 10)

- **What**: Document precedence rule: **descriptor > brief-NLP-parsed > Memory Bank > defaults.** Codify in PIP Skip-Path Resolver (F0111).
- **Why**: Non-deterministic intake on second-encounter projects.
- **Where**: `docs/decisions/0004-pre-generation-intake-protocol.md` (extend); future `atelier-core/src/atelier/intake/skip_path.py`.
- **Effort**: 2h spec; folds into F0111 implementation effort.
- **Acceptance**: Test fixture where descriptor + Memory Bank disagree → resolver returns descriptor's value.

## P2 — Phase 3 fixes (during W3 D15-D20)

### P2-8. Make 5 specialized judges BriefSpec-aware (Gap 7 extension)

- **What**: Beyond Relevance (P0-2), feed `BriefSpec.intent` summary as a constraint header to Brand/Copy/Motion/Token/Coherence judge prompts. Not as the rubric, but as context.
- **Why**: Reduces silent quality decay on edge cases.
- **Where**: All judge prompts in `atelier-core/src/atelier/judges/`.
- **Effort**: 1 day per judge × 4 judges (Brand/Copy/Motion/Coherence — Token-fidelity is purely deterministic and doesn't need it).
- **Acceptance**: A/B run on 50 fixture briefs — judge agreement rate up ≥ 5% with BriefSpec context.

### P2-9. PADI dynamic judge/gate enable list (Gap 3)

- **What**: PADI emits a `runtime_config` block: `enabled_judges: list[JudgeAxis]` × `enabled_gates: list[GateAxis]` × `axis_weights` (from P1-5) × `csc_d_constitution` (from P1-6). Pipeline reads it; disabled nodes skip.
- **Why**: Enables the user's "different parameters per project type" intent at the pipeline-graph level, not just the threshold level.
- **Where**: PRD §5 N4 (`atelier-prd.md:81`); future `atelier-core/src/atelier/intake/padi.py`.
- **Effort**: 5 days. Touches every node's "should-I-run" check.
- **Acceptance**: A "data-viz dashboard" fixture skips the Motion judge entirely; a "marketing landing page" fixture skips the Information-density check.

### P2-10. Wire BriefSpec.intake_transcript into Relevance judge (Gap 6)

- **What**: Beyond intent, feed top-3 most-discriminative intake answers (the ones that resolved scope ambiguity) to the Relevance judge as additional ground truth.
- **Why**: Captures "why this intent was chosen," reducing surface ambiguity.
- **Where**: Relevance judge prompt in `atelier-core/src/atelier/judges/relevance.py`.
- **Effort**: 2 days.
- **Acceptance**: Side-by-side eval — judge with transcript vs. judge without — improves agreement with human raters by ≥ 3%.

---

## Cross-cutting recommendation: ADR 0011 (Anchor Discipline)

Across these 10 gaps, a single architectural ADR ties them together. Recommend writing **`docs/decisions/0011-anchor-discipline-briefspec-everywhere.md`** with these clauses:

1. **BriefSpec is in every subagent's cached prefix** (P0-1).
2. **Every judge prompt template references BriefSpec by name** (P0-2 + P2-8).
3. **Det Gate thresholds are functions of BriefSpec, not constants** (P1-4).
4. **Constitution selection is BriefSpec-conditional** (P1-6).
5. **PADI emits runtime_config consumed by pipeline graph** (P2-9).
6. **Amendment protocol is versioned, never in-place** (P0-3).
7. **Skip-path precedence is descriptor > parsed > Memory Bank > defaults** (P1-7).

This ADR locks the principle. Without it, each gap is a one-off fix; with it, future contributors can't ship judge or gate code that ignores BriefSpec.

---

## Effort summary

| Bucket       | Items   | Total effort                 | Sprint slot                            |
| ------------ | ------- | ---------------------------- | -------------------------------------- |
| P0 (Phase 1) | 3 items | ~3 days (mostly spec + ADRs) | D2-D7 (alongside existing F0004-F0046) |
| P1 (Phase 2) | 4 items | ~9 days                      | W2 D8-D14 (folds into F0085-F0117)     |
| P2 (Phase 3) | 3 items | ~10 days                     | W3 D15-D20                             |
| ADR 0011     | 1 item  | 1 day                        | D2 (anchor for everything else)        |

Net add to sprint: 1 ADR + ~22 days of work distributed. Most of P0 is **spec sharpening** that costs a few hours each; the implementation effort lands inside features already on the schedule (F0004, F0085, F0114).

---

## Pass 2 — Reference enrichment outcome (3 parallel Explore subagents, returned 2026-05-15)

Full per-source results are in `findings.md §"Pass 2"`. Effect on this plan:

- **No items demoted or removed.** All 10 gaps + 10 plan items remain valid.
- **One item promoted**: P1-5 (BriefSpec-conditional axis weighting) is **a novel mitigation, not a fix to a known DAPLab pattern.** Recommend logging this as **N14 novel contribution** in PRD §5 — a publishable closure of the "metastrategic judging gap."
- **One source flagged for user verification**: the AutonomousAgent doc set does not contain `autonomous_agent_principles.md`. The user's command-context citation may be stale. Worth confirming before quoting as Hermes provenance.
- **Three citations strengthened**:
  - N12 RLRD rationale gets DAPLab Pattern 8 + Anthropic Apr 2026 postmortem + Anthropic Sep 2025 context-engineering blog (currently only cites the Nov 26 2025 harness post)
  - P0-1 (BriefSpec broadcast in cache) framed as competitive moat — no commercial agent ships this; Anthropic hasn't published it either
  - PIP (N13) confirmed defensibly novel — no upstream pattern in Anthropic / DAPLab / DeepMind / Stitch / v0 / Subframe / Galileo / Locofy literature

## P0-WRAI — Web-Research-Augmented Intake (added 2026-05-15 per user request)

This addition supersedes part of the original ADR 0011 (anchor discipline) by elevating it to a full novel contribution. ADR 0011 has been written and committed for **Web-Research-Augmented Intake** (the original "anchor discipline" content folds into the new ADR's section on per-tenant cache + Model Armor + trust scoring).

- **What**: Insert a research node between PIP Q&A completion and BriefSpec lock. Dispatches 5-8 parallel Vertex AI Search Grounding queries derived from the draft BriefSpec. Distills findings into structured `ResearchFindings` (applied_standards, inspirations, suggested_overrides, risk_warnings, citations). One-shot user review before lock.
- **Why**: User-requested. Closes 4 audit gaps (4, 5, 6, 9) simultaneously. Anchors aren't bounded by user knowledge; agent surfaces what the user doesn't know they don't know (e.g., WCAG 2.2 added rule 2.4.11) before BriefSpec is locked. Constitutes **novel contribution N14** — first commercial autonomous design agent to ship web-research-augmented intake.
- **Where**: ADR 0011 (`docs/decisions/0011-web-research-augmented-intake.md`) — full architecture + Pydantic data contracts + cost/latency/failure model. PRD §5 N14 + §6.1 architecture diagram updated.
- **Effort**: ~5 days. Includes:
  - Vertex AI Search Grounding integration via `google-cloud-aiplatform[search]` (1d)
  - Domain trust scorer + `config/research-trust.yaml` whitelist (1d)
  - Findings Synthesizer prompt + 8 query templates per project type (1d)
  - One-shot user review UI (1d)
  - Per-tenant 7-day cache + KMS isolation + 12 unit tests + 3 integration tests (1d)
- **Sprint slot**: D13 (May 27) — folds into existing F0110-F0117 PIP feature window. Add new feature IDs F0114a-F0114e for WRAI sub-tasks.
- **Acceptance**:
  - 5 fixture briefs (one per visual_register) → 5 different ResearchFindings outputs
  - Per-tenant cache test: tenant A's cache never returns to tenant B
  - Adversarial prompt-injection test: 20 known prompt-injection patterns in fetched content all blocked by Model Armor
  - Latency p95 ≤ 13s end-to-end on 10 fixture intakes
  - Cost p95 ≤ $0.10 per intake on 10 fixture intakes

## Recommended action ladder (in approval order)

1. **Approve ADR 0011 (Web-Research-Augmented Intake)** — already written; awaits user confirmation. The novel contribution promotion (N14) is contingent on this approval.
2. **Approve N14 + N15 promotions in PRD §5** — N14 = WRAI (this addition); N15 = MJG (BriefSpec-conditional axis weighting from P1-5). Already applied to PRD; reverts on user request.
3. **Approve P0 bucket** (3 items, ~3 days, fits inside D2-D7 alongside existing F0004-F0046). Highest leverage; lands during Phase 1. P0-1 (BriefSpec in cached prefix) is now load-bearing for WRAI's research_findings to survive subagent dispatch.
4. **Approve P0-WRAI bucket** (5 days at D13 in W2). User-requested; promotes to novel contribution.
5. **Approve P1 bucket** (4 items, ~9 days, folds into W2 D8-D14). Demo-day differentiation. Note: P1-5 was renamed to N15 (MJG) upon PRD promotion.
6. **Approve P2 bucket** (3 items, ~10 days, W3 D15-D20). Long-tail correctness.
7. **Defer or accept** the user-cited `autonomous_agent_principles.md §3` — confirm source before any further reference to it.

---

## Approval gate

Per the audit skill: **stop here. Do not implement.** User must approve, request edits, or pick a subset before any P0/P1/P2 item moves to a feature branch.

---

## Pass 4 — Approval landed (2026-05-15)

User approved ALL buckets and greenlit all decisions. Spec absorption commit `<TBD>` lands the following:

### Decisions ratified

- **ADR 0011** — Web-Research-Augmented Intake (N14): status Proposed → **Accepted**
- **ADR 0012 (NEW)** — Anchor Discipline (BriefSpec Everywhere): consolidates P0-1, P0-2, P0-3, P1-7 under 4 binding rules. Mechanically enforced via CI lint rule.
- **ADR 0013 (NEW)** — BriefSpec-Conditional Axis Weighting (N15 MJG): formal specification + 5×5 register×axis heuristic table + 20-run calibration plan
- **ADR 0004 extended** — adds amendment protocol (versioned per ADR 0012 Rule 3) + skip-path precedence (per ADR 0012 Rule 4)

### Features queued (+22 in features.json: F0199–F0220)

| Day        | New feature IDs                          | Audit bucket                              |
| ---------- | ---------------------------------------- | ----------------------------------------- |
| D2 May 16  | F0199, F0200, F0220                      | P0-1 + CI lint enforcement                |
| D8 May 22  | F0201, F0202                             | P0-3 amendment protocol                   |
| D10 May 24 | F0209, F0210, F0215                      | N15 axis weighting + P0-2 Relevance judge |
| D11 May 25 | F0211, F0212                             | N15 calibration + P1-4 compliance gate    |
| D12 May 26 | F0213, F0214                             | P1-6 CSC-D constitution registry          |
| D13 May 27 | F0203, F0204, F0205, F0206, F0207, F0208 | P1-7 + WRAI full stack (N14)              |
| D17 May 31 | F0216                                    | P2-8 5 judges BriefSpec-aware             |
| D18 Jun 1  | F0217, F0218                             | P2-9 PADI dynamic config                  |
| D19 Jun 2  | F0219                                    | P2-10 intake transcript wiring            |

`features.json._meta.total_features`: 183 → 205. Sprint plan updated with Audit Addendum section. Original day-by-day base plan preserved unchanged — additions are dependency-graph composed, not a rewrite.

### Source flag deferred

`autonomous_agent_principles.md §3` was cited in the original audit-trigger context but the file does not exist in `~/RX-Research Project/AutonomousAgent/docs/`. Flagged for user confirmation; no action taken — does not block any of the approved work.

### Status

**Spec absorption complete.** Implementation begins per the standard sprint discipline (TDD-per-feature, worktree-per-phase, commit-per-feature). The audit deliverables themselves remain in `audit/` as historical record of the gap-closure rationale; future contributors reading them see the design evolution from PRD-only to PRD + ADR 0011-0013 + 22 features.

Next session entry point per `docs/sprint/INSIGHTS-2026-05-15.md` D1 must-do list, now extended:

1. Read SESSION-COMPLETE + INSIGHTS
2. Read this audit + the 3 new ADRs (0011, 0012, 0013)
3. Resolve P2 blocker (vite security PRs #21/#22)
4. Begin F0001a → F0001b → F0001c (worktree setup) per existing plan
5. Then F0004 BriefSpec data contract (already on D1 schedule), F0009 data_contracts.py
6. Then **F0199 ADK dispatch wrapper** (NEW — first audit feature) on D2
