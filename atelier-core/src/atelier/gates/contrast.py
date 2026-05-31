"""WCAG 2.2 AA contrast oracle (AT-013, PRD §12 E1).

A pure-Python, browser-free contrast check run on the FINAL candidate (a
non-LLM oracle the AT-007 run-oracle recomputes the composite from, alongside
real axe-core AT-011 and DTCG fidelity AT-012). It complements axe-core: axe
needs a rendered DOM (computed styles); this gate is deterministic and offline,
and catches explicit low-contrast foreground/background pairs declared in the
same CSS rule.

**Gate:** for every CSS rule that sets both a foreground (``color``) and a
background (``background`` / ``background-color``) to a parseable color, compute
the WCAG 2.1/2.2 relative-luminance contrast ratio. AA requires ≥ 4.5:1 for
normal text and ≥ 3:1 for large text (≥ 24px, or ≥ 18.66px bold). Any pair below
its threshold → REJECT. ``var(--token)`` values are resolved against the
candidate's declared tokens + ``tokens.json``.

**Scope (honest):** full per-element contrast needs cascade resolution, which is
axe-core's job (AT-011, browser). This oracle checks same-rule pairs — a
conservative, deterministic subset. **APCA is advisory and intentionally NOT
computed here in V1** (it must not fabricate unverified constants and is never
the gating metric — WCAG 2.2 AA is); the diagnostic states this.

WCAG contrast math: https://www.w3.org/TR/WCAG22/#dfn-contrast-ratio
"""

from __future__ import annotations

import re

from atelier.gates.deterministic import (
    _COLOR_LITERAL_PATTERN,
    _CSS_RULESET_PATTERN,
    _collect_style_text,
    _normalize_color,
)
from atelier.models.data_contracts import CandidateUI, GateOutcome
from atelier.models.enums import GateAxis, GateDecision

#: WCAG 2.2 AA minimum contrast ratios.
_AA_NORMAL_RATIO = 4.5
_AA_LARGE_RATIO = 3.0
#: Large-text thresholds (CSS px): ≥ 24px, or ≥ 18.66px when bold (700+).
_LARGE_PX = 24.0
_LARGE_BOLD_PX = 18.66
#: sRGB companding break-point (WCAG relative-luminance formula).
_SRGB_LINEAR_THRESHOLD = 0.03928
#: r,g,b channel count required to form a color.
_RGB_CHANNEL_COUNT = 3

_COLOR_DECL_RE = re.compile(r"(?<![-\w])color\s*:\s*([^;}]+)", re.IGNORECASE)
_BG_DECL_RE = re.compile(r"background(?:-color)?\s*:\s*([^;}]+)", re.IGNORECASE)
_FONT_SIZE_RE = re.compile(r"font-size\s*:\s*([\d.]+)px", re.IGNORECASE)
_FONT_WEIGHT_RE = re.compile(r"font-weight\s*:\s*(\d+|bold)", re.IGNORECASE)
_VAR_REF_RE = re.compile(r"var\(\s*(--[a-zA-Z0-9_-]+)", re.IGNORECASE)
_VAR_DECL_RE = re.compile(r"(--[a-zA-Z0-9_-]+)\s*:\s*([^;}]+)")


def _srgb_channel_to_linear(value8: float) -> float:
    c = value8 / 255.0
    return c / 12.92 if c <= _SRGB_LINEAR_THRESHOLD else ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = (_srgb_channel_to_linear(channel) for channel in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    lum_fg, lum_bg = _relative_luminance(fg), _relative_luminance(bg)
    lighter, darker = max(lum_fg, lum_bg), min(lum_fg, lum_bg)
    return (lighter + 0.05) / (darker + 0.05)


def _hsl_to_rgb(h: float, s: float, lightness: float) -> tuple[int, int, int]:
    s /= 100.0
    lightness /= 100.0
    chroma = (1 - abs(2 * lightness - 1)) * s
    h_prime = (h % 360) / 60.0
    x = chroma * (1 - abs(h_prime % 2 - 1))
    r1, g1, b1 = {
        0: (chroma, x, 0.0),
        1: (x, chroma, 0.0),
        2: (0.0, chroma, x),
        3: (0.0, x, chroma),
        4: (x, 0.0, chroma),
        5: (chroma, 0.0, x),
    }[int(h_prime) % 6]
    m = lightness - chroma / 2
    return (round((r1 + m) * 255), round((g1 + m) * 255), round((b1 + m) * 255))


def _parse_color(literal: str) -> tuple[int, int, int] | None:  # noqa: PLR0911 — multi-format parser
    """Parse a hex / rgb()/rgba() / hsl()/hsla() literal to an (r,g,b) tuple.

    Alpha is ignored (contrast is computed on the opaque channels); returns None
    for anything unparseable (named colors, gradients, ``currentColor``, etc.).
    """
    text = literal.strip().lower()
    if text.startswith("#"):
        hex_digits = text[1:]
        if len(hex_digits) in (3, 4):
            hex_digits = "".join(ch * 2 for ch in hex_digits[:3])
        elif len(hex_digits) in (6, 8):
            hex_digits = hex_digits[:6]
        else:
            return None
        try:
            return (int(hex_digits[0:2], 16), int(hex_digits[2:4], 16), int(hex_digits[4:6], 16))
        except ValueError:
            return None
    rgb_match = re.match(r"rgba?\(([^)]*)\)", text)
    if rgb_match:
        parts = re.split(r"[,\s/]+", rgb_match.group(1).strip())
        try:
            channels = [
                round(float(p[:-1]) * 255 / 100) if p.endswith("%") else int(float(p))
                for p in parts[:3]
            ]
        except (ValueError, IndexError):
            return None
        if len(channels) < _RGB_CHANNEL_COUNT:
            return None
        return (
            max(0, min(255, channels[0])),
            max(0, min(255, channels[1])),
            max(0, min(255, channels[2])),
        )
    hsl_match = re.match(r"hsla?\(([^)]*)\)", text)
    if hsl_match:
        parts = re.split(r"[,\s/]+", hsl_match.group(1).strip())
        try:
            h = float(re.sub(r"deg$", "", parts[0]))
            s = float(parts[1].rstrip("%"))
            light = float(parts[2].rstrip("%"))
        except (ValueError, IndexError):
            return None
        return _hsl_to_rgb(h, s, light)
    return None


def _build_token_map(style_text: str) -> dict[str, str]:
    """Map each ``--token`` name → its color literal value, from CSS declarations.

    CSS ``--decls`` carry the name→value binding the candidate actually
    references (a DTCG ``tokens.json`` keys by DTCG path, not CSS var name, so it
    cannot resolve ``var(--x)`` without the binding the CSS already provides)."""
    token_map: dict[str, str] = {}
    for name, value in _VAR_DECL_RE.findall(style_text):
        literals = _COLOR_LITERAL_PATTERN.findall(value)
        if literals:
            token_map[name] = literals[0]
    return token_map


def _resolve_to_color(raw_value: str, token_map: dict[str, str]) -> tuple[int, int, int] | None:
    """Resolve a CSS value (literal or single ``var(--x)``) to an (r,g,b)."""
    var_match = _VAR_REF_RE.search(raw_value)
    if var_match:
        mapped = token_map.get(var_match.group(1))
        return _parse_color(mapped) if mapped else None
    literals = _COLOR_LITERAL_PATTERN.findall(raw_value)
    return _parse_color(literals[0]) if literals else None


def _required_ratio(rule_body: str) -> float:
    """AA threshold for a rule: 3:1 if its text is 'large', else 4.5:1."""
    size_match = _FONT_SIZE_RE.search(rule_body)
    weight_match = _FONT_WEIGHT_RE.search(rule_body)
    px = float(size_match.group(1)) if size_match else 0.0
    bold = weight_match is not None and weight_match.group(1) in ("bold", "700", "800", "900")
    if px >= _LARGE_PX or (bold and px >= _LARGE_BOLD_PX):
        return _AA_LARGE_RATIO
    return _AA_NORMAL_RATIO


def check_wcag_contrast(candidate: CandidateUI) -> GateOutcome:
    """WCAG 2.2 AA contrast oracle over same-rule fg/bg color pairs (AT-013).

    PASS if no same-rule color+background pair falls below its AA threshold (and
    when there are no parseable pairs to check — full cascade contrast is axe-core
    AT-011's responsibility). REJECT naming the worst offender(s). APCA advisory
    only (not gated, not computed in V1).
    """
    style_text = _collect_style_text(candidate.artifacts)
    token_map = _build_token_map(style_text)

    violations: list[str] = []
    pairs_checked = 0
    for selector, body in _CSS_RULESET_PATTERN.findall(style_text):
        color_match = _COLOR_DECL_RE.search(body)
        bg_match = _BG_DECL_RE.search(body)
        if not color_match or not bg_match:
            continue
        fg = _resolve_to_color(color_match.group(1), token_map)
        bg = _resolve_to_color(bg_match.group(1), token_map)
        if fg is None or bg is None:
            continue
        pairs_checked += 1
        ratio = _contrast_ratio(fg, bg)
        threshold = _required_ratio(body)
        if ratio < threshold:
            violations.append(
                f"{selector.strip()[:40]!r}: {ratio:.2f}:1 < {threshold:.1f}:1 "
                f"(fg={_normalize_color(color_match.group(1))}, bg={_normalize_color(bg_match.group(1))})"
            )

    if violations:
        listed = "; ".join(violations[:6])
        return GateOutcome(
            candidate_id=candidate.candidate_id,
            axis=GateAxis.LIGHTHOUSE_A11Y,
            decision=GateDecision.REJECT,
            score=0.0,
            diagnostic=(
                f"REJECT: {len(violations)} WCAG 2.2 AA contrast violation(s): {listed}. "
                "(APCA advisory — not gated.)"
            ),
        )

    detail = (
        f"{pairs_checked} fg/bg pair(s) ≥ AA threshold"
        if pairs_checked
        else "no explicit same-rule fg/bg pairs (cascade contrast covered by axe-core AT-011)"
    )
    return GateOutcome(
        candidate_id=candidate.candidate_id,
        axis=GateAxis.LIGHTHOUSE_A11Y,
        decision=GateDecision.PASS,
        score=100.0,
        diagnostic=f"PASS: WCAG 2.2 AA contrast — {detail}. (APCA advisory — not gated.)",
    )
