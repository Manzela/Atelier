"""Tests for the N3c deterministic gate suite + axis-filtered runner.

Covers every gate in :mod:`atelier.gates.deterministic` plus the runner in
:mod:`atelier.gates.runner`. Each gate is exercised with at least one
passing and one failing artifact so regressions to gate logic surface in CI.
"""

from uuid import uuid4

import pytest
from atelier.gates.deterministic import (
    AXE_STUB_SCORE,
    LIGHTHOUSE_STUB_SCORE,
    SEMANTIC_HTML_PASS_THRESHOLD,
    SEMANTIC_LANDMARKS,
    VISUAL_DIFF_STUB_SCORE,
    check_axe_stub,
    check_css_validity,
    check_lighthouse_stub,
    check_semantic_html,
    check_token_fidelity,
    check_visual_diff_stub,
    run_all_gates,
)
from atelier.gates.runner import GateRunner, GateRunResult, run_gates
from atelier.models.data_contracts import CandidateUI
from atelier.models.enums import GateAxis, GateDecision

# ---------------------------------------------------------------------------
# Expected counts — module-level constants so PLR2004 stays quiet
# ---------------------------------------------------------------------------

EXPECTED_GATE_COUNT = 6
EXPECTED_LANDMARK_COUNT = 6
THREE_LANDMARK_SCORE = 50.0
SINGLE_LANDMARK_SCORE = 100.0 / EXPECTED_LANDMARK_COUNT


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_candidate(artifacts: dict[str, str] | None = None) -> CandidateUI:
    """Build a :class:`CandidateUI` from the supplied artifacts.

    Args:
        artifacts: Optional ``{filename: content}`` map. Defaults to a
            minimal HTML + CSS pair that passes every real gate.

    Returns:
        A frozen :class:`CandidateUI` ready for gate evaluation.
    """
    if artifacts is None:
        artifacts = {
            "index.html": (
                "<header></header><nav></nav><main></main>"
                "<section></section><article></article><footer></footer>"
            ),
            "main.css": (
                ":root { --color-primary: #000; --space: 1rem; }\n"
                "body { color: var(--color-primary); padding: var(--space); }\n"
            ),
        }
    return CandidateUI(
        candidate_id=uuid4(),
        surface_id=uuid4(),
        iteration=0,
        artifacts=artifacts,
    )


# ---------------------------------------------------------------------------
# check_semantic_html
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSemanticHtmlGate:
    """:func:`check_semantic_html` scores HTML5 landmark coverage."""

    def test_all_landmarks_pass(self) -> None:
        outcome = check_semantic_html(_make_candidate())
        assert outcome.decision is GateDecision.PASS
        assert outcome.score == 100.0
        assert outcome.axis is GateAxis.SEMANTIC_HTML

    def test_three_landmarks_pass_at_threshold(self) -> None:
        candidate = _make_candidate({"index.html": "<header></header><main></main><nav></nav>"})
        outcome = check_semantic_html(candidate)
        assert outcome.decision is GateDecision.PASS
        assert outcome.score == THREE_LANDMARK_SCORE

    def test_one_landmark_rejected(self) -> None:
        candidate = _make_candidate({"index.html": "<header></header>"})
        outcome = check_semantic_html(candidate)
        assert outcome.decision is GateDecision.REJECT
        assert outcome.score == pytest.approx(SINGLE_LANDMARK_SCORE)

    def test_missing_index_html_rejected(self) -> None:
        candidate = _make_candidate({"main.css": "body {}"})
        outcome = check_semantic_html(candidate)
        assert outcome.decision is GateDecision.REJECT
        assert outcome.score == 0.0
        assert "No index.html" in outcome.diagnostic

    def test_empty_index_html_rejected(self) -> None:
        candidate = _make_candidate({"index.html": ""})
        outcome = check_semantic_html(candidate)
        assert outcome.decision is GateDecision.REJECT

    def test_case_insensitive_match(self) -> None:
        candidate = _make_candidate(
            {"index.html": "<HEADER></HEADER><MAIN></MAIN><NAV></NAV>"},
        )
        outcome = check_semantic_html(candidate)
        assert outcome.decision is GateDecision.PASS

    def test_threshold_constant_is_50(self) -> None:
        assert SEMANTIC_HTML_PASS_THRESHOLD == THREE_LANDMARK_SCORE

    def test_landmark_set_size(self) -> None:
        assert len(SEMANTIC_LANDMARKS) == EXPECTED_LANDMARK_COUNT


# ---------------------------------------------------------------------------
# check_css_validity
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCssValidityGate:
    """:func:`check_css_validity` checks balanced braces + no empty rulesets."""

    def test_valid_css_passes(self) -> None:
        outcome = check_css_validity(_make_candidate())
        assert outcome.decision is GateDecision.PASS
        assert outcome.score == 100.0

    def test_no_css_files_pass(self) -> None:
        outcome = check_css_validity(_make_candidate({"index.html": "<main></main>"}))
        assert outcome.decision is GateDecision.PASS
        assert "nothing to validate" in outcome.diagnostic

    def test_unbalanced_braces_reject(self) -> None:
        candidate = _make_candidate({"main.css": "body { color: red;"})
        outcome = check_css_validity(candidate)
        assert outcome.decision is GateDecision.REJECT
        assert outcome.score == 0.0
        assert "unbalanced" in outcome.diagnostic

    def test_empty_ruleset_reject(self) -> None:
        candidate = _make_candidate({"main.css": "body { }"})
        outcome = check_css_validity(candidate)
        assert outcome.decision is GateDecision.REJECT
        assert "empty ruleset" in outcome.diagnostic

    def test_multiple_css_files_all_valid_pass(self) -> None:
        candidate = _make_candidate(
            {
                "index.html": "<main></main>",
                "a.css": "body { color: red; }",
                "b.css": ":root { --x: 1; } a { color: var(--x); }",
            },
        )
        outcome = check_css_validity(candidate)
        assert outcome.decision is GateDecision.PASS


# ---------------------------------------------------------------------------
# check_token_fidelity
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTokenFidelityGate:
    """:func:`check_token_fidelity` requires CSS custom properties."""

    def test_declared_and_used_pass(self) -> None:
        outcome = check_token_fidelity(_make_candidate())
        assert outcome.decision is GateDecision.PASS
        assert outcome.score > 0.0

    def test_no_css_rejected(self) -> None:
        outcome = check_token_fidelity(_make_candidate({"index.html": "<main></main>"}))
        assert outcome.decision is GateDecision.REJECT
        assert outcome.score == 0.0

    def test_no_custom_properties_rejected(self) -> None:
        candidate = _make_candidate({"main.css": "body { color: red; }"})
        outcome = check_token_fidelity(candidate)
        assert outcome.decision is GateDecision.REJECT
        assert "missing" in outcome.diagnostic.lower()

    def test_declared_but_unused_low_score(self) -> None:
        candidate = _make_candidate({"main.css": ":root { --x: 1; --y: 2; }"})
        outcome = check_token_fidelity(candidate)
        assert outcome.decision is GateDecision.PASS
        assert outcome.score == 0.0

    def test_score_capped_at_100(self) -> None:
        # 1 declaration, 5 references → ratio 5.0 → capped at 100
        candidate = _make_candidate(
            {
                "main.css": (
                    ":root { --x: 1; }\n"
                    "a { color: var(--x); }\n"
                    "b { color: var(--x); }\n"
                    "c { color: var(--x); }\n"
                    "d { color: var(--x); }\n"
                    "e { color: var(--x); }\n"
                ),
            },
        )
        outcome = check_token_fidelity(candidate)
        assert outcome.score == 100.0


# ---------------------------------------------------------------------------
# Stub gates
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStubGates:
    """Stub gates always PASS with their fixed scores."""

    def test_lighthouse_stub(self) -> None:
        outcome = check_lighthouse_stub(_make_candidate())
        assert outcome.decision is GateDecision.PASS
        assert outcome.score == LIGHTHOUSE_STUB_SCORE
        assert outcome.axis is GateAxis.LIGHTHOUSE_A11Y

    def test_axe_stub(self) -> None:
        outcome = check_axe_stub(_make_candidate())
        assert outcome.decision is GateDecision.PASS
        assert outcome.score == AXE_STUB_SCORE
        assert outcome.axis is GateAxis.AXE

    def test_visual_diff_stub(self) -> None:
        outcome = check_visual_diff_stub(_make_candidate())
        assert outcome.decision is GateDecision.PASS
        assert outcome.score == VISUAL_DIFF_STUB_SCORE
        assert outcome.axis is GateAxis.VISUAL_DIFF

    def test_stubs_ignore_artifacts(self) -> None:
        empty = _make_candidate({})
        assert check_lighthouse_stub(empty).decision is GateDecision.PASS
        assert check_axe_stub(empty).decision is GateDecision.PASS
        assert check_visual_diff_stub(empty).decision is GateDecision.PASS


# ---------------------------------------------------------------------------
# run_all_gates
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunAllGates:
    """:func:`run_all_gates` runs every gate in declared order."""

    def test_all_pass_on_full_candidate(self) -> None:
        outcomes = run_all_gates(_make_candidate())
        assert len(outcomes) == EXPECTED_GATE_COUNT
        assert all(o.decision is GateDecision.PASS for o in outcomes)

    def test_order_is_stable(self) -> None:
        outcomes = run_all_gates(_make_candidate())
        axes = [o.axis for o in outcomes]
        assert axes == [
            GateAxis.SEMANTIC_HTML,
            GateAxis.LIGHTHOUSE_PERF,
            GateAxis.TOKEN_FIDELITY,
            GateAxis.LIGHTHOUSE_A11Y,
            GateAxis.AXE,
            GateAxis.VISUAL_DIFF,
        ]


# ---------------------------------------------------------------------------
# run_gates / GateRunner
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGateRunner:
    """:func:`run_gates` + :class:`GateRunner` filter by axis list."""

    def test_empty_axes_vacuous_pass(self) -> None:
        result = run_gates(_make_candidate(), [])
        assert isinstance(result, GateRunResult)
        assert result.all_passed is True
        assert result.outcomes == []
        assert result.failed_axes == []

    def test_single_axis_runs_only_that_gate(self) -> None:
        result = run_gates(_make_candidate(), [GateAxis.SEMANTIC_HTML])
        assert len(result.outcomes) == 1
        assert result.outcomes[0].axis is GateAxis.SEMANTIC_HTML
        assert result.all_passed is True

    def test_failure_collected_in_failed_axes(self) -> None:
        # Empty index.html → semantic_html rejects
        bad = _make_candidate({"index.html": "", "main.css": "body {}"})
        result = run_gates(
            bad,
            [GateAxis.SEMANTIC_HTML, GateAxis.TOKEN_FIDELITY],
        )
        assert result.all_passed is False
        assert GateAxis.SEMANTIC_HTML in result.failed_axes
        assert GateAxis.TOKEN_FIDELITY in result.failed_axes

    def test_duplicate_axes_dedup(self) -> None:
        result = run_gates(
            _make_candidate(),
            [GateAxis.SEMANTIC_HTML, GateAxis.SEMANTIC_HTML, GateAxis.AXE],
        )
        assert len(result.outcomes) == 2

    def test_unsupported_axis_reported(self) -> None:
        result = run_gates(_make_candidate(), [GateAxis.RESPONSIVE])
        assert result.unsupported_axes == [GateAxis.RESPONSIVE]
        assert result.outcomes == []
        # No outcomes ran, so vacuously passes
        assert result.all_passed is True

    def test_mixed_supported_and_unsupported(self) -> None:
        result = run_gates(
            _make_candidate(),
            [GateAxis.SEMANTIC_HTML, GateAxis.RESPONSIVE, GateAxis.AXE],
        )
        assert len(result.outcomes) == 2
        assert result.unsupported_axes == [GateAxis.RESPONSIVE]
        assert result.all_passed is True

    def test_candidate_id_propagated(self) -> None:
        candidate = _make_candidate()
        result = run_gates(candidate, [GateAxis.AXE])
        assert result.candidate_id == candidate.candidate_id

    def test_runner_class_default_axes(self) -> None:
        runner = GateRunner()
        result = runner.run(_make_candidate())
        # Default = every axis with a Phase 1 gate (6 of them)
        assert len(result.outcomes) == EXPECTED_GATE_COUNT
        assert result.all_passed is True

    def test_runner_class_per_call_override(self) -> None:
        runner = GateRunner(axes_required=[GateAxis.AXE])
        result = runner.run(
            _make_candidate(),
            axes_required=[GateAxis.SEMANTIC_HTML],
        )
        assert len(result.outcomes) == 1
        assert result.outcomes[0].axis is GateAxis.SEMANTIC_HTML
