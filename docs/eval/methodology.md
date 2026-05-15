# Eval Methodology

Atelier's evaluation discipline implements **three grader types** per Anthropic's published Jan 2026 taxonomy:

1. **Code-based graders** — lint, typecheck, fail-to-pass tests, tool-call trajectory verification (deterministic; no LLM)
2. **Model-based graders** — LLM-as-judge with rubrics (subjective axes: brand, copy, motion)
3. **Human graders** — calibration golden set hand-rated; designer-in-residence sessions

## Atelier's grader inventory

### Code-based (Layer 1 — Deterministic Gate, N1 DGF-D2C)

| Grader | What it measures | Threshold |
|---|---|---|
| Lighthouse a11y | WCAG 2.1 compliance | ≥ 90 |
| Lighthouse perf | Performance score (LCP, CLS, INP) | ≥ 90 |
| Lighthouse best practices | Standard web practices | ≥ 90 |
| axe-core | A11y violations beyond Lighthouse | 0 violations |
| Token-fidelity grep | Hex/font/spacing values outside DESIGN.md | 0 drift |
| Semantic-HTML linter | Heading hierarchy, ARIA on iconic controls, alt text, semantic landmarks | strict pass |
| Playwright visual-diff | Pixel mismatch vs reference screenshot | ≤ 2% |
| Responsive snapshot | Render correctness at 375 / 768 / 1280 / 1920 px | all 4 pass |
| ADK tool-trajectory | Verifies the agent called the right tools in the right order | exact / ordered match |

### Model-based (Layer 2 — LLM Design Judge, N2 DEMAS-D + N3 PerJudge)

K = 5 specialized rubric judges, each with DEMAS-D Provenance Matrix:

| Judge | Axis | Provenance variables | Threshold (composite floor: 0.7) |
|---|---|---|---|
| Brand-judge | Brand fidelity | Rendered DOM + DESIGN.md tokens + DESIGN_PRINCIPLES_APPLE.md | 0.7 |
| Copy-judge | Voice + tone | Text content + voice rubric | 0.7 |
| Motion-judge | Motion correctness | Animation rules + JS event listeners + `prefers-reduced-motion` results | 0.7 |
| Token-fidelity-judge | Token coherence | Rendered hex/rgb/font/spacing + DESIGN.md token set | 0.8 |
| Cross-screen-coherence-judge | Pattern reuse vs prior surfaces | This surface + top-5-most-similar prior + DECISIONS.md | 0.7 |

Each uses ADK's `rubric_based_final_response_quality_v1`. Bayesian-weighted vote with confidence interval (per ADR 0008).

### Human (Layer 3 — Calibration + Sign-off)

| Grader | When | Set size |
|---|---|---|
| Calibration golden set | Weekly recalibration cron (per limits.calibration.recalibration_cron) | 100 frozen tasks per axis = 500 total |
| Adversarial held-out | Pre-release | 50 tasks |
| Designer-in-residence | Weekly during sprint, as available post-launch | Real project briefs |
| Telegram approval gate | Per limits.approval rules (high-stakes pages) | ad-hoc |

## Eval cadences

| Surface | Cadence | What it catches |
|---|---|---|
| Pre-commit smoke | Every commit | Imports broken, types wrong, basic flow broken |
| CI integration | Every PR | Cross-component breakage |
| WebGen-Bench full (484 tasks) | Nightly (manual trigger only — workflow_dispatch) + on-tag | Headline benchmark regression |
| Calibration golden set | Weekly Mon 03:17 UTC | Judge calibration drift (N8) |
| Adversarial held-out | Pre-release | Eval-set Goodharting check |
| Designer-in-residence | Per session | Real-world quality + testimonial capture |

## Anti-Goodhart defenses

Per Berkeley RDI's published finding that LLM judges can achieve near-perfect benchmark scores without solving any task, Atelier defends with:

1. **Held-out adversarial set** — never seen during development; only run pre-release
2. **Calibration golden set** — frozen task-by-task; correlation drop > 5% week-over-week triggers alert (publicly visible at calibration.atelier.dev)
3. **Designer-in-residence sessions** — real designers with real briefs; their thumbs-up/down feeds DPO as ground-truth labels
4. **ChainPoll** for judges — multi-sample majority voting per judge call
5. **Reward-hacking guard** — 10% of human accept/reject signal is held out from DPO training; quarterly check that judge-train and judge-holdout scores stay correlated

## See also

- [PRD §16 10× outcome checklist](../superpowers/specs/2026-05-14-atelier-prd.md)
- [ADR 0008 — Multi-judge Bayesian-weighted consensus](../decisions/0008-multi-judge-bayesian-consensus.md)
- [ADR 0009 — Public calibration dashboard](../decisions/0009-public-calibration-dashboard.md)
- [bench.atelier.dev](https://bench.atelier.dev) — public scoreboard
- [calibration.atelier.dev](https://calibration.atelier.dev) — public drift dashboard
- [Anthropic: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) (Jan 9, 2026) — three grader types pattern
