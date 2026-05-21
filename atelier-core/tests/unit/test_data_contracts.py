"""Tests for data contracts (PRD §9).

Validates: frozen immutability, schema versioning, extra field rejection,
JSON roundtrip, enum correctness, and field validators for all 10 models.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from atelier.models.data_contracts import (
    AtelierDescriptor,
    CandidateUI,
    CoherenceVerdict,
    ConsensusResult,
    GateOutcome,
    JudgeVote,
    SurfaceManifest,
    SurfaceState,
    TenantContext,
    TrajectoryRecord,
)
from atelier.models.enums import (
    ConsensusDecision,
    GateAxis,
    GateDecision,
    JudgeAxis,
    MutationOp,
    SurfaceType,
    UserSignal,
)
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Expected enum counts (from PRD §9 — documented explicitly to satisfy PLR2004)
# ---------------------------------------------------------------------------

EXPECTED_GATE_AXES = 7
EXPECTED_JUDGE_AXES = 5
EXPECTED_MUTATION_OPS = 6


# ---------------------------------------------------------------------------
# Factories — reusable builders for valid instances
# ---------------------------------------------------------------------------


def _make_tenant_context(**overrides: object) -> TenantContext:
    defaults: dict[str, object] = {
        "tenant_id": "tnt_test",
        "user_id": "usr_test",
        "project_id": "prj_test",
        "cost_budget_usd": Decimal("100.00"),
        "cost_consumed_usd": Decimal("5.50"),
    }
    defaults.update(overrides)
    return TenantContext(**defaults)  # type: ignore[arg-type]


def _make_surface_state(**overrides: object) -> SurfaceState:
    defaults: dict[str, object] = {
        "surface_id": uuid4(),
        "name": "homepage-hero",
        "type": SurfaceType.PAGE,
        "brief": "A hero section with a call-to-action button",
    }
    defaults.update(overrides)
    return SurfaceState(**defaults)  # type: ignore[arg-type]


def _make_candidate_ui(**overrides: object) -> CandidateUI:
    defaults: dict[str, object] = {
        "candidate_id": uuid4(),
        "surface_id": uuid4(),
        "iteration": 0,
        "artifacts": {"index.html": "<!DOCTYPE html>", "main.css": "body {}"},
    }
    defaults.update(overrides)
    return CandidateUI(**defaults)  # type: ignore[arg-type]


def _make_gate_outcome(**overrides: object) -> GateOutcome:
    defaults: dict[str, object] = {
        "candidate_id": uuid4(),
        "axis": GateAxis.LIGHTHOUSE_A11Y,
        "decision": GateDecision.PASS,
        "score": 95.0,
        "diagnostic": "Lighthouse accessibility score: 95/100",
    }
    defaults.update(overrides)
    return GateOutcome(**defaults)  # type: ignore[arg-type]


def _make_judge_vote(**overrides: object) -> JudgeVote:
    defaults: dict[str, object] = {
        "candidate_id": uuid4(),
        "judge_axis": JudgeAxis.BRAND,
        "score": 0.87,
        "confidence_interval": (0.82, 0.92),
        "reasoning": "Strong brand alignment with design system tokens.",
        "provenance_vars": ["color_primary", "font_heading"],
        "judge_model": "gemini-3-flash",
    }
    defaults.update(overrides)
    return JudgeVote(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests — organized by model
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTenantContext:
    """TenantContext uses Decimal for financial fields."""

    def test_frozen(self) -> None:
        ctx = _make_tenant_context()
        with pytest.raises(ValidationError):
            ctx.tenant_id = "changed"  # type: ignore[misc]

    def test_schema_version(self) -> None:
        ctx = _make_tenant_context()
        assert ctx.schema_version == 1

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError, match="extra_forbidden"):
            _make_tenant_context(rogue_field="nope")  # type: ignore[arg-type]

    def test_decimal_precision(self) -> None:
        ctx = _make_tenant_context(
            cost_budget_usd=Decimal("4999.99"),
            cost_consumed_usd=Decimal("0.01"),
        )
        assert ctx.cost_budget_usd == Decimal("4999.99")

    def test_descriptor_optional(self) -> None:
        ctx = _make_tenant_context()
        assert ctx.descriptor is None

    def test_descriptor_set(self) -> None:
        desc = AtelierDescriptor(
            framework="react",
            css_strategy="tailwind",
            design_tokens_path="DESIGN.md",
            package_manager="npm",
        )
        ctx = _make_tenant_context(descriptor=desc)
        assert ctx.descriptor is not None
        assert ctx.descriptor.framework == "react"


@pytest.mark.unit
class TestSurfaceState:
    """SurfaceState tracks iteration progress."""

    def test_frozen(self) -> None:
        surface = _make_surface_state()
        with pytest.raises(ValidationError):
            surface.passes = True  # type: ignore[misc]

    def test_defaults(self) -> None:
        surface = _make_surface_state()
        assert surface.passes is False
        assert surface.iteration_count == 0
        assert surface.human_approved is None

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            _make_surface_state(name="")


@pytest.mark.unit
class TestSurfaceManifest:
    """SurfaceManifest groups surfaces with a dependency graph."""

    def test_roundtrip_json(self) -> None:
        surface = _make_surface_state()
        manifest = SurfaceManifest(
            campaign_id=uuid4(),
            surfaces=[surface],
        )
        restored = SurfaceManifest.model_validate_json(manifest.model_dump_json())
        assert restored.surfaces[0].name == surface.name


@pytest.mark.unit
class TestCandidateUI:
    """CandidateUI stores generated file artifacts."""

    def test_frozen(self) -> None:
        cand = _make_candidate_ui()
        with pytest.raises(ValidationError):
            cand.iteration = 99  # type: ignore[misc]

    def test_mutation_op_optional(self) -> None:
        cand = _make_candidate_ui()
        assert cand.mutation_op is None

    def test_mutation_op_set(self) -> None:
        cand = _make_candidate_ui(mutation_op=MutationOp.PALETTE_SWAP)
        assert cand.mutation_op == MutationOp.PALETTE_SWAP


@pytest.mark.unit
class TestGateOutcome:
    """GateOutcome from deterministic gates."""

    def test_score_nullable(self) -> None:
        gate = _make_gate_outcome(score=None, axis=GateAxis.SEMANTIC_HTML)
        assert gate.score is None

    def test_diagnostic_required(self) -> None:
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            _make_gate_outcome(diagnostic="")


@pytest.mark.unit
class TestJudgeVote:
    """JudgeVote from D-O-R-A-V judges."""

    def test_score_bounds(self) -> None:
        with pytest.raises(ValidationError, match="less than or equal to 1"):
            _make_judge_vote(score=1.5)

    def test_score_zero_valid(self) -> None:
        vote = _make_judge_vote(score=0.0)
        assert vote.score == 0.0

    def test_reasoning_required(self) -> None:
        """CoT-before-score: reasoning must not be empty."""
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            _make_judge_vote(reasoning="")

    def test_roundtrip_json(self) -> None:
        vote = _make_judge_vote()
        restored = JudgeVote.model_validate_json(vote.model_dump_json())
        assert restored.judge_axis == vote.judge_axis
        assert restored.score == vote.score


@pytest.mark.unit
class TestConsensusResult:
    """ConsensusResult aggregates 5 judge votes."""

    def test_frozen(self) -> None:
        vote = _make_judge_vote()
        result = ConsensusResult(
            selected_candidate_id=uuid4(),
            composite_score=0.88,
            per_axis_scores={JudgeAxis.BRAND: vote},
            decision=ConsensusDecision.CONVERGED,
        )
        with pytest.raises(ValidationError):
            result.composite_score = 0.0  # type: ignore[misc]


@pytest.mark.unit
class TestCoherenceVerdict:
    """CoherenceVerdict for cross-surface consistency."""

    def test_violations_empty_on_clean(self) -> None:
        verdict = CoherenceVerdict(
            surface_id=uuid4(),
            token_use_valid=True,
            pattern_reuse_rate=0.95,
            decisions_md_compliant=True,
            regression_check_passed=True,
        )
        assert verdict.violations == []

    def test_pattern_reuse_rate_bounded(self) -> None:
        with pytest.raises(ValidationError, match="less than or equal to 1"):
            CoherenceVerdict(
                surface_id=uuid4(),
                token_use_valid=True,
                pattern_reuse_rate=1.5,
                decisions_md_compliant=True,
                regression_check_passed=True,
            )


@pytest.mark.unit
class TestTrajectoryRecord:
    """TrajectoryRecord for DPO flywheel."""

    def test_roundtrip_json(self) -> None:
        record = TrajectoryRecord(
            trajectory_id=uuid4(),
            tenant_id="tnt_test",
            project_id="prj_test",
            surface_id=uuid4(),
            session_id="session-001",
            ts=datetime.now(UTC),
            node_name="n3a_generator",
            iteration=0,
            encryption_key_id="projects/atelier/locations/global/keyRings/default/cryptoKeys/tenant",
        )
        restored = TrajectoryRecord.model_validate_json(record.model_dump_json())
        assert restored.trajectory_id == record.trajectory_id
        assert restored.node_name == "n3a_generator"

    def test_user_signal_optional(self) -> None:
        record = TrajectoryRecord(
            trajectory_id=uuid4(),
            tenant_id="tnt_test",
            project_id="prj_test",
            surface_id=uuid4(),
            session_id="session-001",
            ts=datetime.now(UTC),
            node_name="n3d_consensus",
            iteration=1,
            user_signal=UserSignal.ACCEPT,
            encryption_key_id="key-001",
        )
        assert record.user_signal == UserSignal.ACCEPT


@pytest.mark.unit
class TestEnumValues:
    """Verify all enum values are correct strings."""

    def test_gate_axis_count(self) -> None:
        assert len(GateAxis) == EXPECTED_GATE_AXES

    def test_judge_axis_count(self) -> None:
        assert len(JudgeAxis) == EXPECTED_JUDGE_AXES

    def test_mutation_op_count(self) -> None:
        assert len(MutationOp) == EXPECTED_MUTATION_OPS

    def test_surface_type_values(self) -> None:
        assert SurfaceType.PAGE.value == "page"
        assert SurfaceType.COMPONENT.value == "component"

    def test_user_signal_values(self) -> None:
        assert UserSignal.ACCEPT.value == "accept"
        assert UserSignal.REJECT.value == "reject"
        assert UserSignal.NEUTRAL.value == "neutral"
