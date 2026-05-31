"""v0 router: deterministic phase + budget → ExpertID mapping (§18.4).

v0 ships D9. Zero Vertex SDK calls live here — the wrapper exists so the
orchestrator can integrate the router surface immediately; actual model
selection happens one layer up when ``Client.models.generate_content`` is
called with the chosen ``ExpertID`` as the model.

The policy from §18.4 docstring, made explicit:

- budget ≤ 0 (any phase)           → GEMINI_3_1_FLASH_LITE  + "cost.degraded"
- BRIEF_PARSE                      → GEMINI_3_FLASH
- INTENT_SCHEMA                    → GEMINI_3_1_FLASH_LITE
- SURFACE_PLAN                     → GEMINI_3_FLASH
- GENERATE_CANDIDATES, budget<0.50 → GEMINI_3_1_FLASH_LITE
- GENERATE_CANDIDATES, budget≥0.50 → GEMINI_3_FLASH
- JUDGE_CANDIDATES                 → GEMINI_2_5_PRO   (Originality pin per §7.1; v0 simplification)
- SELECT_WINNER                    → GEMINI_3_1_FLASH_LITE
- POLISH                           → GEMINI_3_FLASH
- EMIT                             → GEMINI_3_1_FLASH_LITE
"""

from __future__ import annotations

from typing import Final

from .protocol import (
    DAGPhase,
    ExpertID,
    RouteDecision,
    RouteRequest,
)

_GENERATE_BUDGET_FLOOR_USD: Final[float] = 0.50

_STATIC_PHASE_ROUTE: Final[dict[DAGPhase, ExpertID]] = {
    DAGPhase.BRIEF_PARSE: ExpertID.GEMINI_3_FLASH,
    DAGPhase.INTENT_SCHEMA: ExpertID.GEMINI_3_1_FLASH_LITE,
    DAGPhase.SURFACE_PLAN: ExpertID.GEMINI_3_FLASH,
    DAGPhase.JUDGE_CANDIDATES: ExpertID.GEMINI_2_5_PRO,
    DAGPhase.SELECT_WINNER: ExpertID.GEMINI_3_1_FLASH_LITE,
    DAGPhase.POLISH: ExpertID.GEMINI_3_FLASH,
    DAGPhase.EMIT: ExpertID.GEMINI_3_1_FLASH_LITE,
}

_FALLBACK_CHAIN_BY_PRIMARY: Final[dict[ExpertID, tuple[ExpertID, ...]]] = {
    ExpertID.GEMINI_3_PRO: (ExpertID.GEMINI_3_FLASH, ExpertID.GEMINI_3_1_FLASH_LITE),
    ExpertID.GEMINI_3_FLASH: (ExpertID.GEMINI_2_5_FLASH, ExpertID.GEMINI_3_1_FLASH_LITE),
    ExpertID.GEMINI_3_1_FLASH_LITE: (ExpertID.GEMINI_2_5_FLASH,),
    ExpertID.GEMINI_2_5_PRO: (
        ExpertID.GEMINI_3_PRO,
        ExpertID.GEMINI_3_FLASH,
        ExpertID.GEMINI_3_1_FLASH_LITE,
    ),
    ExpertID.GEMINI_2_5_FLASH: (ExpertID.GEMINI_3_FLASH, ExpertID.GEMINI_3_1_FLASH_LITE),
}


class ManagedRoutingRouter:
    """v1.0 implementation router. Deterministic phase x budget -> ExpertID map."""

    async def route(self, request: RouteRequest) -> RouteDecision:
        """Return a route decision based on the static phase table."""
        # Cost-gate fail-soft (§18.7).
        if request.cost_budget_remaining_usd <= 0:
            primary = ExpertID.GEMINI_3_1_FLASH_LITE
            rationale = (
                f"cost.degraded: budget_remaining={request.cost_budget_remaining_usd:.4f} "
                f"≤ 0 — forcing cheapest expert ({primary.value})"
            )
            return RouteDecision(
                expert=primary,
                phase=request.phase,
                score=0.5,
                rationale=rationale,
                fallback_chain=_FALLBACK_CHAIN_BY_PRIMARY[primary],
                routing_mode="v0_managed",
                span_attrs={
                    "atelier.router.phase": request.phase.value,
                    "atelier.router.cost_degraded": True,
                    "atelier.router.budget_remaining_usd": request.cost_budget_remaining_usd,
                },
            )

        # GENERATE_CANDIDATES splits by budget tier.
        if request.phase is DAGPhase.GENERATE_CANDIDATES:
            if request.cost_budget_remaining_usd < _GENERATE_BUDGET_FLOOR_USD:
                primary = ExpertID.GEMINI_3_1_FLASH_LITE
                tier = "low"
            else:
                primary = ExpertID.GEMINI_3_FLASH
                tier = "high"
            rationale = (
                f"generate_candidates: budget_tier={tier} "
                f"(budget={request.cost_budget_remaining_usd:.2f}, floor={_GENERATE_BUDGET_FLOOR_USD}) "
                f"→ {primary.value}"
            )
        else:
            primary = _STATIC_PHASE_ROUTE[request.phase]
            rationale = f"static: phase={request.phase.value} → {primary.value}"

        return RouteDecision(
            expert=primary,
            phase=request.phase,
            score=0.95,
            rationale=rationale,
            fallback_chain=_FALLBACK_CHAIN_BY_PRIMARY[primary],
            routing_mode="v0_managed",
            span_attrs={
                "atelier.router.phase": request.phase.value,
                "atelier.router.cost_degraded": False,
                "atelier.router.budget_remaining_usd": request.cost_budget_remaining_usd,
                "atelier.router.latency_target_ms": request.latency_target_ms,
            },
        )

    async def observe_outcome(
        self,
        *,
        decision: RouteDecision,  # noqa: ARG002
        achieved_score: float,  # noqa: ARG002
        actual_cost_usd: float,  # noqa: ARG002
        actual_latency_ms: int,  # noqa: ARG002
    ) -> None:
        """v0 is closed-loop (Vertex managed); v1 bandit will consume this signal."""
        return
