During the AI Agents Challenge 2026, we built a self-improving design agent using ADK 2.0. We found no documentation covering how to wire ADK's evaluation trajectory data into a Vertex AI `PREFERENCE_TUNING` job for continuous improvement.

## The pattern

This evaluate → extract pairs → tune → promote loop is a production use case for agents that need to improve over time:

1. ADK agent generates output and records full trajectory (tool calls, intermediate responses, final output)
2. Evaluation criteria (`tool_trajectory_avg_score`, `rubric_based_final_response_quality_v1`) score each trajectory
3. Accepted/rejected pairs are extracted from scored trajectories (DPO pair mining)
4. Pairs feed into a Vertex AI `PREFERENCE_TUNING` job via `google.genai` SDK
5. The tuned adapter is evaluated against a calibration seed dataset
6. If the adapter passes evaluation, it's promoted and fed back into the agent pipeline

## What we'd like to see

A new example in the ADK docs covering:

- How to capture evaluation scores from `EvalSet` runs programmatically
- How to structure preference pairs for Vertex AI tuning input
- How to promote a tuned adapter and inject it back into an ADK agent
- Example code showing the full loop end-to-end

## Context

We implemented this pattern in [Atelier](https://github.com/Manzela/atelier) — an autonomous design agent that uses Stitch MCP for generation and ADK for orchestration, evaluation, and session management. The self-improving flywheel is the core differentiator, and ADK's evaluation framework provided the foundation.

## Related

- [ADK Evaluation docs](https://google.github.io/adk-docs/evaluate/)
- [Vertex AI PREFERENCE_TUNING](https://cloud.google.com/vertex-ai/generative-ai/docs/model-garden/tune-models#preference-tuning)
