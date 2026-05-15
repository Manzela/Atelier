# Findings — Atelier Intent Locking Mechanism

**Audit target**: How Atelier implements TaskSpec.json-style dynamic parameter locking (the user's Hermes-derived design pattern).
**Pass**: 1 of 2 (codebase-only, ~15 min wall-clock).
**Date**: 2026-05-15.

---

## TL;DR

Atelier's intent-locking design is **specified end-to-end in the PRD + 2 ADRs**, but **none of the code exists yet** — every directory under `atelier-core/src/atelier/{intake,campaign,dag,judges}/` is empty. The design itself is more thoroughly worked out than the Hermes/AutonomousAgent reference: it adds visual-option rendering, DAPLab-pattern 1:1 question mapping, adaptive depth tiering, immutable post-approval lock with amendment protocol, and per-user-project state persistence (`<user-project>/.atelier/`). The user-flagged gap (Det Gate axis weighting not BriefSpec-dependent) is one of **10 distinct Phase-2 gaps** I found between the design and what would actually be needed to deliver "dynamic parameter locking" as the Hermes design intended.

---

## 1. The mapping: Hermes TaskSpec → Atelier components

| Hermes concept                    | Atelier name                                             | Where defined                                                                                              | Code present?                                                          |
| --------------------------------- | -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Clarification loop                | **PIP (N13)** — Pre-Generation Intake Protocol           | PRD §6.1 (`atelier-prd.md:149-188`); ADR 0004 (`docs/decisions/0004-pre-generation-intake-protocol.md`)    | ❌ `atelier-core/src/atelier/intake/` is empty                         |
| Immutable anchors (TaskSpec.json) | **BriefSpec.json** — frozen Pydantic v2 model            | PRD §9 (`atelier-prd.md:526-541`)                                                                          | ❌ Scheduled F0004 (D1) for data contract; F0114 (D13) for synthesizer |
| Dynamic metric selection          | **PADI (N4)** — Project-Agnostic Descriptor Inference    | PRD §5 N4 (`atelier-prd.md:81`); §6.1 skip-paths                                                           | ❌ Not yet started                                                     |
| Prevents context drift            | **RLRD (N12)** — Recursive Long-Running Discipline       | PRD §6.2 (`atelier-prd.md:189-216`); ADR 0005 (`docs/decisions/0005-recursive-long-running-discipline.md`) | ❌ Scheduled F0100-F0101 (D12) campaign skeleton                       |
| Reduces hallucination             | **CSC-D (N6)** — Constitutional Self-Critique for Design | PRD §5 N6 (`atelier-prd.md:85`); §6.3 N3b (`atelier-prd.md:237`)                                           | ❌ Not yet started                                                     |
| Closed-loop self-eval             | **D-O-R-A-V rubric + 5-judge ConsensusAgent**            | PRD §6.4 (`atelier-prd.md:299-311`)                                                                        | ❌ `judges/` directory empty                                           |

## 2. What's specified well (design strengths)

- **BriefSpec is a frozen Pydantic v2 model** — `BriefSpec(BaseModel, frozen=True)` at `atelier-prd.md:526`. Schema-versioned (`schema_version: int = 1`). Approval audit trail (`approved_at`, `approved_by_user_id`). Intake transcript captured for traceability (`intake_transcript: list[IntakeAnswer]`).
- **Persisted to per-user-project state** — `<user-project>/.atelier/{campaign.json, surfaces.json, DECISIONS.md, REJECTED.md, design-system.lock.md, cost-ledger.json, checkpoints/, trajectories/}` at `atelier-prd.md:191-205`. This is the materialization of "anchors as North Star."
- **DAPLab 1:1 question mapping** — every one of Columbia DAPLab's 9 failure patterns gets a preempting question in the 13-question catalog at `atelier-prd.md:163-178`. This is _more_ anchored than the Hermes reference, which has free-form clarification.
- **Adaptive depth tiering** — atomic 3 / small 6 / large 12 / greenfield 13 questions. Solves the "30-90s intake on a 10-minute task is friction" problem.
- **Visual options for visual questions** — 4 mockup thumbnails for "what visual feel?" instead of text. This is novel vs. Hermes (which is text-only).
- **Skip-when-answered paths** — descriptor (`.atelier.yaml`) + Memory Bank prior answers + brief-NLP-parsed answers eliminate redundant questions. Specified at `atelier-prd.md:154-156`.
- **Initializes DECISIONS.md + design-system.lock.md** at synthesis time — the lock files are siblings of the BriefSpec, not derived later. This is what makes the anchor system durable across sessions (Layer 2 RLRD reads them on resume).
- **Cross-Surface Coherence Validator** at `atelier-prd.md:208-215` — token use against `design-system.lock.md`, pattern reuse ≥30%, DECISIONS.md compliance, regression check. This is the closed-loop enforcement layer that makes BriefSpec load-bearing rather than decorative.

## 3. Implementation status (the honest part)

```
atelier-core/src/atelier/
├── intake/      ← EMPTY (0 .py files)
├── campaign/    ← EMPTY
├── dag/
│   ├── nodes/   ← EMPTY
│   ├── gates/   ← EMPTY
│   └── evolutionary/ ← EMPTY
├── judges/      ← EMPTY
├── memory/      ← EMPTY
├── tools/       ← EMPTY
├── render/      ← EMPTY
├── flywheel/    ← EMPTY
└── adk/         ← EMPTY
```

Only `__init__.py` and `__version__.py` exist. Every load-bearing module is a stub directory.

**Sprint scheduling (from features.json)**:

| Feature     | Day          | Component                                                                            |
| ----------- | ------------ | ------------------------------------------------------------------------------------ |
| F0004       | D1 (May 15)  | BriefSpec Pydantic data contract (frozen, schema-versioned); 2 unit tests            |
| F0009       | D2 (May 16)  | data_contracts.py: 10 enums + 11 frozen models                                       |
| F0013–F0016 | D3 (May 17)  | N1 Brief Parser GateAgent + 3 unit tests + e2e test                                  |
| F0021–F0025 | D4 (May 18)  | N2 Source Resolver + descriptor + DESIGN.md merge                                    |
| F0100–F0101 | D12 (May 26) | Campaign module skeleton + Brief Parser                                              |
| F0110–F0117 | D13 (May 27) | PIP Router + Skip-Path Resolver + Intake Agent + BriefSpec Synthesizer + integration |

PIP itself doesn't ship until **D13 (May 27)** — that's late. The atomic DAG (D3-D7) gets stub briefs until then. Rationale (per sprint plan): build the inner engine first so PIP has something to feed into.

## 4. Gaps between design and "dynamic parameter locking" intent

These are **not** missing implementation (everything is missing); these are missing _specification_ — points where the design needs sharpening before any code lands.

### Gap 1: Det Gate axis weighting is not BriefSpec-conditional ⚠️ (user-flagged)

The user's question already names this: a data-viz dashboard should weight a11y + responsive higher; a marketing landing page should weight brand-fidelity + visual-clarity higher. Currently PRD §6.4 (D-O-R-A-V Design Rubric) has **fixed per-axis floors** (Brand 0.7, Originality 0.6, Relevance 0.7, A11y det/0.8, Visual 0.7) regardless of project type.

**Where it lives**: `atelier-prd.md:303-309` (table) and `atelier-prd.md:1085` (`limits` config).
**What's missing**: A function `compute_axis_weights(brief: BriefSpec) → dict[Axis, float]` that derives per-axis weights from `BriefSpec.visual_register` × `BriefSpec.compliance_level` × `BriefSpec.convergence_bar`.
**Effect**: Without this, PIP's "what visual feel" answer is captured in BriefSpec but **never consulted by the evaluator**. The intent-locking is decorative on this axis.

### Gap 2: "amend BriefSpec" protocol is asserted but unspecified

PRD `atelier-prd.md:187`: _"Spec changes require explicit 'amend BriefSpec' command + re-approval; no silent drift."_

**What's missing**:

- Is `amend BriefSpec` a CLI command? An ADK tool? A new PIP Q&A round?
- Does amendment invalidate prior-converged surfaces?
- Does it rebuild DECISIONS.md or append to it?
- Is amendment versioned (`brief_spec_v2`) or in-place mutation (forbidden by `frozen=True`)?

The Pydantic `frozen=True` constraint means amendment must produce a new BriefSpec instance. The protocol for migrating downstream state (Surface Manifest, DECISIONS, design-system.lock) is undefined.

### Gap 3: PADI's "dynamic metric selection" doesn't reach into judge/gate config

PRD §5 N4 describes PADI as adapting to _tech stack_ (React/Vue/Astro/PHP). It doesn't describe PADI selecting _which judges run_ or _which gate axes apply_.

**What's missing**: A mapping from `BriefSpec.stack` × `BriefSpec.compliance_level` × `BriefSpec.visual_register` → `enabled_judges: list[JudgeAxis]` × `enabled_gates: list[GateAxis]`. Today the design implies all 5 judges + all 7 gate axes always run. That contradicts the user's "dynamic per project request" intent.

### Gap 4: Visual register enum has no behavioral binding

`VisualRegister` enum (`editorial / dense-data / playful / brutalist / custom`) is captured in BriefSpec at `atelier-prd.md:531`. But:

- `brutalist` conflicts with several Apple-Grade CSC-D principles (e.g., "restraint," "calm motion") — what wins?
- `dense-data` should boost the Information-density / Visual-clarity floor; today it doesn't.
- `playful` should loosen the brand-fidelity floor; today it doesn't.

**Where it should bind**: CSC-D constitution per `atelier-prd.md:237` should be conditional on register. Today the constitution path (`@atelier/constitution-apple-grade`) is hard-coded.

### Gap 5: CSC-D constitution is project-agnostic, not BriefSpec-conditional

ADR 0004 doesn't address whether the 12-principle constitution is fixed or per-project. PRD `atelier-prd.md:85` says _"12-principle Apple-Grade constitution"_ implying fixed. But the user's TaskSpec design demands the constitution itself be selected per project type.

**Resolution needed**: Either (a) ship a single Apple-Grade constitution + accept the limitation in marketing scope ("Atelier ships Apple-Grade — for brutalist, opt out"), or (b) ship a constitution-selection layer driven by `BriefSpec.visual_register`.

### Gap 6: BriefSpec.intake_transcript is persisted but not consumed downstream

`BriefSpec.intake_transcript: list[IntakeAnswer]` is captured (`atelier-prd.md:538`) but no downstream node references it. The rationale trace is for audit only.

**What's missing**: At minimum, the **Relevance** judge should score against `BriefSpec.intake_transcript` (not just `BriefSpec.intent`) because the transcript captures _why_ the intent was chosen. Today the Relevance judge has nothing to anchor on except a one-sentence intent string.

### Gap 7: No anchor-grounded "score against BriefSpec" wired in any judge

The 5 judges (Brand / Copy / Motion / Token-fidelity / Coherence) at `atelier-prd.md:250-256` each grade against rubrics. **None of them take BriefSpec as an input.** The design says judges are "anchored" but the wiring isn't specified.

**What's missing**: Each judge's prompt template should include `BriefSpec.intent` + `BriefSpec.visual_register` + `BriefSpec.compliance_level` as constraints. Today they get rubric-only.

### Gap 8: Shared-LLM concurrency / context-isolation strategy is documented for cost, not for anchor integrity

Apigee model routing (`atelier-prd.md:483`) handles model-pool selection for cost. The user's concern about _anchor consistency under shared-LLM concurrency_ (orchestrator/worker/evaluator all call the same Gemini model with different small contexts) isn't addressed.

**What's missing**: A "BriefSpec broadcast" pattern — the BriefSpec is in every subagent's cached prefix (1h TTL breakpoint). Today the cache breakpoint strategy at `atelier-prd.md:11` includes `[tools + system + PRD + DECISIONS]` but doesn't explicitly include `BriefSpec`.

### Gap 9: Compliance level is captured but not wired into Det Gate

`BriefSpec.compliance_level: ComplianceLevel  # AA / AAA / regulatory / none` (`atelier-prd.md:534`). But Det Gate `LIGHTHOUSE_A11Y` axis has a fixed score threshold (≥90) at `atelier-prd.md:319`. No wiring from compliance_level to the gate config.

**What's missing**: When `compliance_level == "AAA"`, Lighthouse a11y threshold should jump to ≥95 + axe AAA rules enabled + manual contrast checks added. Today it doesn't.

### Gap 10: Skip-when-answered conflict resolution is undefined

PRD §6.1: _"descriptor file (`.atelier.yaml`) + Memory Bank prior answers + brief-parsed answers all eliminate redundant questions"_

**What's missing**: If descriptor says `compliance_level: AA` and Memory Bank says the user previously chose AAA on similar projects, which wins? Precedence rules undefined.

**Recommendation**: Document precedence as `descriptor > brief-parsed > Memory Bank > defaults` (descriptor is most explicit, Memory Bank is statistical guess). Add to ADR 0004.

---

## 5. Strengths of the design vs. Hermes baseline

Atelier's design extends Hermes/AutonomousAgent's TaskSpec pattern in 5 substantive ways:

1. **Visual rendering** of options for design-domain questions (Hermes is text-only)
2. **DAPLab 1:1 mapping** — each of the 9 known failure patterns has a preempting question (Hermes uses free-form)
3. **Adaptive depth tiering** based on scope-detection (Hermes uses fixed-depth)
4. **Skip-when-answered paths** with 3 source layers (Hermes asks the same questions every project)
5. **Frozen Pydantic v2 + schema versioning + approval audit trail** (Hermes uses unstructured JSON)

These are publishable as N13 — already noted in PRD §5 (line 99) as a CHI workshop / HCI venue candidate.

## 6. Risks if gaps stay open into Phase 2

| Gap                                    | Risk if unfixed                                                                                                           |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| 1 (axis weighting)                     | Demo shows BriefSpec captured but axes score uniformly → user asks "what did changing my visual register do?" → no answer |
| 2 (amend protocol)                     | First user who needs to change scope gets a non-deterministic agent response                                              |
| 3-5 (PADI/register/CSC-D not wired)    | Same demo-day failure as Gap 1 — captured intent doesn't change downstream behavior                                       |
| 7 (judges not BriefSpec-grounded)      | Relevance scores look fine but evaluator is grading against rubric, not user intent — silent quality decay                |
| 8 (cache breakpoint missing BriefSpec) | Subagents drift from the anchor over long sessions; cost-cache savings come at the price of intent fidelity               |
| 9 (compliance level not wired)         | Enterprise customer specifies AAA, ships AA-grade output — compliance failure                                             |
| 10 (skip-path precedence)              | Non-deterministic intake; same project intake twice produces different BriefSpecs                                         |

---

## Pass 2 — Reference enrichment (3 parallel Explore subagents, returned 2026-05-15)

### Reference scan A — AutonomousAgent / Hermes docs (`/Users/danielmanzela/RX-Research Project/AutonomousAgent/docs/`)

5 questions asked, 5 answered. **Headline finding**: the AutonomousAgent doc set is a Phase-1 deployment + operations spec; it does **not** contain TaskSpec-level specifications. Atelier's BriefSpec layer extends _beyond_ the reference set's scope.

| Question                                                                                      | Answer                                      | Implication                                                                                                                                                  |
| --------------------------------------------------------------------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Amendment protocol for locked TaskSpec?                                                       | **Not specified** in Hermes docs            | Gap 2 / P0-3 is novel design work, not heritage transfer                                                                                                     |
| Shared-LLM context isolation?                                                                 | **Not specified**                           | Gap 8 / P0-1 (BriefSpec in cached prefix) is novel territory                                                                                                 |
| Project-type → evaluator mapping?                                                             | **Not documented**                          | Gap 3 / P2-9 (PADI dynamic config) is novel; Atelier's fixed-5-judges is a starting constraint to lift                                                       |
| Skip-path precedence rule?                                                                    | **Not specified**                           | Gap 10 / P1-7 is Atelier-specific, not Hermes-derived                                                                                                        |
| `autonomous_agent_principles.md §3` ("TaskSpec is the single most important design decision") | **DOCUMENT NOT FOUND** in the reference set | The user's command-context citation may reference a stale or differently-named file. Recommend confirming the source before quoting it as Hermes provenance. |

### Reference scan B — DAPLab + Anthropic agent-failures cache (`~/Professional Profile/.firecrawl/agent-failures-2026/`)

3 questions asked, 3 answered.

| Question                                                                            | Answer                                                                                                                                                                                                                                  | Implication                                                                                                                                                                        |
| ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Does any DAPLab pattern describe **wrong evaluator axis weights for project type**? | **No** — DAPLab's 9 patterns are all implementation-failure modes, not evaluation-strategy failures. Pattern 3 (Business Logic Mismatch) is adjacent but distinct.                                                                      | P1-5 (BriefSpec-conditional axis weighting) closes a _novel_ gap, not a documented failure mode. **Could be promoted to a 14th novel contribution** — "metastrategic judging gap." |
| Anchor drift documented?                                                            | **Yes** — DAPLab Pattern 8 (Codebase Awareness Loss) + Anthropic Apr 2026 postmortem (caching bug cleared thinking history mid-session). Anthropic Sep 2025 context-engineering blog recommends _structured note-taking_ as mitigation. | RLRD (N12) closes a _documented_ failure mode. Cite DAPLab Pattern 8 + Anthropic context-engineering blog in N12 rationale to ground the discipline as research-backed.            |
| Pre-generation intake recommended in literature?                                    | **No** — neither DAPLab nor Anthropic prescribes structured pre-generation intake. Closest precedent is Design2Code's reference-image grounding (single-axis).                                                                          | PIP (N13) is **defensibly novel**. Maps DAPLab's 9 patterns 1:1 to preempting questions — first agent to do so. Strong IP for the G4S brief.                                       |

**Citations from pass 2**:

- `agent-failures-2026/columbia-daplab-9-patterns.md:75-122` (Patterns 3 + 8)
- `agent-failures-2026/anthropic-april-2026-postmortem.md:47-67` (anchor drift via thinking-cache bug)
- `agent-failures-2026/anthropic-context-engineering.md:83-110` (structured note-taking as mitigation)

### Reference scan C — Brainstorm caches (atelier-research + design-agent + deepmind-design)

3 questions asked, 3 answered.

| Question                                                               | Answer                                                                                                                                                                                                                  | Implication                                                                                                                                             |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Any commercial design agent ships dynamic per-project judge weighting? | **No** — verified across Galileo AI, v0, Subframe, Locofy, Stitch. None do contextual rubric tuning.                                                                                                                    | Atelier's "no commercial tool ships personalized intake or per-project judge weighting" claim **holds** as of May 2026. Strong differentiation.         |
| Anthropic published "BriefSpec in cached prefix" pattern?              | **No** — Anthropic's Skills + Stitch MCP integration uses DESIGN.md as a _project-local file_, not as a _cached-prefix protocol_ for subagent orchestration.                                                            | P0-1 (BriefSpec broadcast in cache) is **novel territory + competitive moat**. If Anthropic publishes such a pattern post-May 2026 we still ship first. |
| Stitch's intent-capture mechanism?                                     | **Confirmed**: free-form prompt → immediate generate. "Vibe design" article confirms post-generation refinement only; DESIGN.md is an optional _post-generation_ import to apply rules. **Zero pre-generation intake.** | Atelier's PIP/BriefSpec is **architecturally upstream** of Stitch's workflow. Genuinely novel placement.                                                |

**Citations from pass 2**:

- `design-agent-research/v0-blog.md` (sandboxed PR flows, no intake)
- `stitch-research/blog-vibe-design.md` ("creating with intent" = explanation, not calibration)
- `stitch-research/blog-launch.md:May 20, 2025` (free-form prompt → generation confirmed)
- `stitch-research/medium-claude-mcp.md` (DESIGN.md is project-local, not protocol-cached)

---

## Changes from pass 1

| Change                                                                                                                                                                                                                                                                                        | Reason                                                                                                                                        |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| **NEW: User's source citation flag** — the AutonomousAgent doc set does not contain `autonomous_agent_principles.md` or a `§3` matching the cited "single most important design decision" line. Possible the user's command-context referenced a draft / different repo / different filename. | Surfaced by reference scan A. Action: confirm source with user before quoting as Hermes provenance.                                           |
| **PROMOTE: Gap 1 + P1-5 → potential N14 novel contribution** ("metastrategic judging gap" closure via BriefSpec-conditional axis weighting).                                                                                                                                                  | DAPLab does not document this failure mode; Atelier closes it pre-emptively. If the design ships, it's a publishable contribution.            |
| **STRENGTHEN: N12 RLRD rationale** — cite DAPLab Pattern 8 (Codebase Awareness Loss) + Anthropic Apr 2026 postmortem + Anthropic Sep 2025 context-engineering blog as the research backing.                                                                                                   | Currently N12 is justified by Anthropic's Nov 26 2025 long-running harness post only. Two more citations strengthen the publishability claim. |
| **STRENGTHEN: P0-1 (BriefSpec in cached prefix) framed as competitive moat** — no commercial agent ships this, and Anthropic's published patterns don't recommend it.                                                                                                                         | Strengthens the urgency of P0-1: not just correctness, also differentiation.                                                                  |
| **VALIDATE: P0-3 (amendment protocol) is novel design work, not Hermes transfer** — confirms the recommendation to pick option (a) [versioned, never in-place] is an architectural choice we own.                                                                                             | Confirmed by reference scan A; no upstream pattern to inherit.                                                                                |
| **VALIDATE: P2-9 (PADI dynamic judge/gate enable list) has no upstream precedent** — Hermes doesn't address this either.                                                                                                                                                                      | Confirmed by reference scan A.                                                                                                                |
| **NO CHANGE: P1-5, P1-6, P1-7, P2-8, P2-10** — all P1/P2 items remain valid; pass 2 strengthened the rationale but did not invalidate any item.                                                                                                                                               | Reference scans confirmed the gaps are real and unaddressed in the literature.                                                                |

**Net effect**: Pass 2 strengthens the case for the audit plan rather than reshuffling priorities. The biggest substantive find is the absent `autonomous_agent_principles.md` document — worth raising with the user since their command-context cited it directly.

---

## Pass 3 — User-requested addition: Web-Research-Augmented Intake (2026-05-15)

User feedback after Pass 2 review: _"we should enable the Atelier Design Agent perform a web-research to research best practices and fill-in gaps and enrich/enhance TaskSpec and ensure highest quality and highest industry standards and BEST best practices applied dynamically per user request/project/campaign/etc..."_

This is a substantive design extension. Treated as **Gap 0** (highest priority — explicitly user-requested) and addressed via:

- **ADR 0011** (`docs/decisions/0011-web-research-augmented-intake.md`) — Web-Research-Augmented Intake as N14 novel contribution
- **PRD §5 N14** (added) — first commercial autonomous design agent to ship web-research-augmented intake
- **PRD §5 N15** (promoted from audit P1-5) — MJG (Metastrategic Judging Gap closure via BriefSpec-conditional axis weighting)
- **PRD §6.1** (updated) — architecture diagram now shows WRAI between PIP Q&A and BriefSpec lock
- **`audit/audit-plan.md` P0-WRAI** (added) — 5-day implementation slot at D13, folds into existing F0110-F0117 PIP feature window

**WRAI in 5 lines:**

1. After PIP Q&A, before BriefSpec lock: dispatch 5-8 parallel Vertex AI Search Grounding queries derived from the draft BriefSpec.
2. Per-source trust score (whitelist / PageRank / denylist) + Apigee Model Armor sanitization on every fetched URL.
3. Gemini 3 Flash distills findings into structured `ResearchFindings` (applied_standards, inspirations, suggested_overrides, risk_warnings, citations with `retrieved_at` timestamps).
4. One-shot user review: "We surfaced 12 findings from 8 sources. Apply all / customize / skip." Power-user flag `--no-research` skips entirely.
5. Findings frozen with BriefSpec; per-tenant 7-day cache; cost ~$0.05-$0.10 per intake; latency 8-13s.

**Closes 4 audit gaps** (4, 5, 6, 9) by giving downstream judges + gates current standards + register-specific best practices to ground against, not just the user's existing knowledge.

**Strengthens 3 novel contribution claims**:

- **N13 PIP** + **N14 WRAI** = 2-paper publishable line (intake methodology + research-augmented anchor capture)
- **N15 MJG** = first paper to formalize the metastrategic judging gap and ship a closure
- **N12 RLRD** rationale strengthened by both: research findings travel with the BriefSpec across sessions, demonstrating the discipline at the anchor level (not just the state-file level)

**Failure-handling discipline preserved**: WRAI is fail-soft (research unavailable → BriefSpec proceeds; user notified) and fail-loud where it must be (synthesis hallucinates citation → Reviewer subagent verifies every URL is reachable + matches `research-trust.yaml`; prompt injection in fetched content → Apigee Model Armor blocks).

---

## Pass 4 — Final state (2026-05-15)

User approved ALL audit buckets + all 3 ADRs (0011 WRAI / 0012 Anchor Discipline / 0013 Conditional Axis Weighting). Spec absorption complete:

- All 10 gaps now have a corresponding ADR + feature(s) in features.json (F0199–F0220, +22 features, total 205)
- ADR 0011 status Proposed → Accepted
- ADR 0012 (NEW) consolidates 4 of the P0/P1 gaps under a single Anchor Discipline with mechanical CI enforcement via `atelier-eval/src/atelier_eval/lints/anchor_discipline.py`
- ADR 0013 (NEW) formalizes N15 MJG (Metastrategic Judging Gap) — first paper-publishable closure of an unaddressed agent failure mode
- ADR 0004 (PIP) extended with amendment protocol + skip-path precedence
- Sprint plan annotated with "Audit Addendum" section preserving the original day-by-day plan + listing all +22 additions by day with audit-bucket attribution
- `features.json._meta.audit_addendum` field documents the provenance for future maintainers

The audit deliverables (this file + `audit-plan.md`) become historical record. Future sessions read SESSION-COMPLETE + INSIGHTS-2026-05-15 + the 3 new ADRs to understand the design evolution.
