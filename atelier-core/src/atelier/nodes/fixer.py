"""N3e FixerAgent for the Convergence Loop.

Analyzes gate failures and consensus scores to emit prompt mutations and fixes.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from google.adk.agents import LlmAgent
from google.genai import types as genai_types
from pydantic import BaseModel, ConfigDict, Field

# MutationOp is a Pydantic model field (list[MutationOp]); Pydantic resolves it
# at runtime even under `from __future__ import annotations`, so it must stay a
# runtime import (TC001 is a false positive here).
from atelier.models.enums import MutationOp  # noqa: TC001
from atelier.models.model_armor_callbacks import (
    model_armor_after_callback,
    model_armor_before_callback,
)
from atelier.models.model_registry import FIXER_MODEL
from atelier.models.safety import default_model_armor_config

if TYPE_CHECKING:
    # The live governor passed by the runner is atelier.orchestrator.governor
    # (the token-cap governor, AT-095); annotate against it for type honesty.
    from atelier.models.data_contracts import GateOutcome

    # The runner passes a nodes.consensus.ConsensusEvaluation (it exposes
    # ``votes``), NOT data_contracts.ConsensusResult (which has per_axis_scores
    # and no votes). Annotate against the type actually received so a future
    # caller cannot hand a ConsensusResult and reintroduce the per_axis_scores
    # AttributeError this code path already hit once (audit 2026-06-03).
    from atelier.nodes.consensus import ConsensusEvaluation
    from atelier.orchestrator.governor import MetacognitiveGovernor

logger = logging.getLogger(__name__)

_FIXER_SYSTEM_PROMPT: str = (
    "You are the N3e FixerAgent for the Atelier design pipeline. "
    "Your job is to analyze gate failures and low axis scores to propose fixes for the next iteration.\n"
    "Output exactly the requested JSON schema. Use mutation operators strategically:\n"
    '- A11Y_FAIL -> APPEND_CONSTRAINT ("Ensure all interactive elements have ARIA labels")\n'
    '- TOKEN_DRIFT -> APPEND_CONSTRAINT ("Match the design system token set exactly")\n'
    "- BRAND_INCONSIST -> BOOST_EXAMPLE (add brand examples)\n"
    "- LOW_ORIGINALITY -> ADJUST_TEMPERATURE\n"
    '- MOTION_NO_REDUCED -> APPEND_CONSTRAINT ("Add prefers-reduced-motion")\n'
    "Return only valid JSON."
)


class FixerDirective(BaseModel):
    """Output schema for the Fixer LLM."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mutations: list[MutationOp] = Field(description="Which operators to apply")
    prompt_amendments: list[str] = Field(
        description="Concrete additions to the generator prompt to resolve failures"
    )
    reasoning: str = Field(description="Why these mutations were chosen")


class FixerAgent:
    """N3e: Analyzes failures and proposes a FixerDirective."""

    def __init__(self, governor: MetacognitiveGovernor) -> None:
        """Initialize the FixerAgent with an LLM agent."""
        self._governor = governor
        self._llm = LlmAgent(
            name="atelier_fixer",
            before_model_callback=model_armor_before_callback,
            after_model_callback=model_armor_after_callback,
            model=FIXER_MODEL.model_id,
            output_schema=FixerDirective,
            instruction=_FIXER_SYSTEM_PROMPT,
            # R4 (anchored_context): the fixer carries NO conversation history;
            # each fix is grounded only in the gate/consensus inputs it is given,
            # so accumulated rejected-variant context cannot drift the directive.
            include_contents="none",
            generate_content_config=genai_types.GenerateContentConfig(
                temperature=FIXER_MODEL.temperature,
                model_armor_config=default_model_armor_config(),
            ),
        )

    async def fix(
        self,
        gate_outcomes: list[GateOutcome],
        consensus: ConsensusEvaluation | None,
        memory_service: Any = None,
        tenant_id: str = "default",
    ) -> FixerDirective:
        """Analyze failures and propose a fix.

        Args:
            gate_outcomes: List of gate outcomes from N3c.
            consensus: Consensus result from N3d (can be None).
            memory_service: Injected HierarchicalMemory backend.
            tenant_id: Active tenant identifier.

        Returns:
            A FixerDirective. On LLM failure, returns a fail-soft no-op directive.
        """
        # Query similar resolutions from the Incident Diagnostic Memory Bank
        similar_resolutions = []
        incident_id = None
        memory_bank = None
        if memory_service:
            from uuid import uuid4  # noqa: PLC0415

            from atelier.durability.incident_memory import IncidentMemoryBank  # noqa: PLC0415

            incident_id = str(uuid4())
            memory_bank = IncidentMemoryBank(memory_service)
            await memory_bank.record_incident(
                tenant_id=tenant_id,
                incident_id=incident_id,
                gate_outcomes=gate_outcomes,
                consensus=consensus,
            )
            similar_resolutions = await memory_bank.query_similar_resolutions(
                tenant_id=tenant_id,
                gate_outcomes=gate_outcomes,
                consensus=consensus,
            )

        # Build prompt
        prompt = "Gate Outcomes:\n"
        for o in gate_outcomes:
            prompt += f"- {o.axis.value}: {o.decision.value} ({o.diagnostic})\n"

        if consensus:
            prompt += "\nConsensus Scores:\n"
            for axis, vote in consensus.votes.items():
                prompt += f"- {axis.value}: {vote.score:.2f} ({vote.reasoning})\n"

        if similar_resolutions:
            prompt += "\n--- SIMILAR HISTORICAL SOLUTIONS ---\n"
            for idx, res in enumerate(similar_resolutions, 1):
                prompt += f"Solution {idx}:\n{res}\n"

        try:
            result = await self._call_llm(prompt)
            directive = (
                result
                if isinstance(result, FixerDirective)
                else FixerDirective.model_validate_json(result)
            )
        except Exception as e:  # noqa: BLE001
            # Fail-soft fallback
            self._governor._state.record_step("fixer_failed")
            logger.warning(
                "FixerAgent failed; using fail-soft directive",
                exc_info=True,
                extra={"error": str(e)},
            )
            return FixerDirective(
                mutations=[],
                prompt_amendments=[
                    "The previous iteration failed validation. Please revise and improve the design."
                ],
                reasoning="Fail-soft fallback due to LLM error.",
            )
        else:
            # Record resolution in the memory bank
            if memory_bank and incident_id:
                import json  # noqa: PLC0415

                res_delta = json.dumps(
                    {
                        "mutations": [m.value for m in directive.mutations],
                        "amendments": directive.prompt_amendments,
                    }
                )
                await memory_bank.record_resolution(
                    tenant_id=tenant_id,
                    incident_id=incident_id,
                    resolution_delta=res_delta,
                )
            return directive

    async def _call_llm(self, text: str) -> str | FixerDirective:
        """Execute the LlmAgent via ADK Runner.

        Args:
            text: The failure context prompt.

        Returns:
            The LLM response as a string (JSON) or a pre-validated FixerDirective.
        """
        from google.adk.runners import Runner  # noqa: PLC0415
        from google.adk.sessions import InMemorySessionService  # noqa: PLC0415
        from google.genai import types as _types  # noqa: PLC0415

        session_service = InMemorySessionService()
        runner = Runner(
            agent=self._llm,
            app_name="atelier_fixer",
            session_service=session_service,
        )

        user_id = "fixer-system"
        session = await session_service.create_session(
            app_name="atelier_fixer",
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
            raise ValueError("FixerAgent LLM returned no content.")

        return last_text
