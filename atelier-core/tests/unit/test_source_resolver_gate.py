"""Tests for the N2 SourceResolverGate (deterministic precondition).

Regression coverage for the golden-path defect: ``brief_parser`` never sets
``design_system_source`` (it defaults to ``None``) and the API builds
``TenantContext`` without a descriptor, so the original gate — which passed only
for an explicit DESIGN.md path — rejected *every* first brief before it reached
generation. The whole pipeline suite masked this by patching the gate to
``return_value=True``; this module exercises the real logic, unmocked.

The N2 resolver (``source_resolver_agent`` / ``pull_design_tokens``) is fail-soft
(PRD §21): ``None`` and ``"infer"`` are first-class resolution modes that
auto-discover a DESIGN.md and fall back to safe defaults. The gate must admit
them, reject only a structurally malformed (empty-string) source, and
short-circuit to pass whenever a tenant descriptor is present.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from atelier.intake.brief_spec import (
    BriefSpec,
    ComplianceLevel,
    ConvergenceBar,
    StackChoice,
    VisualRegister,
)
from atelier.intake.source_resolver import source_resolver_gate
from atelier.models.data_contracts import AtelierDescriptor, TenantContext


def _make_brief_spec(**overrides: object) -> BriefSpec:
    """Factory for valid BriefSpec instances (mirrors test_brief_spec)."""
    defaults: dict[str, object] = {
        "spec_id": uuid4(),
        "tenant_id": "tnt_test",
        "project_id": "prj_test",
        "intent": "design a calm onboarding flow",
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


def _tenant_ctx(descriptor: AtelierDescriptor | None = None) -> TenantContext:
    return TenantContext(
        tenant_id="tnt_test",
        user_id="usr_test",
        project_id="prj_test",
        descriptor=descriptor,
    )


@pytest.mark.unit
class TestSourceResolverGate:
    def test_golden_path_none_source_passes(self) -> None:
        """The common first brief: no descriptor, no design source → must pass.

        This is the exact regression. ``brief_parser`` leaves
        ``design_system_source`` at its ``None`` default; the resolver
        auto-discovers + falls back to safe defaults, so the gate must admit it.
        """
        brief = _make_brief_spec(design_system_source=None)
        assert source_resolver_gate(_tenant_ctx(), brief) is True

    def test_infer_source_passes(self) -> None:
        """``"infer"`` triggers PADI auto-discovery — a valid mode, not a failure."""
        brief = _make_brief_spec(design_system_source="infer")
        assert source_resolver_gate(_tenant_ctx(), brief) is True

    def test_explicit_path_passes(self) -> None:
        """An explicit DESIGN.md path is resolved directly."""
        brief = _make_brief_spec(design_system_source="design/DESIGN.md")
        assert source_resolver_gate(_tenant_ctx(), brief) is True

    def test_descriptor_present_short_circuits(self) -> None:
        """A tenant descriptor (prior project state) passes regardless of source."""
        descriptor = AtelierDescriptor(framework="vanilla", css_strategy="vanilla")
        brief = _make_brief_spec(design_system_source=None)
        assert source_resolver_gate(_tenant_ctx(descriptor), brief) is True

    def test_empty_string_source_fails_closed(self) -> None:
        """An empty-string path is neither a real file nor a sentinel — reject it."""
        brief = _make_brief_spec(design_system_source="")
        assert source_resolver_gate(_tenant_ctx(), brief) is False
