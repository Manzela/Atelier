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

Three gates ship with real logic in v1.0 implementation:
    * :func:`check_semantic_html` — HTML5 landmark coverage
    * :func:`check_css_validity` — basic CSS syntax checks
    * :func:`check_token_fidelity` — CSS custom property usage

Three gates ship as scored stubs (real implementations require a browser
sandbox, which current implementation will provide via Playwright):
    * :func:`check_lighthouse_stub` — performance/a11y proxy
    * :func:`check_axe_stub` — accessibility scanner proxy
    * :func:`check_visual_diff_stub` — pixel-diff proxy

PRD Reference: §6.3 N3c (Deterministic Gates)
ADR Reference: 0007 (worktree discipline) — v1.0 implementation scope only
"""

import re
from typing import Final

from atelier.models.data_contracts import CandidateUI, GateOutcome
from atelier.models.enums import GateAxis, GateDecision

# ---------------------------------------------------------------------------
# Heuristic gate constants — used by upgraded stub implementations
# ---------------------------------------------------------------------------

#: Penalty per inline <script> block (each adds ~5ms parse cost equivalent)
_PERF_INLINE_SCRIPT_PENALTY: Final[float] = 5.0

#: Penalty per render-blocking <link rel="stylesheet"> in <head>
_PERF_BLOCKING_CSS_PENALTY: Final[float] = 3.0

#: Penalty per <img> without loading="lazy"
_PERF_EAGER_IMG_PENALTY: Final[float] = 2.0

#: Heuristic: score = 100 - sum(penalties), floor 40
_PERF_FLOOR: Final[float] = 40.0

#: Lighthouse heuristic PASS threshold
_LIGHTHOUSE_PASS_THRESHOLD: Final[float] = 80.0

#: Penalty per <button> or <a> without accessible text
_A11Y_INACCESSIBLE_CONTROL_PENALTY: Final[float] = 8.0

#: Penalty per <img> without alt attribute
_A11Y_MISSING_ALT_PENALTY: Final[float] = 6.0

#: Penalty per <input> without associated <label> or aria-label
_A11Y_MISSING_LABEL_PENALTY: Final[float] = 7.0

#: Penalty per missing viewport meta tag
_A11Y_MISSING_VIEWPORT_PENALTY: Final[float] = 10.0

#: A11y floor — even malformed HTML gets this minimum
_A11Y_FLOOR: Final[float] = 35.0

#: A11y heuristic PASS threshold
_A11Y_PASS_THRESHOLD: Final[float] = 70.0

#: Visual diff — structural tag frequency cosine similarity baseline
_VISUAL_DIFF_GOLDEN_TAGS: Final[tuple[str, ...]] = (
    "div",
    "header",
    "main",
    "section",
    "article",
    "h1",
    "h2",
    "h3",
    "p",
    "button",
    "input",
    "img",
)

#: Minimum structural similarity to PASS visual diff
_VISUAL_DIFF_PASS_THRESHOLD: Final[float] = 55.0

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

# NOTE (AT-010): the former LIGHTHOUSE/AXE/VISUAL_DIFF_STUB_SCORE constants (95/90/85)
# were removed. They were the *inverted-gate bug* (G2): empty/missing index.html was
# scored 95/90/85 and PASSed. Empty/skeleton HTML now REJECTs at 0 via
# _structure_floor_reject(); substantive HTML is scored by each stub's heuristic.


#: Cap on per-file CSS validation errors to keep diagnostics readable.
_MAX_CSS_ERRORS_PER_FILE: int = 5

# Pattern matching CSS custom property declarations (``--foo: value``) and
# references (``var(--foo)``). Kept module-level for compile-once efficiency.
_CSS_VAR_DECL_PATTERN = re.compile(r"--[a-zA-Z0-9_-]+\s*:")
_CSS_VAR_USE_PATTERN = re.compile(r"var\(\s*--[a-zA-Z0-9_-]+")
_CSS_RULESET_PATTERN = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)


# ---------------------------------------------------------------------------
# Real gate implementations (v1.0 implementation)
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
# Stub gates — heuristic browser-free proxies (real tools land in AT-011/AT-013)
# ---------------------------------------------------------------------------

#: A skeleton has fewer than this many content elements (and no visible text).
_SKELETON_MIN_CONTENT_ELEMENTS = 2
#: Opening tags that are pure document boilerplate / non-rendered, not "content".
#: ``script``/``style``/``template``/``link``/``noscript`` are excluded so a
#: page whose only markup is inline scripts or styles still counts as a skeleton.
_BOILERPLATE_TAGS = (
    "html",
    "head",
    "body",
    "meta",
    "title",
    "br",
    "hr",
    "script",
    "style",
    "template",
    "link",
    "noscript",
)
_CONTENT_TAG_RE = re.compile(
    r"<(?!/)(?!(?:" + "|".join(_BOILERPLATE_TAGS) + r")\b)[a-z][a-z0-9-]*",
    re.IGNORECASE,
)
#: ``<script>``/``<style>``/``<template>`` bodies are not user-visible text.
_NON_RENDERED_BLOCK_RE = re.compile(
    r"<(script|style|template)\b[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)


def _is_skeleton(html: str) -> bool:
    """A placeholder skeleton: no visible text AND fewer than two content elements.

    A real screen has either visible text or multiple structural elements; an
    empty/near-empty placeholder (e.g. ``<html><body></body></html>``) has
    neither and must REJECT rather than pass a quality gate (AT-010 / R2).

    ``<script>``/``<style>``/``<template>`` bodies are stripped first so a page
    whose only "text" lives inside a script or style block does not masquerade
    as substantive content (would otherwise evade the floor — review nit, PR #33).
    """
    rendered = _NON_RENDERED_BLOCK_RE.sub("", html)
    visible_text = re.sub(r"<[^>]+>", "", rendered).strip()
    if visible_text:
        return False
    return len(_CONTENT_TAG_RE.findall(rendered)) < _SKELETON_MIN_CONTENT_ELEMENTS


def _structure_floor_reject(
    candidate: CandidateUI, html: str, axis: GateAxis
) -> GateOutcome | None:
    """Empty or skeleton HTML can never pass a quality gate (AT-010 / G2 / R2).

    Returns a REJECT outcome scored 0 for empty/skeleton input; ``None`` for
    substantive HTML so the caller proceeds to its heuristic. This replaces the
    inverted ``if not html: PASS`` stubs that scored empty artifacts 95/90/85.
    """
    if not html or not html.strip():
        return GateOutcome(
            candidate_id=candidate.candidate_id,
            axis=axis,
            decision=GateDecision.REJECT,
            score=0.0,
            diagnostic="REJECT: empty/missing index.html cannot pass a quality gate.",
        )
    if _is_skeleton(html):
        return GateOutcome(
            candidate_id=candidate.candidate_id,
            axis=axis,
            decision=GateDecision.REJECT,
            score=0.0,
            diagnostic="REJECT: skeleton HTML (no substantive content).",
        )
    return None


def check_lighthouse_stub(candidate: CandidateUI) -> GateOutcome:
    """Heuristic Lighthouse performance proxy — browser-free.

    Estimates a performance score from static HTML/CSS analysis without
    a browser sandbox. Penalises patterns that commonly lower real Lighthouse
    scores: inline scripts, render-blocking CSS, eager image loading. current implementation
    replaces this with a real ``@lighthouse-ci`` invocation.

    Scoring formula (per-candidate, so scores vary):
        score = 100 - Σ(penalties), clamped to [_PERF_FLOOR, 100]

    Args:
        candidate: CandidateUI whose ``index.html`` and ``.css`` artifacts
            are analysed. Missing ``index.html`` → conservative mid-range score.

    Returns:
        GateOutcome with axis LIGHTHOUSE_A11Y, differentiated score per candidate.
    """
    html = candidate.artifacts.get("index.html", "")
    floor = _structure_floor_reject(candidate, html, GateAxis.LIGHTHOUSE_A11Y)
    if floor is not None:
        return floor

    lowered = html.lower()
    penalties: list[str] = []
    total_penalty = 0.0

    # Inline <script> blocks
    inline_scripts = lowered.count("<script>") + lowered.count("<script ")
    if inline_scripts > 0:
        p = inline_scripts * _PERF_INLINE_SCRIPT_PENALTY
        penalties.append(f"{inline_scripts} inline script(s) (-{p:.0f})")
        total_penalty += p

    # Render-blocking CSS in <head>
    head_match = re.search(r"<head[^>]*>(.*?)</head>", lowered, re.DOTALL)
    blocking_css = 0
    if head_match:
        blocking_css = head_match.group(1).count('rel="stylesheet"') + head_match.group(1).count(
            "rel='stylesheet'"
        )
    if blocking_css > 1:  # one is expected; extra ones block rendering
        p = (blocking_css - 1) * _PERF_BLOCKING_CSS_PENALTY
        penalties.append(f"{blocking_css - 1} extra blocking stylesheet(s) (-{p:.0f})")
        total_penalty += p

    # Eager images (missing loading="lazy")
    img_count = lowered.count("<img ")
    lazy_count = lowered.count('loading="lazy"') + lowered.count("loading='lazy'")
    eager_imgs = max(0, img_count - lazy_count)
    if eager_imgs > 2:  # noqa: PLR2004
        p = (eager_imgs - 2) * _PERF_EAGER_IMG_PENALTY
        penalties.append(f"{eager_imgs - 2} eager image(s) (-{p:.0f})")
        total_penalty += p

    score = max(_PERF_FLOOR, 100.0 - total_penalty)
    decision = GateDecision.PASS if score >= _LIGHTHOUSE_PASS_THRESHOLD else GateDecision.REJECT
    diagnostic = (
        "Lighthouse heuristic (no browser). "
        + ("; ".join(penalties) if penalties else "No performance penalties detected.")
        + " [Heuristic-based evaluation]"
    )
    return GateOutcome(
        candidate_id=candidate.candidate_id,
        axis=GateAxis.LIGHTHOUSE_A11Y,
        decision=decision,
        score=score,
        diagnostic=diagnostic,
    )


def check_axe_stub(candidate: CandidateUI) -> GateOutcome:
    """Heuristic accessibility gate — browser-free axe-core proxy.

    Penalises common accessibility violations detectable from raw HTML:
    interactive controls without accessible text, images without alt, inputs
    without labels, missing viewport meta. current implementation wires real axe-core against
    a rendered DOM.

    Args:
        candidate: CandidateUI whose ``index.html`` is analysed.

    Returns:
        GateOutcome with axis AXE, differentiated score per candidate.
    """
    html = candidate.artifacts.get("index.html", "")
    floor = _structure_floor_reject(candidate, html, GateAxis.AXE)
    if floor is not None:
        return floor

    lowered = html.lower()
    penalties: list[str] = []
    total_penalty = 0.0

    # Buttons/anchors without accessible text
    buttons = re.findall(r"<button[^>]*>(\s*)</button>", lowered)
    anchors = re.findall(r"<a[^>]*>(\s*)</a>", lowered)
    inaccessible = len(buttons) + len(anchors)
    if inaccessible > 0:
        p = inaccessible * _A11Y_INACCESSIBLE_CONTROL_PENALTY
        penalties.append(f"{inaccessible} empty button/anchor(s) (-{p:.0f})")
        total_penalty += p

    # Images without alt
    imgs = re.findall(r"<img[^>]*>", lowered)
    imgs_without_alt = sum(1 for img in imgs if "alt=" not in img)
    if imgs_without_alt > 0:
        p = imgs_without_alt * _A11Y_MISSING_ALT_PENALTY
        penalties.append(f"{imgs_without_alt} image(s) missing alt (-{p:.0f})")
        total_penalty += p

    # Inputs without label (heuristic: inputs without adjacent <label for=>)
    input_count = lowered.count("<input ")
    label_count = lowered.count("<label")
    unlabeled = max(0, input_count - label_count)
    if unlabeled > 0:
        p = unlabeled * _A11Y_MISSING_LABEL_PENALTY
        penalties.append(f"{unlabeled} unlabeled input(s) (-{p:.0f})")
        total_penalty += p

    # Viewport meta
    if 'name="viewport"' not in lowered and "name='viewport'" not in lowered:
        penalties.append("missing viewport meta (-10)")
        total_penalty += _A11Y_MISSING_VIEWPORT_PENALTY

    score = max(_A11Y_FLOOR, 100.0 - total_penalty)
    decision = GateDecision.PASS if score >= _A11Y_PASS_THRESHOLD else GateDecision.REJECT
    diagnostic = (
        "Accessibility heuristic (no DOM). "
        + ("; ".join(penalties) if penalties else "No accessibility violations detected.")
        + " [Heuristic-based evaluation]"
    )
    return GateOutcome(
        candidate_id=candidate.candidate_id,
        axis=GateAxis.AXE,
        decision=decision,
        score=score,
        diagnostic=diagnostic,
    )


def _tag_frequency_vector(html: str, tags: tuple[str, ...]) -> list[float]:
    """Compute a normalised tag-frequency vector for structural similarity."""
    lowered = html.lower()
    counts = [float(lowered.count(f"<{tag}")) for tag in tags]
    total = sum(counts) or 1.0
    return [c / total for c in counts]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def check_visual_diff_stub(candidate: CandidateUI) -> GateOutcome:
    """Heuristic structural similarity gate — no render required.

    Measures how structurally similar the candidate's HTML is to a
    "golden" reference tag distribution via cosine similarity on a tag-
    frequency vector. Candidates that generate unusual or empty DOM
    structures score low; candidates that use standard HTML5 structure
    score high. current implementation replaces this with pixel-level visual diff.

    Args:
        candidate: CandidateUI whose ``index.html`` is analysed.

    Returns:
        GateOutcome with axis VISUAL_DIFF. PASS if structural similarity
        exceeds _VISUAL_DIFF_PASS_THRESHOLD, else REJECT.
    """
    html = candidate.artifacts.get("index.html", "")
    floor = _structure_floor_reject(candidate, html, GateAxis.VISUAL_DIFF)
    if floor is not None:
        return floor

    # Golden reference: balanced use of the 12 most common structural tags
    golden = [1.0 / len(_VISUAL_DIFF_GOLDEN_TAGS)] * len(_VISUAL_DIFF_GOLDEN_TAGS)
    candidate_vec = _tag_frequency_vector(html, _VISUAL_DIFF_GOLDEN_TAGS)
    similarity = _cosine_similarity(candidate_vec, golden)
    score = round(similarity * 100.0, 1)
    decision = GateDecision.PASS if score >= _VISUAL_DIFF_PASS_THRESHOLD else GateDecision.REJECT
    diagnostic = (
        f"Structural similarity score: {score:.1f}/100 "
        f"(cosine vs golden tag distribution). "
        f"{'PASS' if decision == GateDecision.PASS else 'REJECT'}: "
        f"threshold={_VISUAL_DIFF_PASS_THRESHOLD}. "
        "[Heuristic-based evaluation]"
    )
    return GateOutcome(
        candidate_id=candidate.candidate_id,
        axis=GateAxis.VISUAL_DIFF,
        decision=decision,
        score=score,
        diagnostic=diagnostic,
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
