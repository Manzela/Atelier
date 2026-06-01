"""AT-021 unit tests — QA critique panel + synthesizer.

PRD v2.2 §3.2 / §12 E2 (AT-021).

Three test arms:

  Arm #1 — Panel structure: ``create_critique_panel()`` returns a ``ParallelAgent``
            whose ``sub_agents`` carry the exact ``CRITIQUE_OUTPUT_KEYS`` contract,
            each with a non-empty description, with Visual-QA advisory-flagged.

  Arm #2 — Weighted-sum exact to 1e-6: ``AxisWeights.compute_composite`` returns the
            correct normalized weighted average for a fixed non-uniform weight + score
            combination.

  Arm #3 — Discrimination (P0 core): ``synthesize_panel`` correctly separates known-
            good candidates (passed=True, composite≥0.70) from known-bad ones
            (passed=False, composite<0.70). A sub-test proves the gate-floor is load-
            bearing: the adversarial token-drift and low-contrast fixtures score
            raw_composite≥0.70 (judges alone would wrongly pass them) while the floor
            rejects them — demonstrating the anti-inverted-gate guarantee (G2).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from atelier.models.axis_weights import AxisWeights
from atelier.models.data_contracts import CandidateUI
from atelier.nodes.critique_panel import (
    _CRITICS,
    CRITIQUE_OUTPUT_KEYS,
    GATE_FAIL_CAP,
    create_critique_panel,
    synthesize_panel,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_BODY = (
    "<header role='banner'>"
    "<nav aria-label='Main'><a href='#main'>Skip to content</a></nav>"
    "</header>"
    "<main id='main'>"
    "<article aria-labelledby='t'>"
    "<h1 id='t'>Quiet Co-working Spaces Designed for Deep Focus and Calm</h1>"
    "<p>Find a serene desk in a curated studio built for makers who need "
    "uninterrupted concentration and a welcoming community of peers.</p>"
    "<section aria-label='Features'>"
    "<h2>Why members stay with us</h2>"
    "<p>Ergonomic seating, soundproofed booths, barista coffee, and fast "
    "fibre internet across every floor.</p>"
    "</section>"
    "</article>"
    "<aside aria-label='Plans'>"
    "<h2>Membership plans</h2>"
    "<p>Flexible day passes and dedicated monthly desks tailored to your rhythm.</p>"
    "</aside>"
    "</main>"
    "<footer><img src='logo.png' alt='Studio logo'><p>Contact our team anytime.</p></footer>"
)


def _mk(html: str, css: str | None = None) -> CandidateUI:
    arts: dict[str, str] = {"index.html": html}
    if css is not None:
        arts["main.css"] = css
    return CandidateUI(candidate_id=uuid4(), surface_id=uuid4(), iteration=0, artifacts=arts)


def _page(bg: str, fg: str, extra: str = "") -> CandidateUI:
    """Build a rich, gate-clean candidate using var()-based CSS tokens."""
    css = (
        f":root{{--color-primary:#1a3d5c;--color-bg:{bg};--color-fg:{fg};--color-accent:#e07a3f;"
        "--space-sm:0.5rem;--space-md:1rem;--font-base:'Inter',sans-serif;--radius:8px}"
        "body{color:var(--color-fg);background:var(--color-bg);font-family:var(--font-base);"
        "font-size:18px;line-height:1.6;margin:0;padding:var(--space-md);letter-spacing:0.01em}"
        "header{display:flex;gap:var(--space-md)}nav a{padding:var(--space-sm);font-weight:600}"
        "main{display:grid;grid-template-columns:2fr 1fr;gap:var(--space-md)}"
        "h1{font-size:2.5rem;font-weight:800;margin:var(--space-md);color:var(--color-primary)}"
        "h2{font-size:1.5rem;font-weight:700}article{padding:var(--space-md);border-radius:var(--radius)}"
        "aside{background:var(--color-accent);padding:var(--space-md)}" + extra
    )
    return _mk(
        "<!DOCTYPE html><html lang='en'><head><title>Co</title></head><body>"
        + _BODY
        + "</body></html>",
        css,
    )


# ---------------------------------------------------------------------------
# Known-good fixtures (≥3 required; all must give passed=True, composite≥0.70)
# ---------------------------------------------------------------------------

#: Dark-on-light slate — the primary validated palette.
_GOOD_SLATE = _page("#f4f1ea", "#13293d")

#: Dark-on-light off-white / near-black — alternate high-contrast pair.
_GOOD_CHARCOAL = _page("#faf8f5", "#1c1c1e")

#: Dark navy on light warm-grey — benign extra rule (border-radius only).
_GOOD_NAVY = _page("#f0ebe3", "#0d2b45", "footer{border-radius:4px;padding:var(--space-md)}")

# Known-bad fixtures (adversarial / skeleton)
_BAD_SKELETON = _mk(
    "<!DOCTYPE html><html lang='en'><body><div>hello world</div></body></html>",
    "body{color:#000}",
)

_BAD_TOKEN_DRIFT = _page("#f4f1ea", "#13293d", "h2{color:#9b2d6f}")

_BAD_LOW_CONTRAST = _page("#ffffff", "#fefefe")


# ---------------------------------------------------------------------------
# Arm #1 — Panel structure
# ---------------------------------------------------------------------------


class TestPanelStructure:
    """create_critique_panel() returns a structurally-correct ParallelAgent."""

    def test_output_keys_set_matches_contract(self) -> None:
        """The sub_agents carry exactly the CRITIQUE_OUTPUT_KEYS set."""
        from google.adk.agents.parallel_agent import ParallelAgent

        panel = create_critique_panel()
        assert isinstance(panel, ParallelAgent)

        produced_keys = {getattr(agent, "output_key", None) for agent in panel.sub_agents}
        assert produced_keys == set(CRITIQUE_OUTPUT_KEYS), (
            f"sub_agent output_keys {produced_keys!r} must equal "
            f"CRITIQUE_OUTPUT_KEYS set {set(CRITIQUE_OUTPUT_KEYS)!r}"
        )

    def test_output_keys_order_matches_contract(self) -> None:
        """The sub_agents are in the same order as CRITIQUE_OUTPUT_KEYS."""
        panel = create_critique_panel()
        produced_order = tuple(getattr(agent, "output_key", None) for agent in panel.sub_agents)
        assert produced_order == CRITIQUE_OUTPUT_KEYS, (
            f"sub_agent output_key order {produced_order!r} must equal "
            f"CRITIQUE_OUTPUT_KEYS {CRITIQUE_OUTPUT_KEYS!r}"
        )

    def test_every_critic_has_nonempty_description(self) -> None:
        """Every sub_agent carries a non-empty description."""
        panel = create_critique_panel()
        for agent in panel.sub_agents:
            desc = getattr(agent, "description", None) or ""
            assert desc.strip(), (
                f"sub_agent {getattr(agent, 'name', agent)!r} has empty/missing description"
            )

    def test_visual_qa_critic_is_advisory(self) -> None:
        """The Visual-QA critic (_CRITICS[2]) is flagged advisory=True."""
        visual_qa = next(c for c in _CRITICS if c.output_key == "critique_visual_qa")
        assert visual_qa.advisory is True, (
            "VisualQACritic must be advisory=True (R6: never gates convergence)"
        )

    def test_non_advisory_critics_are_not_advisory(self) -> None:
        """Accessibility, Nielsen, Brand/Coherence must NOT be advisory."""
        non_advisory_keys = {
            "critique_accessibility",
            "critique_nielsen",
            "critique_brand_coherence",
        }
        for spec in _CRITICS:
            if spec.output_key in non_advisory_keys:
                assert spec.advisory is False, (
                    f"Critic {spec.name} ({spec.output_key}) should not be advisory"
                )


# ---------------------------------------------------------------------------
# Arm #2 — Weighted-sum exact to 1e-6
# ---------------------------------------------------------------------------


class TestWeightedSumExact:
    """AxisWeights.compute_composite matches hand-computed normalized weighted sum."""

    def test_compute_composite_exact(self) -> None:
        """Fixed non-uniform weights + fixed scores → composite exact to 1e-6.

        weights: brand=2, originality=1, relevance=1, accessibility=3, visual_clarity=1
        total = 8

        normalized:
          brand         = 2/8 = 0.25
          originality   = 1/8 = 0.125
          relevance     = 1/8 = 0.125
          accessibility = 3/8 = 0.375
          visual_clarity = 1/8 = 0.125

        scores:
          brand=0.80, originality=0.60, relevance=0.70, accessibility=0.90, visual_clarity=0.75

        hand-computed:
          0.25*0.80 + 0.125*0.60 + 0.125*0.70 + 0.375*0.90 + 0.125*0.75
          = 0.200 + 0.075 + 0.0875 + 0.3375 + 0.09375
          = 0.79375
        rounded to 4dp = 0.7938
        """
        weights = AxisWeights(
            brand=2,
            originality=1,
            relevance=1,
            accessibility=3,
            visual_clarity=1,
        )
        scores = {
            "brand": 0.80,
            "originality": 0.60,
            "relevance": 0.70,
            "accessibility": 0.90,
            "visual_clarity": 0.75,
        }

        # Hand-computed expected value (exact arithmetic, then rounded to 4dp
        # as compute_composite does).
        total_w = 2.0 + 1.0 + 1.0 + 3.0 + 1.0  # = 8
        expected = round(
            (2 / total_w) * 0.80
            + (1 / total_w) * 0.60
            + (1 / total_w) * 0.70
            + (3 / total_w) * 0.90
            + (1 / total_w) * 0.75,
            4,
        )

        result = weights.compute_composite(scores)
        assert abs(result - expected) < 1e-6, (
            f"compute_composite returned {result}; expected {expected} (delta > 1e-6)"
        )


# ---------------------------------------------------------------------------
# Arm #3 — Discrimination (P0 core)
# ---------------------------------------------------------------------------


class TestDiscrimination:
    """synthesize_panel correctly separates known-good from known-bad candidates."""

    # --- Known-bad parametrize ---

    @pytest.mark.parametrize(
        ("candidate", "label"),
        [
            (_BAD_SKELETON, "skeleton"),
            (_BAD_TOKEN_DRIFT, "token-drift"),
            (_BAD_LOW_CONTRAST, "low-contrast"),
        ],
    )
    def test_known_bad_is_rejected(self, candidate: CandidateUI, label: str) -> None:
        """Known-bad fixtures must be rejected: passed=False and composite ≤ GATE_FAIL_CAP."""
        verdict = synthesize_panel(candidate, AxisWeights(), seed=7)
        assert verdict.passed is False, (
            f"[{label}] expected passed=False, got passed=True "
            f"(panel_composite={verdict.panel_composite})"
        )
        assert verdict.panel_composite <= 0.55, (
            f"[{label}] expected panel_composite ≤ 0.55 (cap={GATE_FAIL_CAP}), "
            f"got {verdict.panel_composite}"
        )

    # --- Known-good parametrize ---

    @pytest.mark.parametrize(
        ("candidate", "label"),
        [
            (_GOOD_SLATE, "slate"),
            (_GOOD_CHARCOAL, "charcoal"),
            (_GOOD_NAVY, "navy"),
        ],
    )
    def test_known_good_passes(self, candidate: CandidateUI, label: str) -> None:
        """Known-good fixtures must pass: passed=True and composite ≥ 0.70."""
        verdict = synthesize_panel(candidate, AxisWeights(), seed=7)
        assert verdict.passed is True, (
            f"[{label}] expected passed=True, got passed=False "
            f"(panel_composite={verdict.panel_composite}, "
            f"raw_composite={verdict.raw_composite}, "
            f"floor_passed={verdict.floor_passed}, "
            f"gate_failures={verdict.gate_failures})"
        )
        assert verdict.panel_composite >= 0.70, (
            f"[{label}] expected panel_composite ≥ 0.70, got {verdict.panel_composite}"
        )

    # --- Gate-floor load-bearing sub-test (G2 anti-inverted-gate proof) ---

    @pytest.mark.parametrize(
        ("candidate", "label"),
        [
            (_BAD_TOKEN_DRIFT, "token-drift"),
            (_BAD_LOW_CONTRAST, "low-contrast"),
        ],
    )
    def test_gate_floor_is_load_bearing(self, candidate: CandidateUI, label: str) -> None:
        """Prove the gate-floor is load-bearing for adversarial fixtures.

        A judges-only synthesizer (no gate-floor) would rate these candidates
        ≥ 0.70 because the D-O-R-A-V judge composite scores the HTML/CSS quality
        and finds it rich (the adversarial fixtures are structurally correct;
        only one off-token color or a near-identical fg/bg pair violates the
        deterministic gates).

        The gate-floor is what rejects them:
          • raw_composite ≥ 0.70  → judges alone would WRONGLY pass
          • floor_passed = False  → deterministic gate caught the violation
          • passed = False        → the synthesizer correctly rejects

        This is the G2 anti-inverted-gate guarantee (AT-021 acceptance #3,
        mirrors AT-010): the probabilistic judge composite can never override
        a deterministic gate failure.
        """
        verdict = synthesize_panel(candidate, AxisWeights(), seed=7)

        # Judges alone would wrongly pass this candidate.
        assert verdict.raw_composite >= 0.70, (
            f"[{label}] raw_composite={verdict.raw_composite} < 0.70; "
            "fixture may not be gate-clean enough — enrich HTML/CSS content"
        )
        # The deterministic floor caught the violation.
        assert verdict.floor_passed is False, (
            f"[{label}] floor_passed=True; the adversarial gate was not triggered"
        )
        # The synthesizer correctly rejects despite the high judge composite.
        assert verdict.passed is False, (
            f"[{label}] passed=True despite floor_passed=False — "
            "the anti-inverted-gate guarantee (G2) is broken"
        )

    def test_token_drift_gate_failure_name(self) -> None:
        """Token-drift fixture records 'token-fidelity' in gate_failures."""
        verdict = synthesize_panel(_BAD_TOKEN_DRIFT, AxisWeights(), seed=7)
        assert "token-fidelity" in verdict.gate_failures, (
            f"Expected 'token-fidelity' in gate_failures, got {verdict.gate_failures!r}"
        )

    def test_low_contrast_contrast_flag(self) -> None:
        """Low-contrast fixture has contrast_passed=False."""
        verdict = synthesize_panel(_BAD_LOW_CONTRAST, AxisWeights(), seed=7)
        assert verdict.contrast_passed is False, (
            "Expected contrast_passed=False for near-identical fg/bg pair"
        )

    def test_panel_composite_capped_at_gate_fail_cap(self) -> None:
        """When the floor fails, panel_composite == min(raw, GATE_FAIL_CAP)."""
        for candidate, label in [
            (_BAD_TOKEN_DRIFT, "token-drift"),
            (_BAD_LOW_CONTRAST, "low-contrast"),
        ]:
            verdict = synthesize_panel(candidate, AxisWeights(), seed=7)
            expected_cap = round(min(verdict.raw_composite, GATE_FAIL_CAP), 4)
            assert abs(verdict.panel_composite - expected_cap) < 1e-6, (
                f"[{label}] panel_composite={verdict.panel_composite} != "
                f"min(raw={verdict.raw_composite}, cap={GATE_FAIL_CAP})={expected_cap}"
            )
