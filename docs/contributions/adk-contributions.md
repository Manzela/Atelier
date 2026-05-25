# ADK Open Source Contributions

Contributions to the Google ADK ecosystem made during the development of Atelier.

## Proposed: DPO Preference Optimization Pipeline Example

**Target repository**: [google/adk-docs](https://github.com/google/adk-docs)

**Title**: Add example: DPO preference optimization pipeline using ADK evaluation + Vertex AI tuning

**Description**:

During the AI Agents Challenge 2026, we built a self-improving design agent using ADK. We found no documentation covering how to wire ADK's evaluation trajectory data into a Vertex AI PREFERENCE_TUNING job for continuous improvement.

This pattern — evaluate → extract pairs → tune → promote — is a production use case for agents that need to improve over time based on user feedback signals. The pattern works as follows:

1. ADK agent generates output and records full trajectory (tool calls, intermediate responses, final output)
2. Evaluation criteria (`tool_trajectory_avg_score`, `rubric_based_final_response_quality_v1`) score each trajectory
3. Accepted/rejected pairs are extracted from scored trajectories (DPO pair mining)
4. Pairs feed into a Vertex AI `PREFERENCE_TUNING` job via `google.genai` SDK
5. The tuned adapter is evaluated against a calibration seed dataset
6. If Cohen's κ ≥ threshold, the adapter is promoted and fed back into the agent

Proposing a new example section in the ADK docs covering this loop.

**Context**: [github.com/Manzela/atelier](https://github.com/Manzela/atelier)

## How to submit

```bash
# Option A: Open the issue via gh CLI
gh issue create \
  --repo google/adk-docs \
  --title "Add example: DPO preference optimization pipeline using ADK evaluation + Vertex AI tuning" \
  --body-file docs/contributions/adk-dpo-pipeline-issue.md

# Option B: Open directly in browser
# https://github.com/google/adk-docs/issues/new
```

After opening, record the issue URL below and add it to the DevPost submission under "ADK Contributions."

## Issue URL

<!-- Replace with actual URL after opening -->

`https://github.com/google/adk-docs/issues/___`
