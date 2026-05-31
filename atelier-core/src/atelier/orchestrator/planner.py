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
from typing import Literal

from google.adk.agents import LlmAgent
from google.genai import types as genai_types
from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    """

    model_config = ConfigDict(frozen=True)

    should_run_wrai: bool = True
    ensemble_k: int = Field(default=2, ge=1, le=5)
    axis_weights: dict[str, float] = Field(default_factory=lambda: dict(_DEFAULT_AXIS_WEIGHTS))
    constitution: Literal["apple-grade", "brutalist"] | None = None
    gate_axes_to_skip: list[str] = Field(default_factory=list)
    surfaces: list[str] = Field(default_factory=lambda: ["landing page"])
    reasoning: str = ""

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> PlanStep:
        """Validate that axis_weights sum to approximately 1.0."""
        total = sum(self.axis_weights.values())
        if abs(total - 1.0) > _AXIS_WEIGHT_SUM_TOLERANCE:
            raise ValueError(f"axis_weights sum={total:.3f}; must be within 0.05 of 1.0")
        return self


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
            model=self.model,
            output_schema=PlanStep,
            instruction=_PLANNER_SYSTEM_PROMPT,
            generate_content_config=genai_types.GenerateContentConfig(
                model_armor_config=default_model_armor_config(),
            ),
        )

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
