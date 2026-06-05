from __future__ import annotations

import logging
import re

from google.adk.agents import LlmAgent
from google.genai import types as genai_types
from pydantic import BaseModel, ConfigDict

from atelier.intake.brief_spec import BriefSpec
from atelier.models.enums import GateDecision
from atelier.models.model_armor_callbacks import (
    model_armor_after_callback,
    model_armor_before_callback,
)
from atelier.models.model_registry import normalize_model_id, resolve_model_id
from atelier.models.safety import default_model_armor_config

logger = logging.getLogger(__name__)


class BriefGateOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)
    decision: GateDecision
    diagnostic: str


# ---------------------------------------------------------------------------
# Tunable thresholds
# ---------------------------------------------------------------------------
MIN_BRIEF_TOKENS: int = 10  # below this → gate FAIL (too vague)
MAX_BRIEF_TOKENS: int = 4096  # above this → gate FAIL (too large for single call)
INJECTION_PATTERNS: tuple[str, ...] = (
    r"<script",
    r"javascript:",
    r"data:text/html",
    r"\{\{.*\}\}",  # template injection
    r"__import__",  # Python injection
)


class BriefParserGate:
    """Deterministic gate — validates raw brief text before LLM parsing."""

    def check(self, brief_text: str) -> BriefGateOutcome:
        """Returns GateDecision.PASS or GateDecision.FAIL with diagnostic."""
        tokens = brief_text.split()
        if not tokens:
            return BriefGateOutcome(decision=GateDecision.REJECT, diagnostic="Empty brief")
        if len(tokens) < MIN_BRIEF_TOKENS:
            return BriefGateOutcome(decision=GateDecision.REJECT, diagnostic="Brief too short")
        if len(tokens) > MAX_BRIEF_TOKENS:
            return BriefGateOutcome(decision=GateDecision.REJECT, diagnostic="Brief too long")

        for pattern in INJECTION_PATTERNS:
            if re.search(pattern, brief_text, re.IGNORECASE):
                return BriefGateOutcome(
                    decision=GateDecision.REJECT, diagnostic="Injection attempt detected"
                )

        return BriefGateOutcome(decision=GateDecision.PASS, diagnostic="OK")


class BriefParserAgent:
    """Probabilistic agent — extracts BriefSpec from validated brief text via Gemini 3 Flash."""

    def __init__(self, model: str | None = None, project: str = "atelier-build-2026") -> None:
        self.model = normalize_model_id(model or resolve_model_id())
        self.project = project
        self._llm = LlmAgent(
            name="brief_parser_llm",
            before_model_callback=model_armor_before_callback,
            after_model_callback=model_armor_after_callback,
            model=self.model,
            output_schema=BriefSpec,
            generate_content_config=genai_types.GenerateContentConfig(
                model_armor_config=default_model_armor_config(),
            ),
        )

    async def parse(self, brief_text: str) -> BriefSpec:
        """Parse validated brief text → BriefSpec. Raises ValueError on parse failure."""
        response = await self._call_llm(brief_text)
        if isinstance(response, str):
            try:
                return BriefSpec.model_validate_json(response)
            except Exception as e:
                raise ValueError(f"Parse failure: {e}") from e
        elif isinstance(response, BriefSpec):
            return response
        else:
            raise TypeError(f"Unexpected response type: {type(response)}")

    async def _call_llm(self, text: str) -> str | BriefSpec:
        """Execute the LlmAgent via ADK Runner and return the parsed response.

        Uses an ephemeral InMemorySessionService — brief parsing is stateless
        and does not need cross-session persistence. The Runner iterates over
        events; the last event with non-empty ``content`` is the LLM response.

        Args:
            text: The validated brief text to parse into a BriefSpec.

        Returns:
            The LLM response as a string (JSON) or a pre-validated BriefSpec
            if the ADK ``output_schema`` produced a typed object.

        Raises:
            ValueError: If the LLM returns no content after all events.
        """
        from google.adk.runners import Runner  # noqa: PLC0415
        from google.adk.sessions import InMemorySessionService  # noqa: PLC0415
        from google.genai import types as _types  # noqa: PLC0415

        session_service = InMemorySessionService()
        runner = Runner(
            agent=self._llm,
            app_name="atelier_brief_parser",
            session_service=session_service,
        )

        user_id = "brief-parser-system"
        session = await session_service.create_session(
            app_name="atelier_brief_parser",
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
                "BriefParserAgent LLM returned no content. "
                "Check model availability and prompt configuration."
            )

        logger.debug(
            "brief_parser_llm_response",
            extra={"response_length": len(last_text)},
        )
        return last_text
