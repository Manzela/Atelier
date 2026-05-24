# Audit Plan: Frontend Evaluation Benchmark Integration

**Date:** 2026-05-24
**Decision context:** Phase 2 entry; 10-day sprint to submission (2026-06-03 noon)
**Verdict first:** FrontendBench = ADOPT (Phase 2+); UIBench = ADOPT (now, strategic); VisualWebArena = REJECT (wrong domain)

---

## Verdict Summary

| Benchmark          | Verdict               | Rationale in 10 words                                 |
| ------------------ | --------------------- | ----------------------------------------------------- |
| **FrontendBench**  | **ADOPT**             | Perfect domain fit; Gemini 70% baseline to beat       |
| **UIBench**        | **ADOPT (strategic)** | Human preference ground-truth; competitor calibration |
| **VisualWebArena** | **REJECT**            | Browser navigation ≠ design generation; wrong problem |

---

## P0 — Immediate action (no code needed, high strategic value)

### P0-01: Submit Atelier to UIBench comparison platform

**What:** Register Atelier as a competing tool on uibench.ai and submit sample generated UIs for human expert blind comparison.

**Why:** UIBench provides the only external human-preference validation for Atelier's visual quality. The competing tools (Orchids, Lovable, v0) are the exact market context Google's hackathon judges will reference. A UIBench ranking above v0 (22.24 μ) or Figma Make (27.46 μ) is a credible, third-party-verified claim Atelier can make in the DevPost submission.

**Secondary value:** UIBench pairwise comparison data where Atelier is "chosen" can be used as DPO preference pairs — this is human-labeled ground truth for the RL loop at no additional cost beyond sample generation.

**Effort:** ~2 hours. Generate 5-10 sample UI designs from Atelier, submit via UIBench interface.

**Owner:** Daniel (submission requires human action; cannot be automated)

**Where:** `uibench.ai` submission interface

**Success metric:** Atelier appears in UIBench leaderboard with ≥ 3 matches collected

---

### P0-02: Monitor FrontendBench data release

**What:** Watch the FrontendBench repository (arXiv 2506.13832v1, ByteDance) for public data/code release. Implement adapter when released.

**Why:** FrontendBench is the most precise automated eval for Atelier's output. 148 tasks across 5 difficulty levels with 90.54% human-machine correlation. Gemini 2.5 Pro scores 70.27% — Atelier beating this is a quantifiable competitive claim. The atelier-eval scaffold already has the adapter stub planned (`adapters/frontendbench.py`).

**Effort on release:** ~1 day to implement the adapter (harness is Puppeteer/Jest; integrate with Playwright layer already in Atelier's eval stack).

**Blocking condition:** Data not yet public as of 2026-05-24.

**Owner:** Claude (implementation) / Daniel (monitor arXiv + GitHub)

**Where:** `atelier-eval/src/atelier_eval/adapters/frontendbench.py` (when data available)

**Immediate action (no data needed):** Add FrontendBench to the eval section of the DevPost submission description as a planned benchmark with Gemini 2.5 Pro baseline cited.

---

## P1 — Phase 2 implementation (data-dependent)

### P1-01: Implement FrontendBench adapter (when data released)

**What:** Implement `atelier-eval/src/atelier_eval/adapters/frontendbench.py` as a full adapter against the 148-task FrontendBench dataset.

**Why:** FrontendBench is the single highest-value automated benchmark for Atelier's Phase 2 evaluation:

- Tests interactive frontend code (Atelier's primary output)
- 5 difficulty levels map to Atelier's surface type variety
- 90.54% human correlation means it's a reliable automated proxy
- Puppeteer/Jest evaluation integrates with Atelier's existing Playwright eval stack

**Evaluator integration:**

```
FrontendBench task → Atelier pipeline → Generated HTML/CSS/JS
                                      → Puppeteer test runner → pass/fail
                                      → aggregate pass rate → vs 70.27% Gemini baseline
```

**Reward signal use:** FrontendBench Level 1-3 pass/fail outputs can supplement the AND-gate reward signal. A task that passes FrontendBench L3 (basic interactions) but fails L4 (complex interactions) provides a granular correctness signal for the DPO pair miner — richer than the current multi-axis LLM judge alone.

**Effort:** ~3 days (Puppeteer runner integration, task ID mapping, CI job)

**Dependencies:** FrontendBench data public release

**Files:**

- `atelier-eval/src/atelier_eval/adapters/frontendbench.py`
- `atelier-core/tests/eval/test_frontendbench.py`

---

### P1-02: Use UIBench pairwise comparison data as DPO ground truth

**What:** After P0-01, export UIBench pairwise matches where Atelier was involved (chosen vs rejected pairs) and ingest them into the BigQuery `dpo_preference_pairs` table.

**Why:** UIBench provides human-labeled preference pairs at zero annotation cost (the platform does the comparison work). These are the highest-quality DPO training signal possible — real human expert judgments about visual design quality, not LLM-simulated preferences.

**Effort:** ~4 hours (BigQuery ingestion script, format adapter for UIBench export format)

**Dependencies:** P0-01 (UIBench submission); UIBench data export format known

**Files:**

- `atelier-eval/src/atelier_eval/adapters/uibench_dpo_export.py` (new)

---

## P2 — Deferred (wrong stage or wrong fit)

### P2-01: VisualWebArena — permanent reject

**What:** No integration with VisualWebArena.

**Why (in detail):**

1. VisualWebArena tests web-agent navigation (add to cart, post a reply). Atelier generates UI designs. These are orthogonal tasks.
2. Infrastructure cost: Docker + 12GB GPU + 910 tasks × Playwright browser automation = significant compute spend with zero alignment to Atelier's Phase 1 Gate or DevPost rubric.
3. The confusion risk: If Atelier were integrated into VisualWebArena as a "web navigation" benchmark, it would test a capability Atelier doesn't claim, producing misleading results.
4. Anthropic's eval taxonomy (docs/eval/methodology.md): Atelier's code-based graders already use Playwright for visual diff and responsive snapshots — this is the correct level of browser integration for design evaluation.

**Refile as:** Never — strike from any future eval consideration.

---

## Cross-cutting: Reward signal calibration using UIBench

This is the most non-obvious 10× value in the UIBench analysis. Atelier's AND-gate reward currently validates against its own internal golden set (not yet frozen). UIBench provides an external calibration anchor:

```
UIBench pairwise result (human preference)
   ↓
Atelier's CompositeRewardEngine.evaluate() on the same pair
   ↓
Correlation check: does Atelier's AND-gate choose the same winner as humans?
```

If correlation is high (κ ≥ 0.7), Atelier can claim its automated reward signal is validated against human preference. If correlation is low, the reward needs recalibration before Phase 2 DPO runs — catching this early is worth far more than running more DPO iterations on misaligned reward.

**Effort:** ~1 day (compute CompositeRewardEngine scores on UIBench's public pairwise data, run correlation analysis)

**Where:** `atelier-eval/src/atelier_eval/calibration/uibench_correlation.py` (new)

---

## Priority ranking by 10× value + time-to-market

| Priority      | Action                                       | Time     | Value                                                    |
| ------------- | -------------------------------------------- | -------- | -------------------------------------------------------- |
| **P0-01**     | Submit Atelier to UIBench now                | 2h       | DevPost narrative + free DPO labels + market positioning |
| **P0-02**     | Monitor FrontendBench data + cite in DevPost | 0.5h now | Establishes eval credibility in submission               |
| **P1-01**     | Implement FrontendBench adapter on release   | 3d       | Automated functional eval with 90.54% human correlation  |
| **P1-02**     | Ingest UIBench pairs as DPO ground truth     | 4h       | Highest-quality human DPO labels at zero annotation cost |
| Cross-cutting | UIBench reward calibration correlation       | 1d       | Validates AND-gate reward signal before Phase 2 DPO runs |
| **REJECT**    | VisualWebArena                               | —        | Wrong domain; do not implement                           |

---

## Changes from Pass 1

Pass 2 reference fetch produced these material changes to the analysis:

1. **FrontendBench is larger and more interactive than anticipated.** The 148-task scale (vs. assumed smaller) and the 90.54% human-machine correlation (unusually high for automated eval) upgrade it from "useful future eval" to "highest-priority automated benchmark once data drops."

2. **UIBench competitor data is immediately actionable.** Knowing Orchids leads at 67.5% win rate and v0 sits at 22.24 μ gives Atelier a concrete competitive target. Submitting to UIBench now (before sprint end) could produce a leaderboard ranking to include in the DevPost submission — zero code required.

3. **VisualWebArena is a harder REJECT than suspected.** Not just "low fit" but actively misleading — running it would produce results for a capability Atelier doesn't claim, which could undermine credibility if cited without context.

4. **FrontendBench data is not yet released.** The "will be released soon" blocker prevents any immediate integration, but citing the benchmark in the DevPost (with Gemini 2.5 Pro at 70.27% as the baseline to beat) costs nothing and adds evaluation credibility.

---

## To enrich in further passes (if time permits)

- Contact ByteDance FrontendBench authors (hdzhu@smail.nju.edu.cn from paper) to request early access to dataset
- Check if UIBench has an API or public data export format for the pairwise match results
- Verify FrontendBench Puppeteer test format is compatible with Atelier's existing Playwright runner
- Check if FrontendBench's 5 difficulty levels map to Atelier's 8 DAG nodes or to WebGen-Bench's task categories
