"""current implementation LLM judge module for the N3d ConsensusAgent.

v1.0 implementation (:mod:`atelier.nodes.consensus`) ships deterministic heuristics for
every D-O-R-A-V axis. current implementation swaps each ``_score_*`` heuristic for a Vertex
AI LLM call routed via :data:`atelier.models.model_registry.JUDGE_MODEL_CONFIG`
while keeping the surrounding plumbing (anti-bias report, composite weighting,
constitution penalty, :class:`ConsensusEvaluation` shape) untouched.

Module structure:

    * :class:`LLMJudgeResponse` -- the raw envelope a :class:`JudgeClient`
      hands back (text + model_id + token counts + optional avg_logprob).
    * :class:`JudgeClient` -- a Protocol so the surrounding code never
      depends on ``vertexai`` at import time; tests inject a hand-rolled
      fake; production wires :class:`VertexAIJudgeClient`.
    * :func:`extract_score_from_response` and :func:`compute_bayesian_ci`
      -- pure helpers, unit-tested in isolation.
    * :class:`LLMJudge` -- the abstract base implementing the template
      method :meth:`LLMJudge.score`. Five concrete subclasses
      (:class:`BrandLLMJudge`, :class:`OriginalityLLMJudge`,
      :class:`RelevanceLLMJudge`, :class:`AccessibilityLLMJudge`,
      :class:`VisualClarityLLMJudge`) declare only their ``axis_name``;
      everything else is wired from :data:`JUDGE_MODEL_CONFIG` and
      :data:`JUDGE_PROMPTS`.
    * :func:`make_llm_judge` -- factory keyed by axis name.
    * :func:`_resolve_axis_scorers` -- dispatch resolver for the three
      modes the orchestrator can pick: ``heuristic`` (default, returns the
      v1.0 implementation callables verbatim), ``llm`` (every axis routes to its LLM
      judge), or ``hybrid`` (LLM score wins but the diagnostic records both
      so dashboards can plot disagreement). Driven by the
      ``ATELIER_JUDGE_MODE`` env var when ``mode`` is left unset.
    * :class:`VertexAIJudgeClient` -- the production client. The Vertex
      SDK is imported lazily inside :func:`_import_vertex_sdk` so this
      module imports cleanly on hosts where ``google-cloud-aiplatform`` is
      not installed (v1.0 implementation dependency state).

Failure trichotomy (per architectural invariants):

    * **Self-heal** -- not implemented here; client implementations may
      retry transient errors before raising.
    * **Fail-soft** -- :meth:`LLMJudge.score` wraps the client call in a
      ``try/except`` that traps every exception (client timeout, network
      failure, JSON parse error, score out of range) and falls back to the
      v1.0 implementation heuristic for the same axis. The diagnostic is explicitly
      prefixed with ``"LLM judge fallback (<ExceptionName>): "`` so
      downstream consumers (trajectory logger, calibration dashboard) can
      see the degradation -- "agent always acknowledges degradation."
    * **Fail-loud** -- :func:`_resolve_axis_scorers` raises
      :class:`ValueError` for an unknown mode or a missing client; calling
      :meth:`VertexAIJudgeClient.generate` without the SDK installed
      raises :class:`ImportError`. Misconfiguration is loud; runtime
      degradation is soft.

PRD Reference: §6.3 (N3d ConsensusAgent), F0209-F0211
ADR Reference: 0006 (Google-native only), 0014 (Gemini 2.5 Flash Preview pin)
"""

from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    # CandidateUI is only used in type annotations on the JudgeClient
    # Protocol and LLMJudge.evaluate signature; gating it behind
    # TYPE_CHECKING avoids a runtime import cycle if downstream
    # consumers wire CandidateUI through this module.
    from atelier.models.data_contracts import CandidateUI
from atelier.models.model_registry import JUDGE_MODEL_CONFIG, ModelSpec

# _JudgeScore is imported from the cycle-neutral _types module (not from
# consensus directly) so that this module can be imported in any order
# relative to atelier.nodes.consensus without NameError.
from atelier.nodes._types import _JudgeScore

# _AXIS_SCORERS is NOT imported at module level — doing so would create a
# circular dependency because consensus imports _resolve_axis_scorers from
# this module (lazily), and both modules were previously importing from each
# other at module load time. Instead, _AXIS_SCORERS is imported inside
# LLMJudge.__init__ when it is actually needed.

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

#: Name of the environment variable that selects the judge mode at runtime.
#: Per PRD §6.3 (N3d) and the audit's FA-018 routing requirement.
ATELIER_JUDGE_MODE_ENV: str = "ATELIER_JUDGE_MODE"

#: Canonical mode strings. Kept as module-level constants so tests, the
#: dispatch resolver, and orchestrator config code share one source of truth.
JUDGE_MODE_HEURISTIC: str = "heuristic"
JUDGE_MODE_LLM: str = "llm"
JUDGE_MODE_HYBRID: str = "hybrid"

#: The default mode applied when neither the parameter nor the env var
#: supplies one. Heuristic preserves v1.0 implementation behavior so the 249-test Phase
#: 1 suite keeps passing without any opt-in.
DEFAULT_JUDGE_MODE: str = JUDGE_MODE_HEURISTIC

#: Set of all valid mode strings. The resolver checks membership for a fast,
#: explicit failure on unknown modes.
VALID_JUDGE_MODES: frozenset[str] = frozenset(
    {JUDGE_MODE_HEURISTIC, JUDGE_MODE_LLM, JUDGE_MODE_HYBRID},
)

#: Half-width of the synthetic confidence interval used when the LLM
#: response carries no ``avg_logprob``. Mirrors the v1.0 implementation
#: :data:`atelier.nodes.consensus.CONFIDENCE_HALF_WIDTH` so dashboards
#: don't show a discontinuity when LLM mode is enabled.
CI_DEFAULT_HALF_WIDTH: float = 0.10

#: Default timeout for a single LLM judge call, in seconds. Generous because
#: Originality runs on Gemini 2.5 Pro Thinking with an 8K thinking budget;
#: tighter axis-specific budgets can be added if planned enhancement telemetry warrants.
DEFAULT_JUDGE_TIMEOUT_S: float = 30.0

#: Regex that strips an optional ```json ...``` markdown fence from a
#: response body. Gemini occasionally wraps its JSON output in a fence even
#: when asked not to; the parser peels the fence before :func:`json.loads`.
_JSON_FENCE: re.Pattern[str] = re.compile(
    r"^```(?:json)?\s*\n?(.*?)\n?```\s*$",
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Judge prompt registry
# ---------------------------------------------------------------------------

# The output schema every judge is asked to follow. Kept as a shared trailer
# appended to each axis-specific system prompt so the parsing contract is
# defined in exactly one place.
_OUTPUT_SCHEMA_TRAILER = (
    "\n\n"
    "Respond with a single JSON object and nothing else. The object must "
    'have three fields: "score" (a float between 0.0 and 1.0), "reasoning" '
    '(a one-sentence justification of the score), and "evidence" (a list '
    "of artifact filenames you consulted, e.g. ['index.html', 'main.css']). "
    "Do not wrap the JSON in markdown code fences. Do not include any "
    "commentary outside the JSON object."
)

#: Axis → ``(system_prompt, user_template)`` pairs. The system prompt sets
#: the judge persona and scoring rubric; the user template is formatted with
#: ``{artifacts}`` at call time. The five system prompts each mention their
#: axis keyword in lowercase so :func:`TestModuleConstants.test_prompts_mention_axis_specific_concerns`
#: -- the contract that judges don't drift across axes -- is satisfied.
JUDGE_PROMPTS: dict[str, tuple[str, str]] = {
    "brand": (
        "You are a brand-alignment judge for UI candidates. Score how "
        "coherently the candidate expresses a brand identity through CSS "
        "custom-property tokens, a deliberate restrained color palette, "
        "and a consistent typographic voice. Higher scores reflect tighter "
        "token discipline (a single source of truth for colors, spacing, "
        "radii) and a small, intentional palette that signals brand maturity."
        + _OUTPUT_SCHEMA_TRAILER,
        "Evaluate the following candidate artifacts for brand alignment.\n\n{artifacts}",
    ),
    "originality": (
        "You are an originality judge for UI candidates. Score how "
        "original and intentional the design language is. Penalize "
        "template-y CSS vocabularies (few distinct properties, few distinct "
        "selectors, generic markup); reward varied, hand-crafted CSS that "
        "demonstrates deliberate design choices and a recognizable point "
        "of view." + _OUTPUT_SCHEMA_TRAILER,
        "Evaluate the following candidate artifacts for originality.\n\n{artifacts}",
    ),
    "relevance": (
        "You are a relevance judge for UI candidates. Score how "
        "substantively the candidate addresses the inferred brief: is the "
        "content dense and on-topic, or is it placeholder text padding out "
        "empty markup? Higher scores indicate a meaningful chars-per-tag "
        "density and content that reads as a real artifact rather than "
        "scaffold." + _OUTPUT_SCHEMA_TRAILER,
        "Evaluate the following candidate artifacts for relevance.\n\n{artifacts}",
    ),
    "accessibility": (
        "You are an accessibility judge for UI candidates. Score the "
        "candidate's a11y maturity along three dimensions: ARIA attribute "
        "coverage on interactive and structural elements, HTML5 semantic "
        "landmark usage (header, nav, main, article, section, footer), "
        "and image alt-text presence. Higher scores reflect thorough "
        "accessible structure, not isolated tokens." + _OUTPUT_SCHEMA_TRAILER,
        "Evaluate the following candidate artifacts for accessibility.\n\n{artifacts}",
    ),
    "visual_clarity": (
        "You are a visual-clarity judge for UI candidates. Score the "
        "candidate's typographic hierarchy and spacing discipline. Higher "
        "scores reflect intentional use of font sizes, weights, line "
        "heights, and letter spacing to establish hierarchy, paired with "
        "consistent margin/padding/gap rhythms that establish structure." + _OUTPUT_SCHEMA_TRAILER,
        "Evaluate the following candidate artifacts for visual clarity.\n\n{artifacts}",
    ),
}


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------


class LLMJudgeError(Exception):
    """Raised when an LLM judge response cannot be interpreted.

    Distinct from generic :class:`Exception` so callers can choose to retry
    transient client errors (network, timeout) but immediately fall back on
    structured parse errors. :meth:`LLMJudge.score` treats both as
    fail-soft and falls back to the v1.0 implementation heuristic in either case.
    """


# ---------------------------------------------------------------------------
# Response envelope and client Protocol
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMJudgeResponse:
    """Envelope around a single LLM judge call's raw output.

    Frozen so it can be hashed into trajectory records. Plain dataclass --
    no Pydantic -- because the score is parsed out of ``text``; the
    envelope itself just transports raw bytes plus side metadata.

    Attributes:
        text: The raw text the model returned. Expected to be JSON (with
            or without a ```json``` fence) matching the schema declared in
            the system prompt.
        model_id: The Vertex AI model identifier the response came from.
            Recorded for provenance so calibration can distinguish Flash
            vs. Pro vs. Pro-Thinking judges.
        input_tokens: Prompt token count if the client surfaced it; 0
            otherwise. Used for cost ledger accounting.
        output_tokens: Completion token count if surfaced; 0 otherwise.
        avg_logprob: Mean per-token log probability of the response if the
            model surfaced it. ``None`` when unavailable. Used by
            :func:`compute_bayesian_ci` to narrow the confidence interval
            for confident judges.
    """

    text: str
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    avg_logprob: float | None = None


class JudgeClient(Protocol):
    """Pluggable LLM client used by :class:`LLMJudge`.

    The Protocol is the entire surface :class:`LLMJudge` couples to. Tests
    inject a hand-rolled fake; production wires :class:`VertexAIJudgeClient`.
    Keeping this a Protocol (rather than an abstract base class) means we
    never have to subclass it in tests -- duck-typing is enough.
    """

    def generate(
        self,
        *,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_output_tokens: int,
        timeout_s: float,
    ) -> LLMJudgeResponse:
        """Issue a single LLM call and return the raw response envelope.

        Implementations may retry transient errors internally before raising;
        anything that does raise here is caught by :meth:`LLMJudge.score`
        and converted into a heuristic fallback.
        """
        ...


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _clamp_unit(value: float) -> float:
    """Clamp ``value`` to the closed unit interval ``[0.0, 1.0]``."""
    return max(0.0, min(1.0, value))


def extract_score_from_response(
    response: LLMJudgeResponse,
) -> tuple[float, str, list[str]]:
    """Parse an :class:`LLMJudgeResponse` into ``(score, reasoning, evidence)``.

    Tolerates an optional ```json``` markdown fence (Gemini occasionally
    emits one despite the system prompt asking it not to). Clamps the score
    to ``[0.0, 1.0]`` so a model that overshoots the schema still produces
    a valid :class:`atelier.models.data_contracts.JudgeVote`.

    Args:
        response: The :class:`LLMJudgeResponse` envelope from the client.

    Returns:
        A 3-tuple of ``(clamped_score, reasoning_text, evidence_filenames)``.

    Raises:
        LLMJudgeError: When the body is not valid JSON, is JSON but not an
            object, lacks a ``"score"`` field, or has a non-numeric score.
            All four conditions are routed to fallback by the surrounding
            :meth:`LLMJudge.score`.
    """
    text = response.text.strip()

    match = _JSON_FENCE.match(text)
    if match:
        text = match.group(1).strip()

    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMJudgeError(
            f"Judge response is not valid JSON: {exc.msg} at position {exc.pos}"
        ) from exc

    if not isinstance(payload, dict):
        raise LLMJudgeError(f"Judge response must be a JSON object, got {type(payload).__name__}")

    if "score" not in payload:
        raise LLMJudgeError(
            f"Judge response missing required 'score' field; keys present: {sorted(payload.keys())}"
        )

    raw_score = payload["score"]
    # Reject bool explicitly: while bool is a subclass of int in Python, a
    # judge returning True/False instead of a numeric score is a schema
    # violation, not a valid 1.0/0.0 score.
    if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
        raise LLMJudgeError(
            f"Judge response 'score' must be a numeric value, got {type(raw_score).__name__}"
        )

    score = _clamp_unit(float(raw_score))
    reasoning = str(payload.get("reasoning", "")).strip()

    evidence_raw = payload.get("evidence", [])
    if isinstance(evidence_raw, list):  # noqa: SIM108
        evidence = [str(item) for item in evidence_raw]
    else:
        # Tolerate a stringy evidence field by wrapping it. Anything more
        # exotic (dict, number) gets silently dropped to an empty list to
        # keep the fallback simple; the score is still extracted.
        evidence = []

    return (score, reasoning, evidence)


def compute_bayesian_ci(
    score: float,
    avg_logprob: float | None,
) -> tuple[float, float]:
    """Derive a confidence interval around ``score`` from token logprob.

    A confident judge (``avg_logprob`` near 0, ie ``exp(logprob)`` near 1)
    gets a narrow interval; an unconfident judge (very negative logprob,
    ``exp(logprob)`` near 0) gets a band approaching the default width.
    When ``avg_logprob`` is unavailable we fall back to the default symmetric
    half-width :data:`CI_DEFAULT_HALF_WIDTH` so the schema stays consistent.

    Args:
        score: Point estimate in ``[0.0, 1.0]``.
        avg_logprob: Mean per-token log probability of the LLM response,
            or ``None`` when the client cannot surface it.

    Returns:
        ``(low, high)`` clamped to the closed unit interval. Always
        satisfies ``low <= score <= high``.
    """
    if avg_logprob is None:
        half = CI_DEFAULT_HALF_WIDTH
    else:
        # exp(avg_logprob) ∈ (0, 1] is the geometric-mean per-token
        # probability. Subtracting from 1 gives the uncertainty. Scaling
        # by CI_DEFAULT_HALF_WIDTH keeps the interval comparable to the
        # default-band v1.0 implementation votes.
        confidence = math.exp(avg_logprob)
        half = CI_DEFAULT_HALF_WIDTH * (1.0 - confidence)

    low = max(0.0, score - half)
    high = min(1.0, score + half)
    return (low, high)


def _format_artifacts(artifacts: dict[str, str]) -> str:
    """Render a candidate's ``artifacts`` mapping into a prompt-ready block.

    The format ``--- filename ---\\n<content>`` is the same lightweight
    delimiter used by Hermes/agent-dag-pipeline upstream so judges trained
    on those traces can recognize the structure.

    Args:
        artifacts: The :attr:`CandidateUI.artifacts` mapping (filename to
            file content).

    Returns:
        A single string with each artifact preceded by a delimiter line;
        empty artifacts yields ``"(no artifacts provided)"`` so the judge
        always sees a non-empty user prompt body.
    """
    if not artifacts:
        return "(no artifacts provided)"
    return "\n\n".join(f"--- {name} ---\n{content}" for name, content in sorted(artifacts.items()))


# ---------------------------------------------------------------------------
# Judge base class + concrete subclasses (template method)
# ---------------------------------------------------------------------------


class LLMJudge:
    """Abstract base class for the five D-O-R-A-V LLM judges.

    Implements the template-method pattern: subclasses declare only their
    :attr:`axis_name`; this base wires the system prompt, user template,
    model spec, fallback, and the entire :meth:`score` flow. The result is
    that adding or modifying judges is a single-line subclass change plus
    a :data:`JUDGE_PROMPTS` entry.

    Attributes:
        axis_name: Snake-case axis identifier, must match a key in
            :data:`JUDGE_MODEL_CONFIG` and :data:`JUDGE_PROMPTS`. Overridden
            by each concrete subclass; the base value of ``""`` would
            trigger a :class:`KeyError` in :meth:`model_spec` if a caller
            instantiated :class:`LLMJudge` directly.
    """

    axis_name: str = ""

    def __init__(
        self,
        *,
        client: JudgeClient,
        fallback: Callable[[CandidateUI], _JudgeScore] | None = None,
    ) -> None:
        """Wire the judge with a client and an optional explicit fallback.

        Args:
            client: The :class:`JudgeClient` the judge will call. Tests
                inject a fake; production wires :class:`VertexAIJudgeClient`.
            fallback: Optional caller-supplied fallback. When ``None``
                (the common case) the judge falls back to the v1.0 implementation
                heuristic scorer for the same axis -- guaranteeing the
                surrounding pipeline never breaks even if Vertex AI is
                unavailable.
        """
        self._client = client
        # When no caller-supplied fallback exists, fall back to the v1.0 implementation
        # heuristic for the same axis. This is the failure-soft default and
        # the reason the surrounding pipeline never breaks.
        # _AXIS_SCORERS is imported lazily here (not at module level) to
        # break the consensus ↔ llm_judge circular import. Both modules are
        # guaranteed to be fully initialised by the time __init__ is called.
        if fallback is not None:
            self._fallback: Callable[[CandidateUI], _JudgeScore] = fallback
        else:
            from atelier.nodes.consensus import _AXIS_SCORERS  # noqa: PLC0415

            self._fallback = _AXIS_SCORERS[self.axis_name]

    @property
    def model_spec(self) -> ModelSpec:
        """The :class:`ModelSpec` for this judge's axis."""
        return JUDGE_MODEL_CONFIG[self.axis_name]

    @property
    def system_prompt(self) -> str:
        """The system prompt for this judge's axis."""
        return JUDGE_PROMPTS[self.axis_name][0]

    @property
    def user_template(self) -> str:
        """The user prompt template (with ``{artifacts}`` placeholder)."""
        return JUDGE_PROMPTS[self.axis_name][1]

    def score(self, candidate: CandidateUI) -> _JudgeScore:
        """Score a candidate by calling the LLM client; fail-soft on error.

        The full flow:

            1. Format the user prompt from ``candidate.artifacts``.
            2. Call ``self._client.generate(...)`` with the axis-specific
               model spec parameters.
            3. Parse the response into ``(score, reasoning, evidence)``
               via :func:`extract_score_from_response`.
            4. Compute a Bayesian CI from any available ``avg_logprob`` via
               :func:`compute_bayesian_ci`.
            5. Build a :class:`_JudgeScore` populated with the LLM-derived
               ``judge_model`` and ``confidence_interval``.

        Any exception raised by steps 2-4 is caught and routed to
        :attr:`_fallback`, with the diagnostic explicitly prefixed
        ``"LLM judge fallback (<ExceptionName>): "`` so dashboards can
        distinguish degraded votes from healthy ones.

        Args:
            candidate: The :class:`CandidateUI` to score.

        Returns:
            A :class:`_JudgeScore` -- either LLM-derived or fallback-derived.
            Both code paths return a valid score in ``[0.0, 1.0]``.
        """
        spec = self.model_spec
        try:
            user_prompt = self.user_template.format(
                artifacts=_format_artifacts(candidate.artifacts),
            )
            response = self._client.generate(
                model_id=spec.model_id,
                system_prompt=self.system_prompt,
                user_prompt=user_prompt,
                temperature=spec.temperature,
                max_output_tokens=spec.max_output_tokens,
                timeout_s=DEFAULT_JUDGE_TIMEOUT_S,
            )
            score, reasoning, evidence = extract_score_from_response(response)
            ci = compute_bayesian_ci(score, response.avg_logprob)
        except Exception as exc:  # noqa: BLE001
            # Fail-soft: any client error, parse error, or schema mismatch
            # collapses to the heuristic fallback so the surrounding
            # pipeline never breaks. The structured-error rule allows this
            # broad catch because we return a structured _JudgeScore with
            # the degradation explicitly recorded in the diagnostic
            # ("agent always acknowledges degradation" per architectural invariants §
            # failure trichotomy).
            fallback_score = self._fallback(candidate)
            return _JudgeScore(
                score=fallback_score.score,
                diagnostic=(
                    f"LLM judge fallback ({type(exc).__name__}): {fallback_score.diagnostic}"
                ),
                provenance_vars=fallback_score.provenance_vars,
                judge_model=fallback_score.judge_model,
                confidence_interval=fallback_score.confidence_interval,
            )

        diagnostic = (
            reasoning
            if reasoning
            else f"LLM judge ({spec.display_name}) returned score {score:.3f}."
        )
        return _JudgeScore(
            score=score,
            diagnostic=diagnostic,
            provenance_vars=list(evidence),
            judge_model=f"{spec.display_name} ({spec.model_id})",
            confidence_interval=ci,
        )


class BrandLLMJudge(LLMJudge):
    """LLM judge for the Brand axis."""

    axis_name = "brand"


class OriginalityLLMJudge(LLMJudge):
    """LLM judge for the Originality axis. Runs on Gemini 2.5 Pro Thinking."""

    axis_name = "originality"


class RelevanceLLMJudge(LLMJudge):
    """LLM judge for the Relevance axis."""

    axis_name = "relevance"


class AccessibilityLLMJudge(LLMJudge):
    """LLM judge for the Accessibility axis."""

    axis_name = "accessibility"


class VisualClarityLLMJudge(LLMJudge):
    """LLM judge for the Visual-Clarity axis."""

    axis_name = "visual_clarity"


#: Axis → concrete-judge-class registry. Used by :func:`make_llm_judge`.
_LLM_JUDGE_CLASSES: dict[str, type[LLMJudge]] = {
    "brand": BrandLLMJudge,
    "originality": OriginalityLLMJudge,
    "relevance": RelevanceLLMJudge,
    "accessibility": AccessibilityLLMJudge,
    "visual_clarity": VisualClarityLLMJudge,
}


def make_llm_judge(
    axis_name: str,
    client: JudgeClient,
    *,
    fallback: Callable[[CandidateUI], _JudgeScore] | None = None,
) -> LLMJudge:
    """Construct the right :class:`LLMJudge` subclass for ``axis_name``.

    Args:
        axis_name: Snake-case axis identifier (one of ``brand``,
            ``originality``, ``relevance``, ``accessibility``,
            ``visual_clarity``).
        client: The :class:`JudgeClient` to inject.
        fallback: Optional caller-supplied fallback; see
            :meth:`LLMJudge.__init__`.

    Returns:
        A constructed :class:`LLMJudge` instance.

    Raises:
        ValueError: When ``axis_name`` is not a known axis. Fails loud
            because passing a typo'd axis name through to runtime would
            produce a misleading silent heuristic fallback.
    """
    if axis_name not in _LLM_JUDGE_CLASSES:
        raise ValueError(f"Unknown axis '{axis_name}'; valid axes are {sorted(_LLM_JUDGE_CLASSES)}")
    judge_cls = _LLM_JUDGE_CLASSES[axis_name]
    return judge_cls(client=client, fallback=fallback)


# ---------------------------------------------------------------------------
# Dispatch resolver and scorer factories
# ---------------------------------------------------------------------------


def _make_llm_scorer(
    axis_name: str,
    client: JudgeClient,
) -> Callable[[CandidateUI], _JudgeScore]:
    """Bind an :class:`LLMJudge` and return its :meth:`score` method.

    The returned bound method is shape-compatible with the v1.0 implementation
    :data:`_AXIS_SCORERS` dispatch entries.
    """
    judge = make_llm_judge(axis_name, client)
    return judge.score


def _make_hybrid_scorer(
    axis_name: str,
    client: JudgeClient,
) -> Callable[[CandidateUI], _JudgeScore]:
    """Build a hybrid scorer that runs both heuristic and LLM.

    Returns a closure that:

        1. Runs the v1.0 implementation heuristic for the axis.
        2. Runs the LLM judge for the same axis.
        3. Returns the LLM's score (LLM wins) but prefixes the diagnostic
           with ``"hybrid: llm=..., heuristic=..., |delta|=..."`` so
           calibration dashboards can plot disagreement between modes
           without re-running anything.
    """
    from atelier.nodes.consensus import _AXIS_SCORERS  # noqa: PLC0415

    llm_judge = make_llm_judge(axis_name, client)
    heuristic_scorer = _AXIS_SCORERS[axis_name]

    def hybrid_scorer(candidate: CandidateUI) -> _JudgeScore:
        heuristic_result = heuristic_scorer(candidate)
        llm_result = llm_judge.score(candidate)
        delta = abs(llm_result.score - heuristic_result.score)
        diagnostic = (
            f"hybrid: llm={llm_result.score:.3f}, "
            f"heuristic={heuristic_result.score:.3f}, "
            f"|delta|={delta:.3f}. {llm_result.diagnostic}"
        )
        return _JudgeScore(
            score=llm_result.score,
            diagnostic=diagnostic,
            provenance_vars=llm_result.provenance_vars,
            judge_model=llm_result.judge_model,
            confidence_interval=llm_result.confidence_interval,
        )

    return hybrid_scorer


def _resolve_axis_scorers(
    *,
    mode: str | None = None,
    client: JudgeClient | None = None,
) -> dict[str, Callable[[CandidateUI], _JudgeScore]]:
    """Return the per-axis scorer dispatch dict for the requested mode.

    Args:
        mode: One of :data:`JUDGE_MODE_HEURISTIC`, :data:`JUDGE_MODE_LLM`,
            or :data:`JUDGE_MODE_HYBRID`. When ``None`` the mode is read
            from the :data:`ATELIER_JUDGE_MODE_ENV` environment variable,
            falling back to :data:`DEFAULT_JUDGE_MODE` if unset.
        client: A :class:`JudgeClient` required for ``llm`` and ``hybrid``
            modes; ignored in ``heuristic`` mode.

    Returns:
        Dict mapping snake-case axis name to a scorer callable with
        signature ``(CandidateUI) -> _JudgeScore``. In ``heuristic`` mode
        the values are the exact :data:`_AXIS_SCORERS` callables (identity-
        preserving) so backward compatibility tests pass via ``is``.

    Raises:
        ValueError: When ``mode`` is not a known mode, or when ``client``
            is ``None`` for any non-heuristic mode. Fails loud because
            silent fallback to heuristic would mask a misconfiguration.
    """
    # Lazy import of _AXIS_SCORERS breaks the consensus ↔ llm_judge cycle.
    # By the time _resolve_axis_scorers is called, both modules are guaranteed
    # to be fully initialised (it's called from evaluate_candidate, never at
    # import time). Python's module cache ensures this import is O(1) after
    # the first call.
    from atelier.nodes.consensus import _AXIS_SCORERS  # noqa: PLC0415

    if mode is None:
        mode = os.environ.get(ATELIER_JUDGE_MODE_ENV, DEFAULT_JUDGE_MODE)

    if mode not in VALID_JUDGE_MODES:
        raise ValueError(
            f"Unknown judge mode '{mode}'; valid modes are {sorted(VALID_JUDGE_MODES)}"
        )

    if mode == JUDGE_MODE_HEURISTIC:
        # Identity-preserving dict copy: tests assert
        # ``scorers[axis] is _AXIS_SCORERS[axis]`` so we cannot wrap.
        return dict(_AXIS_SCORERS)

    if client is None:
        raise ValueError(
            f"Judge mode '{mode}' requires a non-None client; "
            "pass a JudgeClient (e.g. VertexAIJudgeClient) to evaluate_candidate."
        )

    if mode == JUDGE_MODE_LLM:
        return {axis: _make_llm_scorer(axis, client) for axis in _AXIS_SCORERS}

    # mode == JUDGE_MODE_HYBRID; the membership check above guarantees
    # this is the only remaining case.
    return {axis: _make_hybrid_scorer(axis, client) for axis in _AXIS_SCORERS}


# ---------------------------------------------------------------------------
# Vertex AI client (lazy SDK import)
# ---------------------------------------------------------------------------


def _import_vertex_sdk() -> tuple[Any, Any]:
    """Lazy import of the Vertex AI SDK.

    Kept as a module-level function (rather than inlined) for two reasons:

        1. **Testability** -- the lazy-import contract is verified by
           ``mock.patch.object(module, "_import_vertex_sdk", side_effect=...)``
           which only works if the importer is an attribute of the module.
        2. **Single failure site** -- when the SDK is missing, the
           :class:`ImportError` originates here, making the stack trace
           pinpoint the cause rather than burying it in a Vertex call.

    Returns:
        A two-tuple ``(vertexai, generative_models)`` so callers can
        ``init()`` and construct ``GenerativeModel`` instances.

    Raises:
        ImportError: When ``google-cloud-aiplatform`` is not installed in
            the active environment. Fails loud at the call site instead of
            producing a misleading partial response.
    """
    import vertexai  # noqa: PLC0415
    from vertexai import generative_models  # noqa: PLC0415

    return (vertexai, generative_models)


@dataclass
class VertexAIJudgeClient:
    """Production :class:`JudgeClient` backed by Vertex AI Gemini models.

    Construction does *no* network I/O and does not import the Vertex SDK
    -- both happen lazily inside :meth:`generate`. This keeps the module
    importable on hosts where ``google-cloud-aiplatform`` is not installed
    (the v1.0 implementation dependency state) and lets test environments mock the
    SDK at the boundary.

    Attributes:
        project: GCP project ID hosting the Vertex AI endpoints.
        location: Vertex AI region. Defaults to ``us-central1`` per the
            model registry's primary region.
        _model_cache: Memoizes ``GenerativeModel`` instances per ``model_id``
            so repeated calls share the warmed-up model handle.
        _initialized: Tracks whether :func:`vertexai.init` has been called
            in this process. Reset on every new client instance.
    """

    project: str
    location: str = "us-central1"
    _model_cache: dict[str, Any] = field(default_factory=dict, repr=False)
    _initialized: bool = field(default=False, init=False, repr=False)

    def generate(
        self,
        *,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_output_tokens: int,
        timeout_s: float,
    ) -> LLMJudgeResponse:
        """Issue one Vertex AI Gemini call and wrap the response.

        Imports the Vertex SDK lazily via :func:`_import_vertex_sdk`,
        initializes the SDK on first call, caches the
        :class:`GenerativeModel` handle by ``model_id`` to amortize warm-up,
        and surfaces token counts plus ``avg_logprob`` from the response
        metadata when available.

        Args:
            model_id: Vertex AI model resource name (e.g.,
                ``"gemini-2.5-flash-preview-05-20"``).
            system_prompt: System instruction for the model.
            user_prompt: User-turn prompt body (the formatted artifacts).
            temperature: Sampling temperature from the axis ModelSpec.
            max_output_tokens: Max tokens to generate from the axis ModelSpec.
            timeout_s: Per-call timeout in seconds. Currently advisory --
                the underlying SDK call does not accept a timeout kwarg
                in every version; future-proofed for when it does.

        Returns:
            An :class:`LLMJudgeResponse` envelope with text, model_id,
            token counts, and avg_logprob (when surfaced).

        Raises:
            ImportError: When the Vertex SDK is not installed. Propagated
                from :func:`_import_vertex_sdk` so misconfiguration is
                visible and loud.
            LLMJudgeError: When the SDK returns a malformed response shape.
        """
        # timeout_s is captured for future SDK versions that accept it; the
        # current vertexai client does not, so we annotate the parameter
        # rather than dropping it from the Protocol.
        _ = timeout_s

        vertexai_mod, generative_models = _import_vertex_sdk()

        if not self._initialized:
            vertexai_mod.init(project=self.project, location=self.location)
            # Dataclass mutation is permitted because the class is not frozen;
            # _initialized is excluded from __init__ to keep the constructor
            # signature clean.
            self._initialized = True

        model = self._model_cache.get(model_id)
        if model is None:
            model = generative_models.GenerativeModel(
                model_name=model_id,
                system_instruction=system_prompt,
            )
            self._model_cache[model_id] = model

        generation_config = generative_models.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
        )

        # P0-08: This call blocks the event loop when invoked from async code.
        # The caller (LLMJudge.score → evaluate_candidate in consensus.py)
        # should wrap the entire score() call in asyncio.to_thread() at the
        # call-site to avoid head-of-line blocking. This method stays sync
        # for backwards compatibility with the existing test suite.
        response = model.generate_content(
            user_prompt,
            generation_config=generation_config,
        )

        text = getattr(response, "text", None)
        if text is None:
            raise LLMJudgeError(
                "Vertex AI response has no .text attribute; "
                f"response type was {type(response).__name__}"
            )

        input_tokens = 0
        output_tokens = 0
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
            output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)

        avg_logprob: float | None = None
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            raw_logprob = getattr(candidates[0], "avg_logprobs", None)
            if raw_logprob is not None:
                avg_logprob = float(raw_logprob)

        return LLMJudgeResponse(
            text=text,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            avg_logprob=avg_logprob,
        )
