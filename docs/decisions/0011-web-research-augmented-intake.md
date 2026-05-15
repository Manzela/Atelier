# 0011. Web-Research-Augmented Intake (WRAI) as N14 novel contribution

**Status:** Accepted (approved 2026-05-15)
**Date:** 2026-05-15
**Decision-makers:** Daniel Manzela (+ Claude Opus 4.7 MAX as builder)
**Supersedes:** none (extends ADR 0004 PIP)
**Related:** ADR 0012 (Anchor Discipline), ADR 0013 (Conditional Axis Weighting)

## Context

Atelier's PIP (N13) captures user intent in an immutable BriefSpec via 13-question adaptive intake. But the user's answers are bounded by what they already know. They don't know:

- That WCAG 2.2 added rule 2.4.11 (focus not obscured) which Lighthouse a11y v11 may not yet test
- That brutalist 2026 Awwwards winners deliberately violate brand-fidelity in service of memorability — so the default 0.7 floor is wrong for the register they picked
- That Pentagram's editorial typography pattern (used by 4 of 5 top design publications in 2026) is a strong inspirational anchor for the "editorial" register
- That OWASP ASVS L2 mandates specific patterns for the auth surface in the SaaS dashboard they're describing
- That the React 19 server components pattern they're targeting has a known hydration-mismatch failure mode their visual-diff gate will surface as flakiness

A best-practices-aware agent would proactively research these and surface them at intake time, **before** the BriefSpec is locked, so the anchors reflect the current state of the world rather than the user's existing knowledge.

Every commercial autonomous design tool today (Stitch, v0, Subframe, Lovable, Bolt, Replit Agent, Devin, Builder.io, Tempo Labs) accepts user prompts and applies a static knowledge cut-off. **None ships web-research-augmented intake.** This is a novel contribution opportunity.

## Decision

We will introduce **Layer 3.5 — WRAI (Web-Research-Augmented Intake)** as a node between PIP Q&A completion and BriefSpec lock. WRAI runs after the user finishes PIP intake and **before** they approve the BriefSpec, executing 5-8 parallel research queries derived from the draft BriefSpec, distilling findings into a structured `ResearchFindings` block, and surfacing them for one-shot user review.

WRAI characteristics:

1. **Vertex AI Search Grounding as primary backend** — Google-native (matches ADR 0006), per-tenant isolation built-in, citation-bearing results. Fallback to WebSearch tool only if Search Grounding unavailable.
2. **Domain trust model** — whitelist (w3.org, nngroup.com, smashingmagazine.com, anthropic.com, google.com/research, apple.com/design, material.io, awwwards.com, arxiv.org, brutalist-web.design, GitHub official repos) + scored sources (PageRank-derived 0-1 trust score) + denylist (marketing blogs, content farms). Findings below 0.6 trust shown but flagged.
3. **Query templates derived from BriefSpec draft** — 5-8 parallel queries:
   - Industry best practices (e.g., `<industry> dashboard 2026 best practices`)
   - Compliance standards (e.g., `WCAG 2.2 AAA color contrast 2026`)
   - Stack patterns (e.g., `React 19 server components dashboard patterns`)
   - Visual register references (e.g., `editorial typography 2026 Pentagram`)
   - Competitor analysis (e.g., `<vertical> dashboard UX competitors 2026`)
   - Failure-mode warnings (e.g., `<stack> known a11y regressions 2026`)
4. **Findings synthesis via Gemini 3 Flash** — distills raw search results into structured `ResearchFindings`:
   - `applied_standards: list[Standard]` (e.g., WCAG 2.2 AAA, GDPR Art. 25, OWASP ASVS L2)
   - `inspirations: list[Inspiration]` (URL + visual hash + tags)
   - `suggested_overrides: list[Override]` (e.g., "downgrade brand-fidelity floor to 0.6 for brutalist register based on 2026 Awwwards trends")
   - `risk_warnings: list[Warning]` (e.g., "WCAG 2.2 added rule 2.4.11; verify Lighthouse v11 covers it")
   - `citations: list[Citation]` (URL, retrieved_at ISO 8601, trust_score)
5. **One-shot user review** — UI shows aggregate summary: "We researched 8 sources, surfaced 12 findings. Apply all / customize per-finding / skip." Power-user flag `--no-research` skips entirely.
6. **Research findings frozen with BriefSpec** — once user approves, `BriefSpec.research_findings` is immutable. Same versioning discipline as the rest of the spec (per P0-3).
7. **Per-tenant 7-day cache** — research is "current" but not minute-fresh; same query within 7 days returns cached result. Cache key includes tenant_id (no cross-tenant data leak). User can bypass cache via `--research-fresh`.
8. **Model Armor sanitization** — every fetched URL's content runs through Apigee's `SanitizeUserPrompt` policy before reaching the synthesis LLM. Prompt injection via web content is treated as high-severity in scrubber rules.
9. **Fail-soft, fail-loud** — if research returns nothing, fall back to PADI defaults + log `research_unavailable`. Do not block intake. If Model Armor flags content, drop the source + log warning. If all sources fail, BriefSpec proceeds without `research_findings` and the user sees a "research unavailable for this session" notice (trust > apparent capability).

## Consequences

### Positive

- Constitutes novel contribution **N14** — Web-Research-Augmented Intake. Publishable on its own (CHI workshop or HCI venue) as a 2-paper line with N13 PIP.
- Closes 4 audit gaps simultaneously:
  - Gap 4 (Visual register has no behavioral binding) — research surfaces register-specific best practices
  - Gap 5 (CSC-D constitution is project-agnostic) — research can suggest constitution overrides per industry
  - Gap 6 (intake_transcript not consumed downstream) — research findings join the transcript as ground truth for judges
  - Gap 9 (compliance level not wired) — research surfaces current regulatory standards (WCAG 2.2, ASVS L2, etc.)
- Drives demonstrable BriefSpec quality: each anchor cites a source with timestamp. Demo line: "watch Atelier research 8 sources in 12 seconds, surface 12 findings, then lock the BriefSpec — every constraint is grounded."
- Strong G4S "Use of Google Cloud" alignment — uses Vertex AI Search Grounding (Google-native), Apigee Model Armor (Google-native), per-tenant Cloud KMS for cache.
- Direct counter to user-friction failure mode: users don't know what they don't know; agent fills the gap before the spec is locked, not via 6 iterations of judge feedback.

### Negative

- Adds **15-30 seconds** of research time before BriefSpec approval (offset by reducing iterations later)
- Adds **~$0.05-$0.10** per intake (5-8 Search Grounding calls + ~2K synthesis tokens). Stays within MVP per-session ceiling of $0.50.
- Adds **2 dependencies** to the production stack: Vertex AI Search Grounding + a domain trust scorer. Both Google-native; not new sprawl.
- Failure surface: web content is adversarial input. Mitigation via Model Armor + domain whitelist + trust scoring + fail-soft, but cannot be eliminated. Reviewer subagent must explicitly check `research_findings.citations[].trust_score` before accepting.
- Research findings can become stale post-cache-TTL, but this is acceptable — the BriefSpec is frozen at approval time per the immutability discipline. New research happens on next BriefSpec amendment (per P0-3).

### Neutral

- WRAI is **opt-out** via `atelier run --no-research` for power users who want minimum latency
- Research transcript joins `BriefSpec.intake_transcript` for full audit traceability
- The trust scorer's whitelist is itself a versioned config file (`config/research-trust.yaml`) — additions require an ADR (defends against silent trust-list expansion)

## Alternatives considered

### Option A: Static knowledge base (curated docs shipped in the repo)

- Pros: No web dependency; predictable; cheap; offline-capable
- Cons: Becomes stale immediately; can't cover long-tail (every industry × every stack); doesn't surface emerging standards; adds bloat (~MB per industry)
- Why rejected: The "current state of the world" is the actual differentiator. Static dies on day 30.

### Option B: Web research at generation time, not intake time (per-iteration)

- Pros: Always current; per-surface specificity
- Cons: Latency on every iteration; cost explosion (12 surfaces × 8 iterations × 8 queries = 768 queries per campaign); no user review of findings before they shape generation; defeats anchor immutability
- Why rejected: The whole point of intent-locking is to commit at one moment. Continuous research = continuous drift, the opposite of RLRD.

### Option C: WRAI but with WebSearch + WebFetch only (skip Vertex AI Search Grounding)

- Pros: Lower up-front integration cost
- Cons: Loses per-tenant isolation; no built-in citation bearing; weaker trust-score signal; sprawl away from Google-native stack (per ADR 0006)
- Why rejected: Tenancy isolation is non-negotiable for multi-tenant production. Vertex AI Search Grounding is the right primitive.

### Option D: Skip research, lean harder on user expertise

- Pros: Simplest; no new code
- Cons: Anchors stay bounded by user knowledge; first user with niche compliance need (e.g., HIPAA dashboard) ships an outdated BriefSpec; competitor moat lost
- Why rejected: This is the status quo of every commercial tool. Defeats the "10X" thesis.

## Architecture detail

**Position in pipeline (revised Layer 3 architecture):**

```
PIP Router (assesses scope)
  → Skip-Path Resolver (descriptor + Memory Bank + brief-parsed)
    → Adaptive Question Sequencer (PIP Q&A)
      → WRAI: Web-Research-Augmented Intake [NEW — N14]
        → Query Generator (derives 5-8 parallel queries from draft BriefSpec)
        → Vertex AI Search Grounding (parallel calls; per-tenant cache)
        → Trust Scorer (per-source 0-1; whitelist/scored/denylist)
        → Model Armor (sanitize all fetched content)
        → Findings Synthesizer (Gemini 3 Flash → ResearchFindings)
        → User Review (one-shot summary; per-finding accept/skip)
      → BriefSpec Synthesizer (now embeds research_findings)
        → User final approval → BriefSpec frozen + DECISIONS.md initialized
```

**Pydantic data contract addition** (extends PRD §9):

```python
class TrustScore(BaseModel, frozen=True):
    score: float  # 0.0-1.0
    method: TrustMethod  # WHITELIST | PAGERANK | DOMAIN_AGE | DENIED
    schema_version: int = 1

class Citation(BaseModel, frozen=True):
    url: HttpUrl
    title: str
    retrieved_at: datetime
    trust: TrustScore
    excerpt: str  # max 500 chars; what was used in synthesis
    schema_version: int = 1

class Standard(BaseModel, frozen=True):
    name: str  # e.g., "WCAG 2.2 AAA"
    rule_id: str | None  # e.g., "2.4.11"
    description: str
    citations: list[Citation]
    auto_applied_to_briefspec: bool  # True if user accepted; False if user skipped
    schema_version: int = 1

class Inspiration(BaseModel, frozen=True):
    url: HttpUrl
    visual_hash: str | None  # for visual-diff prior-art comparison
    tags: list[str]
    citations: list[Citation]
    schema_version: int = 1

class Override(BaseModel, frozen=True):
    target_field: str  # e.g., "axis_weights.brand_fidelity"
    suggested_value: str  # JSON-serializable
    rationale: str
    citations: list[Citation]
    user_accepted: bool
    schema_version: int = 1

class Warning(BaseModel, frozen=True):
    severity: WarningSeverity  # INFO | WATCH | BLOCK
    message: str
    affected_axis: str | None
    citations: list[Citation]
    schema_version: int = 1

class ResearchFindings(BaseModel, frozen=True):
    research_id: UUID
    queries_executed: list[str]
    applied_standards: list[Standard]
    inspirations: list[Inspiration]
    suggested_overrides: list[Override]
    risk_warnings: list[Warning]
    citations: list[Citation]  # all citations from this research session
    research_started_at: datetime
    research_completed_at: datetime
    user_skipped: bool = False  # true if user used --no-research
    schema_version: int = 1

# BriefSpec (extended):
class BriefSpec(BaseModel, frozen=True):
    # ... all existing fields ...
    research_findings: ResearchFindings | None = None  # None if --no-research
```

**Cost model:**

- Per intake: 5-8 queries × $0.01 (Vertex AI Search Grounding) = $0.05-$0.08
- Synthesis: ~2K tokens × Gemini 3 Flash ($0.10/1M tokens) = $0.0002
- Total: **~$0.05-$0.08 per BriefSpec** (well within $0.50/session ceiling)

**Latency:**

- Parallel queries: ~3-5s (Search Grounding p95)
- Synthesis: ~5-8s (Gemini 3 Flash)
- User review: variable (user-driven; not counted)
- **Total agent time: 8-13s** (acceptable for one-shot intake)

**Failure-handling trichotomy mapping:**

| Failure                                   | Mode                                               | Action                                                                                                        |
| ----------------------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Vertex AI Search Grounding 503            | self-heal (3 retries with backoff), then fail-soft | Log `research_degraded`; proceed with whatever results returned                                               |
| Single source fails Model Armor           | fail-soft                                          | Drop source; log warning; continue with remaining                                                             |
| All sources fail Model Armor              | fail-soft                                          | Skip research; user sees "research unavailable" notice; BriefSpec proceeds                                    |
| Synthesis LLM hallucinates citation       | fail-loud                                          | Reviewer subagent verifies every citation URL is reachable + matches the trust score in `research-trust.yaml` |
| User-supplied query injects prompt-attack | fail-loud                                          | Apigee Model Armor blocks; surface to user as "your research query was flagged"                               |

## References

- [PRD §6.1 PIP Layer](../superpowers/specs/2026-05-14-atelier-prd.md)
- [ADR 0004 — PIP](0004-pre-generation-intake-protocol.md) — WRAI extends this
- [ADR 0006 — Google-native stack](0006-google-native-stack-no-langfuse.md) — chooses Vertex AI Search Grounding
- [audit/findings.md Gap 4-6, 9](../../audit/findings.md) — gaps WRAI closes
- Vertex AI Search Grounding docs (Google Cloud, 2026)
- Apigee `SanitizeUserPrompt` policy reference
- WCAG 2.2 (W3C, October 2023)
- DAPLab 9 Critical Failure Patterns (Columbia, Jan 2026) — Pattern 3 (Business Logic Mismatch) addressed by surfacing standards user didn't know
