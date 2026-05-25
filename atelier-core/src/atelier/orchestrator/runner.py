from __future__ import annotations

from typing import TYPE_CHECKING

from atelier.intake.brief_parser import BriefParserAgent, BriefParserGate
from atelier.models.enums import GateDecision

if TYPE_CHECKING:
    from atelier.intake.brief_spec import BriefSpec


class AtelierRunner:
    """Phase 1 ADK SequentialAgent runner — N1 only.

    Phase 2 will add N2 Source Resolver and N3a Generator.
    Thin wrapper around ADK so tests can mock the runner interface.
    """

    async def run(self, brief_text: str) -> BriefSpec:
        """Gate → Agent → BriefSpec. Raises on gate failure or parse error."""
        gate = BriefParserGate()
        outcome = gate.check(brief_text)
        if outcome.decision != GateDecision.PASS:
            raise ValueError(f"Brief failed gate: {outcome.diagnostic}")
        agent = BriefParserAgent()
        return await agent.parse(brief_text)
