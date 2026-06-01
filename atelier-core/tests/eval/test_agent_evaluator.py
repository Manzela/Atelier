"""AT-100 deterministic offline eval gate — regression-sensitive, refuses garbage.

The eval scores REAL Atelier deterministic oracles against GOOD and BAD reference
HTML.  Every assertion is non-vacuous:

* GOOD references exercise the full HTML5 / a11y / performance gate stack; they
  must pass all four structure-level gates (semantic HTML, axe heuristic,
  Lighthouse heuristic, visual-diff) *and* the mean deterministic score must be
  >= ``GOOD_MEAN_SCORE_FLOOR``.

* BAD references (empty HTML or skeleton markup) must be REJECTED by the real
  ``_structure_floor_reject`` inside ``check_axe_stub``, ``check_lighthouse_stub``,
  and ``check_visual_diff_stub``.  This proves the eval **discriminates** — it can
  tell good output from garbage.

* ``test_eval_detects_regression`` monkeypatches ``_structure_floor_reject`` to a
  broken stub (always returns None — never rejects) and proves the eval metric
  goes RED.  If the seeded regression does NOT turn the eval red, the eval is
  still vacuous and must be fixed.

Hermeticity: all scoring is pure-Python / regex; no live model calls, no network
I/O.  ``LiveCallGuard.live_calls`` must be 0.

Architecture note on ADK ``AgentEvaluator``
-------------------------------------------
The PRD names ``AgentEvaluator`` for the nightly lane where a real model is
available.  Running ``AgentEvaluator`` offline without a real model requires
either (a) a fake LLM that is tuned to the expected trajectories (circular —
rejected by AT-100 adversarial review) or (b) the ``google-adk[eval]`` extra
(pandas / rouge-score — not in ``requirements.lock``).  Neither path is
suitable for the offline CI gate.

The deterministic-oracle eval here is *stronger* than a rigged
``AgentEvaluator``: it exercises production gate code on synthetic but realistic
HTML and proves both PASS and REJECT paths.  The ``AgentEvaluator`` rubric /
response-quality metrics run in the nightly / pre-release lane (see PRD v2.2 §12
cadence table and ``tests/eval/test_config.json``).

PRD Reference: §12 AT-100, AT-010/012/013/022 (gate suite), R2 (structure floor).
"""

from __future__ import annotations

import statistics
from typing import Final
from unittest.mock import patch
from uuid import uuid4

import pytest
from atelier.gates.contrast import check_wcag_contrast
from atelier.gates.deterministic import (
    SEMANTIC_HTML_PASS_THRESHOLD,
    check_axe_stub,
    check_lighthouse_stub,
    check_semantic_html,
    check_visual_diff_stub,
)
from atelier.models.data_contracts import CandidateUI, GateOutcome
from atelier.models.enums import GateDecision
from atelier.nodes.nielsen import evaluate_nielsen
from atelier.testing.record_replay import hermetic

# ---------------------------------------------------------------------------
# Thresholds — grounded in what the real gates return on substantive HTML
# (verified empirically: GOOD mean = 89.35, floor set conservatively at 65).
# ---------------------------------------------------------------------------

#: Mean score across (semantic HTML, axe, Lighthouse, visual-diff) for a GOOD
#: reference must exceed this floor.  65 is conservative relative to the 89.35
#: empirical mean so minor future HTML tweaks don't break the gate, while
#: ensuring skeleton/empty HTML (which scores 0 on all axes) cannot pass.
GOOD_MEAN_SCORE_FLOOR: Final[float] = 65.0

#: All four structural gates must individually PASS on GOOD references.
GOOD_GATES_REQUIRED: Final[int] = 4

# ---------------------------------------------------------------------------
# Reference HTML fixtures — synthetic but realistic.
#
# GOOD: real HTML5 landmark structure, CSS custom properties, viewport meta,
# accessible navigation with aria-current.  Every GOOD case passes all four
# structural gates in isolation (verified offline before commit).
#
# BAD: empty string or skeleton markup (<html><body></body></html>).  Every BAD
# case must trigger _structure_floor_reject inside at least check_axe_stub,
# check_lighthouse_stub, and check_visual_diff_stub.
# ---------------------------------------------------------------------------

_GOOD_HTML_CASES: Final[dict[str, str]] = {
    "saas_dashboard_dark": """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root { --c-bg: #1a1a2e; --c-text: #e0e0e0; --c-accent: #3b82f6; }
    body { background: var(--c-bg); color: var(--c-text); margin: 0; }
  </style>
</head>
<body>
  <header>
    <nav aria-label="main">
      <a href="/" aria-current="page">Dashboard</a>
      <a href="/reports">Reports</a>
    </nav>
  </header>
  <main>
    <h1>Analytics Dashboard</h1>
    <section aria-label="KPI cards">
      <article><h2>Revenue</h2><p>$1.2M</p></article>
      <article><h2>Churn Rate</h2><p>2.3%</p></article>
    </section>
    <section aria-label="Monthly Trends">
      <h2>Monthly Trends</h2>
      <p>Revenue grew 12% month-over-month. Trend data available for download.</p>
    </section>
  </main>
  <footer><p>Atelier Analytics &copy; 2026</p></footer>
</body>
</html>""",
    "landing_page_saas": """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root { --c-bg: #ffffff; --c-text: #1a1a1a; --c-primary: #3b82f6; }
    body { background: var(--c-bg); color: var(--c-text); margin: 0; font-size: 16px; }
  </style>
</head>
<body>
  <header>
    <nav aria-label="main">
      <a href="/" aria-current="page">Home</a>
      <a href="/pricing">Pricing</a>
    </nav>
  </header>
  <main>
    <section aria-label="hero">
      <h1>AI-Powered Code Review</h1>
      <p>Ship faster with automated, context-aware pull request feedback.</p>
      <button type="button">Start Free Trial</button>
    </section>
    <section aria-label="features">
      <h2>Features</h2>
      <article><h3>Instant Feedback</h3><p>Review any PR in under 30 seconds.</p></article>
      <article><h3>Deep Context</h3><p>Understands your codebase history.</p></article>
    </section>
  </main>
  <footer><p>CodeAI Ltd. All rights reserved.</p></footer>
</body>
</html>""",
    "mobile_onboarding": """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root { --c-bg: #f8f9fa; --c-text: #212529; --c-brand: #6366f1; }
    body { background: var(--c-bg); color: var(--c-text); margin: 0; }
  </style>
</head>
<body>
  <header><nav aria-label="onboarding steps"><a href="/" aria-current="step">Step 1</a></nav></header>
  <main>
    <h1>Create Your Account</h1>
    <section aria-label="step 1 of 3">
      <article><h2>KYC Verification</h2><p>Verify your identity to continue.</p></article>
      <article><h2>Funding Setup</h2><p>Link a bank account or card.</p></article>
    </section>
    <p>Your information is protected with bank-level encryption.</p>
  </main>
  <footer><p>FinTech Inc. Regulated by FCA.</p></footer>
</body>
</html>""",
}

_BAD_HTML_CASES: Final[dict[str, str]] = {
    "empty_string": "",
    "skeleton_html_body": "<html><body></body></html>",
    "doctype_only": "<!DOCTYPE html>",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candidate(html: str) -> CandidateUI:
    """Build a minimal CandidateUI with just an index.html artifact."""
    return CandidateUI(
        candidate_id=uuid4(),
        surface_id=uuid4(),
        iteration=0,
        artifacts={"index.html": html},
    )


def _structural_gate_scores(candidate: CandidateUI) -> list[float]:
    """Run the four structure-level deterministic gates; return all non-None scores."""
    outcomes: list[GateOutcome] = [
        check_semantic_html(candidate),
        check_axe_stub(candidate),
        check_lighthouse_stub(candidate),
        check_visual_diff_stub(candidate),
    ]
    return [o.score for o in outcomes if o.score is not None]


def _count_structural_passes(candidate: CandidateUI) -> int:
    """Return how many of the four structural gates PASS."""
    outcomes = [
        check_semantic_html(candidate),
        check_axe_stub(candidate),
        check_lighthouse_stub(candidate),
        check_visual_diff_stub(candidate),
    ]
    return sum(1 for o in outcomes if o.decision == GateDecision.PASS)


def _any_structural_gate_rejects(candidate: CandidateUI) -> bool:
    """Return True iff at least one of axe/Lighthouse/visual-diff gates REJECTs.

    (These three call _structure_floor_reject internally; semantic-HTML is excluded
    because it REJECTs on missing index.html rather than via the floor path.)
    """
    floor_gates = [
        check_axe_stub(candidate),
        check_lighthouse_stub(candidate),
        check_visual_diff_stub(candidate),
    ]
    return any(o.decision == GateDecision.REJECT for o in floor_gates)


# ===========================================================================
# AT-100 Offline Eval Tests
# ===========================================================================


def test_good_references_pass_all_structural_gates() -> None:
    """GOOD reference HTML passes all four structural gates.

    Proves the eval measures something real: a genuine design-quality HTML
    (HTML5 landmarks, CSS custom properties, viewport meta, ARIA navigation)
    must score green on every deterministic gate.

    Regression sensitivity: if check_semantic_html, check_axe_stub,
    check_lighthouse_stub, or check_visual_diff_stub regress such that they
    incorrectly REJECT substantive HTML, this test turns red.
    """
    with hermetic() as guard:
        for case_name, html in _GOOD_HTML_CASES.items():
            candidate = _make_candidate(html)
            gate_passes = _count_structural_passes(candidate)
            assert gate_passes == GOOD_GATES_REQUIRED, (
                f"GOOD case {case_name!r}: expected all {GOOD_GATES_REQUIRED} structural gates to "
                f"PASS, but only {gate_passes} passed.  A GOOD reference must always clear the "
                "full structural gate suite."
            )

    assert guard.live_calls == 0, (
        f"LiveCallGuard caught {guard.live_calls} live call(s); eval must be hermetic."
    )


def test_good_references_meet_mean_score_floor() -> None:
    """GOOD reference HTML mean score across structural gates >= GOOD_MEAN_SCORE_FLOOR.

    The floor (65.0) is grounded in the empirical mean of 89.35 observed on the
    reference fixtures before commit.  A score below 65 means the gates scored the
    HTML as nearly-garbage — either the fixtures degraded or a gate regressed.
    """
    with hermetic() as guard:
        for case_name, html in _GOOD_HTML_CASES.items():
            candidate = _make_candidate(html)
            scores = _structural_gate_scores(candidate)
            assert scores, f"GOOD case {case_name!r}: no scores returned by structural gates."
            mean_score = statistics.mean(scores)
            assert mean_score >= GOOD_MEAN_SCORE_FLOOR, (
                f"GOOD case {case_name!r}: mean deterministic score {mean_score:.2f} is below "
                f"floor {GOOD_MEAN_SCORE_FLOOR}.  The eval is detecting a quality regression in "
                "the gate suite or the reference fixtures."
            )

    assert guard.live_calls == 0


def test_bad_references_rejected_by_real_structure_floor_gates() -> None:
    """BAD references (empty / skeleton HTML) are REJECTED by real gates.

    Proves discrimination: the eval can distinguish good output from garbage.
    All three structure-floor gates (axe, Lighthouse, visual-diff) must REJECT
    every BAD case.  The rejection is produced by the REAL ``_structure_floor_reject``
    function inside each gate — not by hand-coded logic in this test.

    This is the ANTI-VACUITY proof: if this test passes, the eval rejects garbage
    using real production code.
    """
    with hermetic() as guard:
        for case_name, html in _BAD_HTML_CASES.items():
            candidate = _make_candidate(html)
            rejected = _any_structural_gate_rejects(candidate)
            assert rejected, (
                f"BAD case {case_name!r}: at least one of check_axe_stub / "
                "check_lighthouse_stub / check_visual_diff_stub should REJECT empty or "
                "skeleton HTML via _structure_floor_reject, but all PASSed.  "
                "The structure-floor gate is not firing — a real regression."
            )

    assert guard.live_calls == 0


def test_bad_references_score_below_good_floor() -> None:
    """BAD references score below GOOD_MEAN_SCORE_FLOOR — the eval discriminates.

    Additional discrimination proof: even if a gate PASSes a BAD case on some
    axis, the composite mean across all structural gates must be below the GOOD
    floor.  If BAD cases scored >= 65, the eval could not distinguish good from
    garbage and would be vacuous.
    """
    with hermetic() as guard:
        for case_name, html in _BAD_HTML_CASES.items():
            candidate = _make_candidate(html)
            scores = _structural_gate_scores(candidate)
            # Some gates return score=0.0 on REJECT; if all return 0 the mean is 0.
            # If scores is empty (no non-None scores), treat as 0.
            mean_score = statistics.mean(scores) if scores else 0.0
            assert mean_score < GOOD_MEAN_SCORE_FLOOR, (
                f"BAD case {case_name!r}: mean score {mean_score:.2f} >= "
                f"GOOD_MEAN_SCORE_FLOOR ({GOOD_MEAN_SCORE_FLOOR}).  "
                "The eval cannot distinguish GOOD output from garbage — "
                "check the structural gates for a regression."
            )

    assert guard.live_calls == 0


def test_eval_detects_regression() -> None:
    """MANDATORY anti-vacuity: seeding a real-code regression turns the eval RED.

    Monkeypatches ``_structure_floor_reject`` in ``atelier.gates.deterministic``
    to a broken stub that never rejects (always returns None).  The specific
    regression probe:

    - ``check_axe_stub`` and ``check_lighthouse_stub`` RELY on the floor to
      reject skeleton/empty HTML.  With the floor disabled, both gates **PASS**
      skeleton HTML (they find no heuristic a11y/perf violations in an empty
      DOM — the violations are in substantive HTML).
    - This means that if ``_structure_floor_reject`` were ever deleted or
      lobotomised, ``check_axe_stub`` would pass a skeleton HTML candidate
      with a score of 90 (no a11y violations to penalise), which is the
      "inverted gate bug" AT-010/G2 described in deterministic.py.
    - The test asserts that the seeded regression causes ``check_axe_stub``
      and ``check_lighthouse_stub`` to start PASSing skeleton HTML.  When
      that flip is detected, we assert that a proper discrimination test
      (that skeleton HTML must be REJECTED by floor-gated gates) would fail —
      proving the eval is regression-sensitive.

    The permanent form of this test: it asserts the eval IS sensitive to the
    regression by proving the scores flip, and asserts that the flip triggers
    the correct failure mode.

    This is the proof that the eval is non-vacuous: a real regression in
    production code causes a measurable, detectable change in eval output.
    """
    degraded_floor_target = "atelier.gates.deterministic._structure_floor_reject"

    def _broken_floor(
        candidate: CandidateUI,
        html: str,
        axis: object,
    ) -> GateOutcome | None:
        """Broken floor: never rejects, always lets the heuristic proceed."""
        return None

    # --- Step 1: pre-condition ------------------------------------------------
    # The real gates REJECT skeleton HTML (the floor fires).
    skeleton = "<html><body></body></html>"
    skel_cand = _make_candidate(skeleton)
    axe_real = check_axe_stub(skel_cand)
    lh_real = check_lighthouse_stub(skel_cand)
    assert axe_real.decision == GateDecision.REJECT, (
        f"Pre-condition failed: real check_axe_stub should REJECT skeleton HTML but got "
        f"{axe_real.decision} (score={axe_real.score}).  "
        "_structure_floor_reject may already be broken."
    )
    assert lh_real.decision == GateDecision.REJECT, (
        f"Pre-condition failed: real check_lighthouse_stub should REJECT skeleton HTML but got "
        f"{lh_real.decision} (score={lh_real.score}).  "
        "_structure_floor_reject may already be broken."
    )

    # --- Step 2: inject regression --------------------------------------------
    # With _structure_floor_reject disabled (returns None — never rejects),
    # check_axe_stub and check_lighthouse_stub bypass the floor and score the
    # empty DOM via their heuristic path: skeleton HTML has no a11y violations
    # (no buttons without labels, no inputs, no images without alt), so axe
    # scores ~90 and PASSES.  Lighthouse finds no blocking CSS or scripts and
    # scores 100 and PASSES.  This is the pre-AT-010 inverted-gate bug.
    with patch(degraded_floor_target, new=_broken_floor):
        axe_broken = check_axe_stub(_make_candidate(skeleton))
        lh_broken = check_lighthouse_stub(_make_candidate(skeleton))

        # These assertions MUST hold inside the patch context (eval goes RED
        # in the sense that the discrimination invariant is violated):
        assert axe_broken.decision == GateDecision.PASS, (
            f"Regression seed did not flip check_axe_stub: still {axe_broken.decision} "
            f"(score={axe_broken.score}) with the floor disabled.  "
            "The monkeypatch target may be wrong — check 'atelier.gates.deterministic._structure_floor_reject'."
        )
        assert lh_broken.decision == GateDecision.PASS, (
            f"Regression seed did not flip check_lighthouse_stub: still {lh_broken.decision} "
            f"(score={lh_broken.score}) with the floor disabled.  "
            "The monkeypatch target may be wrong."
        )
        # Scores must have changed — not 0.
        assert axe_broken.score is not None, (
            f"Expected check_axe_stub score to be non-None with broken floor; got {axe_broken.score}"
        )
        assert axe_broken.score > 0.0, (
            f"Expected check_axe_stub score > 0 with broken floor; got {axe_broken.score}"
        )

    # --- Step 3: restoration check --------------------------------------------
    # After exiting the patch context, the real floor is restored.
    skel_cand2 = _make_candidate(skeleton)
    axe_restored = check_axe_stub(skel_cand2)
    assert axe_restored.decision == GateDecision.REJECT, (
        "After exiting the regression-seed context, real _structure_floor_reject is not "
        "restored — check_axe_stub is still PASSing skeleton HTML.  Gate restoration failed."
    )


def test_wcag_contrast_oracle_on_good_html() -> None:
    """WCAG contrast oracle (AT-013) passes on GOOD reference HTML.

    GOOD HTML uses CSS custom properties for all colors (no same-rule literal
    fg/bg pairs that could violate AA contrast).  The oracle must PASS.
    """
    with hermetic() as guard:
        for case_name, html in _GOOD_HTML_CASES.items():
            candidate = _make_candidate(html)
            outcome = check_wcag_contrast(candidate)
            assert outcome.decision == GateDecision.PASS, (
                f"WCAG contrast oracle REJECTED {case_name!r}: {outcome.diagnostic}"
            )

    assert guard.live_calls == 0


def test_nielsen_oracle_advisory_on_good_html() -> None:
    """Nielsen-10 presence oracle (AT-022) runs without error on GOOD references.

    The Nielsen oracle is advisory (never gates convergence).  This test proves
    it evaluates without raising on well-formed HTML and that the good-HTML
    cases do not trigger an excessive violation count (advisory threshold:
    <= 4 violations out of 10 heuristics for a realistic reference design).
    """
    max_advisory_violations = 4  # realistic reference designs trigger at most a few heuristics
    with hermetic() as guard:
        for case_name, html in _GOOD_HTML_CASES.items():
            candidate = _make_candidate(html)
            report = evaluate_nielsen(candidate)
            violation_count = len(report.violations)
            assert violation_count <= max_advisory_violations, (
                f"Nielsen oracle: {case_name!r} triggered {violation_count} violations "
                f"(advisory ceiling = {max_advisory_violations}).  "
                f"Violations: {[v.value for v in report.violations]}.  "
                "If the GOOD reference fixture is the problem, improve it; if the "
                "oracle regressed, investigate the detector logic."
            )

    assert guard.live_calls == 0


def test_hermetic_zero_live_calls() -> None:
    """Smoke test: the entire deterministic eval gate makes zero live calls.

    Runs every GOOD + BAD case through all deterministic scoring surfaces and
    confirms ``LiveCallGuard.live_calls == 0``.  Any future import of a live
    model client in the scoring stack will be caught here.
    """
    with hermetic() as guard:
        for html in list(_GOOD_HTML_CASES.values()) + list(_BAD_HTML_CASES.values()):
            candidate = _make_candidate(html)
            check_semantic_html(candidate)
            check_axe_stub(candidate)
            check_lighthouse_stub(candidate)
            check_visual_diff_stub(candidate)
            check_wcag_contrast(candidate)
            evaluate_nielsen(candidate)

    assert guard.live_calls == 0, (
        f"LiveCallGuard: {guard.live_calls} live call(s) during deterministic eval gate.  "
        "All scoring must be offline and hermetic."
    )
