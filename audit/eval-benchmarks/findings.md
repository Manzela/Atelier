# Findings: Frontend Evaluation Benchmarks vs Atelier

**Audit date:** 2026-05-24
**Auditor:** Claude (Principal Architect session)
**Target:** Three candidate evaluation frameworks for frontend/UI generation quality
**Stage:** Atelier Phase 1 (foundation complete), entering Phase 2 (10× mechanisms)

---

## 1. Current Atelier Evaluation State

### What exists (Pass 1 codebase scan)

| Component                    | Location                                    | Status                                                    |
| ---------------------------- | ------------------------------------------- | --------------------------------------------------------- |
| WebGen-Bench 50-task harness | `atelier-core/tests/eval/test_webgen_50.py` | **50 xfail** — harness wired but pipeline not connected   |
| Eval methodology doc         | `docs/eval/methodology.md`                  | Complete — 3 grader types                                 |
| atelier-eval package         | `atelier-eval/`                             | **Scaffold only** — README describes adapters, no src yet |
| FrontendBench adapter stub   | atelier-eval README only                    | Planned, not implemented                                  |
| Calibration golden set       | planned                                     | Not yet frozen (freezes D11 = 2026-05-29)                 |
| Adversarial held-out         | planned                                     | Not yet frozen                                            |

### Spec discrepancy flagged (R6 handoff)

The spec references "50/484 WebGen-Bench subset." **WebGen-Bench has 101 tasks, not 484.** The 484 is Design2Code (Stanford NAACL 2025). The 50-task subset is correctly drawn from the real 101. This is documented in `tests/eval/README.md` — no action needed.

### Current grader architecture (per `docs/eval/methodology.md`)

- **Layer 1 — Code-based (deterministic):** Lighthouse a11y/perf, axe-core, Playwright visual-diff, responsive snapshots, ADK tool-trajectory
- **Layer 2 — Model-based:** 5 specialized LLM judges (Brand, Copy, Motion, Token-fidelity, Cross-screen-coherence)
- **Layer 3 — Human:** Calibration golden set (100 tasks), adversarial (50 tasks), designer-in-residence sessions

### Reward signal gap analysis

The AND-gate composite reward (`composite.py`) uses:

- `EXTRINSIC_MARGIN_FLOOR = 0.15` — margin between chosen/rejected in LLM judge score
- `SWAP_STABILITY_FLOOR = 0.80` — anti-position-bias
- `MAX_AXIS_REGRESSION = 0.05` — per-axis regression guard
- `KAPPA_VS_GOLDEN_FLOOR = 0.70` — judge calibration against golden set

**Gap:** The reward signal is calibrated against Atelier's internal golden set (not yet frozen). No external benchmark validates whether Atelier's reward signal correlates with human preference or market-relevant quality signals.

---

## 2. Reference 1: FrontendBench (arXiv 2506.13832)

**Publication:** June 16, 2025, ByteDance research team (Hongda Zhu et al.)
**Dataset:** 148 prompt-test case pairs, 5 difficulty levels
**Data availability:** "Will be released soon" — **not yet public**

### Task format

HTML/CSS/JS code generation → automated interactive testing via **Puppeteer + Jest** in headless browser:

- DOM correctness
- Functional correctness via scripted user interactions
- Visual and UI behavior validation

### 5 difficulty levels

| Level | Type                                    | Count |
| ----- | --------------------------------------- | ----- |
| 1     | Simple static pages                     | 9     |
| 2     | Pages with dynamic effects              | 18    |
| 3     | Pages with basic interactions           | 90    |
| 4     | Pages with complex interactions         | 22    |
| 5     | Complex pages with complex interactions | 9     |

### Baseline model performance

| Model              | Pass Rate  |
| ------------------ | ---------- |
| o3-mini            | 83.11%     |
| DeepSeek-R1        | 75.00%     |
| **Gemini 2.5 Pro** | **70.27%** |
| DeepSeek-V3        | 66.89%     |

**Human-machine consistency:** 90.54% (very high — means automated eval is reliable as proxy for human judgment)

### Fit assessment

**DOMAIN MATCH: PERFECT.** Atelier generates interactive frontend code — FrontendBench evaluates exactly that, with the same interaction model (Puppeteer-based browser testing). The 5 difficulty levels map directly to Atelier's surface type variety.

**REWARD SIGNAL VALUE:** Gemini 2.5 Pro at 70.27% gives Atelier a concrete calibration target. If Atelier's generated code scores higher than 70.27% on FrontendBench, that's a quantifiable claim over the best Gemini model in a head-to-head comparison — the strongest possible DevPost narrative.

**BLOCKER:** Data not yet released. Cannot integrate until dataset is public.

---

## 3. Reference 2: VisualWebArena

**Source:** github.com/web-arena-x/visualwebarena
**Tasks:** 910 tasks (233 with human trajectories)
**Infrastructure:** Docker + Playwright + browser automation, 12GB GPU for captioning

### Task format

Multimodal web agents interacting with **live browser environments** (e-commerce, classifieds, Reddit-like) via Playwright. Agents navigate real websites, handle visual grounding, execute multi-step actions. Not code generation.

### Fit assessment

**DOMAIN MATCH: NONE.** VisualWebArena tests whether an agent can **navigate a website** (add to cart, find a product, post a reply). Atelier **generates** UI designs and frontend code. These are orthogonal problems.

Running VisualWebArena would answer: "Can Atelier use a website?" — not "Can Atelier design one?"

**Additional blockers:**

- Requires Docker + 12GB GPU + live browser environments
- 910 tasks × browser automation = days of compute per run
- No leaderboard; requires full infrastructure setup
- Fundamentally wrong evaluation paradigm for a design generation agent

---

## 4. Reference 3: UIBench (uibench.ai)

**Format:** Crowdsourced pairwise blind comparisons via TrueSkill rating
**Matches collected:** 4,047+
**Competing tools ranked:** Orchids (30.08 μ, 67.5% win rate), Figma Make, Lovable, **v0** (22.24 μ), Replit

### Task format

Human expert voters choose between two AI-generated UI outputs in blind pairwise comparison. Not automated. Not code-based. Focuses purely on **visual/aesthetic design quality**.

### Current leaderboard (top 5)

| Rank | Tool       | TrueSkill μ | Win Rate |
| ---- | ---------- | ----------- | -------- |
| 1    | Orchids    | 30.08       | 67.5%    |
| 2    | Figma Make | 27.46       | —        |
| 3    | Lovable    | 27.14       | —        |
| 4    | v0         | 22.24       | —        |
| 5    | Replit     | 20.95       | —        |

### Fit assessment

**DOMAIN MATCH: PARTIAL — visual quality only, not functional.**

UIBench evaluates the exact thing Atelier's "Visual" and "Brand" LLM judges score — but via human experts, not LLMs. This is Atelier's **Layer 3 human grader** equivalent.

**Unique value:** UIBench is a direct market signal. Orchids at 67.5% win rate is the "to beat" number. Submitting Atelier to UIBench would produce a defensible, third-party-verified human preference ranking against direct competitors.

**Critical gap it addresses:** Atelier has no external validation that its multi-axis LLM judge correlates with actual human visual preference. UIBench's blind human comparisons could calibrate Atelier's reward signal against real human preference data.

**NOT useful for:** Automated CI eval, code generation quality, functional correctness, reward signal computation, DPO pair mining.

---

## 5. Benchmark Comparison Matrix

| Dimension                   | WebGen-Bench    | FrontendBench          | VisualWebArena | UIBench             |
| --------------------------- | --------------- | ---------------------- | -------------- | ------------------- |
| **Domain fit**              | High            | **Perfect**            | None           | Partial             |
| **Automated**               | Yes             | Yes                    | Yes            | No                  |
| **CI-usable**               | Yes (xfail now) | Yes (when released)    | No             | No                  |
| **Interactive behavior**    | No              | **Yes**                | Yes            | No                  |
| **Design quality**          | No              | Partial                | No             | **Yes**             |
| **Code generation**         | Yes             | **Yes**                | No             | No                  |
| **Human correlation**       | Unknown         | **90.54%**             | N/A            | Ground truth        |
| **Data available**          | Yes             | **Not yet**            | Yes            | Via participation   |
| **Cost per run**            | Low             | Low                    | Very high      | N/A (submit only)   |
| **Competitor scores known** | No              | Yes (Gemini 70.27%)    | N/A            | Yes (Orchids 67.5%) |
| **DevPost narrative value** | Medium          | **Very high**          | None           | **Very high**       |
| **Already planned**         | Yes             | **Yes (adapter stub)** | No             | No                  |
| **Phase fit**               | Phase 1 Gate    | Phase 2+               | Never          | Now + ongoing       |
