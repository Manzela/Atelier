"""AT-012 DTCG token-fidelity gate tests.

Covers the PRD AT-012 acceptance criteria for
:func:`atelier.gates.deterministic.check_token_fidelity`:

* Zero-tolerance off-token color literals → REJECT
* On-token (tokens.json + var(--…)) usage → PASS
* Malformed tokens.json is fail-closed
* Style detection limited to CSS contexts (not arbitrary HTML body text)
* Oracle independence: gate does not import any generator/node module
"""

import json
import re
from pathlib import Path
from uuid import uuid4

import pytest
from atelier.gates import deterministic
from atelier.gates.deterministic import check_token_fidelity
from atelier.models.data_contracts import CandidateUI
from atelier.models.enums import GateAxis, GateDecision

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DTCG_TWO_COLORS = json.dumps(
    {
        "color": {
            "primary": {"$value": "#2563eb", "$type": "color"},
            "surface": {"$value": "#ffffff", "$type": "color"},
        }
    }
)


def _candidate(artifacts: dict[str, str]) -> CandidateUI:
    return CandidateUI(
        candidate_id=uuid4(),
        surface_id=uuid4(),
        iteration=0,
        artifacts=artifacts,
    )


# ---------------------------------------------------------------------------
# 1. on_token PASS
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_on_token_pass() -> None:
    """Both token declarations and var() references; no raw off-token literals."""
    html = (
        "<html><head>"
        "<style>:root{--color-primary:#2563eb;--color-surface:#ffffff}</style>"
        "</head><body>"
        '<main style="color:var(--color-primary);background:var(--color-surface)">'
        "<h1>Hi</h1></main></body></html>"
    )
    candidate = _candidate({"index.html": html, "tokens.json": _DTCG_TWO_COLORS})
    outcome = check_token_fidelity(candidate)

    assert outcome.axis == GateAxis.TOKEN_FIDELITY
    assert outcome.decision == GateDecision.PASS


# ---------------------------------------------------------------------------
# 2. off_token REJECT(0)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_off_token_reject() -> None:
    """Raw literal #3b82f6 (not in tokens.json, not a --decl) → REJECT score 0."""
    html = (
        "<html><head>"
        "<style>:root{--color-primary:#2563eb;--color-surface:#ffffff}</style>"
        "</head><body>"
        '<main style="color:#3b82f6"><h1>Hi</h1></main>'
        "</body></html>"
    )
    candidate = _candidate({"index.html": html, "tokens.json": _DTCG_TWO_COLORS})
    outcome = check_token_fidelity(candidate)

    assert outcome.axis == GateAxis.TOKEN_FIDELITY
    assert outcome.decision == GateDecision.REJECT
    assert outcome.score == 0.0
    assert "off-token" in outcome.diagnostic


# ---------------------------------------------------------------------------
# 3. Adversarial off-token variants (parametrised)
# ---------------------------------------------------------------------------

_ADVERSARIAL_STYLE_CONTEXTS = [
    # inline style attr — hex literal
    (
        "index.html",
        '<html><head></head><body><div style="color:#ff0000">x</div></body></html>',
    ),
    # inline style attr — rgb()
    (
        "index.html",
        '<html><head></head><body><div style="color:rgb(255,0,0)">x</div></body></html>',
    ),
    # inline style attr — rgba()
    (
        "index.html",
        '<html><head></head><body><div style="color:rgba(255,0,0,0.5)">x</div></body></html>',
    ),
    # <style> block — hsl()
    (
        "index.html",
        "<html><head>"
        "<style>body{background:hsl(210,50%,50%)}</style>"
        "</head><body><p>hi</p></body></html>",
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize(("filename", "content"), _ADVERSARIAL_STYLE_CONTEXTS)
def test_adversarial_off_token_reject(filename: str, content: str) -> None:
    """Every raw color literal variant in a style context with NO matching token → REJECT."""
    candidate = _candidate({filename: content})
    outcome = check_token_fidelity(candidate)

    assert outcome.decision == GateDecision.REJECT, (
        f"Expected REJECT for off-token literal in {filename!r}"
    )
    assert outcome.score == 0.0
    assert "off-token" in outcome.diagnostic


# ---------------------------------------------------------------------------
# 4. Resolvable literal PASSES
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_raw_literal_matching_tokens_json_passes() -> None:
    """A raw literal that equals a tokens.json $value is treated as resolved → PASS."""
    # tokens.json defines #2563eb; HTML uses it raw in inline style
    html = '<html><head></head><body><main style="color:#2563eb"><h1>Hi</h1></main></body></html>'
    candidate = _candidate({"index.html": html, "tokens.json": _DTCG_TWO_COLORS})
    outcome = check_token_fidelity(candidate)

    assert outcome.decision == GateDecision.PASS


@pytest.mark.unit
def test_css_decl_and_var_reference_passes() -> None:
    """--color-x:#2563eb declared then var(--color-x) used → PASS."""
    html = (
        "<html><head>"
        "<style>:root{--color-x:#2563eb}</style>"
        "</head><body>"
        '<main style="color:var(--color-x)"><h1>Hi</h1></main>'
        "</body></html>"
    )
    candidate = _candidate({"index.html": html})
    outcome = check_token_fidelity(candidate)

    assert outcome.decision == GateDecision.PASS


# ---------------------------------------------------------------------------
# 5. Malformed tokens.json is fail-closed
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_malformed_tokens_json_fail_closed() -> None:
    """Malformed tokens.json → no allowed values → raw literal is off-token → REJECT."""
    html = '<html><head></head><body><main style="color:#3b82f6">x</main></body></html>'
    candidate = _candidate({"index.html": html, "tokens.json": "{not valid json"})
    outcome = check_token_fidelity(candidate)

    assert outcome.decision == GateDecision.REJECT
    assert outcome.score == 0.0


# ---------------------------------------------------------------------------
# 6. CSS artifact path
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_off_token_in_css_artifact_rejects() -> None:
    """Off-token literal in a .css file (not HTML) → REJECT."""
    css = "body { color: #deadbe; }"
    candidate = _candidate({"main.css": css})
    outcome = check_token_fidelity(candidate)

    assert outcome.decision == GateDecision.REJECT
    assert outcome.score == 0.0
    assert "off-token" in outcome.diagnostic


@pytest.mark.unit
def test_on_token_css_artifact_passes() -> None:
    """CSS file that declares --x:#2563eb and uses var(--x) → PASS."""
    css = ":root { --x: #2563eb; }\nbody { color: var(--x); }"
    candidate = _candidate({"main.css": css})
    outcome = check_token_fidelity(candidate)

    assert outcome.decision == GateDecision.PASS


@pytest.mark.unit
@pytest.mark.parametrize("attr", ["fill", "stroke", "stop-color"])
def test_svg_presentation_attr_off_token_rejects(attr: str) -> None:
    """Raw color in an SVG presentation attribute (fill/stroke/...) → REJECT.

    A token-bypass the CSS-only scan would miss (PR #35 review): SVG carries the
    color value directly on the attribute rather than via a style declaration.
    """
    html = f'<html><body><svg><rect {attr}="#3b82f6" /></svg></body></html>'
    candidate = _candidate({"index.html": html, "tokens.json": _DTCG_TWO_COLORS})
    outcome = check_token_fidelity(candidate)

    assert outcome.decision == GateDecision.REJECT
    assert outcome.score == 0.0
    assert "off-token" in outcome.diagnostic


@pytest.mark.unit
def test_svg_presentation_attr_on_token_passes() -> None:
    """SVG fill using a value that resolves to a tokens.json entry → PASS."""
    html = '<html><body><svg><rect fill="#2563eb" /></svg></body></html>'
    candidate = _candidate({"index.html": html, "tokens.json": _DTCG_TWO_COLORS})
    outcome = check_token_fidelity(candidate)

    assert outcome.decision == GateDecision.PASS


# ---------------------------------------------------------------------------
# 7. Source-guard: oracle independence
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_gate_module_does_not_import_generator_or_nodes() -> None:
    """The gate module must not import any generator/node module (oracle independence)."""
    source = Path(deterministic.__file__).read_text()

    # No import from atelier.nodes
    node_imports = [
        line
        for line in source.splitlines()
        if re.search(r"\bimport\b", line) and re.search(r"atelier\.nodes|from atelier\.nodes", line)
    ]
    assert not node_imports, (
        f"Gate imports atelier.nodes — oracle independence violated: {node_imports}"
    )

    # No 'generator' in any import line
    generator_imports = [
        line
        for line in source.splitlines()
        if re.search(r"\bimport\b", line) and "generator" in line.lower()
    ]
    assert not generator_imports, (
        f"Gate imports a generator module — oracle independence violated: {generator_imports}"
    )
