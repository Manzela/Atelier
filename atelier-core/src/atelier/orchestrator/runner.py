"""Atelier Pipeline Runner — Phase 1 (N1 → N2 → N3a).

Chains:
    N1 (BriefParserGate + BriefParserAgent)
    → N2 (SourceResolverGate + SourceResolverAgent)
    → N3a (Generator Ensemble via ParallelAgent)

Phase 2 will add N3b-N3h sub-agents and BigQuery session service.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from google.adk.runners import InMemoryRunner

from atelier.intake.brief_parser import BriefParserAgent, BriefParserGate
from atelier.intake.source_resolver import source_resolver_agent, source_resolver_gate
from atelier.models.data_contracts import TenantContext
from atelier.models.enums import GateDecision
from atelier.orchestrator.generator_ensemble import create_generator_ensemble


class AtelierRunner:
    """Phase 1 Pipeline Runner.

    Chains N1 (Brief Parser) -> N2 (Source Resolver) -> N3a (Generator Ensemble).
    """

    async def run(
        self,
        brief_text: str,
        tenant_ctx: TenantContext | None = None,
    ) -> dict[str, Any]:
        """Run the pipeline from brief text to generated candidates.

        Args:
            brief_text: Raw brief text input.
            tenant_ctx: Tenant context for source resolution. Defaults to a
                placeholder context for local development.

        Returns:
            A dictionary containing the final brief, project context, and
            generated candidates.
        """
        # N1: Brief Parser
        gate = BriefParserGate()
        outcome = gate.check(brief_text)
        if outcome.decision != GateDecision.PASS:
            raise ValueError(f"Brief failed gate: {outcome.diagnostic}")
        n1_agent = BriefParserAgent()
        brief = await n1_agent.parse(brief_text)

        # N2: Source Resolver
        if tenant_ctx is None:
            tenant_ctx = TenantContext(
                tenant_id="t1",
                user_id="u1",
                project_id="p1",
                cost_budget_usd=Decimal("100.0"),
            )
        if not source_resolver_gate(tenant_ctx, brief):
            raise ValueError("Source resolver gate failed (no descriptor or design source).")

        project_ctx = await source_resolver_agent(tenant_ctx, brief)

        # N3a: Generator Ensemble
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
