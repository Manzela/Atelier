"""Tests for the PlannerAgent and PlanStep model.

Covers:
    1. PlanStep schema validation (weight-sum constraint)
    2. PlanStep defaults (safe for pipeline)
    3. PlannerAgent.plan() with mock LLM returning structured JSON
    4. PlannerAgent.plan() fail-soft on LLM error
    5. Narrow brief produces should_run_wrai=False (via mock)
    6. Creative brief produces ensemble_k>=3 (via mock)
    7. Accessibility brief produces high accessibility weight (via mock)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from atelier.orchestrator.planner import PlannerAgent, PlanStep

# ---------------------------------------------------------------------------
# PlanStep model tests
# ---------------------------------------------------------------------------


def test_plan_step_defaults() -> None:
    """Default PlanStep has uniform weights summing to 1.0."""
    plan = PlanStep()
    assert plan.should_run_wrai is True
    assert plan.ensemble_k == 2
    assert abs(sum(plan.axis_weights.values()) - 1.0) < 0.01
    assert plan.constitution is None
    assert plan.gate_axes_to_skip == []
    assert plan.reasoning == ""


def test_plan_step_rejects_invalid_weight_sum() -> None:
    """Weights must sum to approximately 1.0."""
    with pytest.raises(ValueError, match="axis_weights sum"):
        PlanStep(axis_weights={"brand": 0.5, "originality": 0.5, "relevance": 0.5})


def test_plan_step_accepts_near_one_weights() -> None:
    """Weights within 0.05 tolerance of 1.0 are accepted."""
    plan = PlanStep(
        axis_weights={
            "brand": 0.21,
            "originality": 0.21,
            "relevance": 0.19,
            "accessibility": 0.19,
            "visual_clarity": 0.21,
        }
    )
    total = sum(plan.axis_weights.values())
    assert abs(total - 1.0) <= 0.05


def test_plan_step_constitution_values() -> None:
    """Constitution accepts valid values and None."""
    assert PlanStep(constitution="brutalist").constitution == "brutalist"
    assert PlanStep(constitution="apple-grade").constitution == "apple-grade"
    assert PlanStep(constitution=None).constitution is None


def test_plan_step_frozen() -> None:
    """PlanStep is immutable."""
    plan = PlanStep()
    with pytest.raises(Exception):
        plan.should_run_wrai = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PlannerAgent tests — mock LLM responses
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_planner_narrow_brief_returns_plan() -> None:
    """Mock LLM returns a PlanStep for a narrow brief."""
    narrow_plan_json = '{"should_run_wrai": false, "ensemble_k": 1, "axis_weights": {"brand": 0.2, "originality": 0.2, "relevance": 0.2, "accessibility": 0.2, "visual_clarity": 0.2}, "constitution": null, "gate_axes_to_skip": [], "reasoning": "Narrow single-component request; skip WRAI."}'

    with patch.object(PlannerAgent, "_call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = narrow_plan_json
        planner = PlannerAgent()
        plan = await planner.plan("Make a button blue")
        assert plan.should_run_wrai is False
        assert plan.ensemble_k == 1
        assert plan.reasoning == "Narrow single-component request; skip WRAI."


@pytest.mark.anyio
async def test_planner_creative_brief_returns_expanded_plan() -> None:
    """Mock LLM returns expanded plan for ambiguous creative brief."""
    creative_plan_json = '{"should_run_wrai": true, "ensemble_k": 3, "axis_weights": {"brand": 0.15, "originality": 0.35, "relevance": 0.15, "accessibility": 0.15, "visual_clarity": 0.2}, "constitution": "brutalist", "gate_axes_to_skip": [], "reasoning": "Ambiguous creative brief needs research + larger ensemble."}'

    with patch.object(PlannerAgent, "_call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = creative_plan_json
        planner = PlannerAgent()
        plan = await planner.plan("Design a brutalist landing page for a Bauhaus revival movement")
        assert plan.should_run_wrai is True
        assert plan.ensemble_k >= 3
        assert plan.constitution == "brutalist"
        assert plan.axis_weights["originality"] >= 0.3


@pytest.mark.anyio
async def test_planner_accessibility_brief_boosts_weight() -> None:
    """Mock LLM boosts accessibility weight for accessibility-focused brief."""
    a11y_plan_json = '{"should_run_wrai": true, "ensemble_k": 2, "axis_weights": {"brand": 0.1, "originality": 0.1, "relevance": 0.2, "accessibility": 0.4, "visual_clarity": 0.2}, "constitution": null, "gate_axes_to_skip": [], "reasoning": "Accessibility-focused brief; boost a11y weight."}'

    with patch.object(PlannerAgent, "_call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = a11y_plan_json
        planner = PlannerAgent()
        plan = await planner.plan(
            "Build a fully accessible form for visually impaired users with screen reader support"
        )
        assert plan.axis_weights["accessibility"] >= 0.3


@pytest.mark.anyio
async def test_planner_fails_soft_on_llm_error() -> None:
    """PlannerAgent returns default PlanStep on any exception."""
    with patch.object(PlannerAgent, "_call_llm", new_callable=AsyncMock) as mock:
        mock.side_effect = RuntimeError("Model unavailable")
        planner = PlannerAgent()
        plan = await planner.plan("Design a page")
        # Fail-soft: should return defaults
        assert isinstance(plan, PlanStep)
        assert plan.should_run_wrai is True  # default
        assert plan.ensemble_k == 2  # default


@pytest.mark.anyio
async def test_planner_fails_soft_on_invalid_json() -> None:
    """PlannerAgent returns default PlanStep on invalid JSON response."""
    with patch.object(PlannerAgent, "_call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = "not valid json {{"
        planner = PlannerAgent()
        plan = await planner.plan("Design a page with lots of content")
        # Fail-soft: should return defaults
        assert isinstance(plan, PlanStep)
        assert plan.should_run_wrai is True


@pytest.mark.anyio
async def test_planner_returns_plan_step_object_directly() -> None:
    """When _call_llm returns a PlanStep object, use it directly."""
    direct_plan = PlanStep(
        should_run_wrai=False,
        ensemble_k=1,
        reasoning="Direct object return test",
    )
    with patch.object(PlannerAgent, "_call_llm", new_callable=AsyncMock) as mock:
        mock.return_value = direct_plan
        planner = PlannerAgent()
        plan = await planner.plan("Simple button tweak")
        assert plan is direct_plan
