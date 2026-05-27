# ADK Evaluation Tests

Golden evaluation set for Atelier using the ADK `EvalSet` format.

## Files

| File               | Purpose                                      |
| ------------------ | -------------------------------------------- |
| `golden_set.json`  | 5 evaluation scenarios in ADK EvalSet format |
| `test_config.json` | Pass/fail thresholds for eval criteria       |

## Running evaluations

### ADK Web UI

```bash
adk web --eval-set atelier-core/tests/eval/golden_set.json
```

Open the Eval tab in the ADK web UI to run all 5 scenarios interactively.

### Programmatic (pytest)

```bash
pytest atelier-core/tests/eval/ -v
```

### agents-cli

```bash
agents-cli eval run \
  --eval-set atelier-core/tests/eval/golden_set.json \
  --agent examples/agents-cli-scaffold/agent.py
```

## Evaluation criteria

| Criterion                                | Threshold | Description                                                 |
| ---------------------------------------- | --------- | ----------------------------------------------------------- |
| `tool_trajectory_avg_score`              | ≥ 0.70    | Exact-match score for tool call sequence (Stitch MCP calls) |
| `rubric_based_final_response_quality_v1` | ≥ 0.65    | LLM-judged quality against the reference rubric             |
| `multi_turn_trajectory_quality_v1`       | ≥ 0.65    | Multi-turn conversation quality assessment                  |

## Scenarios

1. **saas-dashboard-dark** — SaaS analytics dashboard with dark theme, KPI cards, and trend chart
2. **landing-page-saas** — AI code review tool landing page with hero section and CTA
3. **mobile-onboarding** — 3-step fintech onboarding flow (account, KYC, funding)
4. **e-commerce-product** — Luxury skincare product detail page with gallery and reviews
5. **admin-settings** — B2B SaaS admin panel with billing, team, API keys, and notifications

Each scenario validates that Atelier calls `stitch_generate_screen_from_text` with the correct prompt context and produces output matching the reference rubric.
