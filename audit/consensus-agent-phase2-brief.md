# ConsensusAgent Phase 2 — LLM Judge Upgrade Brief

## Task for Claude Opus 4.7 Max

You are implementing the **Phase 2 upgrade** of Atelier's ConsensusAgent (N3d).

## Current State (Phase 1 — COMPLETE, 709 lines, 249 tests passing)

The Phase 1 ConsensusAgent at `atelier-core/src/atelier/nodes/consensus.py` is a
fully-functional deterministic-heuristic implementation with:

- 5 D-O-R-A-V axis scorers (Brand, Originality, Relevance, Accessibility, Visual-Clarity)
- Anti-bias shuffled evaluation order (via `anti_bias.py`)
- Constitution soft-penalty enforcement
- AxisWeights-driven composite scoring
- ConsensusEvaluation frozen dataclass output
- Integration with JudgeVote Pydantic model, TrajectoryRecord, model_registry

The Phase 1 design was **intentionally deterministic-first** so the pipeline
(Fixer, Orchestrator, trajectory logging) could integrate against a stable contract.

## Phase 2 Upgrade Goal

Replace each `_score_*` deterministic helper with a **Vertex AI LLM judge** call while:

1. Keeping the surrounding plumbing (anti-bias, composite weighting, constitution) unchanged
2. Using the `_AXIS_SCORERS` dispatch table for drop-in swapping
3. Routing via `JUDGE_MODEL_CONFIG` from `model_registry.py`
4. Emitting real Bayesian confidence intervals from token-level logits
5. Recording full provenance (DEMAS-D) per vote

## Key Architecture Decisions

Per the research documents:

### From Research (C4 — Intrinsic Reward Engine):

- Each judge emits `JudgeVote(score: float, confidence_interval: tuple)`
- Composite reward = Bayesian-weighted vote
- Write reward to `TrajectoryRecord` for DPO extraction
- Dense, multi-signal reward (not sparse binary)

### From Research (C6 — Consensus ↔ Episodic Split):

- Read-only core (constitution, design-system.lock) vs read-write periphery (BriefSpec)
- Docker volume enforcement: consensus files mounted `read_only: true`

### From Research (C7 — Metacognitive Governor):

- MAPE-K loop: Monitor → Analyze → Plan → Execute → Knowledge
- PRD §21 failure trichotomy: fail-loud / fail-soft / self-heal
- Iteration caps, budget caps, panic exits

### From PRD §6.3 N3d:

- 5 specialized rubric judges per D-O-R-A-V axis
- BriefSpec-conditional axis weighting via N15 (MJG)
- Constitution enforcement via N6 (CSC-D)
- Convergence check: `ConsensusResult.decision == CONVERGED`

### From PRD §6.4 (Judge Rubric):

- Per-axis floors (not just composite threshold)
- Brand: design token discipline, color palette
- Originality: CSS property/selector variety beyond templates
- Relevance: content-to-markup density, semantic accuracy
- Accessibility: WCAG AA, semantic HTML, ARIA
- Visual-clarity: typography hierarchy, spacing, whitespace

## Constraints

1. **Google-native only** (ADR 0006): Vertex AI for LLM calls, Cloud Trace for spans
2. **Model**: `gemini-2.5-flash-preview-05-20` pinned (ADR 0014)
3. **Failure trichotomy**: Single judge timeout → fail-soft (partial consensus + flag)
4. **OTel spans**: Each judge call gets its own span with `gen_ai.system=atelier`
5. **No external deps**: Use google-cloud-aiplatform SDK only
6. **Tests**: Must maintain backward compatibility with Phase 1 test suite
7. **DPO readiness**: JudgeVote output must be TrajectoryRecord-compatible

## Existing Files to Read (CRITICAL — read these before writing ANY code)

1. `atelier-core/src/atelier/nodes/consensus.py` — current 709-line implementation
2. `atelier-core/src/atelier/nodes/anti_bias.py` — anti-bias shuffling
3. `atelier-core/src/atelier/models/axis_weights.py` — weight computation
4. `atelier-core/src/atelier/models/constitution_registry.py` — constitution loading
5. `atelier-core/src/atelier/models/data_contracts.py` — JudgeVote, CandidateUI, ConsensusResult
6. `atelier-core/src/atelier/models/model_registry.py` — JUDGE_MODEL_CONFIG
7. `atelier-core/src/atelier/models/enums.py` — JudgeAxis enum
8. `atelier-core/src/atelier/observability/spans.py` — OTel span helpers
9. `consensus/axis_weights_heuristic.yaml` — surface-type × axis weight matrix
10. `consensus/constitution-apple-grade/` — 7 principle markdown files + index.json
11. `consensus/constitutions/apple-grade.yaml` — YAML constitution definition

## What to Build

### 1. LLM Judge Module (`atelier-core/src/atelier/nodes/llm_judge.py`)

- Abstract `LLMJudge` base class
- 5 concrete implementations (BrandJudge, OriginalityJudge, etc.)
- Each uses structured output (JSON mode) with Gemini 2.5 Flash
- Prompt templates grounded in constitution principles
- Bayesian CI extraction from response metadata
- OTel span per judge call
- Timeout handling with fail-soft fallback to Phase 1 heuristic

### 2. Judge Prompt Templates

- System prompts per axis referencing constitution principles
- User prompts with candidate artifacts (HTML + CSS)
- Structured output schema enforcing score + reasoning + provenance
- Anti-hallucination: require specific evidence citations from candidate code

### 3. Consensus Upgrade Path

- `_AXIS_SCORERS` dispatch table gets swapped entries
- Configuration flag: `ATELIER_JUDGE_MODE=heuristic|llm|hybrid`
- Hybrid mode: run both, log disagreements, use LLM score
- Backward-compatible: Phase 1 tests must still pass

### 4. Tests

- Mock Vertex AI responses for unit tests
- Integration test with real model (marked `@pytest.mark.external`)
- Calibration tests: LLM scores should correlate >0.7 with heuristic scores

## Research Context

Read these two documents for deep architectural context:

- `/Users/danielmanzela/.gemini/antigravity-ide/brain/e9962ddd-ddea-4979-a1d2-fa00102a9019/autonomous_agent_audit_and_checklist.md`
- `/Users/danielmanzela/Downloads/autonomous_agent_architecture_research.md`

## Quality Bar

This is for a **Google Hackathon competition** (deadline June 5). Judges are
internal Googlers. Technical Implementation is 30% of the score. The ConsensusAgent
is the heart of Atelier's 10× thesis — it must be:

- Production-grade (not a demo)
- Well-documented (every function has a docstring)
- Tested (≥20 new tests)
- Observable (OTel spans on every LLM call)
- Fail-safe (no unhandled exceptions crash the pipeline)

Think deep. Take your time. No false positives, no false negatives, no hallucinations.
