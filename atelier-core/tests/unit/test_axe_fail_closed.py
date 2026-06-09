"""Regression tests for axe-core and verify_run fail-closed behavior under
non-PlaywrightError exceptions (finding 103).

The existing test_known_bad_axe_violation test only exercises the heuristic/
fail-soft path that fires on PlaywrightError or when chromium is absent.
These tests pin the invariant that:

  1. check_axe is total: _scan_in_thread raising any exception (not just
     PlaywrightError) must be handled by the fail-soft path, returning a
     GateOutcome instead of propagating.

  2. verify_run is total: when the axe scan errors and falls back to the
     heuristic, verify_run still returns a RunVerdict (never raises).  For
     HTML with heuristic-detectable violations the axe criterion is False and
     complete=False, confirming the fail-closed chain is intact.
"""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from atelier.models.acceptance import AcceptanceCriteria
from atelier.models.data_contracts import CandidateUI, GateOutcome
from atelier.models.enums import GateAxis
from atelier.oracle.verify_run import verify_run

# ---------------------------------------------------------------------------
# Shared helpers (mirrors test_verify_run.py without importing it)
# ---------------------------------------------------------------------------

_TOK = json.dumps(
    {
        "color": {"$type": "color", "primary": {"$value": "#2563eb"}},
        "font": {"$type": "dimension", "base": {"$value": "16px"}},
        "space": {"$type": "dimension", "md": {"$value": "16px"}},
    }
)

_GOLDEN_HTML = (
    "<html lang='en'><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>Landing</title>"
    "<style>:root{--fg:#111111;--bg:#ffffff}"
    "body{color:var(--fg);background:var(--bg)}</style></head>"
    "<body><main><h1>Welcome</h1><p>Real content.</p>"
    "<nav><a href='/'>Home</a></nav></main></body></html>"
)


def _cand(html: str = _GOLDEN_HTML) -> CandidateUI:
    return CandidateUI(
        candidate_id=uuid4(),
        surface_id=uuid4(),
        iteration=0,
        artifacts={"index.html": html, "tokens.json": _TOK},
    )


def _acc() -> AcceptanceCriteria:
    return AcceptanceCriteria(
        run_id="r1",
        brief_sha256="abc",
        required_surfaces=["landing"],
        required_token_groups=["color", "font", "space"],
        handoff_artifacts=["tokens.json", "index.html", "style-dictionary outputs"],
    )


# ---------------------------------------------------------------------------
# Finding 103 — test 1: check_axe fail-softs on non-PlaywrightError (OSError)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_check_axe_failsofts_on_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """check_axe must return a GateOutcome (not raise) when _scan_in_thread raises OSError.

    Confirms the ``except Exception`` catch in axe_core.check_axe covers
    non-PlaywrightError exceptions (OSError, MemoryError, RuntimeError, etc.).
    """
    import atelier.gates.axe_core as axe_mod
    from atelier.gates.axe_core import check_axe

    def _raise_os_error(_html: str) -> list[object]:
        raise OSError("chromium binary not found")

    monkeypatch.setattr(axe_mod, "_scan_in_thread", _raise_os_error)

    outcome = check_axe(_cand())

    assert isinstance(outcome, GateOutcome), "check_axe must return GateOutcome, not raise"
    assert outcome.axis == GateAxis.AXE
    assert "DEGRADED" in (outcome.diagnostic or ""), (
        "fail-soft diagnostic must contain 'DEGRADED' so the §14 trace can surface it"
    )


# ---------------------------------------------------------------------------
# Finding 103 — test 2: check_axe fail-softs on non-PlaywrightError (MemoryError)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_check_axe_failsofts_on_memory_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """check_axe must return a GateOutcome when _scan_in_thread raises MemoryError."""
    import atelier.gates.axe_core as axe_mod
    from atelier.gates.axe_core import check_axe

    def _raise_memory_error(_html: str) -> list[object]:
        raise MemoryError("OOM")

    monkeypatch.setattr(axe_mod, "_scan_in_thread", _raise_memory_error)

    outcome = check_axe(_cand())

    assert isinstance(outcome, GateOutcome)
    assert outcome.axis == GateAxis.AXE


# ---------------------------------------------------------------------------
# Finding 103 — test 3: verify_run is total when check_axe errors internally
# ---------------------------------------------------------------------------

# HTML that the heuristic stub rejects: enough accumulated penalties to score
# below the 70-point threshold.  5 images without alt (-6 each = -30) +
# 5 empty buttons (-8 each = -40) + no viewport meta (-10) = -80 -> score 20.
_HEAVY_AXE_HTML = (
    "<html lang='en'><head><meta charset='utf-8'>"
    "<title>Landing</title>"
    "<style>:root{--fg:#111111;--bg:#ffffff}"
    "body{color:var(--fg);background:var(--bg)}</style></head>"
    "<body><main><h1>Welcome</h1><p>Real content.</p>"
    "<img src='a.png'><img src='b.png'><img src='c.png'>"
    "<img src='d.png'><img src='e.png'>"
    "<button></button><button></button><button></button>"
    "<button></button><button></button>"
    "<nav><a href='/'>Home</a></nav></main></body></html>"
)


@pytest.mark.unit
def test_verify_run_total_when_axe_scan_raises_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """verify_run must return a RunVerdict (not raise) when the axe scan errors.

    Patches _scan_in_thread so it raises OSError.  check_axe converts this to
    a degraded GateOutcome via the heuristic fallback.  For HTML with enough
    heuristic-detectable violations to score below the 70-point REJECT threshold,
    the axe criterion is False, confirming the full fail-closed chain:
    OSError -> fail-soft -> heuristic REJECT -> verdict False -> complete False.
    """
    import atelier.gates.axe_core as axe_mod

    def _raise_os_error(_html: str) -> list[object]:
        raise OSError("disk full")

    monkeypatch.setattr(axe_mod, "_scan_in_thread", _raise_os_error)

    result = verify_run(_acc(), {"landing": _cand(_HEAVY_AXE_HTML)})

    # verify_run must return a RunVerdict, not propagate any exception.
    axe_verdicts = [c for c in result.criteria if c.kind == "axe"]
    assert axe_verdicts, "axe criterion must be present in the verdict map even under error"
    assert not axe_verdicts[0].verdict, (
        "axe criterion must be False for heavily-violated HTML in heuristic-fallback mode"
    )
    assert result.complete is False, "run must not be complete when axe detects violations"
    # Confirm the fail-soft diagnostic is present so operators can distinguish
    # a heuristic result from a real axe-core result.
    assert "DEGRADED" in (axe_verdicts[0].evidence_ref or ""), (
        "fail-soft evidence_ref must mention DEGRADED"
    )
