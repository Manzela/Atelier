"""Tests for OTel span attribute schema (FA-007) and model registry (FA-016)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from atelier.models.model_registry import (
    ALL_MODEL_IDS,
    ALL_REGIONS,
    JUDGE_MODEL_CONFIG,
    NODE_MODEL_CONFIG,
    ModelCapability,
)
from atelier.observability.spans import (
    MANDATORY_ATTRS,
    set_atelier_span_attrs,
    validate_span_attrs,
)

# ---------------------------------------------------------------------------
# Model Registry Tests (FA-016)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModelRegistry:
    """Verify model registry completeness and correctness."""

    def test_all_dorav_axes_have_models(self) -> None:
        expected_axes = {"brand", "originality", "relevance", "accessibility", "visual_clarity"}
        assert set(JUDGE_MODEL_CONFIG.keys()) == expected_axes

    def test_all_node_types_have_models(self) -> None:
        expected_nodes = {"n3a_generator", "n3b_copy_editor", "n3e_fixer"}
        assert set(NODE_MODEL_CONFIG.keys()) == expected_nodes

    def test_design_judge_has_vision(self) -> None:
        spec = JUDGE_MODEL_CONFIG["brand"]
        assert ModelCapability.VISION in spec.capabilities

    def test_originality_judge_has_thinking(self) -> None:
        spec = JUDGE_MODEL_CONFIG["originality"]
        assert ModelCapability.THINKING in spec.capabilities
        assert spec.thinking_budget is not None

    def test_relevance_judge_has_grounding(self) -> None:
        spec = JUDGE_MODEL_CONFIG["relevance"]
        assert ModelCapability.GROUNDING in spec.capabilities

    def test_generator_has_code_capability(self) -> None:
        spec = NODE_MODEL_CONFIG["n3a_generator"]
        assert ModelCapability.CODE in spec.capabilities

    def test_all_model_ids_non_empty(self) -> None:
        assert len(ALL_MODEL_IDS) > 0
        for model_id in ALL_MODEL_IDS:
            assert len(model_id) > 0

    def test_all_regions_include_primary(self) -> None:
        assert "us-central1" in ALL_REGIONS

    def test_model_spec_frozen(self) -> None:
        spec = JUDGE_MODEL_CONFIG["brand"]
        with pytest.raises(AttributeError):
            spec.model_id = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# OTel Span Attribute Tests (FA-007)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSpanAttributes:
    """Verify span attribute schema completeness."""

    def test_mandatory_attrs_count(self) -> None:
        assert len(MANDATORY_ATTRS) == 15

    def test_validate_all_present(self) -> None:
        attrs = dict.fromkeys(MANDATORY_ATTRS, "")
        missing = validate_span_attrs(attrs)
        assert missing == []

    def test_validate_missing_attrs(self) -> None:
        attrs = {"atelier.tenant_id": "test"}
        missing = validate_span_attrs(attrs)
        assert len(missing) == 14

    def test_set_atelier_span_attrs_sets_all_mandatory(self) -> None:
        span = MagicMock()
        set_atelier_span_attrs(
            span,
            tenant_id="tnt_1",
            user_id="usr_1",
            project_id="prj_1",
            session_id="sess_1",
            node_name="n3a_generator",
            surface_id="srf_1",
            iteration=0,
            candidate_id="cand_1",
            campaign_id="camp_1",
            model="gemini-2.5-flash",
            input_tokens=100,
            output_tokens=200,
            judge_axis="brand",
            composite_score=0.95,
        )
        assert span.set_attribute.call_count == 15

    def test_optional_attrs_not_set_when_none(self) -> None:
        span = MagicMock()
        set_atelier_span_attrs(span)
        # Only 15 mandatory calls, no optional ones
        assert span.set_attribute.call_count == 15

    def test_optional_attrs_set_when_provided(self) -> None:
        span = MagicMock()
        set_atelier_span_attrs(
            span,
            cost_usd=0.02,
            gate_axis="lighthouse_a11y",
            gate_decision="pass",
            mutation_op="palette_swap",
            convergence_bar="production",
        )
        # 15 mandatory + 5 optional
        assert span.set_attribute.call_count == 20
