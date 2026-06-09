# RFC: Autonomous Design Convergence Specification (v1.0)

- **Status**: Draft / RFC
- **Date**: 2026-06-08
- **Authors**: Atelier Core Team
- **Implementation**: `atelier-core/src/atelier/orchestrator/runner.py`

## 1. Introduction

This document specifies the **Convergence Protocol** for autonomous design agents. While standard generation agents terminate after a single model pass, a **Convergent Agent** executes a closed-loop cycle of generation, verification, and refinement until a predefined quality threshold is met.

## 2. The Convergence Loop

A compliant agent MUST implement the following 8-node Directed Acyclic Graph (DAG) for each design surface:

1. **N1: Brief Parser** (Probabilistic) - Extracts intent into an immutable `BriefSpec`.
2. **N2: Source Resolver** (Deterministic) - Resolves project context and design tokens.
3. **N3: EvoDesign Loop** (Iterative):
   - **N3a: Generator** (K=6) - Produces parallel design hypotheses.
   - **N3b: Constitutional Self-Critique (CSC-D)** - Pre-flight heuristic filter.
   - **N3c: Deterministic Gates** - Hard verification (Lighthouse, axe-core, W3C).
   - **N3d: Consensus Judge (D-O-R-A-V)** - Multi-axis rubric scoring.
   - **N3e: Hebbian Fixer** - Prompt mutation based on failures.
4. **N4: Final Validator** - Selects the best candidate and renders to A2UI.

## 3. Convergence Criteria (κ)

Convergence is defined by a composite score (κ) derived from the **D-O-R-A-V** rubric.

### 3.1 D-O-R-A-V Rubric Axes

| Axis                   | Metric                               | Floor |
| :--------------------- | :----------------------------------- | :---- |
| **Design (D)**         | Adherence to tokens and brand guides | 0.70  |
| **Originality (O)**    | Distinction from generic templates   | 0.60  |
| **Relevance (R)**      | Alignment with the BriefSpec         | 0.70  |
| **Accessibility (A)**  | axe-core (0 errors) + Judge score    | 0.80  |
| **Visual Clarity (V)** | Hierarchy and cognitive load         | 0.70  |

### 3.2 Thresholds

- **κ ≥ 0.70**: Converged. The design is production-ready.
- **κ < 0.70**: Non-converged. Requires further iteration or human-in-the-loop intervention.

## 4. Trajectory Schema

Every convergence attempt MUST be recorded as a `TrajectoryRecord`.

```json
{
  "session_id": "uuid",
  "surface_id": "string",
  "iterations": [
    {
      "iteration_num": 1,
      "candidates": [
        {
          "candidate_id": "c1",
          "gate_outcome": { "passed": true, "failures": [] },
          "judge_votes": { "D": 0.8, "O": 0.7, "R": 0.9, "A": 0.9, "V": 0.8 },
          "composite_score": 0.82
        }
      ],
      "best_candidate_id": "c1",
      "fixer_mutation": null
    }
  ],
  "final_outcome": "converged",
  "tokens_consumed": 12400
}
```

## 5. Benchmarking Protocol

Agents implementing this spec SHOULD be evaluated using the **Open Eval Adapters Library**, supporting:

- **WebGen-Bench** (Layout/Functional)
- **Design2Code** (Visual Fidelity)
- **Web2Code** (Vision-to-Code)
- **ScreenSpot** (GUI Grounding)
- **FrontendBench** (Code Quality)

## 6. Implementation Reference

Atelier serves as the reference implementation for this specification. The convergence logic is encapsulated in `atelier.orchestrator.runner.Runner`.
