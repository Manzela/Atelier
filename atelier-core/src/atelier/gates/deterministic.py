"""Deterministic gate implementations for N3c pipeline stage.

Per PRD §6.3 N3c, every candidate from N3a Generator must clear a battery of
deterministic gates BEFORE the probabilistic D-O-R-A-V judges run. This
deterministic-gate-first architecture is a core invariant of the Atelier
pipeline: cheap, fast, hallucination-free signals filter the candidate set
before any LLM is invoked.

Each gate is a pure function that takes a :class:`CandidateUI` and returns a
:class:`GateOutcome`. Pure-function purity guarantees:
    * Repeatable evaluation (same input → same output)
    * No I/O side effects (safe to call in any context)
    * Trivially testable with synthetic candidates

Three gates ship with real logic in Phase 1:
    * :func:`check_semantic_html` — HTML5 landmark coverage
    * :func:`check_css_validity` — basic CSS syntax checks
    * :func:`check_token_fidelity` — CSS custom property usage

Three gates ship as scored stubs (real implementations require a browser
sandbox, which Phase 2 will provide via Playwright):
    * :func:`check_lighthouse_stub` — performance/a11y proxy
    * :func:`check_axe_stub` — accessibility scanner proxy
    * :func:`check_visual_diff_stub` — pixel-diff proxy

PRD Reference: §6.3 N3c (Deterministic Gates)
ADR Reference: 0007 (worktree discipline) — Phase 1 scope only
"""

import re

from atelier.models.data_contracts import CandidateUI, GateOutcome
from atelier.models.enums import GateAxis, GateDecision

# ---------------------------------------------------------------------------
# Tunable thresholds — kept module-level so tests can assert against them
# ---------------------------------------------------------------------------

#: HTML5 semantic landmark elements scored by :func:`check_semantic_html`.
SEMANTIC_LANDMARKS: tuple[str, ...] = (
    "header",
    "main",
    "nav",
    "footer",
    "article",
    "section",
)

#: Minimum semantic-HTML coverage score (0-100) required to PASS.
SEMANTIC_HTML_PASS_THRESHOLD: float = 50.0

#: Stub score for :func:`check_lighthouse_stub` (real Lighthouse needs browser).
LIGHTHOUSE_STUB_SCORE: float = 95.0

#: Stub score for :func:`check_axe_stub` (real axe-core needs DOM).
AXE_STUB_SCORE: float = 90.0

#: Stub score for :func:`check_visual_diff_stub` (real visual diff needs render).
VISUAL_DIFF_STUB_SCORE: float = 85.0


#: Cap on per-file CSS validation errors to keep diagnostics readable.
_MAX_CSS_ERRORS_PER_FILE: int = 5

# Pattern matching CSS custom property declarations (``--foo: value``) and
# references (``var(--foo)``). Kept module-level for compile-once efficiency.
_CSS_VAR_DECL_PATTERN = re.compile(r"--[a-zA-Z0-9_-]+\s*:")
_CSS_VAR_USE_PATTERN = re.compile(r"var\(\s*--[a-zA-Z0-9_-]+")
_CSS_RULESET_PATTERN = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)


# ---------------------------------------------------------------------------
# Real gate implementations (Phase 1)
# ---------------------------------------------------------------------------


def check_semantic_html(candidate: CandidateUI) -> GateOutcome:
    """Validate HTML5 semantic landmark coverage.

    Searches ``artifacts["index.html"]`` for the six HTML5 landmark elements
    listed in :data:`SEMANTIC_LANDMARKS`. Each landmark found contributes
    equally to the score. A candidate without an ``index.html`` artifact is
    rejected outright — there is nothing to evaluate.

    Args:
        candidate: The :class:`CandidateUI` to evaluate. Its ``artifacts``
            dict must contain ``"index.html"`` for a real evaluation;
            otherwise the gate REJECTs with score ``0.0``.

    Returns:
        A :class:`GateOutcome` with:
            * ``axis`` = :attr:`GateAxis.SEMANTIC_HTML`
            * ``score`` in ``[0.0, 100.0]`` (proportion of landmarks present, times 100)
            * ``decision`` = PASS if score >= :data:`SEMANTIC_HTML_PASS_THRESHOLD`,
              else REJECT
            * ``diagnostic`` listing found and missing landmarks

    Examples:
        >>> from uuid import uuid4
        >>> cand = CandidateUI(
        ...     candidate_id=uuid4(),
        ...     surface_id=uuid4(),
        ...     iteration=0,
        ...     artifacts={"index.html": "<header></header><main></main><nav></nav>"},
        ... )
        >>> outcome = check_semantic_html(cand)
        >>> outcome.decision
        <GateDecision.PASS: 'pass'>
    """
    html = candidate.artifacts.get("index.html", "")
    if not html:
        return GateOutcome(
            candidate_id=candidate.candidate_id,
            axis=GateAxis.SEMANTIC_HTML,
            decision=GateDecision.REJECT,
            score=0.0,
            diagnostic="No index.html artifact present; cannot evaluate semantic HTML.",
        )

    found: list[str] = []
    missing: list[str] = []
    lowered = html.lower()
    for landmark in SEMANTIC_LANDMARKS:
        if f"<{landmark}" in lowered:
            found.append(landmark)
        else:
            missing.append(landmark)

    score = (len(found) / len(SEMANTIC_LANDMARKS)) * 100.0
    decision = GateDecision.PASS if score >= SEMANTIC_HTML_PASS_THRESHOLD else GateDecision.REJECT
    diagnostic = (
        f"Semantic HTML coverage: {len(found)}/{len(SEMANTIC_LANDMARKS)} landmarks. "
        f"Found: {sorted(found) or 'none'}. Missing: {sorted(missing) or 'none'}."
    )
    return GateOutcome(
        candidate_id=candidate.candidate_id,
        axis=GateAxis.SEMANTIC_HTML,
        decision=decision,
        score=score,
        diagnostic=diagnostic,
    )


def check_css_validity(candidate: CandidateUI) -> GateOutcome:
    """Run basic CSS syntax validation across all ``.css`` artifacts.

    Validates two cheap-but-load-bearing properties of every CSS artifact:
        1. Brace balance — every ``{`` has a matching ``}``.
        2. No empty rulesets — every ``selector { ... }`` block contains at
           least one declaration. Empty rulesets are a strong smell of
           generator hallucination.

    A candidate with no ``.css`` artifacts is PASSed with a neutral diagnostic
    (the absence of CSS is the absence of CSS errors, not a defect for this
    gate to catch — :func:`check_semantic_html` covers structural concerns).

    Args:
        candidate: The :class:`CandidateUI` whose ``artifacts`` are scanned
            for any filename ending in ``.css``.

    Returns:
        A :class:`GateOutcome` with:
            * ``axis`` = :attr:`GateAxis.LIGHTHOUSE_PERF` (CSS validity sits
              under the performance gate axis until a dedicated axis exists)
            * ``score`` = ``100.0`` on PASS, ``0.0`` on REJECT
            * ``decision`` = PASS if all CSS files are syntactically valid,
              else REJECT
            * ``diagnostic`` listing the first few errors found
    """
    css_files = {
        name: content for name, content in candidate.artifacts.items() if name.endswith(".css")
    }
    if not css_files:
        return GateOutcome(
            candidate_id=candidate.candidate_id,
            axis=GateAxis.LIGHTHOUSE_PERF,
            decision=GateDecision.PASS,
            score=100.0,
            diagnostic="No CSS artifacts present; nothing to validate.",
        )

    errors: list[str] = []
    for filename, content in css_files.items():
        open_braces = content.count("{")
        close_braces = content.count("}")
        if open_braces != close_braces:
            errors.append(
                f"{filename}: unbalanced braces ({open_braces} open, {close_braces} close)"
            )
            continue
        for match in _CSS_RULESET_PATTERN.finditer(content):
            selector = match.group(1).strip()
            body = match.group(2).strip()
            if not body:
                errors.append(f"{filename}: empty ruleset for selector '{selector}'")
                # Cap errors per file to keep diagnostic readable.
                if len(errors) >= _MAX_CSS_ERRORS_PER_FILE:
                    break

    if errors:
        return GateOutcome(
            candidate_id=candidate.candidate_id,
            axis=GateAxis.LIGHTHOUSE_PERF,
            decision=GateDecision.REJECT,
            score=0.0,
            diagnostic="CSS validation errors: " + "; ".join(errors[:5]),
        )
    return GateOutcome(
        candidate_id=candidate.candidate_id,
        axis=GateAxis.LIGHTHOUSE_PERF,
        decision=GateDecision.PASS,
        score=100.0,
        diagnostic=f"CSS valid across {len(css_files)} file(s); braces balanced, no empty rulesets.",
    )


def check_token_fidelity(candidate: CandidateUI) -> GateOutcome:
    """Verify CSS custom properties (design tokens) are declared and referenced.

    Atelier's design-token discipline (PRD §6.5) requires generated CSS to
    declare tokens via CSS custom properties (``--token-name: value``) and
    reference them via ``var(--token-name)``. This gate ensures both halves
    of that contract are present:

        * At least one declaration found → tokens exist
        * Score reflects the *use* ratio = ``var()`` references / declarations

    A high ratio (≥ 1.0) means every declared token is used at least once.
    A low ratio means tokens are declared but ignored — a hallucination
    smell. The score is capped at ``100.0`` to keep the GateOutcome bounds
    well-defined.

    Args:
        candidate: The :class:`CandidateUI` whose ``.css`` artifacts are
            scanned for CSS custom property declarations and references.

    Returns:
        A :class:`GateOutcome` with:
            * ``axis`` = :attr:`GateAxis.TOKEN_FIDELITY`
            * ``score`` ∈ ``[0.0, 100.0]``
            * ``decision`` = PASS if at least one custom property is declared,
              else REJECT
            * ``diagnostic`` with declaration + reference counts
    """
    css_blobs: list[str] = [
        content for name, content in candidate.artifacts.items() if name.endswith(".css")
    ]
    if not css_blobs:
        return GateOutcome(
            candidate_id=candidate.candidate_id,
            axis=GateAxis.TOKEN_FIDELITY,
            decision=GateDecision.REJECT,
            score=0.0,
            diagnostic="No CSS artifacts present; cannot evaluate token fidelity.",
        )

    declarations = 0
    references = 0
    for blob in css_blobs:
        declarations += len(_CSS_VAR_DECL_PATTERN.findall(blob))
        references += len(_CSS_VAR_USE_PATTERN.findall(blob))

    if declarations == 0:
        return GateOutcome(
            candidate_id=candidate.candidate_id,
            axis=GateAxis.TOKEN_FIDELITY,
            decision=GateDecision.REJECT,
            score=0.0,
            diagnostic="No CSS custom properties declared; design tokens missing.",
        )

    use_ratio = references / declarations
    score = min(use_ratio * 100.0, 100.0)
    return GateOutcome(
        candidate_id=candidate.candidate_id,
        axis=GateAxis.TOKEN_FIDELITY,
        decision=GateDecision.PASS,
        score=score,
        diagnostic=(
            f"Token fidelity: {declarations} declaration(s), {references} reference(s), "
            f"use ratio {use_ratio:.2f}."
        ),
    )


# ---------------------------------------------------------------------------
# Stub gates — placeholders until Phase 2 wires real browser-based tools
# ---------------------------------------------------------------------------


def check_lighthouse_stub(candidate: CandidateUI) -> GateOutcome:
    """Stubbed Lighthouse accessibility gate.

    A real Lighthouse run requires a headless browser sandbox (Chrome via
    Puppeteer or Playwright). Phase 1 is browser-less, so this stub returns a
    fixed PASS with a high score that mirrors what a well-formed static
    artifact would typically earn. Phase 2 replaces this with a real
    ``@lighthouse-ci`` invocation against a rendered preview.

    Args:
        candidate: The :class:`CandidateUI` to evaluate. The stub does not
            inspect the artifacts; the parameter is kept for signature
            compatibility with the real implementation.

    Returns:
        A :class:`GateOutcome` with ``axis = LIGHTHOUSE_A11Y``,
        ``decision = PASS``, and ``score = LIGHTHOUSE_STUB_SCORE``.
    """
    return GateOutcome(
        candidate_id=candidate.candidate_id,
        axis=GateAxis.LIGHTHOUSE_A11Y,
        decision=GateDecision.PASS,
        score=LIGHTHOUSE_STUB_SCORE,
        diagnostic=(
            f"Lighthouse stub: returning score={LIGHTHOUSE_STUB_SCORE}. "
            "Real Lighthouse requires browser sandbox (Phase 2)."
        ),
    )


def check_axe_stub(candidate: CandidateUI) -> GateOutcome:
    """Stubbed axe-core accessibility gate.

    Real axe-core needs a live DOM, so Phase 1 returns a fixed PASS. The
    stubbed score is slightly lower than :func:`check_lighthouse_stub` to
    reflect axe-core's typically stricter rule set.

    Args:
        candidate: The :class:`CandidateUI` whose ``candidate_id`` is echoed
            back in the result. Artifacts are not inspected.

    Returns:
        A :class:`GateOutcome` with ``axis = AXE``, ``decision = PASS``,
        and ``score = AXE_STUB_SCORE``.
    """
    return GateOutcome(
        candidate_id=candidate.candidate_id,
        axis=GateAxis.AXE,
        decision=GateDecision.PASS,
        score=AXE_STUB_SCORE,
        diagnostic=(
            f"axe-core stub: returning score={AXE_STUB_SCORE}. "
            "Real axe-core requires DOM (Phase 2)."
        ),
    )


def check_visual_diff_stub(candidate: CandidateUI) -> GateOutcome:
    """Stubbed visual-diff gate.

    Real visual diffing requires rasterizing the candidate and comparing
    against a golden image (typically via ``resemble.js`` or ``pixelmatch``).
    Phase 1 returns a fixed PASS with a conservative score.

    Args:
        candidate: The :class:`CandidateUI` whose ``candidate_id`` is echoed
            back. Artifacts are not inspected.

    Returns:
        A :class:`GateOutcome` with ``axis = VISUAL_DIFF``, ``decision = PASS``,
        and ``score = VISUAL_DIFF_STUB_SCORE``.
    """
    return GateOutcome(
        candidate_id=candidate.candidate_id,
        axis=GateAxis.VISUAL_DIFF,
        decision=GateDecision.PASS,
        score=VISUAL_DIFF_STUB_SCORE,
        diagnostic=(
            f"Visual-diff stub: returning score={VISUAL_DIFF_STUB_SCORE}. "
            "Real visual diff requires render (Phase 2)."
        ),
    )


# ---------------------------------------------------------------------------
# Convenience: run every gate against a candidate
# ---------------------------------------------------------------------------


def run_all_gates(candidate: CandidateUI) -> list[GateOutcome]:
    """Execute every deterministic gate against a candidate.

    Convenience wrapper that runs all six gates in declared order. Use this
    for smoke tests, debugging, or when no axis filter is appropriate. For
    axis-filtered execution (the production path), see
    :class:`atelier.gates.runner.GateRunner`.

    Args:
        candidate: The :class:`CandidateUI` to evaluate against every gate.

    Returns:
        A list of six :class:`GateOutcome` objects in the order: semantic
        HTML, CSS validity, token fidelity, Lighthouse, axe, visual diff.
    """
    return [
        check_semantic_html(candidate),
        check_css_validity(candidate),
        check_token_fidelity(candidate),
        check_lighthouse_stub(candidate),
        check_axe_stub(candidate),
        check_visual_diff_stub(candidate),
    ]
