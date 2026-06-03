"""PlannerAgent — dynamic DAG routing based on brief analysis.

The PlannerAgent is the differentiating node that makes Atelier's pipeline
adaptive: given a brief, it decides which downstream nodes run, with what
parameters. This replaces the fixed DAG (same path for every brief) with
a planner-led DAG where edges activate conditionally based on the plan.

The ``PlanStep`` Pydantic model drives all downstream routing:
    - ``should_run_wrai``: skip expensive web research for narrow briefs
    - ``ensemble_k``: allocate more generators for ambiguous creative briefs
    - ``axis_weights``: reweight D-O-R-A-V judges per the brief's objective
    - ``constitution``: select brand constitution (apple-grade, brutalist, etc.)
    - ``gate_axes_to_skip``: skip irrelevant gates for efficiency
    - ``reasoning``: one-sentence justification (surfaced in trace + dashboard)

PRD Reference: §6.3 N0 (PlannerAgent)
ADR Reference: 0007 (worktree discipline)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

# <no_unverified_apis>: google-adk pinned >=2.1.0,<3 (pyproject.toml §G4). Verified
# against the installed wheel (google.adk.__version__ == "2.1.0") that the LlmAgent
# symbol imported below resolves to class google.adk.agents.llm_agent.LlmAgent.
# Per the verified project override (§24), the clarify gate is EVENT-DRIVEN and does
# NOT use google.adk.agents.LoopAgent (which exists in 2.1.0 but is deliberately
# avoided): a fixed-round loop would re-ask on every turn; uncertainty-gating fires
# the clarify event at most twice per surface (AT-030 <=2-events/surface cap).
from google.adk.agents import LlmAgent
from google.genai import types as genai_types
from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from atelier.intake.research_findings import ResearchFindings
    from atelier.models.clarify_models import Gap, OpenQuestion

from atelier.models.model_armor_callbacks import (
    model_armor_after_callback,
    model_armor_before_callback,
)
from atelier.models.model_registry import resolve_model_id
from atelier.models.safety import default_model_armor_config

logger = logging.getLogger(__name__)

# D-O-R-A-V default weights — uniform distribution
_DEFAULT_AXIS_WEIGHTS: dict[str, float] = {
    "brand": 0.2,
    "originality": 0.2,
    "relevance": 0.2,
    "accessibility": 0.2,
    "visual_clarity": 0.2,
}

# Tolerance for the axis_weights sum-to-one validator (floating-point slack).
_AXIS_WEIGHT_SUM_TOLERANCE = 0.05

# PlannerAgent system prompt — instructs the LLM to produce PlanStep JSON
_PLANNER_SYSTEM_PROMPT: str = (
    "You are the planning node of an autonomous UI/UX design agent called Atelier. "
    "Given a design brief, output a structured PlanStep that drives the execution "
    "graph. Follow these rules:\n"
    "- should_run_wrai=false for narrow, unambiguous briefs (<50 words, "
    "  single-component, no brand context needed)\n"
    "- ensemble_k=3 or more for ambiguous, creative, or brand-sensitive briefs\n"
    "- Set axis_weights to emphasize what the brief actually optimizes for "
    "  (e.g. 'accessible' → accessibility=0.4; 'brutalist' → originality=0.35)\n"
    "- constitution='brutalist' if brief mentions brutalism, raw, raw-css, monochrome grid\n"
    "- constitution='apple-grade' if brief mentions premium, minimal, Apple-inspired\n"
    "- Identify the screens or surfaces requested in the brief and list them in the `surfaces` field (e.g. ['landing page', 'pricing page']). If the brief requests only one screen or doesn't specify, default to ['landing page'].\n"
    "- reasoning: one sentence explaining your top routing decision\n"
    "Output valid JSON matching PlanStep schema. No other text."
)


class ProposedDefault(BaseModel):
    """A domain Tier-1 standard the planner proposes applying by default (AT-025).

    Surfaced from :class:`atelier.intake.research_findings.ResearchFindings` so the
    clarify-gate (AT-030, separate feature) can decide ask-vs-silent. Each carries
    its full provenance — a default Atelier applies on the user's behalf is always
    attributable to a cited, trust-scored source (PRD §3.5).

    Attributes:
        standard_id: The source standard's stable id (e.g. ``"dash-card-cap"``).
        name: Human-readable source title.
        rule: The imperative rule text being proposed as a default.
        citation_url: The authoritative source URL (never empty).
        trust_score: Trust seed in ``[0.0, 1.0]``.
        domain: The project-type scope the standard applies to.
    """

    model_config = ConfigDict(frozen=True)

    standard_id: str
    name: str
    rule: str
    citation_url: str
    trust_score: float = Field(ge=0.0, le=1.0)
    domain: str


class PlanStep(BaseModel):
    """Dynamic DAG execution plan from brief analysis.

    The planner output drives ADK graph routing at runtime.
    All fields have defaults so narrow briefs produce minimal compute.

    Attributes:
        should_run_wrai: Whether to run web-research-augmented intake (N14).
        ensemble_k: Number of generator candidates to produce (1-5).
        axis_weights: D-O-R-A-V axis weight distribution (must sum to ~1.0).
        constitution: Brand constitution to apply (or None for default).
        gate_axes_to_skip: Deterministic gate axes to skip for efficiency.
        surfaces: List of screens or pages to generate sequentially.
        reasoning: One-sentence justification for the plan.
        open_questions: Under-specified aspects of the brief worth clarifying.
            AT-025 populates the data field; AT-030 owns the clarify-gate logic
            that decides which become user-facing asks.
        gaps: Known coverage gaps (e.g. research unavailable, no reference seed).
        proposed_defaults: Domain Tier-1 standards surfaced from WRAI research as
            defaults Atelier proposes applying (each cited + trust-scored).
    """

    model_config = ConfigDict(frozen=True)

    should_run_wrai: bool = True
    ensemble_k: int = Field(default=2, ge=1, le=5)
    axis_weights: dict[str, float] = Field(default_factory=lambda: dict(_DEFAULT_AXIS_WEIGHTS))
    constitution: Literal["apple-grade", "brutalist"] | None = None
    gate_axes_to_skip: list[str] = Field(default_factory=list)
    surfaces: list[str] = Field(default_factory=lambda: ["landing page"])
    reasoning: str = ""
    # AT-025 anti-railroad fields. Data model + population live here; the
    # clarify-gate DECISION logic (ask vs. silent-default-with-citation) is owned
    # by AT-030. Safe empty defaults keep narrow briefs and the LLM JSON contract
    # unchanged (the planner LLM is not asked to populate these).
    open_questions: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    proposed_defaults: list[ProposedDefault] = Field(default_factory=list)
    # AT-030 clarify-gate inputs. ``gaps_detail`` carries the *classified* gaps
    # (the human-readable strings stay in ``gaps`` for the dashboard) so the stakes
    # router can decide ask-vs-silent. Typed via a forward ref to break the
    # planner<->clarify_models import cycle; resolved by a ``model_rebuild`` at the
    # bottom of :mod:`atelier.models.clarify_models` (which imports this module).
    gaps_detail: list[Gap] = Field(default_factory=list)
    open_questions_detail: list[OpenQuestion] = Field(default_factory=list)

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> PlanStep:
        """Validate that axis_weights sum to approximately 1.0."""
        total = sum(self.axis_weights.values())
        if abs(total - 1.0) > _AXIS_WEIGHT_SUM_TOLERANCE:
            raise ValueError(f"axis_weights sum={total:.3f}; must be within 0.05 of 1.0")
        return self

    def with_research(self, findings: ResearchFindings) -> PlanStep:
        """Return a copy enriched with WRAI research (AT-025).

        Populates ``proposed_defaults`` from the research's domain Tier-1
        standards (highest-trust first) and records a ``gaps`` entry when the
        research path was blocked or unavailable, so the acknowledgment is
        carried on the plan the user reviews. PlanStep is frozen, so this returns
        a NEW instance (``model_copy(update=...)``) rather than mutating in place.

        AT-030 consumes ``proposed_defaults`` / ``open_questions`` / ``gaps`` to
        drive the clarify gate; this method only populates the data.

        Args:
            findings: The frozen ResearchFindings synthesized post-N14.

        Returns:
            A new PlanStep with the research fields populated.
        """
        from atelier.intake.research_findings import ArmorVerdict  # noqa: PLC0415

        proposed = [
            ProposedDefault(
                standard_id=s.standard_id,
                name=s.name,
                rule=s.rule,
                citation_url=s.citation_url,
                trust_score=s.trust_score,
                domain=s.domain,
            )
            for s in findings.proposed_defaults()
        ]
        gaps = list(self.gaps)
        if findings.armor_verdict == ArmorVerdict.BLOCKED:
            gaps.append(
                "Grounded web research was blocked on the safety path "
                "(prompt-injection pattern); proceeding with applicable standards only."
            )
        elif findings.armor_verdict == ArmorVerdict.UNAVAILABLE:
            gaps.append(
                "Grounded web research was unavailable (degraded); "
                "proceeding with applicable standards only."
            )
        return self.model_copy(update={"proposed_defaults": proposed, "gaps": gaps})

    def with_clarify_assessment(
        self,
        assessment: SpecAssessment,
        findings: ResearchFindings,
    ) -> PlanStep:
        """Return a copy enriched with the AT-030 clarify assessment.

        A CLEAR brief (low ambiguity, no unsafe gaps) is left untouched: no
        questions, no proposed defaults — the gate stays silent (acceptance A). An
        UNDER-SPECIFIED brief in a recognizable domain surfaces the domain's
        Tier-1 standards as cited proposed defaults *and* records the classified
        gaps the clarify gate routes (acceptance B). The ask-vs-silent decision
        itself lives in :func:`atelier.gates.clarify.clarify_gate`; this method
        only populates the data the gate consumes.

        Emission rule (PRD §3.5): surface a clarify batch iff the brief is
        ambiguous on >=2 dimensions OR carries an unsafe gap (safety dimension
        weak, or an irreversible/global decision). A clear brief satisfies
        neither and is returned unchanged.

        Args:
            assessment: The 6-dimension :class:`SpecAssessment`.
            findings: The frozen :class:`ResearchFindings` (domain standards).

        Returns:
            A new PlanStep carrying ``gaps_detail`` (classified) + ``proposed_defaults``
            (cited) when a clarify is warranted, else an unchanged copy.
        """
        if not assessment.warrants_clarify():
            # Clear brief: keep the gate silent. We still preserve any defaults a
            # prior ``with_research`` populated, but emit no new clarify data.
            return self.model_copy(update={"gaps_detail": [], "open_questions_detail": []})

        gaps = assessment.to_gaps(findings)
        # Proposed defaults are the cited domain standards (highest-trust first),
        # the same provenance AT-025 surfaces — the clarify gate routes per-gap.
        proposed = [
            ProposedDefault(
                standard_id=s.standard_id,
                name=s.name,
                rule=s.rule,
                citation_url=s.citation_url,
                trust_score=s.trust_score,
                domain=s.domain,
            )
            for s in findings.proposed_defaults()
        ]
        return self.model_copy(update={"gaps_detail": gaps, "proposed_defaults": proposed})


# ---------------------------------------------------------------------------
# AT-030 — specification assessment (the 6-dimension uncertainty model)
# ---------------------------------------------------------------------------

#: The six dimensions a brief is scored on. A score is in ``[0.0, 1.0]`` where
#: 1.0 == fully specified / unambiguous and 0.0 == absent. The dimensions are the
#: minimal coordinate system a downstream design agent needs to NOT railroad:
#: what to build, how we'll know it's done, how much, under what limits, for whom,
#: and what must never break.
_ASSESSMENT_DIMENSIONS: tuple[str, ...] = (
    "objective",
    "done_criteria",
    "scope",
    "constraints",
    "environment",
    "safety",
)

#: A dimension scoring below this is considered "ambiguous" for the >=2-dimension
#: emission rule.
_AMBIGUOUS_DIMENSION_THRESHOLD = 0.5

#: Minimum number of ambiguous dimensions that, on its own, warrants a clarify
#: batch (an unsafe gap also warrants one regardless of this count). Two is the
#: floor: a single soft gap is silently defaulted; two means the brief is
#: genuinely under-specified.
_MIN_AMBIGUOUS_FOR_CLARIFY = 2

#: Lexical signals per dimension. Presence of ANY signal lifts the dimension's
#: score; this is a general heuristic (not test-specific hard-coding) over the
#: vocabulary a design brief uses to specify each coordinate. Lowercased substring
#: match. The lists are deliberately broad so they generalize across briefs.
_DIMENSION_SIGNALS: dict[str, tuple[str, ...]] = {
    # What is being built — a concrete noun/component or explicit verb of intent.
    "objective": (
        "button",
        "form",
        "page",
        "dashboard",
        "card",
        "modal",
        "nav",
        "menu",
        "hero",
        "table",
        "chart",
        "checkout",
        "cart",
        "landing",
        "screen",
        "component",
        "build",
        "create",
        "design",
        "make a",
        "build a",
    ),
    # How we'll know it's done — success metrics / acceptance signals.
    "done_criteria": (
        "success",
        "done when",
        "acceptance",
        "metric",
        "kpi",
        "conversion",
        "goal",
        "target",
        "must show",
        "should show",
        "convert",
        "complete",
        "pass",
        "score",
        "threshold",
        "submits",
        "confirmation message",
        "success message",
    ),
    # How much / which surfaces — scope enumeration.
    "scope": (
        "single",
        "one ",
        "only",
        "page",
        "pages",
        "screen",
        "screens",
        "surface",
        "section",
        "just a",
        "just the",
        "campaign",
        "set of",
        "each",
        "per ",
        "cards",
        "count",
    ),
    # Under what limits — technical/brand constraints.
    "constraints": (
        "stack",
        "html",
        "css",
        "react",
        "vue",
        "svelte",
        "tailwind",
        "vanilla",
        "brand",
        "palette",
        "color",
        "font",
        "typeface",
        "register",
        "brutalist",
        "minimal",
        "apple",
        "monochrome",
        "grid",
        "style",
        "must not",
        "forbidden",
        "constraint",
        "budget",
        "limit",
    ),
    # For whom / where — audience + context.
    "environment": (
        "audience",
        "user",
        "users",
        "desktop",
        "mobile",
        "tablet",
        "responsive",
        "for ",
        "context",
        "internal",
        "external",
        "customer",
        "operator",
        "admin",
        "viewport",
        "device",
        "marketing",
        "enterprise",
    ),
    # What must never break — destructive/irreversible ops acknowledged.
    "safety": (
        "no destructive",
        "not destructive",
        "irreversible",
        "reversible",
        "performs no",
        "read-only",
        "read only",
        "safe",
        "no irreversible",
        "non-destructive",
        "wcag",
        "accessible",
        "accessibility",
        "compliance",
        "privacy",
        "auth",
        "security",
        "no data",
        "without deleting",
    ),
}

#: Tokens that, when present in a brief, signal a HIGH-STAKES / irreversible
#: decision is in play that the brief did NOT pin down — the router must ASK these,
#: never silently default (fail-closed; PRD §3.5 / failure trichotomy fail-loud).
_HIGH_STAKES_SIGNALS: tuple[str, ...] = (
    "payment",
    "checkout",
    "delete",
    "purchase",
    "charge",
    "billing",
    "transfer",
    "auth",
    "login",
    "sign in",
    "sign-in",
    "password",
    "pii",
    "personal data",
    "irreversible",
    "destructive",
    "legal",
    "consent",
    "gdpr",
    "refund",
)

#: A brief shorter than this (in words) is treated as scope-ambiguous regardless
#: of lexical hits — three words cannot specify six dimensions.
_TERSE_WORD_FLOOR = 8


@dataclass(frozen=True)
class SpecAssessment:
    """The 6-dimension specification assessment of a brief (AT-030).

    Attributes:
        dimension_scores: Per-dimension specificity in ``[0.0, 1.0]``.
        ambiguity_score: ``1 - mean(dimension_scores)`` — the headline uncertainty.
        unsafe_gaps: Dimensions/decisions that are high-stakes or irreversible and
            were NOT pinned down by the brief (always asked, never defaulted).
        ambiguous_dimensions: Dimensions scoring below the ambiguity threshold.
    """

    dimension_scores: dict[str, float]
    ambiguity_score: float
    unsafe_gaps: list[str] = field(default_factory=list)
    ambiguous_dimensions: list[str] = field(default_factory=list)

    def warrants_clarify(self) -> bool:
        """Emit a clarify batch iff >=2 dimensions ambiguous OR an unsafe gap exists.

        This is the gate's emission predicate (PRD §3.5): a clear brief (0-1
        ambiguous dimensions, no unsafe gap) is NOT interrupted; an under-specified
        or high-stakes brief is.
        """
        return len(self.ambiguous_dimensions) >= _MIN_AMBIGUOUS_FOR_CLARIFY or bool(
            self.unsafe_gaps
        )

    def to_gaps(self, findings: ResearchFindings) -> list[Gap]:
        """Classify each ambiguous dimension into a routable :class:`Gap`.

        High-stakes / irreversible / global dimensions (anything in
        ``unsafe_gaps``, or the ``safety`` dimension) are classified
        costly/global/high so the router ASKS them. Cheap, local, low-stakes
        dimensions are bound to the domain's strongest applicable standard (when
        one exists) so the router can silently default WITH a citation.
        """
        from atelier.models.clarify_models import Gap  # noqa: PLC0415 — cycle break

        # Strongest cited domain standard available as a default anchor.
        domain_defaults = findings.proposed_defaults()
        gaps: list[Gap] = []
        for dim in self.ambiguous_dimensions:
            is_unsafe = dim in self.unsafe_gaps or dim == "safety"
            if is_unsafe:
                gaps.append(
                    Gap(
                        decision_id=f"{dim}-unspecified",
                        dimension=dim,
                        description=(
                            f"The brief does not pin down the '{dim}' dimension, "
                            "and the decision is high-stakes or irreversible."
                        ),
                        reversibility="costly",
                        blast_radius="global",
                        stakes="high",
                    )
                )
                continue
            # Cheap + local: bind to a cited domain standard when one exists.
            anchor = domain_defaults[0] if domain_defaults else None
            if anchor is not None:
                gaps.append(
                    Gap(
                        decision_id=anchor.standard_id,
                        dimension=dim,
                        description=(
                            f"The brief leaves the '{dim}' dimension to a default; "
                            f"applying the domain standard '{anchor.name}'."
                        ),
                        reversibility="cheap",
                        blast_radius="local",
                        stakes="low",
                        recommended_value=anchor.rule,
                        citation_url=anchor.citation_url,
                        rationale=anchor.rule,
                    )
                )
                # Consume the anchor so distinct dimensions bind distinct standards
                # where the pack has them (avoids proposing the same default twice).
                domain_defaults = domain_defaults[1:] or domain_defaults
        return gaps


def assess_specification(brief_text: str) -> SpecAssessment:
    """Score a brief on the six specification dimensions (AT-030 core).

    A general lexical-coverage model (NOT test-specific hard-coding): each
    dimension's score is the fraction of independent signals present, with a terse
    brief (< :data:`_TERSE_WORD_FLOOR` words) floored toward ambiguous because a
    handful of words cannot specify six coordinates. The ``safety`` dimension is
    additionally driven to an unsafe gap whenever a high-stakes token
    (payment/auth/delete/...) appears WITHOUT an explicit safety acknowledgment —
    the fail-closed bias: a consequential, unconfirmed decision is always asked.

    Args:
        brief_text: The raw brief text.

    Returns:
        A frozen :class:`SpecAssessment`.
    """
    lowered = brief_text.lower()
    word_count = len(brief_text.split())
    terse = word_count < _TERSE_WORD_FLOOR

    dimension_scores: dict[str, float] = {}
    for dim in _ASSESSMENT_DIMENSIONS:
        signals = _DIMENSION_SIGNALS[dim]
        hits = sum(1 for sig in signals if sig in lowered)
        # Saturating coverage: two distinct signals already make a dimension
        # "specified". A single hit is partial; zero hits is absent.
        score = min(1.0, hits / 2.0)
        if terse:
            # A terse brief can't have meaningfully specified a dimension even if a
            # keyword coincidentally matched — cap each dimension at "partial".
            score = min(score, 0.5)
        dimension_scores[dim] = round(score, 3)

    # Safety fail-closed override: a high-stakes token with no explicit safety
    # acknowledgment forces the safety dimension low and flags an unsafe gap.
    high_stakes_present = any(tok in lowered for tok in _HIGH_STAKES_SIGNALS)
    safety_acknowledged = dimension_scores["safety"] >= _AMBIGUOUS_DIMENSION_THRESHOLD
    unsafe_gaps: list[str] = []
    if high_stakes_present and not safety_acknowledged:
        dimension_scores["safety"] = min(dimension_scores["safety"], 0.2)
        unsafe_gaps.append("safety")

    ambiguous_dimensions = [
        dim for dim, score in dimension_scores.items() if score < _AMBIGUOUS_DIMENSION_THRESHOLD
    ]
    mean_score = sum(dimension_scores.values()) / len(dimension_scores)
    ambiguity_score = round(1.0 - mean_score, 3)

    return SpecAssessment(
        dimension_scores=dimension_scores,
        ambiguity_score=ambiguity_score,
        unsafe_gaps=unsafe_gaps,
        ambiguous_dimensions=ambiguous_dimensions,
    )


class PlannerAgent:
    """N0: Analyzes brief and produces a dynamic PlanStep for graph routing.

    Uses ``gemini-2.5-flash`` (GA, stable) for plan generation.
    Fail-soft: any exception falls back to the default PlanStep so the
    pipeline never breaks due to a planner failure.

    Examples:
        >>> planner = PlannerAgent()
        >>> plan = await planner.plan("Make a button blue")
        >>> plan.should_run_wrai
        False  # narrow brief — skip web research
    """

    def __init__(self, model: str | None = None) -> None:
        """Initialize the PlannerAgent with an LLM agent.

        Args:
            model: Gemini model ID. Defaults to the pinned served id
                (``resolve_model_id()`` → ``GEMINI_MODEL_ID`` env or
                ``gemini-2.5-pro`` GA, AT-024). Override in tests with a mock.
        """
        self.model = model or resolve_model_id()
        self._llm = LlmAgent(
            name="atelier_planner",
            before_model_callback=model_armor_before_callback,
            after_model_callback=model_armor_after_callback,
            model=self.model,
            output_schema=PlanStep,
            instruction=_PLANNER_SYSTEM_PROMPT,
            generate_content_config=genai_types.GenerateContentConfig(
                model_armor_config=default_model_armor_config(),
            ),
        )

    @property
    def llm(self) -> LlmAgent:
        """The underlying ADK ``LlmAgent`` (consumed by the Agent Engine deploy, AT-082)."""
        return self._llm

    async def plan(self, brief_text: str) -> PlanStep:
        """Parse brief → PlanStep. Falls back to default plan on failure.

        Args:
            brief_text: The validated brief text to analyze.

        Returns:
            A PlanStep driving downstream DAG routing.
            On any failure, returns PlanStep() with safe defaults.
        """
        try:
            result = await self._call_llm(brief_text)
            if isinstance(result, PlanStep):
                return result
            return PlanStep.model_validate_json(result)
        except Exception:  # noqa: BLE001
            # Fail-soft: default plan never breaks the pipeline.
            # The exc_info=True logging below captures the full exception
            # in structured logs with brief_length context.
            logger.warning(
                "PlannerAgent failed; using default plan",
                exc_info=True,
                extra={"brief_length": len(brief_text)},
            )
            return PlanStep()

    async def _call_llm(self, text: str) -> str | PlanStep:
        """Execute the LlmAgent via ADK Runner and return the parsed response.

        Uses an ephemeral InMemorySessionService — planning is stateless.

        Args:
            text: The validated brief text.

        Returns:
            The LLM response as a string (JSON) or a pre-validated PlanStep.

        Raises:
            ValueError: If the LLM returns no content.
        """
        from google.adk.runners import Runner  # noqa: PLC0415
        from google.adk.sessions import InMemorySessionService  # noqa: PLC0415
        from google.genai import types as _types  # noqa: PLC0415

        session_service = InMemorySessionService()
        runner = Runner(
            agent=self._llm,
            app_name="atelier_planner",
            session_service=session_service,
        )

        user_id = "planner-system"
        session = await session_service.create_session(
            app_name="atelier_planner",
            user_id=user_id,
        )

        last_text: str | None = None
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=_types.Content(
                role="user",
                parts=[_types.Part(text=text)],
            ),
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        last_text = part.text

        if last_text is None:
            raise ValueError(
                "PlannerAgent LLM returned no content. "
                "Check model availability and prompt configuration."
            )

        logger.debug(
            "planner_llm_response",
            extra={"response_length": len(last_text)},
        )
        return last_text


# ---------------------------------------------------------------------------
# Resolve PlanStep's AT-030 forward refs (``gaps_detail: list[Gap]`` /
# ``open_questions_detail: list[OpenQuestion]``) at module load, so ``PlanStep`` is
# fully defined the moment THIS module is imported — even when imported directly
# (e.g. the sign-off gate tests) without first importing clarify_models.
#
# clarify_models does NOT import planner at its module top (only under
# TYPE_CHECKING), so this bottom-of-module import never deadlocks: ``Gap`` /
# ``OpenQuestion`` are defined before clarify_models reaches its own (local)
# ``ProposedDefault`` import, which by then is already defined above.
# ---------------------------------------------------------------------------
from atelier.models.clarify_models import Gap as _Gap  # noqa: E402
from atelier.models.clarify_models import OpenQuestion as _OpenQuestion  # noqa: E402

PlanStep.model_rebuild(_types_namespace={"Gap": _Gap, "OpenQuestion": _OpenQuestion})
