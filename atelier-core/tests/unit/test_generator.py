"""Tests for the N3a template-based generator.

Verifies :func:`atelier.nodes.generator.generate_candidate` returns a
gate-clean :class:`CandidateUI` whose artifacts honor the contract every
downstream gate assumes: semantic HTML landmarks, CSS custom-property
declarations, and template-level injection safety.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from atelier.gates.deterministic import (
    SEMANTIC_LANDMARKS,
    check_css_validity,
    check_semantic_html,
    check_token_fidelity,
)
from atelier.intake.brief_spec import (
    BriefSpec,
    ComplianceLevel,
    ConvergenceBar,
    StackChoice,
    VisualRegister,
)
from atelier.models.data_contracts import CandidateUI, SurfaceState
from atelier.models.enums import GateDecision, SurfaceType
from atelier.nodes.generator import generate_candidate

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_ARTIFACT_COUNT = 2
ITERATION_FIVE = 5


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_brief(register: VisualRegister = VisualRegister.EDITORIAL) -> BriefSpec:
    """Build a minimally-valid :class:`BriefSpec` for a single test."""
    return BriefSpec(
        spec_id=uuid4(),
        tenant_id="tnt_test",
        project_id="prj_test",
        intent="Help users find a quiet co-working spot",
        visual_register=register,
        stack=StackChoice.VANILLA_HTML,
        compliance_level=ComplianceLevel.WCAG_AA,
        convergence_bar=ConvergenceBar.SHIP_IT,
        approved_at=datetime.now(UTC),
        approved_by_user_id="usr_test",
    )


def _make_surface(name: str = "homepage-hero", brief: str = "Hero with CTA") -> SurfaceState:
    """Build a :class:`SurfaceState` with sensible defaults."""
    return SurfaceState(
        surface_id=uuid4(),
        name=name,
        type=SurfaceType.PAGE,
        brief=brief,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerateCandidate:
    """:func:`generate_candidate` returns a gate-clean :class:`CandidateUI`."""

    def test_returns_candidate_ui(self) -> None:
        candidate = generate_candidate(_make_brief(), _make_surface())
        assert isinstance(candidate, CandidateUI)

    def test_artifact_filenames(self) -> None:
        candidate = generate_candidate(_make_brief(), _make_surface())
        assert set(candidate.artifacts.keys()) == {"index.html", "main.css"}
        assert len(candidate.artifacts) == EXPECTED_ARTIFACT_COUNT

    def test_html_contains_all_landmarks(self) -> None:
        candidate = generate_candidate(_make_brief(), _make_surface())
        html = candidate.artifacts["index.html"].lower()
        for landmark in SEMANTIC_LANDMARKS:
            assert f"<{landmark}" in html, f"missing landmark: {landmark}"

    def test_html_includes_doctype_and_lang(self) -> None:
        candidate = generate_candidate(_make_brief(), _make_surface())
        html = candidate.artifacts["index.html"]
        assert html.startswith("<!DOCTYPE html>")
        assert 'lang="en"' in html

    def test_css_declares_tokens(self) -> None:
        candidate = generate_candidate(_make_brief(), _make_surface())
        css = candidate.artifacts["main.css"]
        assert "--color-primary" in css
        assert "var(--color-primary)" in css

    def test_surface_id_propagated(self) -> None:
        surface = _make_surface()
        candidate = generate_candidate(_make_brief(), surface)
        assert candidate.surface_id == surface.surface_id

    def test_default_iteration_is_zero(self) -> None:
        candidate = generate_candidate(_make_brief(), _make_surface())
        assert candidate.iteration == 0

    def test_iteration_numbering(self) -> None:
        candidate = generate_candidate(
            _make_brief(),
            _make_surface(),
            iteration=ITERATION_FIVE,
        )
        assert candidate.iteration == ITERATION_FIVE

    def test_parent_id_propagated(self) -> None:
        parent_id = uuid4()
        candidate = generate_candidate(
            _make_brief(),
            _make_surface(),
            parent_candidate_id=parent_id,
        )
        assert candidate.parent_candidate_id == parent_id

    def test_mutation_op_is_none_for_template_path(self) -> None:
        candidate = generate_candidate(_make_brief(), _make_surface())
        assert candidate.mutation_op is None

    def test_candidate_id_is_unique_per_call(self) -> None:
        a = generate_candidate(_make_brief(), _make_surface())
        b = generate_candidate(_make_brief(), _make_surface())
        assert a.candidate_id != b.candidate_id

    def test_html_escapes_user_text(self) -> None:
        surface = _make_surface(brief="<script>alert('xss')</script>")
        candidate = generate_candidate(_make_brief(), surface)
        html = candidate.artifacts["index.html"]
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


@pytest.mark.unit
class TestGeneratorPassesGates:
    """Every generated candidate should clear the real Phase 1 gates."""

    @pytest.mark.parametrize("register", list(VisualRegister))
    def test_all_real_gates_pass(self, register: VisualRegister) -> None:
        candidate = generate_candidate(_make_brief(register), _make_surface())
        assert check_semantic_html(candidate).decision is GateDecision.PASS
        assert check_css_validity(candidate).decision is GateDecision.PASS
        assert check_token_fidelity(candidate).decision is GateDecision.PASS
