"""N3d ConsensusAgent — D-O-R-A-V multi-judge consensus for Atelier.

Per PRD §6.3 N3d, every candidate that clears the N3c deterministic gate
battery is then evaluated by five probabilistic judges -- one per D-O-R-A-V
axis (Brand, Originality, Relevance, Accessibility, Visual-clarity). Each
judge emits a normalized score in ``[0.0, 1.0]`` plus a diagnostic; the five
scores are then combined into a single composite using an
:class:`AxisWeights`-driven weighted average.

This module is the **Phase 1** scaffold of that node: every judge here is a
*deterministic* heuristic that inspects ``candidate.artifacts`` for concrete
signals (CSS custom properties, semantic HTML, ARIA attributes, typography
declarations, etc.). Phase 2 swaps each ``_score_*`` helper for a Vertex AI
LLM call routed via :data:`atelier.models.model_registry.JUDGE_MODEL_CONFIG`,
while the surrounding plumbing (anti-bias report, composite weighting,
constitution enforcement, ``ConsensusEvaluation`` shape) stays untouched.

Key design choices:

    * **Deterministic-first** -- shipping concrete heuristics in Phase 1 lets
      the rest of the pipeline (Fixer, Orchestrator, trajectory logging)
      integrate against a stable contract before LLM judges land.
    * **Anti-bias coupled by composition, not inheritance** -- the report is
      built via :func:`atelier.nodes.anti_bias.build_anti_bias_report` and
      attached to the diagnostics dict; consensus logic never reaches into
      ``shuffle_evaluation_order`` or ``detect_dominance`` directly.
    * **Constitution as a soft penalty** -- when a constitution is provided
      and the composite falls below ``scoring.target``, the score is reduced
      via a graded penalty (floored at :data:`CONSTITUTION_FLOOR`), not
      hard-rejected. Hard-reject is the Orchestrator's job once it sees the
      ``passed`` flag.

Naming note: the existing Pydantic :class:`atelier.models.data_contracts.ConsensusResult`
already occupies the ``ConsensusResult`` symbol with a different shape
(``selected_candidate_id`` + ``per_axis_scores`` + ``decision``). To avoid a
silent name clash we use :class:`ConsensusEvaluation` for the per-candidate
result returned by :func:`evaluate_candidate`.

PRD Reference: §6.3 (N3d ConsensusAgent), F0209-F0211
Audit Reference: §7 (FA-018 model routing, FA-019 weighting, bias mitigation)
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from atelier.models.axis_weights import AxisWeights
from atelier.models.constitution_registry import Constitution
from atelier.models.data_contracts import CandidateUI, JudgeVote
from atelier.models.enums import JudgeAxis
from atelier.models.model_registry import JUDGE_MODEL_CONFIG
from atelier.nodes.anti_bias import AntiBiasReport, build_anti_bias_report

if TYPE_CHECKING:
    # Imported only for type checking to avoid a runtime circular import:
    # llm_judge depends on _AXIS_SCORERS / _JudgeScore from this module at
    # import time, while evaluate_candidate below lazily imports
    # `_resolve_axis_scorers` from llm_judge at call time.
    from atelier.nodes.llm_judge import JudgeClient

# ---------------------------------------------------------------------------
# Tunable thresholds -- kept module-level so tests can assert against them
# and Phase 2 LLM judges can re-use the same target values for calibration.
# ---------------------------------------------------------------------------

#: Target count of CSS custom property declarations for full Brand credit.
#: A well-tokenized stylesheet declares at least this many ``--token: value``
#: pairs before brand alignment is considered "fully expressed."
BRAND_TARGET_VARS: int = 5

#: Target count of distinct hex colors used in CSS. Brand systems usually
#: express identity through 3 anchor colors (primary, accent, neutral).
BRAND_TARGET_COLORS: int = 3

#: Target count of distinct CSS properties for full Originality credit. A
#: vocabulary below this size signals template-y output; above it signals
#: intentional design language.
ORIGINALITY_TARGET_PROPS: int = 12

#: Target count of distinct CSS selectors. Combined with property variety,
#: selector variety distinguishes hand-crafted CSS from boilerplate.
ORIGINALITY_TARGET_SELECTORS: int = 6

#: Target text-content-to-tag ratio (chars per tag) for full Relevance credit.
#: Below this, the candidate is mostly markup with no substantive content;
#: above it, the content has enough density to read as a real artifact.
RELEVANCE_TARGET_CHARS_PER_TAG: float = 30.0

#: Target count of ARIA attributes for full Accessibility credit.
ACCESSIBILITY_TARGET_ARIA: int = 3

#: Target count of semantic HTML landmark elements for full Accessibility
#: credit. Mirrors :data:`atelier.gates.deterministic.SEMANTIC_LANDMARKS`
#: but applied as a smooth score rather than a binary threshold.
ACCESSIBILITY_TARGET_SEMANTIC: int = 5

#: Target count of typography-related CSS declarations
#: (``font-family``, ``font-size``, ``font-weight``, ``line-height``) for
#: full Visual-Clarity credit.
VISUAL_TARGET_TYPOGRAPHY: int = 4

#: Target count of spacing-related CSS declarations (``margin``, ``padding``,
#: ``gap``) for full Visual-Clarity credit.
VISUAL_TARGET_SPACING: int = 4

#: Default composite threshold above which a candidate is considered to have
#: cleared the convergence bar. Mirrors PRD §6 ship_it default of 0.70.
CONVERGENCE_DEFAULT: float = 0.70

#: Half-width of the synthetic confidence interval attached to every Phase 1
#: :class:`JudgeVote`. Real judges in Phase 2 will emit their own CIs from
#: Bayesian sampling; here we record a fixed band so the schema stays
#: consistent downstream.
CONFIDENCE_HALF_WIDTH: float = 0.10

#: Strength of the constitution penalty. When composite falls below
#: ``scoring.target`` the score is multiplied by ``1 - strength * gap_ratio``
#: where ``gap_ratio`` is ``(target - composite) / target`` clamped to
#: ``[0.0, 1.0]``. A strength of 0.3 means even maximum-gap candidates lose
#: at most 30% before the floor kicks in.
CONSTITUTION_PENALTY_STRENGTH: float = 0.30

#: Hard floor on the constitution penalty multiplier. Even a maximally
#: failing candidate keeps at least 50% of its raw composite so the
#: Fixer/EvoDesign loop has signal to act on.
CONSTITUTION_FLOOR: float = 0.50

# ---------------------------------------------------------------------------
# Static lookups -- module-level so they compile once.
# ---------------------------------------------------------------------------

#: CSS properties that contribute to the typography sub-score in Visual.
TYPOGRAPHY_PROPS: tuple[str, ...] = (
    "font-family",
    "font-size",
    "font-weight",
    "line-height",
    "letter-spacing",
)

#: CSS properties that contribute to the spacing sub-score in Visual.
SPACING_PROPS: tuple[str, ...] = (
    "margin",
    "padding",
    "gap",
)

#: Semantic HTML5 elements counted by the Accessibility scorer.
SEMANTIC_ELEMENTS: tuple[str, ...] = (
    "header",
    "main",
    "nav",
    "footer",
    "article",
    "section",
    "aside",
)

#: Mapping from snake_case axis identifier (used by :class:`AxisWeights` and
#: :data:`JUDGE_MODEL_CONFIG`) to the kebab-case :class:`JudgeAxis` enum
#: member. Centralized so the two naming conventions never have to be
#: reconciled inline.
_AXIS_NAME_TO_ENUM: dict[str, JudgeAxis] = {
    "brand": JudgeAxis.BRAND,
    "originality": JudgeAxis.ORIGINALITY,
    "relevance": JudgeAxis.RELEVANCE,
    "accessibility": JudgeAxis.ACCESSIBILITY,
    "visual_clarity": JudgeAxis.VISUAL_CLARITY,
}

# ---------------------------------------------------------------------------
# Pre-compiled regex patterns -- module-level for compile-once efficiency.
# Kept private (leading underscore) because they are an implementation
# detail of the scorers, not part of the public API.
# ---------------------------------------------------------------------------

_CSS_VAR_DECL = re.compile(r"--[a-zA-Z0-9_-]+\s*:")
_CSS_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")
_CSS_PROPERTY = re.compile(r"([a-zA-Z-]+)\s*:")
_CSS_SELECTOR_RULE = re.compile(r"([^{}]+)\{", re.MULTILINE)
_HTML_TAG = re.compile(r"<[^>]+>")
_HTML_ARIA = re.compile(r"\saria-[a-z-]+\s*=", re.IGNORECASE)
_HTML_ALT = re.compile(r"<img[^>]*\salt\s*=", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Internal result containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _JudgeScore:
    """Internal per-axis result produced by a ``_score_*`` helper.

    Not exported: callers see :class:`JudgeVote` instances built from this
    via :func:`_build_judge_vote`. Kept as a separate type so the scoring
    helpers stay pure (no Pydantic, no UUID) and can be unit-tested in
    isolation from the consensus aggregation path.

    Attributes:
        score: Normalized score in ``[0.0, 1.0]``.
        diagnostic: Human-readable explanation of what was counted and why
            the score landed where it did. Embedded into
            :attr:`JudgeVote.reasoning` downstream.
        provenance_vars: DEMAS-D variable names the scorer "consulted."
            Phase 1 scorers report the artifact filenames they actually
            opened; Phase 2 LLM judges will report richer provenance.
    """

    score: float
    diagnostic: str
    provenance_vars: list[str] = field(default_factory=list)
    #: Optional LLM judge identifier set by Phase 2 LLMJudge.score().
    #: Defaults to ``None`` so Phase 1 heuristic scorers can construct
    #: with the original 3-argument signature; _build_judge_vote falls
    #: back to the Phase 1 stub suffix when this is None.
    judge_model: str | None = None
    #: Optional Bayesian confidence interval set by Phase 2 LLMJudge.score().
    #: Defaults to ``None`` so _build_judge_vote can derive the synthetic
    #: Phase 1 band via :func:`_confidence_interval` when absent.
    confidence_interval: tuple[float, float] | None = None


@dataclass(frozen=True)
class ConsensusEvaluation:
    """Aggregate consensus result for a single candidate.

    This is the per-candidate analogue of
    :class:`atelier.models.data_contracts.ConsensusResult` -- but instead of
    a multi-candidate winner-selection record, it captures the full per-axis
    breakdown plus diagnostics for **one** candidate. The Orchestrator
    composes many ``ConsensusEvaluation`` records into a final
    ``ConsensusResult`` once it has scored every contender.

    The dataclass is frozen so it can be hashed into trajectory records and
    passed across the DAG without defensive copies.

    Attributes:
        candidate_id: UUID of the evaluated :class:`CandidateUI`.
        votes: One :class:`JudgeVote` per axis, keyed by :class:`JudgeAxis`.
            Always contains every axis listed in
            :data:`_AXIS_NAME_TO_ENUM` -- partial evaluations are not
            representable.
        composite_score: Weighted composite in ``[0.0, 1.0]``, computed via
            :meth:`AxisWeights.compute_composite` and (optionally)
            attenuated by the constitution penalty.
        passed: Whether ``composite_score >= convergence_threshold``. The
            single boolean the Orchestrator branches on.
        constitution_name: Name of the :class:`Constitution` enforced
            during evaluation, or ``None`` if no constitution was supplied.
        diagnostics: Free-form per-axis diagnostic strings plus two
            reserved keys: ``"bias_warning"`` (from
            :class:`AntiBiasReport`) and ``"constitution"`` (from the
            penalty helper). Reserved keys are present whether or not their
            value is informative -- absent keys would force every consumer
            to defensively ``.get(..., None)``.
    """

    candidate_id: UUID
    votes: dict[JudgeAxis, JudgeVote]
    composite_score: float
    passed: bool
    constitution_name: str | None
    diagnostics: dict[str, str]


# ---------------------------------------------------------------------------
# Per-axis deterministic scorers
# ---------------------------------------------------------------------------


def _collect_text(artifacts: dict[str, str], suffix: str) -> str:
    """Concatenate every artifact whose filename ends with ``suffix``.

    Args:
        artifacts: The ``CandidateUI.artifacts`` mapping.
        suffix: File extension to filter on (e.g., ``".css"``).

    Returns:
        Newline-joined string of matching artifact contents. Empty string if
        no artifacts match.
    """
    return "\n".join(content for name, content in artifacts.items() if name.endswith(suffix))


def _score_brand(candidate: CandidateUI) -> _JudgeScore:
    """Score brand expression via CSS token + color discipline.

    Heuristic: a brand-aligned candidate uses **CSS custom properties** (so
    tokens are reusable) and a **deliberate small palette** (so identity is
    consistent). We measure both and weight tokens 60% / colors 40% because
    a tokenless design with three colors is more brand-incoherent than a
    well-tokenized design that happens to reference a few extra accent hexes.

    Args:
        candidate: The :class:`CandidateUI` whose ``.css`` artifacts will be
            scanned. CSS-less candidates score zero (with diagnostic) rather
            than raising -- a generator producing only HTML is a meaningful
            data point, not an error condition.

    Returns:
        A :class:`_JudgeScore` in ``[0.0, 1.0]`` plus diagnostic.
    """
    css = _collect_text(candidate.artifacts, ".css")
    if not css:
        return _JudgeScore(
            score=0.0,
            diagnostic="Brand: no CSS artifacts present; cannot assess token discipline.",
            provenance_vars=[],
        )

    var_count = len(_CSS_VAR_DECL.findall(css))
    unique_colors = {match.lower() for match in _CSS_HEX_COLOR.findall(css)}
    color_count = len(unique_colors)

    var_credit = min(var_count / BRAND_TARGET_VARS, 1.0)
    color_credit = min(color_count / BRAND_TARGET_COLORS, 1.0)
    score = round(var_credit * 0.6 + color_credit * 0.4, 4)

    diagnostic = (
        f"Brand: {var_count} CSS custom properties (target {BRAND_TARGET_VARS}), "
        f"{color_count} distinct hex colors (target {BRAND_TARGET_COLORS}). "
        f"Token credit {var_credit:.2f}, color credit {color_credit:.2f}."
    )
    return _JudgeScore(
        score=score,
        diagnostic=diagnostic,
        provenance_vars=sorted(name for name in candidate.artifacts if name.endswith(".css")),
    )


def _score_originality(candidate: CandidateUI) -> _JudgeScore:
    """Score originality via CSS property + selector variety.

    Heuristic: template-y output reuses a tiny vocabulary of CSS properties
    and selectors. Hand-crafted design language stretches both -- many
    distinct properties (transforms, grid-template-areas, custom timing
    functions) and many distinct selectors. Both metrics are normalized to
    their respective targets and averaged equally.

    Args:
        candidate: The :class:`CandidateUI` whose ``.css`` artifacts will be
            inspected.

    Returns:
        A :class:`_JudgeScore` in ``[0.0, 1.0]`` plus diagnostic.
    """
    css = _collect_text(candidate.artifacts, ".css")
    if not css:
        return _JudgeScore(
            score=0.0,
            diagnostic="Originality: no CSS artifacts present; cannot assess design variety.",
            provenance_vars=[],
        )

    unique_props = {match.group(1).lower() for match in _CSS_PROPERTY.finditer(css)}
    unique_selectors = {match.group(1).strip() for match in _CSS_SELECTOR_RULE.finditer(css)}

    prop_credit = min(len(unique_props) / ORIGINALITY_TARGET_PROPS, 1.0)
    selector_credit = min(len(unique_selectors) / ORIGINALITY_TARGET_SELECTORS, 1.0)
    score = round((prop_credit + selector_credit) / 2.0, 4)

    diagnostic = (
        f"Originality: {len(unique_props)} unique CSS properties "
        f"(target {ORIGINALITY_TARGET_PROPS}), {len(unique_selectors)} unique "
        f"selectors (target {ORIGINALITY_TARGET_SELECTORS}). "
        f"Property credit {prop_credit:.2f}, selector credit {selector_credit:.2f}."
    )
    return _JudgeScore(
        score=score,
        diagnostic=diagnostic,
        provenance_vars=sorted(name for name in candidate.artifacts if name.endswith(".css")),
    )


def _score_relevance(candidate: CandidateUI) -> _JudgeScore:
    """Score relevance via HTML text-to-tag density.

    Heuristic: a relevant candidate has substantive content per unit of
    markup. We strip all tags, count visible text characters, divide by the
    number of tags, and normalize against
    :data:`RELEVANCE_TARGET_CHARS_PER_TAG`. A candidate with zero tags or no
    HTML scores zero -- there is nothing to be relevant *about*.

    Args:
        candidate: The :class:`CandidateUI` whose HTML artifacts will be
            measured.

    Returns:
        A :class:`_JudgeScore` in ``[0.0, 1.0]`` plus diagnostic.
    """
    html = _collect_text(candidate.artifacts, ".html")
    if not html:
        return _JudgeScore(
            score=0.0,
            diagnostic="Relevance: no HTML artifacts present; cannot assess content density.",
            provenance_vars=[],
        )

    tag_count = len(_HTML_TAG.findall(html))
    if tag_count == 0:
        return _JudgeScore(
            score=0.0,
            diagnostic="Relevance: HTML present but contains no tags; treated as empty markup.",
            provenance_vars=sorted(name for name in candidate.artifacts if name.endswith(".html")),
        )

    stripped = _HTML_TAG.sub("", html)
    text_chars = len(stripped.strip())
    ratio = text_chars / tag_count
    score = round(min(ratio / RELEVANCE_TARGET_CHARS_PER_TAG, 1.0), 4)

    diagnostic = (
        f"Relevance: {text_chars} text chars across {tag_count} tags, "
        f"ratio {ratio:.2f} chars/tag (target {RELEVANCE_TARGET_CHARS_PER_TAG:.1f})."
    )
    return _JudgeScore(
        score=score,
        diagnostic=diagnostic,
        provenance_vars=sorted(name for name in candidate.artifacts if name.endswith(".html")),
    )


def _score_accessibility(candidate: CandidateUI) -> _JudgeScore:
    """Score accessibility via ARIA + semantic-HTML + alt-text counts.

    Heuristic: three signals contribute equally to accessibility maturity --
    explicit ARIA attributes, HTML5 semantic landmarks, and image alt-text
    coverage. The first two are normalized against fixed targets; alt-text
    is a coverage ratio (alt-bearing imgs / total imgs, treated as 1.0 when
    there are no images at all).

    Args:
        candidate: The :class:`CandidateUI` whose HTML artifacts are
            inspected for accessibility hooks.

    Returns:
        A :class:`_JudgeScore` in ``[0.0, 1.0]`` plus diagnostic.
    """
    html = _collect_text(candidate.artifacts, ".html")
    if not html:
        return _JudgeScore(
            score=0.0,
            diagnostic="Accessibility: no HTML artifacts present; cannot assess.",
            provenance_vars=[],
        )

    aria_count = len(_HTML_ARIA.findall(html))
    lowered = html.lower()
    semantic_count = sum(1 for elem in SEMANTIC_ELEMENTS if f"<{elem}" in lowered)

    img_count = lowered.count("<img")
    alt_count = len(_HTML_ALT.findall(html))
    alt_ratio = 1.0 if img_count == 0 else min(alt_count / img_count, 1.0)

    aria_credit = min(aria_count / ACCESSIBILITY_TARGET_ARIA, 1.0)
    semantic_credit = min(semantic_count / ACCESSIBILITY_TARGET_SEMANTIC, 1.0)
    score = round((aria_credit + semantic_credit + alt_ratio) / 3.0, 4)

    diagnostic = (
        f"Accessibility: {aria_count} aria attrs (target {ACCESSIBILITY_TARGET_ARIA}), "
        f"{semantic_count} semantic landmarks (target {ACCESSIBILITY_TARGET_SEMANTIC}), "
        f"{alt_count}/{img_count} imgs with alt text. "
        f"Credits aria {aria_credit:.2f}, semantic {semantic_credit:.2f}, alt {alt_ratio:.2f}."
    )
    return _JudgeScore(
        score=score,
        diagnostic=diagnostic,
        provenance_vars=sorted(name for name in candidate.artifacts if name.endswith(".html")),
    )


def _score_visual_clarity(candidate: CandidateUI) -> _JudgeScore:
    """Score visual clarity via typography + spacing declaration counts.

    Heuristic: visually-clear candidates make deliberate, varied choices
    about typography (multiple font sizes/weights/families to establish
    hierarchy) and spacing (margin/padding/gap to separate concerns).
    Counts of relevant CSS declarations -- not unique properties, but
    total occurrences -- are normalized against fixed targets and averaged.

    Args:
        candidate: The :class:`CandidateUI` whose ``.css`` artifacts will be
            scanned.

    Returns:
        A :class:`_JudgeScore` in ``[0.0, 1.0]`` plus diagnostic.
    """
    css = _collect_text(candidate.artifacts, ".css")
    if not css:
        return _JudgeScore(
            score=0.0,
            diagnostic="Visual clarity: no CSS artifacts present; cannot assess.",
            provenance_vars=[],
        )

    lowered = css.lower()
    typo_count = sum(lowered.count(f"{prop}:") for prop in TYPOGRAPHY_PROPS)
    spacing_count = sum(lowered.count(f"{prop}:") for prop in SPACING_PROPS)

    typo_credit = min(typo_count / VISUAL_TARGET_TYPOGRAPHY, 1.0)
    spacing_credit = min(spacing_count / VISUAL_TARGET_SPACING, 1.0)
    score = round((typo_credit + spacing_credit) / 2.0, 4)

    diagnostic = (
        f"Visual clarity: {typo_count} typography decls (target {VISUAL_TARGET_TYPOGRAPHY}), "
        f"{spacing_count} spacing decls (target {VISUAL_TARGET_SPACING}). "
        f"Credits typo {typo_credit:.2f}, spacing {spacing_credit:.2f}."
    )
    return _JudgeScore(
        score=score,
        diagnostic=diagnostic,
        provenance_vars=sorted(name for name in candidate.artifacts if name.endswith(".css")),
    )


#: Dispatch table from snake_case axis name to its scorer. Module-level so
#: tests can iterate over every axis without re-listing them and Phase 2
#: can swap a single entry to drop in an LLM-backed judge.
_AXIS_SCORERS: dict[str, Callable[[CandidateUI], _JudgeScore]] = {
    "brand": _score_brand,
    "originality": _score_originality,
    "relevance": _score_relevance,
    "accessibility": _score_accessibility,
    "visual_clarity": _score_visual_clarity,
}


# ---------------------------------------------------------------------------
# Assembly helpers
# ---------------------------------------------------------------------------


def _confidence_interval(score: float) -> tuple[float, float]:
    """Clamp a symmetric confidence band around ``score`` to ``[0, 1]``.

    Phase 1 scorers are deterministic so the "interval" is purely cosmetic
    -- it keeps the :class:`JudgeVote` schema satisfied. Phase 2 judges
    will replace this with a real Bayesian CI from their token-level logits.

    Args:
        score: The point score in ``[0.0, 1.0]``.

    Returns:
        ``(low, high)`` where ``low = max(0, score - half)`` and
        ``high = min(1, score + half)``.
    """
    low = max(0.0, score - CONFIDENCE_HALF_WIDTH)
    high = min(1.0, score + CONFIDENCE_HALF_WIDTH)
    return (round(low, 4), round(high, 4))


def _build_judge_vote(
    candidate_id: UUID,
    axis_name: str,
    judge_score: _JudgeScore,
) -> JudgeVote:
    """Wrap an internal :class:`_JudgeScore` into a Pydantic :class:`JudgeVote`.

    Bridges the dataclass world (cheap, no validation) and the contract
    world (validated, serializable, persistable to BigQuery).

    Args:
        candidate_id: UUID of the candidate being scored.
        axis_name: Snake-case axis identifier (e.g., ``"visual_clarity"``).
        judge_score: The internal score record produced by a ``_score_*``
            helper.

    Returns:
        A frozen :class:`JudgeVote` ready for inclusion in a trajectory
        record. Constructed with :attr:`JudgeVote.judge_model` set to the
        Phase 1 model's display name, suffixed with ``" (Phase 1 stub)"`` so
        downstream dashboards can distinguish heuristic Phase 1 votes from
        real LLM votes in Phase 2.
    """
    axis_enum = _AXIS_NAME_TO_ENUM[axis_name]
    model_spec = JUDGE_MODEL_CONFIG[axis_name]
    # Honor Phase 2 LLM-provided judge_model / confidence_interval when
    # the scorer surfaces them; otherwise emit the Phase 1 defaults so
    # heuristic mode keeps its original on-the-wire shape unchanged.
    if judge_score.judge_model is not None:
        judge_model = judge_score.judge_model
    else:
        judge_model = f"{model_spec.display_name} (Phase 1 stub)"
    if judge_score.confidence_interval is not None:
        confidence_interval = judge_score.confidence_interval
    else:
        confidence_interval = _confidence_interval(judge_score.score)
    return JudgeVote(
        candidate_id=candidate_id,
        judge_axis=axis_enum,
        score=judge_score.score,
        confidence_interval=confidence_interval,
        reasoning=judge_score.diagnostic,
        provenance_vars=judge_score.provenance_vars,
        judge_model=judge_model,
    )


def _apply_constitution(
    composite: float,
    constitution: Constitution,
) -> tuple[float, str]:
    """Apply a soft constitution penalty when composite falls below target.

    The penalty is multiplicative and floored at :data:`CONSTITUTION_FLOOR`
    so the Fixer always has a non-trivial gradient to follow. When the
    composite already meets or exceeds ``scoring.target`` the function
    returns the composite unchanged with an affirmative diagnostic.

    Args:
        composite: The pre-penalty composite score in ``[0.0, 1.0]``.
        constitution: The :class:`Constitution` to enforce.

    Returns:
        ``(penalized_score, diagnostic)``. ``penalized_score`` is rounded
        to four decimal places to match :meth:`AxisWeights.compute_composite`.
    """
    target = constitution.scoring.target
    if composite >= target:
        diagnostic = (
            f"Constitution '{constitution.name}' satisfied: composite "
            f"{composite:.3f} >= target {target:.3f}."
        )
        return composite, diagnostic

    gap_ratio = (target - composite) / target if target > 0 else 0.0
    gap_ratio = min(max(gap_ratio, 0.0), 1.0)
    penalty_mult = max(
        1.0 - CONSTITUTION_PENALTY_STRENGTH * gap_ratio,
        CONSTITUTION_FLOOR,
    )
    penalized = round(composite * penalty_mult, 4)
    diagnostic = (
        f"Constitution '{constitution.name}' penalty: composite {composite:.3f} "
        f"< target {target:.3f}, multiplier {penalty_mult:.3f}, "
        f"adjusted score {penalized:.3f}."
    )
    return penalized, diagnostic


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def evaluate_candidate(
    candidate: CandidateUI,
    weights: AxisWeights,
    *,
    constitution: Constitution | None = None,
    convergence_threshold: float = CONVERGENCE_DEFAULT,
    seed: int | None = None,
    judge_mode: str | None = None,
    judge_client: "JudgeClient | None" = None,
) -> ConsensusEvaluation:
    """Run the full D-O-R-A-V consensus over a single candidate.

    Flow:

        1. Build an :class:`AntiBiasReport` so the evaluation order is
           randomized (or seeded, in tests) and any weight-dominance is
           surfaced to downstream consumers.
        2. Score every axis in the *shuffled* order using the dispatch
           table :data:`_AXIS_SCORERS`. Order only matters once Phase 2
           LLM judges land (they may share KV-cache prefixes), but we
           shuffle now so trajectory logs already carry the data.
        3. Wrap each internal score into a :class:`JudgeVote` and feed the
           scores into :meth:`AxisWeights.compute_composite`.
        4. Optionally apply the constitution penalty.
        5. Compare the (possibly penalized) composite to
           ``convergence_threshold`` to set ``passed``.

    Args:
        candidate: The :class:`CandidateUI` to score.
        weights: :class:`AxisWeights` configured for the BriefSpec at hand.
            Drives both the composite calculation and the dominance warning.
        constitution: Optional :class:`Constitution` selected by CSC-D
            (N6). When provided, a soft penalty is applied if the composite
            falls below ``constitution.scoring.target``.
        convergence_threshold: Composite score above which ``passed`` is
            ``True``. Defaults to :data:`CONVERGENCE_DEFAULT`.
        seed: Optional integer seed forwarded to
            :func:`atelier.nodes.anti_bias.shuffle_evaluation_order`. Pass
            a stable value in tests; pass ``None`` in production.

    Returns:
        A frozen :class:`ConsensusEvaluation` with one
        :class:`JudgeVote` per axis, the composite score, the pass flag,
        the constitution name (if any), and a diagnostics dict containing
        every per-axis diagnostic plus ``"bias_warning"`` and
        ``"constitution"`` reserved keys.

    Raises:
        ValueError: Propagated from
            :meth:`AxisWeights.compute_composite` if any per-axis score
            falls outside ``[0.0, 1.0]``. The scorers never produce
            out-of-range values, so in practice this only fires if a
            future scorer regresses on its contract.
    """
    bias_report: AntiBiasReport = build_anti_bias_report(weights, seed=seed)

    # Lazy import inside the function body avoids a circular import
    # at module load time (llm_judge imports _AXIS_SCORERS/_JudgeScore
    # from this module).
    from atelier.nodes.llm_judge import _resolve_axis_scorers  # noqa: PLC0415

    scorers = _resolve_axis_scorers(mode=judge_mode, client=judge_client)

    raw_scores: dict[str, float] = {}
    votes: dict[JudgeAxis, JudgeVote] = {}
    diagnostics: dict[str, str] = {}

    for axis_name in bias_report.evaluation_order:
        judge_score = scorers[axis_name](candidate)
        raw_scores[axis_name] = judge_score.score
        votes[_AXIS_NAME_TO_ENUM[axis_name]] = _build_judge_vote(
            candidate.candidate_id, axis_name, judge_score
        )
        diagnostics[axis_name] = judge_score.diagnostic

    composite = weights.compute_composite(raw_scores)

    constitution_name: str | None = None
    if constitution is not None:
        composite, constitution_diagnostic = _apply_constitution(composite, constitution)
        diagnostics["constitution"] = constitution_diagnostic
        constitution_name = constitution.name
    else:
        diagnostics["constitution"] = "No constitution supplied; composite unaltered."

    diagnostics["bias_warning"] = bias_report.bias_warning or "No weight dominance detected."

    passed = composite >= convergence_threshold

    return ConsensusEvaluation(
        candidate_id=candidate.candidate_id,
        votes=votes,
        composite_score=composite,
        passed=passed,
        constitution_name=constitution_name,
        diagnostics=diagnostics,
    )
