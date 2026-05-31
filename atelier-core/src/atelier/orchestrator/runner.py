"""Atelier Pipeline Runner — current implementation (N1 → N2 → N3a → N3c → N3d + Governor + SessionBackend).

Full 8-node DAG (current implementation):
    N1  BriefParserGate + BriefParserAgent
    N14 WRAI — web research augmented intake (parallel)
    N2  SourceResolverGate + SourceResolverAgent
    N3a Generator Ensemble (ParallelAgent, K=3 candidates)
    N3c Deterministic Gates (6 gates per candidate — fast, hallucination-free filter)
    N3d ConsensusAgent (D-O-R-A-V multi-judge evaluation on passing candidates)
    N4  Final scoring and convergence decision

All LLM steps execute under MetacognitiveGovernor governance:
    - Fail-loud at $5K MAX cap (GovernorBudgetExceeded)
    - Self-heal on 429/503 transients (3 retries, exponential backoff)
    - Fail-soft on tool degradation (log + degrade, do not crash)

Session service injectable via ``SessionBackend`` Protocol (B4):
    - Production: ``BigQuerySessionBackend`` (BQ-backed, cross-instance resumption)
    - Local dev:  ``InMemorySessionService`` (ephemeral, default fallback)

PRD Reference: §6.3 (N1-N4), §21 (Failure Trichotomy)
"""

from __future__ import annotations

import logging
import os
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from google.adk.runners import Runner
from google.genai import types as genai_types

if TYPE_CHECKING:
    from google.adk.sessions import BaseSessionService

    from atelier.nodes.llm_judge import JudgeClient

from atelier.gates.runner import run_gates
from atelier.intake.brief_parser import BriefParserAgent, BriefParserGate
from atelier.intake.source_resolver import source_resolver_agent, source_resolver_gate
from atelier.intake.web_research import WebResearchReport, research_brief
from atelier.models.axis_weights import AxisWeights
from atelier.models.data_contracts import CandidateUI, TenantContext
from atelier.models.enums import GateAxis, GateDecision
from atelier.nodes.consensus import evaluate_candidate
from atelier.orchestrator.generator_ensemble import create_generator_ensemble
from atelier.orchestrator.governor import (
    GovernorState,
    MetacognitiveGovernor,
)

logger = logging.getLogger(__name__)

# Hard $5K MAX cap per PRD §7.2
BUDGET_CAP_USD: float = 5000.0

# Estimated cost per N3a ensemble run (3 generators x ~$0.05 each)
N3A_COST_ESTIMATE_USD: float = 0.15

# N3c gate axes — all 6 run in current implementation
_N3C_GATE_AXES: list[GateAxis] = [
    GateAxis.SEMANTIC_HTML,
    GateAxis.LIGHTHOUSE_PERF,
    GateAxis.TOKEN_FIDELITY,
    GateAxis.LIGHTHOUSE_A11Y,
    GateAxis.AXE,
    GateAxis.VISUAL_DIFF,
]

# D-O-R-A-V convergence threshold — composite score must meet this to PASS
CONVERGENCE_THRESHOLD: float = 0.70

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
    """current implementation Pipeline Runner with Governor + injectable SessionBackend.

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
        judge_client: JudgeClient | None = None,
        max_iterations: int = 3,
    ) -> None:
        """Initialize the runner with a governor, session service, and optional judge client.

        Args:
            budget_cap_usd: Maximum cumulative cost in USD. Defaults to $5K.
            session_service: Injectable session service. Defaults to
                BigQuerySessionBackend (with InMemorySessionService fallback).
            judge_client: Injectable LLM judge client. When ``None`` and
                ``ATELIER_JUDGE_MODE`` is ``"llm"`` or ``"hybrid"``,
                auto-constructs a :class:`VertexAIJudgeClient` using
                ``ATELIER_GCP_PROJECT`` (default ``"atelier-build-2026"``).
                Pass an explicit client in tests to avoid network I/O.
        """
        state = GovernorState(budget_cap_usd=budget_cap_usd)
        self._governor = MetacognitiveGovernor(state=state)
        self._session_service = session_service or _default_session_service()

        # Auto-wire production Vertex client when a non-heuristic mode is
        # configured via the environment.  Tests inject a fake client to
        # avoid importing vertexai or hitting the network.
        from atelier.nodes.llm_judge import (  # noqa: PLC0415
            ATELIER_JUDGE_MODE_ENV,
            JUDGE_MODE_HEURISTIC,
            VertexAIJudgeClient,
        )

        effective_mode = os.environ.get(ATELIER_JUDGE_MODE_ENV, JUDGE_MODE_HEURISTIC)
        if judge_client is not None:
            self._judge_client: JudgeClient | None = judge_client
        elif effective_mode != JUDGE_MODE_HEURISTIC:
            project = os.environ.get("ATELIER_GCP_PROJECT", "atelier-build-2026")
            self._judge_client = VertexAIJudgeClient(project=project)
        else:
            self._judge_client = None
        self._max_iterations = max_iterations

    def _run_n3c_n3d_n4(
        self,
        raw_candidates: list[Any],
        brief_text: str,  # noqa: ARG002
        iteration: int = 0,
    ) -> dict[str, Any]:
        """Execute N3c (deterministic gates) → N3d (consensus) → N4 (final pick).

        This is the convergence engine that separates Atelier from one-shot
        generators. Every candidate from N3a is evaluated through:

            N3c: 6 deterministic gates (semantic HTML, CSS, token fidelity,
                 Lighthouse heuristic, axe heuristic, visual diff). Only
                 candidates that pass ALL gates proceed to N3d.

            N3d: D-O-R-A-V consensus evaluation (5-axis weighted scoring).
                 Produces a composite score per passing candidate.

            N4:  Selects the best-scoring candidate that exceeds the
                 convergence threshold. Falls back to the best available
                 candidate if none exceed the threshold.

        Gates are pure-Python (no LLM calls). Consensus mode is controlled
        by ``ATELIER_JUDGE_MODE``: ``"heuristic"`` (default, v1.0 implementation scorers),
        ``"llm"`` (Vertex AI per-axis judges), or ``"hybrid"`` (LLM wins,
        heuristic disagreement recorded for calibration dashboards).

        Args:
            raw_candidates: List of candidate strings from N3a. Each string
                is assumed to be raw HTML/CSS output from a generator.
            brief_text: Original brief text (used to build candidate metadata).

        Returns:
            Dict with keys: best_candidate, all_gate_results, all_evaluations,
            converged, composite_score, candidates_evaluated, candidates_passed_gates.
        """
        from uuid import uuid4  # noqa: PLC0415

        weights = AxisWeights()
        gate_results = []
        evaluations = []
        candidates_passed_gates = 0

        for raw in raw_candidates:
            html_content = raw if isinstance(raw, str) else str(raw)
            if not html_content.strip():
                continue

            # Build CandidateUI for gate + consensus evaluation
            candidate = CandidateUI(
                candidate_id=uuid4(),
                surface_id=uuid4(),
                iteration=iteration,
                artifacts={"index.html": html_content},
            )

            # N3c: deterministic gates
            gate_result = run_gates(candidate, _N3C_GATE_AXES)
            gate_results.append(gate_result)

            if not gate_result.all_passed:
                failed_axes = [
                    o.axis.value for o in gate_result.outcomes if o.decision != GateDecision.PASS
                ]
                logger.info(
                    "N3c: candidate %s REJECTED — failed gates: %s",
                    str(candidate.candidate_id)[:8],
                    failed_axes,
                )
                continue

            candidates_passed_gates += 1

            # N3d: D-O-R-A-V consensus evaluation (heuristic or LLM per ATELIER_JUDGE_MODE)
            # Consensus evaluation runs synchronously; consider asyncio.to_thread for high-concurrency deployments.
            evaluation = evaluate_candidate(candidate, weights, judge_client=self._judge_client)
            evaluations.append((evaluation, html_content))
            logger.info(
                "N3d: candidate %s composite=%.3f passed=%s",
                str(candidate.candidate_id)[:8],
                evaluation.composite_score,
                evaluation.passed,
            )

        # N4: select best candidate
        best_candidate: str | None = None
        best_score: float = 0.0
        converged = False

        if evaluations:
            # Sort by composite score descending
            evaluations.sort(key=lambda x: x[0].composite_score, reverse=True)
            best_evaluation, best_candidate = evaluations[0]
            best_score = best_evaluation.composite_score
            converged = best_score >= CONVERGENCE_THRESHOLD

            logger.info(
                "N4: selected candidate with composite=%.3f (converged=%s, threshold=%.2f)",
                best_score,
                converged,
                CONVERGENCE_THRESHOLD,
            )
        elif raw_candidates:
            # No candidates passed gates — fall back to first raw candidate
            best_candidate = (
                raw_candidates[0] if isinstance(raw_candidates[0], str) else str(raw_candidates[0])
            )
            logger.warning(
                "N4: all candidates failed N3c gates; falling back to raw candidate 1/%d",
                len(raw_candidates),
            )

        return {
            "best_candidate": best_candidate,
            "all_gate_results": gate_results,
            "all_evaluations": [e for e, _ in evaluations],
            "converged": converged,
            "composite_score": best_score,
            "candidates_evaluated": len(raw_candidates),
            "candidates_passed_gates": candidates_passed_gates,
        }

    async def _run_n1_n2(
        self,
        brief_text: str,  # current implementation: used for trajectory metadata
        tenant_ctx: TenantContext,
    ) -> tuple[Any, Any, WebResearchReport, Any]:
        """Execute N1 (Brief Parser), N0 (Planner), WRAI (conditional), and N2 (Source Resolver).

        The PlannerAgent (N0) runs after brief parsing to produce a PlanStep
        that drives WRAI routing: narrow briefs skip web research, creative
        briefs get full research augmentation.

        Returns:
            Tuple of (brief, project_ctx, wrai_report, plan_step).
        """
        from atelier.orchestrator.planner import PlannerAgent  # noqa: PLC0415

        gate = BriefParserGate()
        outcome = gate.check(brief_text)
        if outcome.decision != GateDecision.PASS:
            raise ValueError(f"Brief failed gate: {outcome.diagnostic}")
        n1_agent = BriefParserAgent()
        brief = await n1_agent.parse(brief_text)

        # N0: PlannerAgent — dynamic DAG routing based on brief analysis
        planner = PlannerAgent()
        plan = await planner.plan(brief_text)
        logger.info(
            "N0: PlannerAgent produced plan",
            extra={
                "should_run_wrai": plan.should_run_wrai,
                "ensemble_k": plan.ensemble_k,
                "constitution": plan.constitution,
                "reasoning": plan.reasoning,
            },
        )

        # N14 WRAI: conditional on plan.should_run_wrai
        if plan.should_run_wrai:
            wrai_report = await research_brief(brief_text)
        else:
            logger.info("N14 WRAI: skipped per PlannerAgent (should_run_wrai=False)")
            wrai_report = WebResearchReport(results=[], query=brief_text)

        if not source_resolver_gate(tenant_ctx, brief):
            raise ValueError("Source resolver gate failed (no descriptor or design source).")
        project_ctx = await source_resolver_agent(tenant_ctx, brief)
        return brief, project_ctx, wrai_report, plan

    async def run(
        self,
        brief_text: str,  # current implementation: used for trajectory metadata
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

        brief, project_ctx, wrai_report, plan = await self._run_n1_n2(brief_text, tenant_ctx)

        # Create a session via the injected session service (B4)
        session_id = str(uuid.uuid4())
        session = await self._session_service.create_session(
            app_name=_APP_NAME,
            user_id=tenant_ctx.user_id or "anonymous",
            state={"brief_text": brief_text[:500]},  # Truncate for state storage
            session_id=session_id,
        )

        # Initialize convergence state
        generator_prompt = "Generate screens based on the brief and project context."
        best_candidate = None
        convergence_result: dict[str, Any] = {}
        stitch_degraded = False
        degradation_reason = None
        user_message = None
        gate_results_serialized: list[dict[str, Any]] = []
        evaluations_serialized: list[dict[str, Any]] = []
        raw_candidates: list[Any] = []
        exit_reason = "max_iterations"
        iteration = 0

        # Import fixer dynamically to avoid circular dependencies
        from atelier.nodes.fixer import FixerAgent  # noqa: PLC0415

        fixer = FixerAgent(self._governor)

        for iteration in range(self._max_iterations):
            self._governor._state.record_step(f"convergence_loop_{iteration}")

            if self._governor._state.is_over_budget():
                logger.warning("Convergence loop halted: budget exceeded.")
                exit_reason = "budget_exhausted"
                break

            if self._governor._state.is_loop():
                logger.warning("Convergence loop halted: governor detected infinite loop.")
                exit_reason = "governor_loop_detected"
                break

            # N3a: Generator Ensemble — governed
            async def _run_ensemble(prompt: str = generator_prompt) -> tuple[list[Any], bool]:
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
                        parts=[genai_types.Part(text=prompt)],
                    ),
                ):
                    candidates.extend(_extract_text_from_event(event))

                return candidates, stitch_degradation.is_degraded

            governed_result = await self._governor.run_with_governance(
                _run_ensemble,
                step_id=f"n3a_generator_ensemble_{iteration}",
                cost_estimate_usd=N3A_COST_ESTIMATE_USD,
            )

            if governed_result is None:
                # Governor returned None — fail-soft
                raw_candidates = []
                stitch_degraded = False
                degradation_reason = "n3a_governor_fail_soft"
                user_message = (
                    "The generation step degraded unexpectedly due to an infrastructure "
                    "condition (budget cap, rate limit, or stall timeout). Your session "
                    "was preserved. Please retry — no additional charge was applied."
                )
                logger.warning(
                    "N3a governed run returned None (fail-soft); loop broken",
                    extra={
                        "step_id": f"n3a_generator_ensemble_{iteration}",
                        "budget_used_usd": self._governor._state.total_cost_usd,
                        "budget_cap_usd": self._governor._state.budget_cap_usd,
                    },
                )
                exit_reason = "governor_fail_soft"
                break
            raw_candidates, stitch_degraded = governed_result
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

            # N3c → N3d → N4: gate filtering + consensus evaluation + best-pick
            convergence_result = self._run_n3c_n3d_n4(
                raw_candidates, brief_text, iteration=iteration
            )
            best_candidate = convergence_result.get("best_candidate")

            gate_results_serialized = [
                {
                    "candidate_id": str(gr.candidate_id),
                    "all_passed": gr.all_passed,
                    "outcomes": [
                        {
                            "axis": o.axis.value,
                            "score": o.score,
                            "passed": o.decision == GateDecision.PASS,
                        }
                        for o in gr.outcomes
                    ],
                }
                for gr in convergence_result.get("all_gate_results", [])
            ]
            evaluations_serialized = [
                {
                    "composite_score": e.composite_score,
                    "passed": e.passed,
                    "votes": {axis.value: {"score": v.score} for axis, v in e.votes.items()},
                }
                for e in convergence_result.get("all_evaluations", [])
            ]

            if convergence_result.get("converged"):
                logger.info("Convergence achieved at iteration %d", iteration)
                exit_reason = "converged"
                break

            # If not converged and we have more iterations, run FixerAgent
            if iteration < self._max_iterations - 1:
                logger.info("Iteration %d did not converge. Running FixerAgent.", iteration)

                # Extract outcomes for the best candidate (or first if none)
                best_evals = convergence_result.get("all_evaluations", [])
                best_consensus = best_evals[0] if best_evals else None

                all_gate_results = convergence_result.get("all_gate_results", [])
                target_gate_outcomes = all_gate_results[0].outcomes if all_gate_results else []

                directive = await fixer.fix(
                    gate_outcomes=target_gate_outcomes, consensus=best_consensus
                )

                # Mutate prompt for next iteration
                amendments = "\n".join(directive.prompt_amendments)
                generator_prompt += f"\n\n--- FEEDBACK FROM ITERATION {iteration} ---\n{amendments}"
                logger.info("FixerAgent proposed mutations: %s", directive.mutations)

        # Mid-flight DPO pair extraction — Dreaming Module (fail-soft).
        # Pairs are written fire-and-forget; write failures must not block response.
        try:
            from atelier.optimize.dreaming_module import (  # noqa: PLC0415
                extract_pairs_midflight,
                write_pairs_to_bq,
            )

            dpo_pairs = extract_pairs_midflight(
                session_id=session.id,
                tenant_id=tenant_ctx.tenant_id,
                surface_id=str(uuid.uuid4()),
                brief_text=brief_text,
                candidates=[str(c) for c in raw_candidates],
                evaluations=evaluations_serialized,
                gate_results=gate_results_serialized,
                best_candidate=str(best_candidate) if best_candidate is not None else None,
                converged=convergence_result["converged"],
            )
            write_pairs_to_bq(dpo_pairs)
        except Exception as _dreaming_exc:  # noqa: BLE001
            # Fail-soft — pair extraction is non-critical, must never break generate
            logger.warning(
                "Mid-flight DPO pair extraction failed (fail-soft): %s: %s",
                type(_dreaming_exc).__name__,
                str(_dreaming_exc)[:200],
            )

        return {
            "brief": brief,
            "project_context": project_ctx,
            # Raw candidates from N3a (all generators)
            "candidates": raw_candidates,
            # Best candidate selected by N4 after gate + consensus scoring
            "best_candidate": best_candidate,
            # Convergence metadata
            "convergence_iteration": iteration,
            "exit_reason": exit_reason,
            "converged": convergence_result.get("converged", False),
            "composite_score": convergence_result.get("composite_score", 0.0),
            "candidates_evaluated": convergence_result.get("candidates_evaluated", 0),
            "candidates_passed_gates": convergence_result.get("candidates_passed_gates", 0),
            # Gate + evaluation details for the bench dashboard
            "gate_results": gate_results_serialized,
            "evaluations": evaluations_serialized,
            # Degradation signals
            "stitch_degraded": stitch_degraded,
            "degradation_reason": degradation_reason,
            "user_message": user_message,
            "budget_used_usd": self._governor._state.total_cost_usd,
            "budget_cap_usd": self._governor._state.budget_cap_usd,
            "web_research": wrai_report,
            "session_id": session.id,
            # current implementation: PlannerAgent routing metadata (visible in traces)
            "plan": plan.model_dump() if hasattr(plan, "model_dump") else {},
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
