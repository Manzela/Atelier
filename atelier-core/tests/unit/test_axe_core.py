"""Real axe-core a11y gate (AT-011): discrimination + fail-soft degradation.

Browser tests (`@pytest.mark.browser`) launch chromium and run the dequelabs
axe-core engine; they skip when chromium is not launchable so the hermetic
``make verify`` lane stays cold-clone-runnable (chromium is a `make preflight`
prerequisite, not a `make verify` one). The structure-floor and fail-soft tests
need no browser and always run.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from atelier.gates import axe_core
from atelier.gates.axe_core import check_axe
from atelier.gates.deterministic import check_axe_stub
from atelier.models.data_contracts import CandidateUI
from atelier.models.enums import GateAxis, GateDecision
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


def _chromium_launchable() -> bool:
    try:
        with sync_playwright() as p:
            p.chromium.launch().close()
    except Exception:  # noqa: BLE001 — any launch failure means "skip browser tests"
        return False
    return True


_CHROMIUM = _chromium_launchable()
needs_chromium = pytest.mark.skipif(
    not _CHROMIUM, reason="chromium not launchable (run `playwright install chromium`)"
)


def _cand(html: str) -> CandidateUI:
    return CandidateUI(
        candidate_id=uuid4(), surface_id=uuid4(), iteration=0, artifacts={"index.html": html}
    )


#: Accessible page: lang, title, charset, landmarks, alt text, labelled control.
_ACCESSIBLE = (
    "<html lang='en'><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>Dashboard</title></head><body><main><h1>Welcome</h1>"
    "<p>Your metrics at a glance.</p><img src='logo.png' alt='Company logo'>"
    "<nav><a href='/home'>Home</a></nav></main></body></html>"
)

#: Inaccessible page: no lang/title, empty button + empty link, img w/o alt.
_INACCESSIBLE = (
    "<html><body><img src='x.png'><button></button><a href='#'></a>"
    "<main><h1>Hi</h1></main></body></html>"
)

#: TDD-red fixture: the browser-free heuristic PASSes it (no empty controls, no
#: img, has viewport), but real axe-core REJECTs it on serious page-level
#: violations the regex heuristic cannot see (missing <title>, missing html lang).
_STUB_BLIND_SPOT = (
    "<html><head><meta name='viewport' content='width=device-width'></head>"
    "<body><main><h1>Welcome</h1><p>Real, substantive content here.</p>"
    "<nav><a href='/home'>Home</a></nav></main></body></html>"
)


@pytest.mark.unit
def test_empty_rejects_before_browser() -> None:
    """Empty index.html → REJECT@0 via the structure floor (no browser launch)."""
    outcome = check_axe(_cand(""))
    assert outcome.axis is GateAxis.AXE
    assert outcome.decision is GateDecision.REJECT
    assert outcome.score == 0.0


@pytest.mark.unit
def test_skeleton_rejects_before_browser() -> None:
    """Skeleton HTML → REJECT via the structure floor, before any browser."""
    outcome = check_axe(_cand("<html><body></body></html>"))
    assert outcome.decision is GateDecision.REJECT
    assert outcome.score == 0.0


@pytest.mark.unit
def test_fail_soft_to_heuristic_when_chromium_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Browser-path error → fail-soft to the heuristic, ACKNOWLEDGED (R9).

    No chromium needed: the scan is monkeypatched to raise, exercising the
    fail-soft branch deterministically.
    """

    def _boom(_html: str) -> list[dict[str, object]]:
        raise PlaywrightError("chromium executable not found")

    monkeypatch.setattr(axe_core, "_scan_in_thread", _boom)
    outcome = check_axe(_cand(_ACCESSIBLE))
    # Degrades to the heuristic verdict (this page passes it) — does NOT raise.
    assert outcome.axis is GateAxis.AXE
    assert outcome.decision is check_axe_stub(_cand(_ACCESSIBLE)).decision
    assert outcome.diagnostic.startswith("DEGRADED (fail-soft):")


@pytest.mark.browser
@needs_chromium
def test_accessible_page_passes() -> None:
    """A real, accessible page → PASS (0 critical/serious axe-core violations)."""
    outcome = check_axe(_cand(_ACCESSIBLE))
    assert outcome.decision is GateDecision.PASS, outcome.diagnostic
    assert "real axe-core" in outcome.diagnostic


@pytest.mark.browser
@needs_chromium
def test_inaccessible_page_rejected() -> None:
    """A page with critical/serious violations → REJECT, naming the violations."""
    outcome = check_axe(_cand(_INACCESSIBLE))
    assert outcome.decision is GateDecision.REJECT, outcome.diagnostic
    assert "critical/serious" in outcome.diagnostic


@pytest.mark.browser
@needs_chromium
def test_real_axe_catches_what_heuristic_misses() -> None:
    """TDD-red (AT-011): the heuristic stub PASSes a page that real axe-core REJECTs.

    Proves the real gate adds discrimination over HEAD's browser-free proxy —
    the stub cannot see missing <title>/lang, which axe scores as serious.
    """
    cand = _cand(_STUB_BLIND_SPOT)
    assert check_axe_stub(cand).decision is GateDecision.PASS  # HEAD wrongly passes
    assert check_axe(cand).decision is GateDecision.REJECT  # real gate correctly fails
