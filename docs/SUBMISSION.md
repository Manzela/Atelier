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
  failing silently. A Model Armor injection-guard callback wraps every model
  call, active when its template is configured.
- **Human-in-the-loop by design.** The pipeline halts at sign-off and resumes
  only on approval; a non-destructive stop preserves a checkpoint.

Atelier runs on Google's managed stack. The live deployment uses Google ADK to
orchestrate the agents, Gemini on Vertex AI to serve them, a Vertex LLM judge
panel to score them, Cloud Run to host the API and the Studio, Firebase
Authentication for Google sign-on, Firebase Hosting for the public Bench
Observatory, and BigQuery for the trajectory and DPO-preference tables behind the
data flywheel. The live production service additionally runs on Vertex AI Agent
Engine session services, Model Armor injection-screening on every model call, and
a Firestore-backed token cap — all verified enabled on the deployed Cloud Run
revision. Vertex Memory Bank is integrated and configuration-selectable.

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

Atelier is built end-to-end on Google Cloud (region `us-central1`).

In the live deployment:

- Google Agent Development Kit (ADK) — agent orchestration
- Gemini on Vertex AI — model serving (`GOOGLE_GENAI_USE_VERTEXAI=true`) and the LLM judge panel (`ATELIER_JUDGE_MODE=llm`)
- Vertex AI Agent Engine — session services (`SESSION_BACKEND=vertex`, engine `8092258795629051904`)
- Model Armor — prompt-injection screening on model calls (`ATELIER_MODEL_ARMOR_ENABLED=true`, `atelier-default` template)
- Cloud Run — API and Studio hosting (the agent runtime), `--concurrency=1`
- Cloud Build + Artifact Registry — container build and image storage
- Firebase Authentication — Google single sign-on
- Firebase Hosting — the public Bench Observatory (managed TLS)
- Firestore — per-user token-cap persistence (`ATELIER_USAGE_BACKEND=firestore`, production service)
- BigQuery — trajectory, DPO-pair, calibration, and cost-ledger tables for the data flywheel
- Cloud Logging — structured request and pipeline logs (native to Cloud Run)

Integrated in code and Terraform, configuration-selectable, and not enabled in
this deployment:

- Vertex AI Memory Bank — long-term memory persistence (Agent Engine sessions are live; Memory Bank is wired and selectable)
- Vertex AI Agent Engine reasoning-engine deploy target — the live agents run on Cloud Run and use Agent Engine session/memory services; the managed reasoning-engine runtime is the alternate deploy target
- Cloud Load Balancing + Cloud Armor and Certificate Manager + Cloud DNS — the
  custom-domain ingress design; the live custom domain is currently served via
  Firebase Hosting with Cloudflare DNS

## Pre-filing checklist

- [ ] `make production-readiness` is green against the live stack (AT-110).
- [ ] `make submission-check` is green (this file complete, all links resolve).
- [ ] Demo video URL pasted above and resolves.
- [ ] Repository is judge-accessible.
- [ ] "Built with Google Cloud" attribution present (above).
