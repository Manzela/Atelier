"""Tests for the N3d ConsensusAgent (:mod:`atelier.nodes.consensus`).

Covers every public symbol plus every Phase 1 deterministic scorer:

    * :func:`_score_brand`, :func:`_score_originality`,
      :func:`_score_relevance`, :func:`_score_accessibility`,
      :func:`_score_visual_clarity` -- each gets passing + failing artifacts
      to lock down the heuristic contract before Phase 2 LLM judges land.
    * :func:`_apply_constitution` -- soft penalty math, target satisfied
      path, and the :data:`CONSTITUTION_FLOOR` clamp.
    * :func:`evaluate_candidate` -- end-to-end composition: seeded order,
      composite computation, ``passed`` flag, JudgeVote schema integrity,
      and constitution attachment.

These tests intentionally exercise the module-private ``_score_*``
helpers because the user-facing ``evaluate_candidate`` cannot otherwise
isolate per-axis scoring regressions. Private-symbol access in tests is
an accepted Python pattern when it improves diagnostic resolution.
"""

from uuid import UUID, uuid4

import pytest
from atelier.models.axis_weights import AxisWeights
from atelier.models.constitution_registry import (
    Constitution,
    ConstitutionPrinciple,
    ConstitutionScoring,
)
from atelier.models.data_contracts import CandidateUI, JudgeVote
from atelier.models.enums import JudgeAxis
from atelier.nodes.consensus import (
    ACCESSIBILITY_TARGET_ARIA,
    ACCESSIBILITY_TARGET_SEMANTIC,
    BRAND_TARGET_COLORS,
    BRAND_TARGET_VARS,
    CONFIDENCE_HALF_WIDTH,
    CONSTITUTION_FLOOR,
    CONVERGENCE_DEFAULT,
    ORIGINALITY_TARGET_PROPS,
    ORIGINALITY_TARGET_SELECTORS,
    RELEVANCE_TARGET_CHARS_PER_TAG,
    VISUAL_TARGET_SPACING,
    VISUAL_TARGET_TYPOGRAPHY,
    ConsensusEvaluation,
    _apply_constitution,
    _score_accessibility,
    _score_brand,
    _score_originality,
    _score_relevance,
    _score_visual_clarity,
    evaluate_candidate,
)

# ---------------------------------------------------------------------------
# Module-level constants -- keep PLR2004 quiet and make intent explicit.
# ---------------------------------------------------------------------------

DETERMINISTIC_SEED = 42
EXPECTED_AXIS_COUNT = 5
ZERO_SCORE = 0.0
PERFECT_SCORE = 1.0

# Constitution targets used across `_apply_constitution` tests.
PERMISSIVE_TARGET = 0.50
STRICT_TARGET = 0.95
HIGH_COMPOSITE = 0.90
LOW_COMPOSITE = 0.40

# JudgeVote provenance suffix appended to the model display name.
PHASE_1_SUFFIX = "(Phase 1 stub)"

# Convergence thresholds used in `evaluate_candidate` tests.
EASY_THRESHOLD = 0.01  # trivially passable
HARD_THRESHOLD = 0.99  # only the most polished artifacts pass


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def _make_candidate(artifacts: dict[str, str] | None = None) -> CandidateUI:
    """Build a :class:`CandidateUI` from the supplied artifacts.

    Args:
        artifacts: Optional ``{filename: content}`` map. Defaults to an
            empty artifacts dict (useful for "no CSS / no HTML" edge tests).

    Returns:
        A frozen :class:`CandidateUI` ready for scoring.
    """
    return CandidateUI(
        candidate_id=uuid4(),
        surface_id=uuid4(),
        iteration=0,
        artifacts=artifacts if artifacts is not None else {},
    )


def _rich_css() -> str:
    """Return a CSS document that should max out every CSS-driven score."""
    return (
        ":root {\n"
        "  --color-primary: #112233;\n"
        "  --color-accent:  #aabbcc;\n"
        "  --color-bg:      #ffffff;\n"
        "  --space-sm: 0.5rem;\n"
        "  --space-md: 1rem;\n"
        "  --space-lg: 2rem;\n"
        "  --radius: 4px;\n"
        "}\n"
        "body {\n"
        "  background: var(--color-bg);\n"
        "  color: var(--color-primary);\n"
        "  margin: var(--space-md);\n"
        "  padding: var(--space-md);\n"
        "  font-family: 'Inter', sans-serif;\n"
        "  font-size: 16px;\n"
        "  font-weight: 400;\n"
        "  line-height: 1.5;\n"
        "  letter-spacing: 0.01em;\n"
        "}\n"
        "header { padding: var(--space-lg); gap: var(--space-md); }\n"
        "nav    { margin: var(--space-sm); display: flex; }\n"
        "main   { padding: var(--space-lg); }\n"
        "footer { margin: var(--space-md); border-top: 1px solid var(--color-accent); }\n"
        "article h1 { font-size: 2rem; font-weight: 700; line-height: 1.2; }\n"
        ".card { transform: translateY(0); border-radius: var(--radius); }\n"
    )


def _rich_html() -> str:
    """Return an HTML document that should max out every HTML-driven score.

    The relevance scorer requires at least ``RELEVANCE_TARGET_CHARS_PER_TAG``
    (30) characters of text per HTML tag on average.  We embed several long
    paragraphs so the total text-chars / tag-count comfortably exceeds 30.
    """
    body_paras = (
        "Atelier turns a one-sentence brief into a designed, code-shipped "
        "surface in minutes, combining five autonomous judges that score "
        "brand consistency, originality, relevance, accessibility, and "
        "visual clarity against a calibrated golden set."
        " "
        "The system uses a deterministic gate battery followed by a "
        "multi-judge Bayesian consensus protocol. Each judge emits a "
        "normalized score with provenance variables traced back to the "
        "source artifacts, ensuring full auditability of every decision."
        " "
        "Candidates that clear the consensus threshold proceed to the "
        "trajectory recorder for DPO preference pair extraction, while "
        "rejected candidates are routed to the fixer node for iterative "
        "improvement guided by structured diagnostics from each judge."
    )
    return (
        "<header aria-label='Top bar'><nav aria-label='Primary'>"
        "<a href='/'>Home</a></nav></header>"
        "<main aria-labelledby='hero'>"
        "<section>"
        f"<article><h1 id='hero'>Atelier Design Agent</h1>"
        f"<p>{body_paras}</p></article>"
        "</section>"
        "<aside><img src='/hero.png' alt='Atelier hero illustration' /></aside>"
        "</main>"
        "<footer>Copyright 2026 Atelier. All rights reserved.</footer>"
    )


def _make_constitution(
    *,
    name: str = "test-constitution",
    target: float = STRICT_TARGET,
) -> Constitution:
    """Build a lightweight :class:`Constitution` for penalty tests."""
    return Constitution(
        name=name,
        version=1,
        applies_to=("test",),
        principles=(
            ConstitutionPrinciple(
                principle_id="T1",
                name="Test principle",
                description="Used only by the test suite.",
            ),
        ),
        scoring=ConstitutionScoring(
            minimum_pass=0.70,
            target=target,
            exceptional=0.99,
        ),
    )


# ---------------------------------------------------------------------------
# _score_brand
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScoreBrand:
    """:func:`_score_brand` measures CSS token + palette discipline."""

    def test_rich_css_scores_full_credit(self) -> None:
        candidate = _make_candidate({"main.css": _rich_css()})
        result = _score_brand(candidate)
        assert result.score == PERFECT_SCORE
        assert "CSS custom properties" in result.diagnostic
        assert result.provenance_vars == ["main.css"]

    def test_no_css_scores_zero(self) -> None:
        candidate = _make_candidate({"index.html": "<header></header>"})
        result = _score_brand(candidate)
        assert result.score == ZERO_SCORE
        assert "no CSS" in result.diagnostic
        assert result.provenance_vars == []

    def test_partial_tokens_and_colors_scaled(self) -> None:
        # 1 token + 1 color: var_credit = 0.2, color_credit = 0.333.
        # weighted = 0.2 * 0.6 + 0.333 * 0.4 ≈ 0.253
        css = ":root { --c: #abc; } body { color: var(--c); }"
        candidate = _make_candidate({"main.css": css})
        result = _score_brand(candidate)
        expected = round(
            (1 / BRAND_TARGET_VARS) * 0.6 + (1 / BRAND_TARGET_COLORS) * 0.4,
            4,
        )
        assert result.score == expected


# ---------------------------------------------------------------------------
# _score_originality
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScoreOriginality:
    """:func:`_score_originality` measures CSS property + selector variety."""

    def test_rich_css_scores_full_credit(self) -> None:
        candidate = _make_candidate({"main.css": _rich_css()})
        result = _score_originality(candidate)
        assert result.score == PERFECT_SCORE
        assert "unique CSS properties" in result.diagnostic

    def test_no_css_scores_zero(self) -> None:
        candidate = _make_candidate({"index.html": "<p>hi</p>"})
        result = _score_originality(candidate)
        assert result.score == ZERO_SCORE
        assert "no CSS" in result.diagnostic

    def test_minimal_css_partial_credit(self) -> None:
        css = "body { color: red; }"
        candidate = _make_candidate({"main.css": css})
        result = _score_originality(candidate)
        # 1 unique property + 1 unique selector vs targets 12 and 6.
        expected = round(
            ((1 / ORIGINALITY_TARGET_PROPS) + (1 / ORIGINALITY_TARGET_SELECTORS)) / 2.0,
            4,
        )
        assert result.score == expected


# ---------------------------------------------------------------------------
# _score_relevance
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScoreRelevance:
    """:func:`_score_relevance` measures HTML text-to-tag density."""

    def test_rich_html_scores_full_credit(self) -> None:
        candidate = _make_candidate({"index.html": _rich_html()})
        result = _score_relevance(candidate)
        assert result.score == PERFECT_SCORE
        assert "text chars" in result.diagnostic

    def test_no_html_scores_zero(self) -> None:
        candidate = _make_candidate({"main.css": "body {}"})
        result = _score_relevance(candidate)
        assert result.score == ZERO_SCORE
        assert "no HTML" in result.diagnostic

    def test_html_without_tags_scores_zero(self) -> None:
        candidate = _make_candidate({"index.html": "raw text only"})
        result = _score_relevance(candidate)
        assert result.score == ZERO_SCORE
        assert "no tags" in result.diagnostic

    def test_partial_density_below_target(self) -> None:
        # 5 tags, ~10 text chars -> 2 chars/tag. Below RELEVANCE_TARGET.
        html = "<p>hi</p><p>hi</p><p>hi</p>"
        candidate = _make_candidate({"index.html": html})
        result = _score_relevance(candidate)
        # Don't recompute the exact ratio in the test; just assert it
        # landed strictly inside the (0, 1) interval and below target.
        assert ZERO_SCORE < result.score < PERFECT_SCORE
        assert "chars/tag" in result.diagnostic
        # Sanity: targets imply at least RELEVANCE_TARGET_CHARS_PER_TAG of
        # density would be needed for a perfect score.
        assert RELEVANCE_TARGET_CHARS_PER_TAG > 0


# ---------------------------------------------------------------------------
# _score_accessibility
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScoreAccessibility:
    """:func:`_score_accessibility` aggregates ARIA + landmarks + alt text."""

    def test_rich_html_scores_full_credit(self) -> None:
        candidate = _make_candidate({"index.html": _rich_html()})
        result = _score_accessibility(candidate)
        assert result.score == PERFECT_SCORE

    def test_no_html_scores_zero(self) -> None:
        candidate = _make_candidate({"main.css": "body {}"})
        result = _score_accessibility(candidate)
        assert result.score == ZERO_SCORE
        assert "no HTML" in result.diagnostic

    def test_image_without_alt_drops_alt_ratio(self) -> None:
        # 0 ARIA, 0 semantic landmarks, 1 img with no alt -> alt_ratio 0.
        html = "<div><img src='x.png' /></div>"
        candidate = _make_candidate({"index.html": html})
        result = _score_accessibility(candidate)
        assert result.score == ZERO_SCORE

    def test_image_with_alt_lifts_alt_ratio(self) -> None:
        # alt_ratio fires at 1.0 even without any ARIA/landmarks.
        html = "<div><img src='x.png' alt='hero' /></div>"
        candidate = _make_candidate({"index.html": html})
        result = _score_accessibility(candidate)
        # Pure alt-only contribution = (0 + 0 + 1) / 3 = 0.333...
        assert result.score == round(1.0 / 3.0, 4)

    def test_landmarks_only_partial_credit(self) -> None:
        # Three landmarks, no ARIA, no images.
        html = "<header></header><main></main><footer></footer>"
        candidate = _make_candidate({"index.html": html})
        result = _score_accessibility(candidate)
        # aria=0/target, semantic=3/target, alt=1.0 (no imgs).
        semantic_credit = min(3 / ACCESSIBILITY_TARGET_SEMANTIC, 1.0)
        expected = round((0.0 + semantic_credit + 1.0) / 3.0, 4)
        assert result.score == expected
        # Touch the ARIA constant to assert it stays meaningful.
        assert ACCESSIBILITY_TARGET_ARIA > 0


# ---------------------------------------------------------------------------
# _score_visual_clarity
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScoreVisualClarity:
    """:func:`_score_visual_clarity` counts typography + spacing decls."""

    def test_rich_css_scores_full_credit(self) -> None:
        candidate = _make_candidate({"main.css": _rich_css()})
        result = _score_visual_clarity(candidate)
        assert result.score == PERFECT_SCORE

    def test_no_css_scores_zero(self) -> None:
        candidate = _make_candidate({"index.html": "<p>hi</p>"})
        result = _score_visual_clarity(candidate)
        assert result.score == ZERO_SCORE
        assert "no CSS" in result.diagnostic

    def test_typography_only_partial_credit(self) -> None:
        # Only font-size present; no spacing decls.
        css = "body { font-size: 16px; }"
        candidate = _make_candidate({"main.css": css})
        result = _score_visual_clarity(candidate)
        expected = round(((1 / VISUAL_TARGET_TYPOGRAPHY) + 0.0) / 2.0, 4)
        assert result.score == expected
        # Spacing target should remain a positive integer constant.
        assert VISUAL_TARGET_SPACING > 0


# ---------------------------------------------------------------------------
# _apply_constitution
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestApplyConstitution:
    """:func:`_apply_constitution` enforces a graded penalty floored at 50%."""

    def test_meeting_target_returns_unchanged(self) -> None:
        constitution = _make_constitution(target=PERMISSIVE_TARGET)
        score, diagnostic = _apply_constitution(HIGH_COMPOSITE, constitution)
        assert score == HIGH_COMPOSITE
        assert "satisfied" in diagnostic

    def test_below_target_reduces_score(self) -> None:
        constitution = _make_constitution(target=STRICT_TARGET)
        score, diagnostic = _apply_constitution(LOW_COMPOSITE, constitution)
        assert score < LOW_COMPOSITE
        assert score >= LOW_COMPOSITE * CONSTITUTION_FLOOR
        assert "penalty" in diagnostic
        assert "multiplier" in diagnostic

    def test_floor_clamps_extreme_gaps(self) -> None:
        # Composite of 0 against a strict target should hit the floor.
        constitution = _make_constitution(target=STRICT_TARGET)
        score, _ = _apply_constitution(ZERO_SCORE, constitution)
        # 0 * any_multiplier = 0; the floor is on the multiplier, not the
        # final score. Verify we did NOT divide by zero or go negative.
        assert score == ZERO_SCORE

    def test_floor_observed_for_nonzero_composite(self) -> None:
        constitution = _make_constitution(target=STRICT_TARGET)
        score, _ = _apply_constitution(0.10, constitution)
        # Multiplier must be at least CONSTITUTION_FLOOR.
        assert score >= 0.10 * CONSTITUTION_FLOOR


# ---------------------------------------------------------------------------
# evaluate_candidate
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEvaluateCandidate:
    """End-to-end tests for :func:`evaluate_candidate`."""

    def test_rich_candidate_passes_with_default_weights(self) -> None:
        candidate = _make_candidate(
            {
                "index.html": _rich_html(),
                "main.css": _rich_css(),
            }
        )
        result = evaluate_candidate(
            candidate,
            AxisWeights(),
            seed=DETERMINISTIC_SEED,
        )
        assert isinstance(result, ConsensusEvaluation)
        assert result.candidate_id == candidate.candidate_id
        assert result.composite_score == PERFECT_SCORE
        assert result.passed is True
        assert result.constitution_name is None

    def test_empty_candidate_returns_zero_composite(self) -> None:
        candidate = _make_candidate()
        result = evaluate_candidate(
            candidate,
            AxisWeights(),
            seed=DETERMINISTIC_SEED,
        )
        assert result.composite_score == ZERO_SCORE
        assert result.passed is False

    def test_every_axis_has_a_vote(self) -> None:
        candidate = _make_candidate(
            {
                "index.html": _rich_html(),
                "main.css": _rich_css(),
            }
        )
        result = evaluate_candidate(
            candidate,
            AxisWeights(),
            seed=DETERMINISTIC_SEED,
        )
        assert set(result.votes.keys()) == set(JudgeAxis)
        assert len(result.votes) == EXPECTED_AXIS_COUNT

    def test_judge_vote_schema_integrity(self) -> None:
        candidate = _make_candidate(
            {
                "index.html": _rich_html(),
                "main.css": _rich_css(),
            }
        )
        result = evaluate_candidate(
            candidate,
            AxisWeights(),
            seed=DETERMINISTIC_SEED,
        )
        vote = result.votes[JudgeAxis.BRAND]
        assert isinstance(vote, JudgeVote)
        assert isinstance(vote.candidate_id, UUID)
        assert vote.candidate_id == candidate.candidate_id
        assert vote.judge_axis is JudgeAxis.BRAND
        assert ZERO_SCORE <= vote.score <= PERFECT_SCORE
        low, high = vote.confidence_interval
        assert ZERO_SCORE <= low <= vote.score <= high <= PERFECT_SCORE
        assert (high - low) <= 2 * CONFIDENCE_HALF_WIDTH + 1e-6
        assert PHASE_1_SUFFIX in vote.judge_model
        assert len(vote.reasoning) > 0

    def test_diagnostics_include_bias_and_constitution_keys(self) -> None:
        candidate = _make_candidate(
            {
                "index.html": _rich_html(),
                "main.css": _rich_css(),
            }
        )
        result = evaluate_candidate(
            candidate,
            AxisWeights(),
            seed=DETERMINISTIC_SEED,
        )
        assert "bias_warning" in result.diagnostics
        assert "constitution" in result.diagnostics
        # Every axis name should also have a diagnostic entry.
        for axis_name in ("brand", "originality", "relevance", "accessibility", "visual_clarity"):
            assert axis_name in result.diagnostics

    def test_constitution_penalty_drops_score(self) -> None:
        # Build a candidate that scores ~0.5 -- below a strict target so
        # the penalty fires.
        candidate = _make_candidate({"index.html": "<p>only text</p>"})
        constitution = _make_constitution(target=STRICT_TARGET)
        without = evaluate_candidate(
            candidate,
            AxisWeights(),
            seed=DETERMINISTIC_SEED,
        )
        with_const = evaluate_candidate(
            candidate,
            AxisWeights(),
            constitution=constitution,
            seed=DETERMINISTIC_SEED,
        )
        assert with_const.constitution_name == "test-constitution"
        assert with_const.composite_score <= without.composite_score
        assert "penalty" in with_const.diagnostics["constitution"]

    def test_seed_makes_evaluation_order_deterministic(self) -> None:
        candidate = _make_candidate(
            {
                "index.html": _rich_html(),
                "main.css": _rich_css(),
            }
        )
        first = evaluate_candidate(
            candidate,
            AxisWeights(),
            seed=DETERMINISTIC_SEED,
        )
        second = evaluate_candidate(
            candidate,
            AxisWeights(),
            seed=DETERMINISTIC_SEED,
        )
        assert first.composite_score == second.composite_score
        assert first.diagnostics == second.diagnostics

    def test_passed_flag_respects_explicit_threshold(self) -> None:
        candidate = _make_candidate({"main.css": "body { color: red; }"})
        easy = evaluate_candidate(
            candidate,
            AxisWeights(),
            convergence_threshold=EASY_THRESHOLD,
            seed=DETERMINISTIC_SEED,
        )
        hard = evaluate_candidate(
            candidate,
            AxisWeights(),
            convergence_threshold=HARD_THRESHOLD,
            seed=DETERMINISTIC_SEED,
        )
        assert easy.passed is True
        assert hard.passed is False
        # Both runs share the same composite -- only the gate changed.
        assert easy.composite_score == hard.composite_score

    def test_default_convergence_threshold_constant(self) -> None:
        # Tighten the contract on the documented default so future
        # PRD-driven tweaks force an explicit test update.
        assert CONVERGENCE_DEFAULT == 0.70

    def test_no_constitution_diagnostic_acknowledges_absence(self) -> None:
        candidate = _make_candidate({"main.css": "body { color: red; }"})
        result = evaluate_candidate(
            candidate,
            AxisWeights(),
            seed=DETERMINISTIC_SEED,
        )
        assert result.constitution_name is None
        assert "No constitution" in result.diagnostics["constitution"]
