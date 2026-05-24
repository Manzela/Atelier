# Evaluation Framework Sweep 2 — Additional 10X Candidates

**Date:** 2026-05-24
**Context:** Enrichment of prior audit (sweep 1) which covered FrontendBench, UIBench, VisualWebArena.
**Prior verdict:** FrontendBench ADOPT, UIBench strategic ADOPT, VisualWebArena REJECT.

---

## New finding 1: Lighthouse a11y + perf as AND-gate reward signal (PIONEER OPPORTUNITY)

### What it is

Google's open-source Lighthouse audit tool runs automatically against rendered HTML pages and produces objective, deterministic scores in 4 categories: Performance, Accessibility (a11y), Best Practices, SEO. axe-core (bundled inside Lighthouse) detects 57% of WCAG violations. Already listed in Atelier's `docs/eval/methodology.md` as a Layer 1 code-based grader — but NOT yet used as a reward signal for DPO pair mining.

### 10X impact analysis

**No published paper has used Lighthouse scores as a DPO reward signal.** Research agent confirmed zero papers on Lighthouse → RL. One analogous project (ALISA/WebRenderBench) uses layout/style consistency metrics as RL rewards for webpages — the principle is validated but Lighthouse specifically has never been done. This is a FIRST.

**Mechanism:** Add Lighthouse a11y ≥ 90 and Lighthouse perf ≥ 90 as two additional predicates in the AND-gate composite reward (`reward/composite.py`). A DPO pair where chosen scores a11y=95/perf=92 vs rejected a11y=72/perf=68 has an OBJECTIVE reward signal that requires no LLM, is reproducible by any judge, and is calibrated against Google's own standard.

**Hackathon narrative:** _"Atelier's reward engine includes Lighthouse performance and accessibility scores as hard gates. The DPO training signal is partially objective — candidates that score below Lighthouse 90 on accessibility are automatically rejected from the preference dataset, regardless of aesthetic quality. This prevents the system from being Goodharted on visual appearance alone."_

This is a unique claim that NO competing tool (Orchids, Lovable, v0, Figma Make) makes. Google built Lighthouse. The hackathon judges know Lighthouse. Citing it as a reward component is an instant credibility signal with internal Googlers.

**Cost:** 30–60 seconds per page. For 6 candidate generations × 50 Phase 1 test tasks = 300 Lighthouse runs ≈ 3–5 hours for a batch calibration run. Low cost.

**Implementation effort:** ~1 day. Wrap `lighthouse --output=json` CLI into Python, parse a11y and perf scores, add two predicates to `AndGateRewardEngine`.

**Verdict: ADOPT — highest 10X value of this sweep.**

---

## New finding 2: Design2Code (Stanford / NAACL 2025) as objective DPO reward signal

### What it is

484 manually curated real-world webpages. Input: screenshot of a production webpage. Task: generate HTML/CSS that renders visually to match the screenshot. Metrics: visual element recall, layout correctness. CC BY 4.0, publicly available.

### 10X impact analysis

**Inverted use case:** Atelier doesn't take screenshots as input — it takes text briefs. But Design2Code's 484 reference pages provide a ground-truth quality bar: if you generate HTML from a structured brief and it achieves high visual similarity to a comparable real-world production page (measured by perceptual hash or SSIM), you have an objective quality signal.

**Mechanism:**

1. For each Atelier-generated surface, find the closest Design2Code reference page by embedding similarity of the brief
2. Compute SSIM / CLIP perceptual similarity between Atelier's rendered output and the reference page
3. Higher similarity = higher extrinsic quality score
4. This score SUPPLEMENTS (not replaces) the LLM judge — giving the AND-gate a partially objective anchor

**Why it's 10X:** The current extrinsic margin (LLM judge score difference) is subjective. If it's augmented with an objective perceptual-similarity signal calibrated against 484 real production pages, the DPO training signal is grounded in real-world quality. This addresses the core critique of LLM-as-judge: "how do you know the judge is right?"

**Secondary value:** The 484 reference pages can serve as few-shot anchors for Atelier's generator — "generate a surface similar to this reference-class page."

**Adapter already planned:** `atelier-eval/src/atelier_eval/adapters/design2code.py` is in the atelier-eval README.

**Effort:** ~2 days (download dataset, implement SSIM computation, integrate with eval pipeline)

**Verdict: ADOPT — P1 implementation priority.**

---

## New finding 3: Web2Code training corpus as generator calibration (NeurIPS 2024)

### What it is

1,179,700 screenshot-to-HTML instruction-response pairs (MBZUAI-LLM/web2code, NeurIPS 2024). Dual benchmarks: Webpage Understanding (WUB) and Code Generation (WCGB). Uses GPT-4V rendering-based evaluation.

### 10X impact analysis

**Not primarily a benchmark — primarily a training corpus.** The 1.17M pairs are the value. For Atelier's DPO loop, this data provides:

1. A **calibration signal** for the generator: what does high-quality screenshot-to-code look like at massive scale?
2. **DPO warm-start pairs**: sort by GPT-4V evaluation score → use top/bottom quintiles as preferred/rejected pairs → pre-train the DPO loop before any Atelier-generated pairs exist
3. **Diversity hedge**: 1.17M pairs cover design patterns Atelier's K=6 candidate generator hasn't seen

**Limitation:** The benchmark uses GPT-4V as judge (not objective). The scale is the value, not the evaluation methodology.

**Cost:** Dataset is large (likely 50GB+). Not suitable for CI eval. Suitable as Phase 2 training data supplement.

**Effort:** ~1 day to download, sample, and ingest top-quintile pairs into BigQuery `dpo_preference_pairs`

**Verdict: ADOPT as training corpus (Phase 2 warm-start), not as eval benchmark.**

---

## Downgraded from sweep 1: Vertex AI Eval Service

Research confirms the Vertex AI Eval Service is designed for **text LLM output evaluation** (rubric-based scoring of text responses). It does NOT natively support:

- Visual/screenshot evaluation
- Frontend code rendering quality
- Perceptual similarity

It does support custom Python metric functions — so Lighthouse scores COULD be wrapped inside a custom metric and submitted to Vertex Eval Service. But this adds a layer without adding value. The direct Lighthouse integration (Finding 1) is simpler and more transparent.

**Revised verdict: LOW VALUE as standalone. Acceptable as a report-publishing layer if needed for hackathon demo, but not a core eval component.**

---

## Updated priority table (sweep 1 + sweep 2 combined)

| Priority      | Benchmark/Tool                          | Effort           | Phase    | Why 10X                                                            |
| ------------- | --------------------------------------- | ---------------- | -------- | ------------------------------------------------------------------ |
| **P0**        | UIBench submission                      | 2h (Daniel)      | NOW      | Human preference ranking vs. Orchids/v0; DPO labels                |
| **P0**        | FrontendBench cite in DevPost           | 0.5h (Daniel)    | NOW      | Credibility; Gemini 70.27% baseline to beat                        |
| **P1-A**      | **Lighthouse as AND-gate reward**       | 1d (Claude)      | Phase 2  | Pioneer: objective Google-built reward signal; hackathon narrative |
| **P1-B**      | Design2Code adapter + SSIM reward       | 2d (Antigravity) | Phase 2  | Objective DPO signal anchored to 484 real production pages         |
| **P1-C**      | Web2Code corpus warm-start              | 1d (Antigravity) | Phase 2  | 1.17M DPO warm-start pairs; generator calibration                  |
| **P2**        | FrontendBench adapter (when data drops) | 3d (Antigravity) | Phase 2+ | 148-task automated benchmark with 90.54% human correlation         |
| **P2**        | UIBench reward calibration check        | 1d (Claude)      | Phase 2  | Validates AND-gate against human preference ground truth           |
| **REJECT**    | VisualWebArena                          | —                | Never    | Browser navigation ≠ design generation                             |
| **DOWNGRADE** | Vertex AI Eval Service                  | —                | Optional | Text LLM eval only; use direct Lighthouse integration instead      |

---

## Single most important new finding for hackathon win

**Lighthouse as AND-gate reward signal is the ONLY recommendation in this entire audit that gives Atelier a novel research claim.** Every other evaluation framework is used by existing tools. No published paper, no competing product uses Lighthouse a11y + perf scores as DPO reward predicates. Citing this in the DevPost: "Atelier's reward engine uses Google's own Lighthouse tool as an objective DPO gate" is a claim that:

1. Judges can verify instantly (Lighthouse is public, deterministic, reproducible)
2. No competing tool can make
3. Directly demonstrates "built with Google" beyond just using APIs
4. Addresses the Goodhart/reward-hacking critique with a concrete mitigation

**Recommendation: Implement Lighthouse predicates in `reward/composite.py` before Phase 2 DPO runs start.** This is a 1-day implementation that could be the single most differentiated technical claim in the submission.
