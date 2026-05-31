"""Gate discrimination: empty/skeleton REJECT, real candidates PASS (AT-010 / G2).

The pre-AT-010 stubs returned PASS at 95/90/85 on empty/missing index.html (G2,
the inverted-gate bug). These tests assert the credibility-core invariant (R2):
empty -> REJECT(0), skeleton -> REJECT(<floor), real -> PASS. They FAIL on the
pre-AT-010 code and PASS only after the inversion (TDD-on-bugfix, PRD §8).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import pytest
from atelier.gates import deterministic as deterministic_module
from atelier.gates.deterministic import (
    check_axe_stub,
    check_lighthouse_stub,
    check_visual_diff_stub,
)
from atelier.models.data_contracts import CandidateUI, GateOutcome
from atelier.models.enums import GateDecision

GateCheck = Callable[[CandidateUI], GateOutcome]

_STUBS: tuple[GateCheck, ...] = (check_lighthouse_stub, check_axe_stub, check_visual_diff_stub)

#: Real candidate pages -- standard structure + visible text; must PASS all stubs.
_REAL_PAGES = (
    "<html><header><nav>Home About</nav></header><main><section><h1>Welcome</h1>"
    "<p>This is a real landing page with substantive content.</p>"
    "<button>Get started</button></section></main><footer>Contact</footer></html>",
    "<html><header>Brand</header><main><article><h1>Pricing</h1><p>Choose a plan "
    "that fits your team.</p><section><h2>Pro</h2><p>$20/mo</p></section></article>"
    "</main><footer>(c) 2026</footer></html>",
    "<html><header><nav>Docs</nav></header><main><section><h1>Dashboard</h1>"
    "<p>Your metrics at a glance.</p><article><h2>Revenue</h2><p>Up 12%.</p>"
    "</article></section></main><footer>Help</footer></html>",
)

#: Adversarial near-empty / skeleton variants; must all REJECT (>= 5 per acceptance).
_SKELETONS = (
    "",  # truly empty
    "   \n  \t ",  # whitespace only
    "<html></html>",
    "<html><head></head><body></body></html>",
    "<div></div>",
    "<html><body><main></main></body></html>",  # single empty content element
    # script/style-only pages: "text" lives in non-rendered blocks (PR #33 nit).
    "<html><body><script>console.log('this is a long script body');</script></body></html>",
    "<html><head><style>.x{color:#fff;background:#000;padding:2rem}</style></head><body></body></html>",
    "<html><body><script>var a=1</script><script>var b=2</script></body></html>",
)


def _cand(html: str) -> CandidateUI:
    return CandidateUI(
        candidate_id=uuid4(), surface_id=uuid4(), iteration=0, artifacts={"index.html": html}
    )


@pytest.mark.unit
@pytest.mark.parametrize("check", _STUBS)
def test_empty_rejects_at_zero(check: GateCheck) -> None:
    """Empty/missing index.html -> REJECT at score 0 (was PASS at 95/90/85)."""
    outcome = check(_cand(""))
    assert outcome.decision is GateDecision.REJECT
    assert outcome.score == 0.0


@pytest.mark.unit
@pytest.mark.parametrize("check", _STUBS)
@pytest.mark.parametrize("skeleton", _SKELETONS)
def test_skeletons_reject_below_floor(check: GateCheck, skeleton: str) -> None:
    """Every adversarial skeleton REJECTs with a near-zero score (< 10 on 0-100)."""
    outcome = check(_cand(skeleton))
    assert outcome.decision is GateDecision.REJECT, f"skeleton passed: {skeleton!r}"
    assert outcome.score < 10.0


@pytest.mark.unit
@pytest.mark.parametrize("check", _STUBS)
@pytest.mark.parametrize("page", _REAL_PAGES)
def test_real_pages_pass(check: GateCheck, page: str) -> None:
    """Each real candidate PASSes every stub (discrimination, not blanket reject)."""
    outcome = check(_cand(page))
    assert outcome.decision is GateDecision.PASS, f"real page rejected by {check.__name__}"


@pytest.mark.unit
def test_source_wires_structure_floor_and_drops_inverted_bug() -> None:
    """CI guard: all three stubs route through the structure floor, and the
    inverted-gate fingerprint is gone from the source (AT-010 / G2).

    Positive: each stub calls ``_structure_floor_reject`` before scoring, so
    empty/skeleton HTML can never reach the heuristic. Negative: the old
    ``if not html: PASS @ 95/90/85`` fingerprint (its diagnostic and constants)
    is absent, so a copy-paste regression of the bug fails this guard.
    """
    src = Path(deterministic_module.__file__).read_text(encoding="utf-8")
    # Positive: one floor call-site per stub (lighthouse / axe / visual_diff).
    assert src.count("floor = _structure_floor_reject(") == len(_STUBS)
    # Negative: the inverted-bug fingerprints must not return.
    assert "returning conservative heuristic score" not in src, (
        "inverted-gate diagnostic resurfaced"
    )
    for const in ("LIGHTHOUSE_STUB_SCORE", "AXE_STUB_SCORE", "VISUAL_DIFF_STUB_SCORE"):
        assert not re.search(rf"score\s*=\s*{const}\b", src), (
            f"inverted-gate regression: {const} returned as a score"
        )
