"""Multi-surface product delivery (AT — pre-submission remediation A1).

A multi-surface run converges N surfaces in the runner (``screens_results``),
but the Studio could previously only render ``surfaces[0]``: the ``complete``
event never exposed a clean per-surface HTML map, so every non-primary surface
tab read ``undefined`` and was disabled. The fix exposes ``screens_html`` — a
flat ``{surface_name: best_candidate_html}`` map — on the enriched complete
payload so the frontend can render the whole product, not just the first
surface.
"""

from __future__ import annotations

from atelier.api.generate import _enrich_complete_payload

_HTML_L = (
    "<!DOCTYPE html><html lang='en'><head><title>Landing</title></head>"
    "<body><main><h1>Landing</h1><p>Hero copy.</p></main></body></html>"
)
_HTML_P = (
    "<!DOCTYPE html><html lang='en'><head><title>Pricing</title></head>"
    "<body><main><h1>Pricing</h1><p>Three tiers.</p></main></body></html>"
)


def test_enrich_complete_payload_exposes_every_converged_surface() -> None:
    """The complete event must carry a {surface: html} map for ALL surfaces."""
    payload = {
        "screens": {
            "landing page": {"best_candidate": _HTML_L},
            "pricing page": {"best_candidate": _HTML_P},
        },
        "best_candidate": _HTML_L,
        "evaluations": [],
    }

    enriched = _enrich_complete_payload(payload)

    assert enriched["screens_html"] == {
        "landing page": _HTML_L,
        "pricing page": _HTML_P,
    }


def test_enrich_complete_payload_skips_empty_surface_candidates() -> None:
    """A surface with no/empty best_candidate is omitted (never a blank tab)."""
    payload = {
        "screens": {
            "landing page": {"best_candidate": _HTML_L},
            "pricing page": {"best_candidate": ""},
            "dashboard": {"best_candidate": None},
        },
        "best_candidate": _HTML_L,
        "evaluations": [],
    }

    enriched = _enrich_complete_payload(payload)

    assert enriched["screens_html"] == {"landing page": _HTML_L}


def test_enrich_marks_nonconverged_complete_as_degraded() -> None:
    """L28: every `complete` carries an explicit `degraded` flag. A non-converged
    run must enrich to degraded=True so the Studio cannot take the success branch
    and report convergence over a sub-bar product. (With L10, `converged` reflects
    ALL surfaces, so a partially-converged product also lands here.)"""
    payload = {
        "screens": {"landing page": {"best_candidate": _HTML_L}},
        "best_candidate": _HTML_L,
        "evaluations": [],
        "converged": False,
    }

    enriched = _enrich_complete_payload(payload)

    assert enriched["degraded"] is True
    assert enriched.get("degradation_reason")


def test_enrich_does_not_force_degraded_on_a_converged_run() -> None:
    """A converged run must NOT be spuriously marked degraded."""
    payload = {
        "screens": {"landing page": {"best_candidate": _HTML_L}},
        "best_candidate": _HTML_L,
        "evaluations": [],
        "converged": True,
    }

    enriched = _enrich_complete_payload(payload)

    assert enriched.get("degraded", False) is False


def test_run_verdict_flags_a_planned_but_unproduced_surface() -> None:
    """The acceptance oracle is plan-seeded (A2): it requires EVERY surface the
    approved plan named, so a surface the run failed to produce fails
    ``surface:NAME:exists`` and the run is INCOMPLETE — honest about
    completeness, not self-satisfying on the produced set."""
    from atelier.api.generate import _build_run_verdict

    payload = {
        "plan": {"surfaces": ["landing page", "pricing page"]},
        # Only the landing page was produced; the planned pricing page was dropped.
        "screens": {"landing page": {"best_candidate": _HTML_L}},
        "best_candidate": _HTML_L,
        "session_id": "run-A2",
    }

    verdict = _build_run_verdict(payload)

    assert verdict is not None
    pricing_exists = [
        c for c in verdict["criteria"] if c["criterion_id"] == "surface:pricing page:exists"
    ]
    assert pricing_exists, "the dropped planned surface must be a required criterion"
    assert pricing_exists[0]["verdict"] is False
    assert verdict["complete"] is False
