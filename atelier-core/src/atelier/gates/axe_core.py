"""Real axe-core accessibility oracle (AT-011, PRD §12 E1).

Renders the candidate's ``index.html`` in headless chromium and runs the
dequelabs **axe-core** engine over the live DOM via ``axe-playwright-python``.

**Fail-closed** (R2 credibility core, ``<no_skeleton_convergence>``): any axe
violation of impact ``critical`` or ``serious`` → ``REJECT``. This replaces the
browser-free heuristic (:func:`atelier.gates.deterministic.check_axe_stub`) on
the AXE axis — the heuristic misses page-level violations axe catches
(e.g. ``document-title``, ``html-has-lang``, computed-style ``color-contrast``).

**Failure trichotomy** (R9): the structure floor (empty/skeleton → REJECT 0)
runs *first*, before any browser launch. If chromium is unavailable or the scan
errors, the gate **fail-softs** to the heuristic proxy with an explicit
``DEGRADED`` acknowledgement in the diagnostic — never a silent PASS, never a
silent swallow. In production chromium is guaranteed (Dockerfile + the
``make preflight`` chromium probe), so the soft path is a dev/offline safety net.

**Concurrency**: the Playwright *sync* API cannot run inside a running asyncio
loop, and the gate runner is invoked synchronously from the orchestrator's async
``run`` loop (``orchestrator/runner.py``). The scan therefore executes in a
dedicated worker thread (which has no event loop), keeping the runner's
synchronous ``Callable[[CandidateUI], GateOutcome]`` contract intact.
"""

from __future__ import annotations

import concurrent.futures
import os

import structlog
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from atelier.gates.deterministic import _structure_floor_reject, check_axe_stub
from atelier.models.data_contracts import CandidateUI, GateOutcome
from atelier.models.enums import GateAxis, GateDecision

logger = structlog.get_logger(__name__)

#: Impacts that block convergence. axe-core impact ∈ {minor, moderate, serious,
#: critical}; the gate fails closed on the two highest tiers (PRD §6.3, §7).
_AXE_BLOCKING_IMPACTS = frozenset({"critical", "serious"})
#: Score (0-100) for a candidate with zero blocking violations.
_AXE_PASS_SCORE = 100.0
#: Per-violation penalties (kept on a 0-100 scale for parity with the stubs).
_AXE_BLOCKING_PENALTY = 30.0
_AXE_NONBLOCKING_PENALTY = 4.0
#: Floor so a PASS with many minor issues still reads as a (low) PASS, not 0.
_AXE_PASS_FLOOR = 60.0
#: Bound the render so a pathological/external-resource page cannot hang the gate.
_SET_CONTENT_TIMEOUT_MS = 15_000


def _launch_args() -> list[str]:
    """Chromium launch flags. In the production container (non-root Cloud Run),
    the platform provides isolation and chromium's own sandbox cannot initialise,
    so ``--no-sandbox`` is required; locally / in CI it launches sandboxed. The
    rendered content is Atelier-self-generated inline HTML, not arbitrary web."""
    return ["--no-sandbox"] if os.getenv("ATELIER_ENV") == "production" else []


def _scan_sync(html: str) -> list[dict[str, object]]:
    """Launch chromium, render ``html``, run axe-core, return its violations.

    Runs the Playwright **sync** API; must be called from a thread with no
    running event loop (see module docstring). Raises :class:`PlaywrightError`
    if chromium cannot launch or the page cannot render.
    """
    axe = Axe()
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_launch_args())
        try:
            page = browser.new_page()
            # Candidates are self-contained inline-Tailwind HTML (PRD §6/§14), so
            # domcontentloaded is sufficient and avoids blocking on any stray
            # external subresource; the timeout bounds the worst case.
            page.set_content(html, wait_until="domcontentloaded", timeout=_SET_CONTENT_TIMEOUT_MS)
            results = axe.run(page)
        finally:
            browser.close()
    violations = results.response.get("violations", [])
    return violations if isinstance(violations, list) else []


def _scan_in_thread(html: str) -> list[dict[str, object]]:
    """Run :func:`_scan_sync` in a worker thread so it never touches the loop."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_scan_sync, html).result()


def _outcome_from_violations(
    candidate: CandidateUI, violations: list[dict[str, object]]
) -> GateOutcome:
    """Map axe-core violations to a fail-closed :class:`GateOutcome`."""
    blocking = [v for v in violations if v.get("impact") in _AXE_BLOCKING_IMPACTS]
    nonblocking_count = len(violations) - len(blocking)

    if blocking:
        ids = ", ".join(sorted(str(v.get("id", "?")) for v in blocking))
        score = max(0.0, _AXE_PASS_SCORE - _AXE_BLOCKING_PENALTY * len(blocking))
        return GateOutcome(
            candidate_id=candidate.candidate_id,
            axis=GateAxis.AXE,
            decision=GateDecision.REJECT,
            score=score,
            diagnostic=(f"REJECT: {len(blocking)} critical/serious axe-core violation(s): {ids}."),
        )

    score = max(_AXE_PASS_FLOOR, _AXE_PASS_SCORE - _AXE_NONBLOCKING_PENALTY * nonblocking_count)
    detail = (
        "No critical/serious violations."
        if nonblocking_count == 0
        else f"No critical/serious violations ({nonblocking_count} minor/moderate noted)."
    )
    return GateOutcome(
        candidate_id=candidate.candidate_id,
        axis=GateAxis.AXE,
        decision=GateDecision.PASS,
        score=score,
        diagnostic=f"PASS: real axe-core over rendered DOM. {detail}",
    )


def _fail_soft_to_heuristic(candidate: CandidateUI, error: Exception) -> GateOutcome:
    """Fail-soft (R9): degrade to the browser-free heuristic, ACKNOWLEDGED.

    The exception is logged with structured context (not swallowed), and the
    returned outcome's diagnostic states the degradation so the §14 trace and
    the AT-094 degraded banner can surface it. The structure floor has already
    rejected empty/skeleton input, so this never blesses garbage.
    """
    logger.warning(
        "axe_core.fail_soft_to_heuristic",
        candidate_id=str(candidate.candidate_id),
        error=str(error),
        error_type=type(error).__name__,
    )
    degraded = check_axe_stub(candidate)
    return GateOutcome(
        candidate_id=degraded.candidate_id,
        axis=GateAxis.AXE,
        decision=degraded.decision,
        score=degraded.score,
        diagnostic=(
            "DEGRADED (fail-soft): chromium/axe-core unavailable; used browser-free "
            f"heuristic a11y proxy. {degraded.diagnostic}"
        ),
    )


def check_axe(candidate: CandidateUI) -> GateOutcome:
    """Real axe-core a11y gate for the AXE axis (AT-011).

    Pipeline: structure floor (empty/skeleton → REJECT 0) → real axe-core over a
    chromium-rendered DOM (any critical/serious → REJECT) → fail-soft to the
    heuristic proxy with acknowledgement if the browser path errors.
    """
    html = candidate.artifacts.get("index.html", "")
    floor = _structure_floor_reject(candidate, html, GateAxis.AXE)
    if floor is not None:
        return floor

    try:
        violations = _scan_in_thread(html)
    except PlaywrightError as exc:
        return _fail_soft_to_heuristic(candidate, exc)

    return _outcome_from_violations(candidate, violations)
