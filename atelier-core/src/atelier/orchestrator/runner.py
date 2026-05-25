from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from google.adk.agents.invocation_context import InvocationContext

from atelier.intake.brief_parser import BriefParserAgent, BriefParserGate
from atelier.intake.source_resolver import source_resolver_agent, source_resolver_gate
from atelier.models.data_contracts import TenantContext
from atelier.models.enums import GateDecision
from atelier.orchestrator.generator_ensemble import create_generator_ensemble

if TYPE_CHECKING:
    from atelier.intake.brief_spec import BriefSpec


class AtelierRunner:
    """Phase 1 Pipeline Runner.

    Chains N1 (Brief Parser) -> N2 (Source Resolver) -> N3a (Generator Ensemble).
    """

    async def run(self, brief_text: str) -> dict[str, Any]:
        """Runs the pipeline from brief text to generated candidates.

        Returns:
            A dictionary containing the final brief, project context, and generated candidates.
        """
        # N1: Brief Parser
        gate = BriefParserGate()
        outcome = gate.check(brief_text)
        if outcome.decision != GateDecision.PASS:
            raise ValueError(f"Brief failed gate: {outcome.diagnostic}")
        n1_agent = BriefParserAgent()
        brief = await n1_agent.parse(brief_text)

        # N2: Source Resolver
        from decimal import Decimal
        tenant_ctx = TenantContext(
            tenant_id="t1",
            user_id="u1",
            project_id="p1",
            cost_budget_usd=Decimal("100.0"),
        )
        if not source_resolver_gate(tenant_ctx, brief):
            raise ValueError("Source resolver gate failed (no descriptor or design source).")

        project_ctx = await source_resolver_agent(tenant_ctx, brief)

        from google.adk.runners import InMemoryRunner

        ensemble = create_generator_ensemble()
        adk_runner = InMemoryRunner(agent=ensemble)

        candidates = []
        async for event in adk_runner.run_async(
            user_id=tenant_ctx.user_id,
            session_id="session-1",
            new_message="Generate screens based on the brief and project context.",
        ):
            # In an actual deployment, we'd look for specific agent output events
            if hasattr(event, "type") and event.type == "message":
                candidates.append(getattr(event, "data", event))
            elif isinstance(event, dict) and event.get("type") == "message":
                candidates.append(event.get("data", event))
            else:
                candidates.append(event)

        return {"brief": brief, "project_context": project_ctx, "candidates": candidates}
