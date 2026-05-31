"""AT-013 WCAG 2.2 AA contrast gate tests.

Covers :func:`atelier.gates.contrast.check_wcag_contrast` and its pure-function
helpers: ``_contrast_ratio``, ``_parse_color``, ``_relative_luminance``.

Gate contract under test:
- Returns GateOutcome on axis GateAxis.LIGHTHOUSE_A11Y.
- Scans style contexts for CSS rules that set BOTH color: AND background/background-color:.
- Computes WCAG 2.1/2.2 relative-luminance contrast ratio.
- AA: normal text >= 4.5:1; large text (font-size>=24px or >=18.66px bold) >= 3:1.
- Any same-rule pair below threshold → REJECT score 0.0.
- No parseable same-rule pairs → PASS (diagnostic mentions "no explicit same-rule").
- var(--x) resolved via CSS --x declarations in the same style text.
"""

from uuid import uuid4

import pytest
from atelier.gates.contrast import (
    _contrast_ratio,
    _parse_color,
    _relative_luminance,
    check_wcag_contrast,
)
from atelier.models.data_contracts import CandidateUI
from atelier.models.enums import GateAxis, GateDecision

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _candidate(artifacts: dict[str, str]) -> CandidateUI:
    return CandidateUI(
        candidate_id=uuid4(),
        surface_id=uuid4(),
        iteration=0,
        artifacts=artifacts,
    )


# ---------------------------------------------------------------------------
# 1. _contrast_ratio math
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_contrast_ratio_black_white() -> None:
    """Black on white must be exactly 21:1 (WCAG reference pair)."""
    result = _contrast_ratio((0, 0, 0), (255, 255, 255))
    assert abs(result - 21.0) < 0.01, f"Expected ~21.0, got {result}"


@pytest.mark.unit
def test_contrast_ratio_white_white() -> None:
    """White on white has ratio ~1.0 (no contrast)."""
    result = _contrast_ratio((255, 255, 255), (255, 255, 255))
    assert abs(result - 1.0) < 0.01, f"Expected ~1.0, got {result}"


# ---------------------------------------------------------------------------
# 2. _parse_color
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_parse_color_short_hex() -> None:
    assert _parse_color("#fff") == (255, 255, 255)


@pytest.mark.unit
def test_parse_color_full_hex() -> None:
    assert _parse_color("#3b82f6") == (59, 130, 246)


@pytest.mark.unit
def test_parse_color_rgb() -> None:
    assert _parse_color("rgb(255,0,0)") == (255, 0, 0)


@pytest.mark.unit
def test_parse_color_rgba_alpha_ignored() -> None:
    """rgba() alpha channel must be ignored; only RGB channels returned."""
    assert _parse_color("rgba(0,0,0,0.5)") == (0, 0, 0)


@pytest.mark.unit
def test_parse_color_hsl_red() -> None:
    """hsl(0,100%,50%) is pure red; allow ±2 per channel for rounding."""
    result = _parse_color("hsl(0,100%,50%)")
    assert result is not None
    r, g, b = result
    assert abs(r - 255) <= 2
    assert abs(g - 0) <= 2
    assert abs(b - 0) <= 2


@pytest.mark.unit
@pytest.mark.parametrize(
    "non_color",
    ["red", "none", "url(#x)", "currentColor"],
)
def test_parse_color_non_color_returns_none(non_color: str) -> None:
    """Named colors, none, url(), and currentColor must return None."""
    assert _parse_color(non_color) is None


# ---------------------------------------------------------------------------
# 3. Low-contrast inline style → REJECT
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_low_contrast_inline_style_rejects() -> None:
    """#bbbbbb on #ffffff ≈ 2.32:1 — below 4.5:1 AA threshold → REJECT score 0."""
    html = "<html><head><style>p{color:#bbbbbb;background:#ffffff}</style></head><body><p>hi</p></body></html>"
    outcome = check_wcag_contrast(_candidate({"index.html": html}))

    assert outcome.axis == GateAxis.LIGHTHOUSE_A11Y
    assert outcome.decision == GateDecision.REJECT
    assert outcome.score == 0.0
    assert "contrast" in outcome.diagnostic.lower()
    assert outcome.diagnostic.startswith("REJECT:")


# ---------------------------------------------------------------------------
# 4. High-contrast → PASS
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_high_contrast_passes() -> None:
    """#111111 on #ffffff ≈ 18.1:1 — well above 4.5:1 → PASS score 100."""
    css = "p{color:#111111;background:#ffffff}"
    outcome = check_wcag_contrast(_candidate({"main.css": css}))

    assert outcome.axis == GateAxis.LIGHTHOUSE_A11Y
    assert outcome.decision == GateDecision.PASS
    assert outcome.score == 100.0


# ---------------------------------------------------------------------------
# 5. var() token resolution → REJECT (low contrast via tokens)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_var_token_resolution_low_contrast_rejects() -> None:
    """var(--fg) resolves to #777777 (~4.48:1 on white — below 4.5 threshold)."""
    # #777777 on #ffffff ratio check:
    #   relative luminance of #777777 ≈ 0.2126*(0x77/255 linearised)*3 ≈ 0.1776
    #   L_white=1.0, ratio=(1.05)/(0.1776+0.05)=4.48 — just below 4.5
    ratio = _contrast_ratio((0x77, 0x77, 0x77), (0xFF, 0xFF, 0xFF))
    assert ratio < 4.5, f"Pre-condition failed: #777777 on white should be <4.5:1, got {ratio:.4f}"

    css = ":root{--fg:#777777;--bg:#ffffff}p{color:var(--fg);background:var(--bg)}"
    outcome = check_wcag_contrast(_candidate({"main.css": css}))

    assert outcome.decision == GateDecision.REJECT
    assert outcome.score == 0.0
    assert "contrast" in outcome.diagnostic.lower()


# ---------------------------------------------------------------------------
# 6. Large-text threshold: same pair, normal → REJECT, with font-size:28px → PASS
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_large_text_normal_text_rejects() -> None:
    """#8a8a8a on #ffffff ≈ 3.45:1 — below 4.5:1 for normal text → REJECT."""
    # Verify the ratio is strictly between 3.0 and 4.5 (computed via the helper itself)
    ratio = _contrast_ratio((0x8A, 0x8A, 0x8A), (0xFF, 0xFF, 0xFF))
    assert 3.0 < ratio < 4.5, f"Pre-condition failed: ratio={ratio:.4f} must be in (3.0, 4.5)"

    css = "p{color:#8a8a8a;background:#ffffff}"
    outcome = check_wcag_contrast(_candidate({"main.css": css}))

    assert outcome.decision == GateDecision.REJECT
    assert outcome.score == 0.0


@pytest.mark.unit
def test_large_text_with_font_size_passes() -> None:
    """Same #8a8a8a on #ffffff pair but font-size:28px → large text → 3:1 threshold → PASS."""
    ratio = _contrast_ratio((0x8A, 0x8A, 0x8A), (0xFF, 0xFF, 0xFF))
    assert ratio >= 3.0, f"Pre-condition: ratio={ratio:.4f} must be >=3.0 to PASS as large text"

    css = "p{color:#8a8a8a;background:#ffffff;font-size:28px}"
    outcome = check_wcag_contrast(_candidate({"main.css": css}))

    assert outcome.decision == GateDecision.PASS
    assert outcome.score == 100.0


# ---------------------------------------------------------------------------
# 7. No background in same rule → PASS, diagnostic mentions "no explicit same-rule"
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_pairs_passes_with_no_same_rule_diagnostic() -> None:
    """color: set without background in the same rule → no checkable pair → PASS."""
    css = "p{color:#111}"
    outcome = check_wcag_contrast(_candidate({"main.css": css}))

    assert outcome.decision == GateDecision.PASS
    assert outcome.score == 100.0
    assert "no explicit same-rule" in outcome.diagnostic


# ---------------------------------------------------------------------------
# 8. .css artifact path → REJECT
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_low_contrast_in_css_artifact_rejects() -> None:
    """Low-contrast pair in a .css artifact (not HTML) → REJECT."""
    css = "body{color:#cccccc;background-color:#ffffff}"
    outcome = check_wcag_contrast(_candidate({"main.css": css}))

    assert outcome.decision == GateDecision.REJECT
    assert outcome.score == 0.0
    assert "contrast" in outcome.diagnostic.lower()


# ---------------------------------------------------------------------------
# 9. APCA advisory string present in PASS and REJECT diagnostics
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_apca_advisory_in_reject_diagnostic() -> None:
    """REJECT diagnostic must contain 'APCA advisory' (non-gating notice)."""
    css = "p{color:#cccccc;background:#ffffff}"
    outcome = check_wcag_contrast(_candidate({"main.css": css}))
    assert outcome.decision == GateDecision.REJECT
    assert "APCA advisory" in outcome.diagnostic


@pytest.mark.unit
def test_apca_advisory_in_pass_diagnostic() -> None:
    """PASS diagnostic must contain 'APCA advisory' (non-gating notice)."""
    css = "p{color:#111111;background:#ffffff}"
    outcome = check_wcag_contrast(_candidate({"main.css": css}))
    assert outcome.decision == GateDecision.PASS
    assert "APCA advisory" in outcome.diagnostic
