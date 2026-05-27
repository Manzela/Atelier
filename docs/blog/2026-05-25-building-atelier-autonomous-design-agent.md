# How We Built Atelier: The First Autonomous Design Agent That Converges, Not Just Generates

Every tool in the autonomous UI generation space — Stitch, v0, Lovable, Subframe — solves the same problem: turn a text prompt into a working interface. They do it well. Some of them do it remarkably well. But they all share a fundamental limitation: they generate and stop.

The output you receive after hitting "generate" is the final output. Whether it meets accessibility standards, whether the layout holds on mobile, whether the design tokens match the system you specified — that's on you to verify. Google's own Antigravity codelab calls this step "Vibe Check." We've been building production UI for long enough to know that a vibe check isn't a quality gate. It's a prayer.

## The architecture behind Atelier

Atelier runs every design request through an 8-node pipeline built on Google's ADK 2.0. The pipeline isn't linear — it's a directed acyclic graph where each stage has a clear responsibility and a defined contract with the next.

The request enters at N1 (brief parsing), gets enriched with live web context at N14 via Vertex AI Search Grounding, and lands at N3a — a parallel generator ensemble that produces K=3 candidates simultaneously using Stitch MCP. Each of those candidates then passes through N3c, a battery of six deterministic gates. These gates are fast, hallucination-free, and non-negotiable: semantic HTML validation, CSS syntax checking, token fidelity against the design system, Lighthouse performance heuristics, axe accessibility scoring, and visual-diff structural similarity against the reference. No LLM is involved at this stage. A candidate either passes all six gates or it's filtered out before any judge sees it.

Candidates that survive N3c advance to N3d — a multi-judge consensus evaluation across five axes (Design, Originality, Relevance, Accessibility, Visual Clarity) using Bayesian-weighted scoring. The judges don't see each other's scores. Their composite output goes to N4, which applies a convergence gate at κ=0.70. If the best candidate meets the threshold, the pipeline declares convergence and returns it. If not, the result still returns — but flagged as non-converged, with per-axis scores attached so the user knows exactly where the design fell short.

```python
# From runner.py — convergence decision (N4)
if best_score >= CONVERGENCE_THRESHOLD:
    converged = True
    logger.info("Pipeline converged at %.3f (threshold %.2f)",
                best_score, CONVERGENCE_THRESHOLD)
```

## The self-improving flywheel

Every pipeline execution — converged or not — writes a full trajectory record to BigQuery. The record captures input brief, candidate outputs, per-axis gate scores, judge votes, cost, and latency. Over time, this table accumulates the raw material for preference learning.

The DPO Pair Miner reads these trajectories and extracts preference pairs: cases where two candidates for the same surface received different outcomes (one accepted, one rejected). These pairs feed into a Vertex AI PREFERENCE_TUNING job using `google.genai`. The tuning job produces a fine-tuned adapter with a margin score for each pair. If the adapter passes a κ-gated evaluation against a calibration seed dataset (κ ≥ 0.70), it's promoted — and the next generation cycle uses the improved model. We call this the "Dreaming Module": the system reviews its own past work, learns which outputs users preferred, and tunes itself to produce better candidates the next time around.

## What we learned building on ADK

ADK 2.0 made several things significantly easier than building from scratch. The `Runner` class with injectable `SessionService` meant we could swap `InMemorySessionService` for `BigQuerySessionBackend` without changing any pipeline code. The evaluation framework gave us a standard format for golden test sets — five canonical design briefs with expected tool trajectories — that judges at Google can inspect directly. The `MCPToolset` integration with Stitch was clean: one function call to register the MCP server, and every agent in the pipeline could invoke Stitch tools by name.

The hardest problem we solved was making deterministic gates work before LLM-based judges. LLM judge calls are expensive (both in latency and cost), and early in development we were sending all K=3 candidates through full consensus evaluation. Moving the six deterministic gates before the judges cut evaluation cost by roughly 40% on briefs where one or more candidates had structural issues. The tradeoff was getting the gate thresholds right — too strict and nothing passes, too loose and the judges get noisy input.

## What's next

Phase 3 targets a full WebGen-Bench evaluation pass and multi-surface campaign support — redesigning 12+ pages in a single session with cross-surface coherence. The DPO flywheel has been running on accumulated trajectory data, and preliminary κ measurements suggest the tuned adapter outperforms the base model on our golden set. The submission for Google for Startups AI Agents Challenge 2026 is targeting June 3.
