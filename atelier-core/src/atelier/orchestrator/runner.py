"""Atelier Pipeline Runner — Phase 2 (N1 -> N2 -> N3a + Governor + SessionBackend).

Chains:
    N1 (BriefParserGate + BriefParserAgent)
    -> N2 (SourceResolverGate + SourceResolverAgent)
    -> N3a (Generator Ensemble via ParallelAgent)

All pipeline steps execute under MetacognitiveGovernor governance:
    - Pre-check budget before N3a (fail-loud at $5K MAX cap)
    - Post-check cost accounting after N3a
    - Self-heal on 429/503 transients
    - Fail-soft on tool degradation

Session service is injectable via the ``SessionBackend`` Protocol (B4):
    - Production: ``BigQuerySessionBackend`` (BQ-backed persistence)
    - Staging: ``VertexAiSessionService`` (ADK managed sessions)
    - Local dev: ``InMemorySessionService`` (ephemeral, default)

PRD Reference: section 6.3, section 21 (Failure Trichotomy)
Audit Reference: FIX-1 (CostGovernor), B4 (SessionBackend swap)
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from google.adk.runners import Runner
from google.genai import types as genai_types

if TYPE_CHECKING:
    from google.adk.sessions import BaseSessionService

from atelier.intake.brief_parser import BriefParserAgent, BriefParserGate
from atelier.intake.source_resolver import source_resolver_agent, source_resolver_gate
from atelier.intake.web_research import WebResearchReport, research_brief
from atelier.models.data_contracts import TenantContext
from atelier.models.enums import GateDecision
from atelier.orchestrator.generator_ensemble import create_generator_ensemble
from atelier.orchestrator.governor import (
    GovernorState,
    MetacognitiveGovernor,
)

logger = logging.getLogger(__name__)

# Hard $5K MAX cap per PRD section 7.2
BUDGET_CAP_USD: float = 5000.0

# Estimated cost per N3a ensemble run (3 generators x ~$0.05 each)
N3A_COST_ESTIMATE_USD: float = 0.15

# ADK app name constant
_APP_NAME: str = "atelier"


def _default_session_service() -> BaseSessionService:
    """Create the default session service.

    In local dev (no BQ SDK), falls back to InMemorySessionService.
    In production, uses BigQuerySessionBackend.

    Returns:
        A BaseSessionService implementation.
    """
    try:
        from atelier.memory.bigquery_session import BigQuerySessionBackend  # noqa: PLC0415

        return BigQuerySessionBackend()
    except ImportError:
        from google.adk.sessions.in_memory_session_service import (  # noqa: PLC0415
            InMemorySessionService,
        )

        logger.info("Using InMemorySessionService (BigQuery SDK not available)")
        return InMemorySessionService()


class AtelierRunner:
    """Phase 2 Pipeline Runner with Governor + injectable SessionBackend.

    Chains N1 (Brief Parser) -> N2 (Source Resolver) -> N3a (Generator Ensemble).
    All LLM calls are governed by the budget cap and failure trichotomy.

    The session service is injectable via the ``SessionBackend`` Protocol (B4).
    Default: ``BigQuerySessionBackend`` -> ``InMemorySessionService`` fallback.
    """

    def __init__(
        self,
        *,
        budget_cap_usd: float = BUDGET_CAP_USD,
        session_service: BaseSessionService | None = None,
    ) -> None:
        """Initialize the runner with a governor and session service.

        Args:
            budget_cap_usd: Maximum cumulative cost in USD. Defaults to $5K.
            session_service: Injectable session service. Defaults to
                BigQuerySessionBackend (with InMemorySessionService fallback).
        """
        state = GovernorState(budget_cap_usd=budget_cap_usd)
        self._governor = MetacognitiveGovernor(state=state)
        self._session_service = session_service or _default_session_service()

    async def _run_n1_n2(
        self,
        brief_text: str,
        tenant_ctx: TenantContext,
    ) -> tuple[Any, Any, WebResearchReport]:
        """Execute N1 (Brief Parser), WRAI, and N2 (Source Resolver) stages."""
        gate = BriefParserGate()
        outcome = gate.check(brief_text)
        if outcome.decision != GateDecision.PASS:
            raise ValueError(f"Brief failed gate: {outcome.diagnostic}")
        n1_agent = BriefParserAgent()
        brief = await n1_agent.parse(brief_text)

        # N14 WRAI: web research before BriefSpec lock (AG-09)
        wrai_report = await research_brief(brief_text)

        if not source_resolver_gate(tenant_ctx, brief):
            raise ValueError("Source resolver gate failed (no descriptor or design source).")
        project_ctx = await source_resolver_agent(tenant_ctx, brief)
        return brief, project_ctx, wrai_report

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
            A dictionary containing the final brief, project context,
            generated candidates, stitch degradation flag, web research,
            and session metadata.

        Raises:
            GovernorBudgetExceeded: When cumulative cost exceeds the budget cap.
                This is a fail-loud condition per PRD section 21.
            ValueError: When brief fails the deterministic gate.
        """
        if tenant_ctx is None:
            tenant_ctx = TenantContext(
                tenant_id="t1",
                user_id="u1",
                project_id="p1",
                cost_budget_usd=Decimal("100.0"),
            )

        brief, project_ctx, wrai_report = await self._run_n1_n2(brief_text, tenant_ctx)

        # Create a session via the injected session service (B4)
        session_id = str(uuid.uuid4())
        session = await self._session_service.create_session(
            app_name=_APP_NAME,
            user_id=tenant_ctx.user_id or "anonymous",
            state={"brief_text": brief_text[:500]},  # Truncate for state storage
            session_id=session_id,
        )

        # N3a: Generator Ensemble — governed
        async def _run_ensemble() -> tuple[list[Any], bool]:
            ensemble, stitch_degradation = create_generator_ensemble()
            adk_runner = Runner(
                agent=ensemble,
                session_service=self._session_service,
                app_name=_APP_NAME,
            )

            candidates: list[Any] = []
            async for event in adk_runner.run_async(
                user_id=tenant_ctx.user_id or "anonymous",
                session_id=session.id,
                new_message=genai_types.Content(
                    role="user",
                    parts=[
                        genai_types.Part(
                            text="Generate screens based on the brief and project context."
                        )
                    ],
                ),
            ):
                candidates.extend(_extract_text_from_event(event))

            return candidates, stitch_degradation.is_degraded

        governed_result = await self._governor.run_with_governance(
            _run_ensemble,
            step_id="n3a_generator_ensemble",
            cost_estimate_usd=N3A_COST_ESTIMATE_USD,
        )

        if governed_result is None:
            # Governor returned None — fail-soft: the N3a ensemble was degraded by
            # the governor (budget cap, 429 exhaustion, stall timeout, or loop
            # detection). This is NOT a Stitch failure — Stitch's availability is
            # unknown when the governor degrades. stitch_degraded must remain False.
            candidates: list[Any] = []
            stitch_degraded = False
            degradation_reason: str | None = "n3a_governor_fail_soft"
            user_message: str | None = (
                "The generation step degraded unexpectedly due to an infrastructure "
                "condition (budget cap, rate limit, or stall timeout). Your session "
                "was preserved. Please retry — no additional charge was applied."
            )
            logger.warning(
                "N3a governed run returned None (fail-soft); candidates list is empty",
                extra={
                    "step_id": "n3a_generator_ensemble",
                    "budget_used_usd": self._governor._state.total_cost_usd,
                    "budget_cap_usd": self._governor._state.budget_cap_usd,
                },
            )
        else:
            candidates, stitch_degraded = governed_result
            if stitch_degraded:
                degradation_reason = "stitch_mcp_unavailable"
                user_message = (
                    "The Stitch design tool is temporarily unavailable. "
                    "Generating directly from the model — output will not include "
                    "Stitch design-system tokens. Retry to use the full design pipeline."
                )
            else:
                degradation_reason = None
                user_message = None

        return {
            "brief": brief,
            "project_context": project_ctx,
            "candidates": candidates,
            "stitch_degraded": stitch_degraded,
            "degradation_reason": degradation_reason,
            "user_message": user_message,
            "budget_used_usd": self._governor._state.total_cost_usd,
            "budget_cap_usd": self._governor._state.budget_cap_usd,
            "web_research": wrai_report,
            "session_id": session.id,
        }

    @property
    def total_cost_usd(self) -> float:
        """Current cumulative cost tracked by the governor."""
        return self._governor._state.total_cost_usd

    @property
    def session_service(self) -> BaseSessionService:
        """The active session service (for testing/inspection)."""
        return self._session_service


def _extract_text_from_event(event: Any) -> list[Any]:
    """Extract text content from an ADK 2.0 Event.

    Handles multiple event shapes:
        - ADK Event objects with content.parts[].text
        - Dict events with 'data' key (test mocks, legacy format)
        - Raw events (fallback -- returns event as-is)

    Returns a list of text strings or the raw event.
    """
    texts: list[Any] = []

    # ADK 2.0 Event API: content.parts[].text
    if hasattr(event, "content") and hasattr(event.content, "parts"):
        for part in event.content.parts:
            if hasattr(part, "text") and part.text:
                texts.append(part.text)

    # Dict-based events (test mocks, legacy format)
    elif isinstance(event, dict) and "data" in event:
        texts.append(event["data"])

    if not texts:
        texts.append(event)
    return texts
