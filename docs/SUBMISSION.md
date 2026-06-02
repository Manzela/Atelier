# Atelier — Google AI Agents Challenge 2026 submission package

This file is the operator checklist and source text for the DevPost submission.
Every field below is verified by `scripts/check_submission_readiness.sh` before
filing. Target file date: 2026-06-03 (deadline 2026-06-05).

## Project description (<= 500 words)

**Atelier is an autonomous design-systems agent.** Given a natural-language
brief, it researches the domain, proposes a plan, pauses for human sign-off,
then generates, judges, and iterates a production-grade design system — and it
refuses to ship work that fails its gates.

The market's AI design tools share four failures: they regenerate instead of
edit, they drift off the brand's tokens, they hide their cost, and they take an
ambiguous prompt literally. Atelier answers each with architecture rather than a
larger prompt.

- **Deterministic-gate-first.** Every node is a deterministic gate in front of a
  probabilistic agent, never the reverse. An empty or skeleton candidate is
  rejected before any judge scores it; off-token output cannot pass on judge
  scores alone. The gate battery (semantic HTML, contrast, accessibility via
  axe-core, token fidelity, performance, visual diff) runs on every candidate.
- **A design system, not a screenshot.** The deliverable is DTCG design tokens
  plus self-contained portable HTML. Changing one token propagates across every
  generated surface — a property the token-fidelity gate enforces, not merely
  applies.
- **Multi-axis judging.** Candidates are scored on Design, Originality,
  Relevance, Accessibility, and Visual clarity (D-O-R-A-V) by a panel, gated by
  the deterministic floor so judge scores can never override a hard failure.
- **Governed autonomy.** A per-user lifetime token cap is enforced server-side
  before any model call; a live token meter shows used-versus-remaining with the
  thinking-token split; the agent always acknowledges degradation rather than
  failing silently. Model Armor guards every model call against injection.
- **Human-in-the-loop by design.** The pipeline halts at sign-off and resumes
  only on approval; a non-destructive stop preserves a checkpoint.

Atelier runs end-to-end on Google's managed stack: Google ADK orchestrates the
agents, Gemini on Vertex AI serves them, Agent Engine hosts the runtime, Vertex
Sessions and Memory Bank persist state, Model Armor enforces safety, and
Firestore, Cloud Run, Cloud Armor, and Certificate Manager carry the product.

Every claim is reproducible. `make verify` runs the hermetic offline suite,
including a byte-identical golden trajectory across repeated runs; `make replay`
reproduces a recorded production run; the gate behavior is demonstrated by a
live off-token rejection. Nothing in the judged path is mocked.

## Required submission fields

| Field        | Value                                                                          |
| ------------ | ------------------------------------------------------------------------------ |
| Project name | Atelier                                                                        |
| Live URL     | https://atelier.autonomous-agent.dev                                           |
| Repository   | https://github.com/Manzela/Atelier (judge-accessible)                          |
| Demo video   | TODO: operator records the live production walkthrough and pastes the URL here |
| Team         | Daniel Manzela                                                                 |
| Track        | Build                                                                          |

## Built with Google Cloud

Atelier is built end-to-end on Google Cloud (region `us-central1`):

- Google Agent Development Kit (ADK) — agent orchestration
- Gemini on Vertex AI — model serving
- Vertex AI Agent Engine — managed agent runtime
- Vertex AI Sessions + Memory Bank — session and long-term memory persistence
- Model Armor — prompt-injection and output safety
- Cloud Run — API and dashboard hosting
- Cloud Load Balancing + Cloud Armor — public ingress and edge protection
- Certificate Manager + Cloud DNS — managed certificate and custom domain
- Firestore — state, board, and per-user token-cap counters
- Firebase Authentication — Google single sign-on
- BigQuery — trajectory storage for the data flywheel
- Cloud Trace + Cloud Logging — observability

## Pre-filing checklist

- [ ] `make production-readiness` is green against the live stack (AT-110).
- [ ] `make submission-check` is green (this file complete, all links resolve).
- [ ] Demo video URL pasted above and resolves.
- [ ] Repository is judge-accessible.
- [ ] "Built with Google Cloud" attribution present (above).
