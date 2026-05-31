"""AT-007 run-completion oracle tests.

Covers:
  - GOLDEN positive path (complete=True, composite >= 0.7)
  - Per-criterion verdict map coverage (all expected kinds present)
  - ≥6 known-bad fixtures, each asserting its SPECIFIC criterion_id in failed_criteria()
  - Adversarial oracle-independence test (skeleton candidate, agent state ignored)
  - Source-guard: oracle imports no generator/node module (§8 oracle independence)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import uuid4

import atelier.oracle.verify_run as vr_mod
import pytest
from atelier.models.acceptance import (
    AcceptanceCriteria,
    BrandConstraints,
)
from atelier.models.data_contracts import CandidateUI
from atelier.oracle.verify_run import verify_run

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# Minimal valid DTCG tokens.json with color, font, and space groups.
TOK = json.dumps(
    {
        "color": {"$type": "color", "primary": {"$value": "#2563eb"}},
        "font": {"$type": "dimension", "base": {"$value": "16px"}},
        "space": {"$type": "dimension", "md": {"$value": "16px"}},
    }
)

# Substantive, on-token HTML that passes all four non-LLM oracles.
# - has lang attr (axe: html-has-lang)
# - has title (axe: document-title)
# - has viewport meta (axe heuristic)
# - declares --fg / --bg as CSS custom properties (token fidelity)
# - body rule references var(--fg) / var(--bg) only (no raw literals)
# - fg=#111111, bg=#ffffff → contrast ratio ≈ 18.1:1 (AA pass)
# - has <main> and <nav> (structure floor: not skeleton)
GOLDEN_HTML = (
    "<html lang='en'><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>Landing</title>"
    "<style>:root{--fg:#111111;--bg:#ffffff}"
    "body{color:var(--fg);background:var(--bg)}</style></head>"
    "<body><main><h1>Welcome</h1><p>Real content.</p>"
    "<nav><a href='/'>Home</a></nav></main></body></html>"
)


def cand(html: str, tok: str = TOK, extra: dict[str, str] | None = None) -> CandidateUI:
    """Build a CandidateUI with index.html + tokens.json, plus optional extra artifacts."""
    art: dict[str, str] = {"index.html": html, "tokens.json": tok}
    if extra:
        art.update(extra)
    return CandidateUI(candidate_id=uuid4(), surface_id=uuid4(), iteration=0, artifacts=art)


def acc(**kw: object) -> AcceptanceCriteria:
    """Build an AcceptanceCriteria with sensible defaults for the 'landing' surface."""
    base: dict[str, object] = {
        "run_id": "r1",
        "brief_sha256": "abc",
        "required_surfaces": ["landing"],
        "required_token_groups": ["color", "font", "space"],
        "handoff_artifacts": ["tokens.json", "index.html", "style-dictionary outputs"],
    }
    base.update(kw)
    return AcceptanceCriteria(**base)


# ---------------------------------------------------------------------------
# Test 1 — GOLDEN positive
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_golden_positive_complete() -> None:
    """GOLDEN candidate → complete=True, no failed criteria, composite >= 0.7."""
    result = verify_run(acc(), {"landing": cand(GOLDEN_HTML)})

    assert result.complete is True
    assert result.failed_criteria() == []
    assert result.composite_by_surface["landing"] >= 0.7


# ---------------------------------------------------------------------------
# Test 2 — Per-criterion verdict map coverage
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_verdict_map_covers_all_criterion_kinds() -> None:
    """The returned criteria list contains all expected kind values."""
    result = verify_run(acc(), {"landing": cand(GOLDEN_HTML)})

    kinds_present = {c.kind for c in result.criteria}
    expected_kinds = {
        "surface_exists",
        "composite",
        "axe",
        "contrast",
        "token_fidelity",
        "token_group",
        "handoff",
    }
    assert expected_kinds <= kinds_present, (
        f"Missing criterion kinds: {expected_kinds - kinds_present}"
    )


@pytest.mark.unit
def test_verdict_map_contains_expected_criterion_ids() -> None:
    """Specific criterion_ids for landing surface + token groups + handoffs are present."""
    result = verify_run(acc(), {"landing": cand(GOLDEN_HTML)})

    ids = {c.criterion_id for c in result.criteria}
    # Surface-level
    assert "surface:landing:exists" in ids
    assert "surface:landing:composite" in ids
    assert "surface:landing:axe" in ids
    assert "surface:landing:contrast" in ids
    assert "surface:landing:token_fidelity" in ids
    # Token groups
    assert "token_group:color" in ids
    assert "token_group:font" in ids
    assert "token_group:space" in ids
    # Handoffs (style-dictionary outputs is a logical group)
    assert "handoff:tokens.json" in ids
    assert "handoff:index.html" in ids
    assert "handoff:style-dictionary outputs" in ids


# ---------------------------------------------------------------------------
# Test 3 — Known-bad fixtures (one per criterion)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_known_bad_surface_missing() -> None:
    """3a: no 'landing' candidate in surfaces → surface:landing:exists in failed."""
    result = verify_run(acc(), {})

    assert result.complete is False
    assert "surface:landing:exists" in result.failed_criteria()


@pytest.mark.unit
def test_known_bad_composite_below_min() -> None:
    """3b: skeleton HTML → surface:landing:composite in failed (structure floor = 0)."""
    skeleton_html = "<html><body></body></html>"
    result = verify_run(acc(), {"landing": cand(skeleton_html)})

    assert result.complete is False
    assert "surface:landing:composite" in result.failed_criteria()


@pytest.mark.unit
def test_known_bad_axe_violation() -> None:
    """3c: img without alt + empty button in otherwise-valid HTML → axe criterion fails.

    Injects violations into GOLDEN_HTML so the rest of the oracles see substantive
    content and valid tokens. The heuristic stub penalises missing alt and empty
    button even when chromium is unavailable (fail-soft path), so the test is
    environment-independent.
    """
    # Inject <img src='x.png'> (missing alt) and <button></button> (empty text)
    # into <main> so only a11y is affected; tokens + contrast remain intact.
    axe_html = GOLDEN_HTML.replace(
        "<p>Real content.</p>",
        "<p>Real content.</p><img src='x.png'><button></button>",
    )
    result = verify_run(acc(), {"landing": cand(axe_html)})

    assert result.complete is False
    assert "surface:landing:axe" in result.failed_criteria()


@pytest.mark.unit
def test_known_bad_token_fidelity_off_token_literal() -> None:
    """3d: raw off-token color literal in CSS class → token_fidelity in failed.

    Injects .extra{color:#ff00ff} into the <style> block — the color is not in
    tokens.json and is not a --token declaration, so it is an off-token literal.
    The injection is in a non-referenced class so axe-core does not flag it.
    """
    tok_html = GOLDEN_HTML.replace(
        ":root{--fg:#111111;--bg:#ffffff}",
        ":root{--fg:#111111;--bg:#ffffff}.extra{color:#ff00ff}",
    )
    result = verify_run(acc(), {"landing": cand(tok_html)})

    assert result.complete is False
    assert "surface:landing:token_fidelity" in result.failed_criteria()


@pytest.mark.unit
def test_known_bad_token_group_missing() -> None:
    """3e: required_token_groups includes 'elevation' absent from tokens.json → fails."""
    result = verify_run(
        acc(required_token_groups=["color", "font", "space", "elevation"]),
        {"landing": cand(GOLDEN_HTML)},
    )

    assert result.complete is False
    assert "token_group:elevation" in result.failed_criteria()


@pytest.mark.unit
def test_known_bad_handoff_artifact_missing() -> None:
    """3f: handoff_artifacts requires 'robots.txt' not in candidate artifacts → fails."""
    result = verify_run(
        acc(handoff_artifacts=["tokens.json", "index.html", "robots.txt"]),
        {"landing": cand(GOLDEN_HTML)},
    )

    assert result.complete is False
    assert "handoff:robots.txt" in result.failed_criteria()


@pytest.mark.unit
def test_known_bad_forbidden_color_present() -> None:
    """3g: --fg:#111111 declared in GOLDEN_HTML styles; #111111 is forbidden → fails."""
    result = verify_run(
        acc(brand_constraints=BrandConstraints(forbidden_colors=["#111111"])),
        {"landing": cand(GOLDEN_HTML)},
    )

    assert result.complete is False
    assert "forbidden_colors" in result.failed_criteria()


# ---------------------------------------------------------------------------
# Test 4 — Adversarial: oracle ignores agent convergence state
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_adversarial_oracle_ignores_agent_convergence() -> None:
    """Skeleton candidate → complete=False regardless of agent state.

    verify_run's signature is (AcceptanceCriteria, dict[str, CandidateUI]) —
    it accepts no convergence/composite argument and CANNOT read agent state.
    It recomputes composite from artifacts only, so a skeleton always fails.
    """
    # A skeleton with no visible text and fewer than two content elements.
    skeleton = "<html><body></body></html>"
    result = verify_run(acc(), {"landing": cand(skeleton)})

    # Oracle must not rubber-stamp a known-bad artifact just because an agent
    # might have set converged=True in its own state (G2 at the run level).
    assert result.complete is False
    assert "surface:landing:composite" in result.failed_criteria()


# ---------------------------------------------------------------------------
# Test 5 — Source-guard: oracle independence (§8)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_source_guard_oracle_does_not_import_generator_or_nodes() -> None:
    """verify_run must not import any generator/node module (oracle independence, §8).

    A CI grep enforces: no line in verify_run.py both contains 'import' and
    matches 'atelier.nodes' or the word 'generator'. Gates (atelier.gates.*)
    are explicitly allowed.
    """
    source = Path(vr_mod.__file__).read_text(encoding="utf-8")
    forbidden_pattern = re.compile(
        r"^.*import.*(?:atelier\.nodes|generator).*$",
        re.MULTILINE | re.IGNORECASE,
    )
    offending_lines = forbidden_pattern.findall(source)
    assert offending_lines == [], (
        f"verify_run.py imports a generator/node module (oracle independence violation §8): "
        f"{offending_lines}"
    )
