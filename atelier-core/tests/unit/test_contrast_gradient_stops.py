"""AT-013 regression: WCAG contrast must check ALL gradient stops, not just the first.

A ``background`` gradient shorthand carries multiple color literals. Resolving
only the first stop lets foreground text that is unreadable against a later/darker
stop slip through the gate. These tests pin the worst-stop behaviour so the gate
cannot silently regress to first-stop-only resolution.
"""

from uuid import uuid4

import pytest
from atelier.gates.contrast import check_wcag_contrast
from atelier.models.data_contracts import CandidateUI
from atelier.models.enums import GateDecision


def _candidate(css: str) -> CandidateUI:
    return CandidateUI(
        candidate_id=uuid4(),
        surface_id=uuid4(),
        iteration=0,
        artifacts={"main.css": css},
    )


@pytest.mark.unit
def test_gradient_unreadable_last_stop_rejects() -> None:
    """White text on a gradient whose FIRST stop is black but LAST stop is white.

    First-stop-only resolution would compute 21:1 against #000 and PASS. The text
    is invisible against the #fff stop (~1:1), so the worst-stop gate must REJECT.
    """
    css = "p{color:#ffffff;background:linear-gradient(#000000, #ffffff)}"
    outcome = check_wcag_contrast(_candidate(css))

    assert outcome.decision == GateDecision.REJECT, (
        "white text over a gradient ending in white must REJECT — the worst stop "
        "(white-on-white) is unreadable; first-stop-only resolution would have passed"
    )
    assert outcome.score == 0.0


@pytest.mark.unit
def test_gradient_unreadable_first_stop_rejects() -> None:
    """Mirror case: the FIRST stop passes but a LATER stop fails.

    Light-grey text passes against the dark first stop but fails against the light
    last stop. Guards against an off-by-one that only checks the final literal.
    """
    css = "p{color:#dddddd;background:linear-gradient(#111111, #eeeeee)}"
    outcome = check_wcag_contrast(_candidate(css))

    assert outcome.decision == GateDecision.REJECT
    assert outcome.score == 0.0


@pytest.mark.unit
def test_gradient_all_stops_readable_passes() -> None:
    """Near-black text readable against every stop of a light gradient → PASS."""
    css = "p{color:#111111;background:linear-gradient(#ffffff, #f0f0f0)}"
    outcome = check_wcag_contrast(_candidate(css))

    assert outcome.decision == GateDecision.PASS
    assert outcome.score == 100.0
