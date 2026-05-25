from __future__ import annotations

import re

from google.adk.agents import LlmAgent
from google.genai import types as genai_types
from pydantic import BaseModel, ConfigDict

from atelier.intake.brief_spec import BriefSpec
from atelier.models.enums import GateDecision
from atelier.models.safety import default_safety_settings


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

    def __init__(self, model: str = "gemini-3-flash", project: str = "atelier-build-2026") -> None:
        self.model = model
        self.project = project
        self._llm = LlmAgent(
            name="brief_parser_llm",
            model=model,
            output_schema=BriefSpec,
            generate_content_config=genai_types.GenerateContentConfig(
                safety_settings=default_safety_settings(),
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

    async def _call_llm(self, text: str) -> str | BriefSpec:  # noqa: ARG002
        """Isolated call method to facilitate mocking."""
        # Stub: The real execution logic is handled by the ADK orchestrator
        # or replaced by a mock in unit tests.
        return ""
