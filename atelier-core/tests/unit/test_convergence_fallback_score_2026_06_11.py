"""Degraded-pipeline root cause RC-2 / RC-3 (2026-06-11 staging regression).

The staging run the operator flagged as "broken, non-responsive" exposed a
self-heal trap: when NO candidate clears every N3c gate, the convergence engine
falls back to the best-scoring partial HTML candidate AND serves it — but it
returned a hard-pinned ``composite_score`` of ``0.0`` while the *same function*
already held the real fallback mean (``best_partial_score``). Because the loop
feeds that zeroed scalar into ``is_no_improvement(previous, current)``, the
second iteration always saw ``0.0 -> 0.0`` and stopped on ``no_improvement`` at
iteration 1 — euthanizing the Fixer self-heal regardless of real candidate
quality (the run never used its remaining iterations).

RC-2: the fallback path must report ``best_partial_score / 100`` as the
top-level ``composite_score``, matching the per-candidate ``scored_candidates``
entry the function already computed (the cross-check that was missing).

RC-3: with the honest score flowing, ``is_no_improvement`` discriminates a
genuinely improving fallback (continue) from a flat one (honest stop) — a thing
the zeroed scalar could never do.

Hermetic: ``run_gates`` is monkeypatched to fail, so no chromium / Vertex / net.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from atelier.models.enums import GateAxis, GateDecision
from atelier.orchestrator.runner import AtelierRunner, _looks_like_html
from atelier.orchestrator.stop_reason import is_no_improvement

pytestmark = pytest.mark.unit

# A real, renderable full document (passes _looks_like_html / survives
# normalization unchanged) so it is eligible as the best_partial_html fallback.
_HTML = (
    "<!DOCTYPE html>\n<html lang='en'><head><title>t</title></head>"
    "<body><main><h1>Hi</h1><p>x</p></main></body></html>"
)


def _failing_gates_at(mean_score: float):
    """run_gates double: every candidate FAILS, with a single outcome whose score
    drives the best_partial mean to ``mean_score`` (a renderable-but-sub-bar run)."""

    def _run(candidate, _axes):
        outcome = SimpleNamespace(
            axis=GateAxis.SEMANTIC_HTML,
            decision=GateDecision.REJECT,
            score=mean_score,
        )
        return SimpleNamespace(all_passed=False, outcomes=[outcome])

    return _run


def test_fallback_composite_score_is_best_partial_not_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("atelier.orchestrator.runner.run_gates", _failing_gates_at(64.0))
    runner = AtelierRunner()

    result = runner._run_n3c_n3d_n4([_HTML], "brief")

    # No candidate cleared the gates, yet a real fallback design is served ...
    assert result["candidates_passed_gates"] == 0
    assert result["best_candidate"], "fallback must surface a real screen"
    # ... and the top-level composite must be the partial mean, NOT a pinned 0.0.
    assert result["composite_score"] == pytest.approx(0.64)
    # The scalar must agree with the per-candidate entry the function also built.
    assert result["scored_candidates"][0]["composite_score"] == pytest.approx(
        result["composite_score"]
    )
    # A fallback candidate did not pass all gates → never reported as converged.
    assert result["converged"] is False


def test_fallback_score_lets_no_improvement_discriminate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # RC-3: drive two iterations' worth of fallback results and prove the honest
    # composite makes is_no_improvement answer differently for an improving run
    # vs a flat one — the discrimination the zeroed 0.0 -> 0.0 scalar destroyed.
    runner = AtelierRunner()

    monkeypatch.setattr("atelier.orchestrator.runner.run_gates", _failing_gates_at(64.0))
    iter0 = runner._run_n3c_n3d_n4([_HTML], "brief")["composite_score"]

    monkeypatch.setattr("atelier.orchestrator.runner.run_gates", _failing_gates_at(69.0))
    iter1_improved = runner._run_n3c_n3d_n4([_HTML], "brief")["composite_score"]

    monkeypatch.setattr("atelier.orchestrator.runner.run_gates", _failing_gates_at(64.0))
    iter1_flat = runner._run_n3c_n3d_n4([_HTML], "brief")["composite_score"]

    # Improving fallback (0.64 -> 0.69, Δ=0.05 > ε=0.02) → loop CONTINUES.
    assert is_no_improvement(iter0, iter1_improved) is False
    # Flat fallback (0.64 -> 0.64) → honest stop.
    assert is_no_improvement(iter0, iter1_flat) is True
    # The pre-fix world pinned both to 0.0, so it ALWAYS stopped — independent of
    # whether the Fixer actually improved the design. Guard that we left it.
    assert iter0 != 0.0


def test_last_resort_never_serves_non_renderable_prose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # RC-4 (backend never-blank): when NOT ONE raw event is gradable HTML (every
    # candidate was prose / markdown narration), the last-resort fallback used to
    # serve raw_candidates[0] verbatim — prose that renders as a BLANK,
    # non-responsive canvas (the exact staging symptom). The guard must instead
    # surface a minimal, VALID, honest acknowledgment document: never blank, never
    # a fake design, and the raw output preserved for reference.
    def _ungradable(candidate, _axes):
        return SimpleNamespace(all_passed=False, outcomes=[])

    monkeypatch.setattr("atelier.orchestrator.runner.run_gates", _ungradable)
    runner = AtelierRunner()

    prose = "I have analyzed the brief. The layout will use a sidebar and a main panel."
    result = runner._run_n3c_n3d_n4([prose], "brief")

    best = result["best_candidate"]
    assert best, "must never serve an empty screen"
    assert best.strip(), "must never serve a whitespace-only screen"
    assert _looks_like_html(best), "the served fallback must be a renderable document"
    assert "<html" in best.lower()
    # Honest, not a fabricated 'converged' design.
    assert result["converged"] is False
    # The raw specialist output is preserved (escaped) rather than silently dropped.
    assert "sidebar and a main panel" in best
    # The per-candidate entry mirrors the same renderable fallback (never raw prose).
    assert _looks_like_html(result["scored_candidates"][0]["html"])
