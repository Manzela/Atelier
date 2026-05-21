"""Tests for BriefSpec data contract (PIP layer output).

Per ADR 0004: BriefSpec is immutable post-approval.
Per CLAUDE.md: schema_version on every model.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from atelier.intake.brief_spec import (
    BriefSpec,
    CampaignScope,
    ComplianceLevel,
    ConvergenceBar,
    IntakeAnswer,
    StackChoice,
    VisualRegister,
)
from pydantic import ValidationError


def _make_brief_spec(**overrides: object) -> BriefSpec:
    """Factory for valid BriefSpec instances."""
    defaults: dict[str, object] = {
        "spec_id": uuid4(),
        "tenant_id": "tnt_test",
        "project_id": "prj_test",
        "intent": "redesign hero section",
        "visual_register": VisualRegister.EDITORIAL,
        "stack": StackChoice.VANILLA_HTML,
        "design_system_source": None,
        "compliance_level": ComplianceLevel.WCAG_AA,
        "convergence_bar": ConvergenceBar.PRODUCTION,
        "reference_artifacts": [],
        "campaign_scope": None,
        "intake_transcript": [],
        "approved_at": datetime.now(UTC),
        "approved_by_user_id": "usr_test",
    }
    defaults.update(overrides)
    return BriefSpec(**defaults)  # type: ignore[arg-type]


@pytest.mark.unit
class TestBriefSpecFrozen:
    """BriefSpec is immutable post-approval (per ADR 0004)."""

    def test_mutation_raises(self) -> None:
        spec = _make_brief_spec()
        with pytest.raises(ValidationError):
            spec.intent = "different intent"  # type: ignore[misc]

    def test_different_specs_are_unequal(self) -> None:
        spec_a = _make_brief_spec(intent="intent A")
        spec_b = _make_brief_spec(intent="intent B")
        assert spec_a != spec_b


@pytest.mark.unit
class TestBriefSpecSchema:
    """Every Pydantic model carries schema_version per CLAUDE.md invariant."""

    def test_schema_version_defaults_to_1(self) -> None:
        spec = _make_brief_spec()
        assert spec.schema_version == 1

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra_forbidden"):
            _make_brief_spec(unknown_field="boom")  # type: ignore[arg-type]


@pytest.mark.unit
class TestBriefSpecEnums:
    """Enum values are correct strings."""

    def test_visual_register_values(self) -> None:
        assert VisualRegister.EDITORIAL.value == "editorial"
        assert VisualRegister.DENSE_DATA.value == "dense-data"
        assert VisualRegister.BRUTALIST.value == "brutalist"

    def test_compliance_levels(self) -> None:
        assert ComplianceLevel.NONE.value == "none"
        assert ComplianceLevel.WCAG_AA.value == "wcag-aa"
        assert ComplianceLevel.WCAG_AAA.value == "wcag-aaa"
        assert ComplianceLevel.REGULATORY.value == "regulatory"

    def test_convergence_bars(self) -> None:
        assert ConvergenceBar.SHIP_IT.value == "ship-it"
        assert ConvergenceBar.PRODUCTION.value == "production"
        assert ConvergenceBar.PERFECTIONIST.value == "perfectionist"


@pytest.mark.unit
class TestBriefSpecCampaignScope:
    """CampaignScope is optional and frozen."""

    def test_campaign_scope_none_for_atomic(self) -> None:
        spec = _make_brief_spec(campaign_scope=None)
        assert spec.campaign_scope is None

    def test_campaign_scope_set_for_campaign(self) -> None:
        scope = CampaignScope(
            surface_count_estimate=12,
            timeline="this-week",
            budget_per_session_usd=0.50,
            budget_per_campaign_usd=6.0,
            failure_policy="best-effort-and-flag",
        )
        spec = _make_brief_spec(campaign_scope=scope)
        assert spec.campaign_scope is not None
        assert spec.campaign_scope.surface_count_estimate == 12

    def test_campaign_scope_is_frozen(self) -> None:
        scope = CampaignScope(
            surface_count_estimate=12,
            timeline="today",
            budget_per_session_usd=0.50,
            budget_per_campaign_usd=6.0,
            failure_policy="skip",
        )
        with pytest.raises(ValidationError):
            scope.surface_count_estimate = 99  # type: ignore[misc]


@pytest.mark.unit
class TestIntakeAnswer:
    """IntakeAnswer is frozen with schema_version."""

    def test_intake_answer_frozen(self) -> None:
        answer = IntakeAnswer(
            question_id="q1",
            answer_text="A SaaS dashboard for analytics",
        )
        with pytest.raises(ValidationError):
            answer.answer_text = "changed"  # type: ignore[misc]

    def test_intake_answer_schema_version(self) -> None:
        answer = IntakeAnswer(
            question_id="q1",
            answer_text="test",
        )
        assert answer.schema_version == 1


@pytest.mark.unit
class TestBriefSpecSerialization:
    """BriefSpec serializes to/from JSON correctly."""

    def test_roundtrip_json(self) -> None:
        spec = _make_brief_spec()
        json_str = spec.model_dump_json()
        restored = BriefSpec.model_validate_json(json_str)
        assert restored == spec
        assert restored.intent == spec.intent
        assert restored.visual_register == spec.visual_register
