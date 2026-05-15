# 0012. Anchor Discipline — BriefSpec Everywhere

**Status:** Accepted (approved 2026-05-15)
**Date:** 2026-05-15
**Decision-makers:** Daniel Manzela (+ Claude Opus 4.7 MAX as builder)
**Related:** ADR 0004 (PIP), ADR 0011 (WRAI), ADR 0013 (Conditional Axis Weighting)

## Context

Audit `audit/findings.md` (2026-05-15) surfaced 10 gaps between Atelier's BriefSpec design and the dynamic-parameter-locking intent the user articulated. Four of those gaps share a single root cause: **BriefSpec is captured but does not propagate as the operative anchor across subagents, judges, and amendment workflows.** Without a single architectural rule binding BriefSpec to every downstream context, intent locking is decorative — judges score against rubrics rather than user intent, subagents drift across multi-day sessions, and amendments mutate state non-deterministically.

The four gaps consolidated here are:

| Gap                                    | Audit ID      | Symptom                                                                                         |
| -------------------------------------- | ------------- | ----------------------------------------------------------------------------------------------- |
| Cache prefix doesn't include BriefSpec | Gap 8 / P0-1  | Subagents drift from anchor over long sessions; cost-cache savings come at intent-fidelity cost |
| Relevance judge has no anchor input    | Gap 7 / P0-2  | Relevance scoring becomes synonymous with Brand; anchor doesn't bite                            |
| "amend BriefSpec" command unspecified  | Gap 2 / P0-3  | First user with mid-campaign scope change gets non-deterministic agent response                 |
| Skip-path precedence undefined         | Gap 10 / P1-7 | Same project intake twice produces different BriefSpecs                                         |

Each is small individually; together they break the "anchors as North Star" promise of N12 RLRD.

## Decision

We will adopt a single Anchor Discipline composed of four binding rules. Future judge, gate, subagent, and amendment code MUST satisfy all four. The Reviewer subagent is configured to reject any PR that violates them (mechanically enforced via lint rule + checklist).

### Rule 1 — BriefSpec is in every subagent's cached prefix

The cache breakpoint at end of `[tools + system + PRD + DECISIONS]` (PRD §11) becomes `[tools + system + PRD + DECISIONS + BriefSpec]`. The 1h TTL applies; on amendment, the breakpoint is invalidated for that tenant + project (so the new BriefSpec lands in the next subagent dispatch's cached prefix).

**Implementation**: `atelier-core/src/atelier/adk/dispatch.py` wraps every subagent invocation. The wrapper reads BriefSpec from the per-project state at `<user-project>/.atelier/brief_spec_v<N>.json` and prepends it to the system message. A unit test asserts every subagent's first system message contains the serialized BriefSpec; CI fails if not.

**Cost**: BriefSpec is ~2-4K tokens at p95. At 1h TTL × 50 sessions/day × 5 subagents per session = ~$0.30/day in cache-write overhead per active project. Negligible vs. avoided drift.

### Rule 2 — Relevance judge is the single judge whose entire job is "score against the anchor"

The Relevance judge (one of the 5 D-O-R-A-V judges in PRD §6.4) receives `BriefSpec.intent` + `BriefSpec.visual_register` + the top-3 most-discriminative answers from `BriefSpec.intake_transcript` as its rubric. The other 4 judges (Brand / Copy / Motion / Token-fidelity / Coherence) stay rubric-anchored but receive `BriefSpec.intent` as a constraint header (P2-8).

**Implementation**: `atelier-core/src/atelier/judges/relevance.py` prompt template is structured as:

```
You are scoring a candidate UI against a locked user intent.

LOCKED INTENT:
{brief_spec.intent}

VISUAL REGISTER (locked at PIP):
{brief_spec.visual_register}

KEY INTAKE ANSWERS (top 3 most discriminative):
{top_3_intake_transcript_entries}

WRAI APPLIED STANDARDS (if present):
{brief_spec.research_findings.applied_standards}

CANDIDATE:
{candidate_artifacts}

Score 0.0-1.0 on alignment between CANDIDATE and LOCKED INTENT.
Demote candidates that satisfy other axes but drift from intent.
```

A 5-fixture unit test asserts that the judge correctly demotes off-intent candidates that pass other axes.

### Rule 3 — Amendment is versioned, never in-place mutation

`BriefSpec` is `frozen=True` Pydantic. Amendment produces a new BriefSpec instance. Per-user-project state directory layout extended:

```
<user-project>/.atelier/
├── brief_spec_v1.json          # original lock (immutable)
├── brief_spec_v2.json          # first amendment (immutable)
├── brief_spec_current.json     # symlink to current version
├── brief_spec_history.jsonl    # append-only log: who, when, why, diff
├── ...
```

**Amendment trigger**: CLI command `atelier amend` opens a focused PIP re-intake — only the questions whose answers the user wants to change are re-asked. WRAI re-runs only for affected fields. New BriefSpec version produced. User approves explicitly.

**In-flight surface handling**: surfaces with `state == GENERATING` pause; surfaces with `state == CONVERGED` get a `coherence_review_required: true` flag that the Cross-Surface Coherence Validator picks up on next campaign tick. The validator then re-scores converged surfaces against the new BriefSpec; surfaces that still pass are marked `regrandfathered: true`; surfaces that no longer pass go back to the queue.

**Surface Manifest gets a `brief_spec_version` field** so each surface is bound to the BriefSpec version it was generated under. This lets the agent answer "which surfaces converged under v1 vs v2?" and supports rollback to a prior version if amendment is reverted.

**Implementation**: `atelier-core/src/atelier/intake/amendment.py` + Surface Manifest schema bump.

### Rule 4 — Skip-path precedence is `descriptor > brief-NLP-parsed > Memory Bank > defaults`

When PIP's Skip-Path Resolver finds an answer for a question in multiple sources, the precedence is fixed:

1. **Descriptor** (`.atelier.yaml` in user project) — explicit user intent in version-controlled file
2. **Brief-NLP-parsed** — answer extracted from the user's free-form brief by Gemini 3 Flash
3. **Memory Bank** — answer from prior projects (statistical inference)
4. **Defaults** — schema defaults

**Rationale**: Descriptor is the most explicit user intent, version-controlled, and durable. Memory Bank is a statistical guess from past behavior that may not reflect current intent.

**Implementation**: `atelier-core/src/atelier/intake/skip_path.py` exposes `resolve_skip_path(question_id: str, sources: SkipPathSources) → ResolvedAnswer`. ResolvedAnswer carries the source it came from for traceability. A 4-fixture test where descriptor + Memory Bank disagree → resolver returns descriptor's value.

## Consequences

### Positive

- Single architectural anchor for 4 audit gaps that would otherwise be 4 one-off fixes
- Future contributors can't ship judge/gate/subagent code that ignores BriefSpec — Rules 1+2 are mechanically enforced
- Amendment becomes deterministic with a clear UX (versioned, with re-intake of changed fields only) — first user with a real campaign won't hit non-determinism
- Skip-path precedence is documented; intake repeatability across sessions
- Strengthens N12 RLRD claim: anchors propagate not just across files but across subagents
- Enables P1-4 (compliance level → gate), P1-5/N15 (axis weighting), P1-6 (CSC-D constitution selection), P2-9 (PADI dynamic config) — each of these reads BriefSpec and must trust it's the current authoritative version

### Negative

- Rule 1 adds ~2-4K tokens per cached prefix → ~$0.30/day cache-write overhead per active project. Negligible.
- Rule 3 amendment workflow adds ~1d implementation work (versioning, history log, in-flight surface handling) — slots into Phase 2
- Rule 3 re-validation of converged surfaces adds latency to amendment operations (a campaign with 50 converged surfaces re-evaluates all 50). Mitigation: re-validation is a parallel batch, not sequential.
- Cache breakpoint invalidation on amendment costs one cache miss per active subagent at amendment time

### Neutral

- Reviewer subagent rejection-on-violation requires a CI lint rule (`atelier-eval/src/atelier_eval/lints/anchor_discipline.py`) — small effort, large enforcement value
- The `brief_spec_history.jsonl` becomes a useful audit trail for compliance scenarios
- `--no-research` flag from WRAI also applies to amendment WRAI re-runs

## Alternatives considered

### Option A: Pass BriefSpec per-call instead of cached-prefix

- Pros: Smaller cached prefix; no invalidation cost on amendment
- Cons: Higher per-call cost (BriefSpec serialized per dispatch instead of once per hour); subagents pay tokens for the same data repeatedly
- Why rejected: Cache amortization is the cost lever; per-call shipping defeats the point

### Option B: In-place BriefSpec mutation with revision-history file

- Pros: Simpler state directory layout (one file); no symlink dance
- Cons: Violates `frozen=True` Pydantic constraint; surfaces don't have a stable BriefSpec version to bind to; rollback is non-trivial
- Why rejected: Versioning matches the rest of the schema-versioned data contracts (PRD §9 `schema_version` discipline)

### Option C: Memory Bank wins on skip-path conflicts

- Pros: Personalization-first (user's prior preferences dominate)
- Cons: Conflicts with explicit `.atelier.yaml` declarations; surprises users who edited their descriptor expecting it to take effect; non-deterministic if Memory Bank's statistical inference shifts with new data
- Why rejected: Explicit user intent (descriptor) must beat statistical inference (Memory Bank). Personalization belongs in defaults selection, not explicit-conflict resolution.

## References

- [audit/findings.md](../../audit/findings.md) — Gaps 2, 7, 8, 10
- [audit/audit-plan.md](../../audit/audit-plan.md) — P0-1, P0-2, P0-3, P1-7
- [ADR 0004 — PIP](0004-pre-generation-intake-protocol.md) — extended by this ADR
- [ADR 0011 — WRAI](0011-web-research-augmented-intake.md) — sister ADR
- [PRD §11 Strategy v2 cache breakpoint](../superpowers/specs/2026-05-14-atelier-prd.md)
- Anthropic "Effective context engineering for AI agents" (Sep 29 2025) — structured note-taking pattern
