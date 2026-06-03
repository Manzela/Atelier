# DevPost submission kit — Atelier

Paste-ready copy for every DevPost field. Claims match the running system (see
`SUBMISSION.md` for the live-vs-integrated Google Cloud split). Filing then
reduces to: paste these fields, upload the three images in `assets/`, paste the
demo-video URL, and submit (Track: Build).

---

## Tagline

An autonomous design-systems agent that refuses to ship work which fails its gates.

## Inspiration

Today's AI design tools produce output that looks plausible but isn't
accountable: they regenerate instead of edit, drift off the brand's tokens, hide
their cost, and take an ambiguous prompt literally. We wanted to show that design
autonomy can be governed — accessible, on-brand, and within budget by
architecture, not by a larger prompt.

## What it does

Given a natural-language brief, Atelier researches the domain, proposes a plan,
pauses for human sign-off, then generates, judges, and iterates a production-grade
design system — and it refuses to ship candidates that fail its gates.

- **Deterministic-gate-first.** Every node is a deterministic gate in front of a
  probabilistic agent, never the reverse. A skeleton or off-token candidate is
  rejected before any judge scores it. The gate battery — semantic HTML, contrast,
  accessibility via axe-core, token fidelity, performance, and visual diff — runs
  on every candidate.
- **A design system, not a screenshot.** The deliverable is DTCG design tokens
  plus self-contained portable HTML. Changing one token propagates across every
  generated surface — a property the token-fidelity gate enforces.
- **Multi-axis judging (D-O-R-A-V).** Surviving candidates are scored on Design,
  Originality, Relevance, Accessibility, and Visual clarity by a judge panel,
  floored by the deterministic gates so judge scores can never override a hard
  failure. The loop iterates until it converges above threshold.
- **Governed autonomy.** A per-user lifetime token cap is enforced server-side
  before any model call; a live meter shows used-versus-remaining with the
  thinking-token split; the agent always acknowledges degradation rather than
  failing silently.
- **Human-in-the-loop by design.** The pipeline halts at sign-off and resumes only
  on approval; a non-destructive stop preserves a checkpoint.

## How we built it

A six-role DDLC pipeline (UX Research, Information Architecture, Wireframe, UI
Design, Interaction, Tokens) runs as a Google ADK `SequentialAgent`, each
specialist consuming the prior's output. Its candidates pass the N3c deterministic
gate battery, then the N3d D-O-R-A-V judge panel, then an N4 best-pick and an N3e
fixer loop that iterates to convergence (threshold 0.70). Accepted-versus-rejected
pairs are mined into DPO preference signal in BigQuery — the self-improving
flywheel. The live deployment runs on Google ADK, Gemini on Vertex AI, Cloud Run,
Firebase Authentication and Hosting, and BigQuery, with Cloud Logging for
observability.

## Challenges we ran into

Making generation functional end-to-end on real Vertex took more than wiring: the
candidates had to be normalized before the zero-tolerance gates, the design-tool
transport and controlled-generation schemas had to be reconciled with Vertex's
constraints, and the gate thresholds had to be calibrated so real HTML passes
while skeletons fail. The subtlest class of bugs were cross-module ordering
contracts that only became reachable once the whole pipeline ran end-to-end — for
example, a candidate-to-score join that, if paired positionally instead of by id,
silently inverted the preference pairs written to BigQuery. We fixed it at the
root and added red-green regression tests.

## Accomplishments that we're proud of

Generation converges on real Vertex AI (recent live runs scored 0.92 and 0.98),
and nothing in the judged path is mocked. The deterministic floor is demonstrable:
an off-token candidate is rejected on structure before any judge sees it. The
quality story is measured rather than asserted — a public Bench Observatory, a
hermetic offline suite, and a byte-identical golden trajectory across repeated
runs.

## What we learned

Putting a deterministic gate before each probabilistic agent — never the reverse —
is the load-bearing idea: it is what lets an autonomous agent be trusted to refuse
its own bad output. Honest degradation beats apparent capability. And the hardest
defects are not in any single module; they are the cross-module contracts that
only become reachable once the entire system works.

## What's next

Promote the integrated Google-native backends from configuration-selectable to
on-by-default in production — Vertex Agent Engine as the managed runtime, Vertex
Sessions and Memory Bank for state, Model Armor on every model call, a
Firestore-backed token cap, and Cloud Load Balancing with Cloud Armor for the
custom-domain ingress. Route the intermediate specialists to a faster model to cut
end-to-end latency (ADR-0025). Expand the calibration and adversarial evaluation
sets.

## Built with

`google-adk` · `gemini` · `vertex-ai` · `cloud-run` · `firebase-authentication` ·
`firebase-hosting` · `bigquery` · `cloud-logging` · `python` · `typescript` ·
`next.js` · `axe-core` · `dtcg-design-tokens`

## Links

| Field      | Value                                           |
| ---------- | ----------------------------------------------- |
| Live URL   | https://atelier.autonomous-agent.dev            |
| Repository | https://github.com/Manzela/Atelier              |
| Demo video | (paste the recorded URL — see `DEMO-SCRIPT.md`) |
| Track      | Build                                           |

## Gallery images (upload from `assets/`)

1. `01-bench-observatory.png` — the public quality dashboard (calibration, per-judge
   scores, D-O-R-A-V axes, DPO promotion events).
2. `03-generated-fintech-onboarding.png` — a real converged output (0.92): a calm
   fintech onboarding with a single clear primary CTA.
3. `02-studio-login.png` — the Studio entry with Google sign-on.
