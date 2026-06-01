"""Atelier Pipeline Runner — current implementation (N1 → N2 → N3a → N3c → N3d + Governor + SessionBackend).

Full 8-node DAG (current implementation):
    N1  BriefParserGate + BriefParserAgent
    N14 WRAI — web research augmented intake (parallel)
    N2  SourceResolverGate + SourceResolverAgent
    N3a DDLC Specialist Pipeline (SequentialAgent of 6 role specialists — AT-020)
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

import json
import logging
import os
import uuid
from collections.abc import Callable
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
from atelier.orchestrator.governor import (
    GovernorState,
    MetacognitiveGovernor,
)
from atelier.orchestrator.specialists import create_specialist_pipeline
from atelier.orchestrator.stop_reason import (
    StopReason,
    StopSignals,
    candidate_fingerprint,
    is_duplicate,
    is_no_improvement,
    resolve_stop_reason,
)

logger = logging.getLogger(__name__)

# Hard $5K MAX cap per PRD §7.2
BUDGET_CAP_USD: float = 5000.0

# Estimated cost per N3a run (DDLC SequentialAgent — 6 specialists, AT-020)
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


def _compose_anchor(brief: Any, project_ctx: Any, wrai_report: Any) -> str:
    """R4 (ADR-0012 anchored_context): the immutable anchor re-injected into the
    generator prompt every iteration -- the signed-off brief + design tokens +
    research findings, serialized deterministically so the re-injection is
    byte-identical across iterations regardless of accumulated fixer history.
    """
    brief_blob = brief.model_dump_json() if hasattr(brief, "model_dump_json") else str(brief)
    tokens = getattr(project_ctx, "design_tokens", None) or {}
    tokens_blob = json.dumps(tokens, sort_keys=True, default=str)
    findings = getattr(wrai_report, "results", None) or []
    research_blob = json.dumps([str(f) for f in findings], sort_keys=True)
    return (
        "--- BRIEF (anchor; do not deviate) ---\n"
        + brief_blob
        + "\n--- DESIGN TOKENS (anchor) ---\n"
        + tokens_blob
        + "\n--- RESEARCH FINDINGS (anchor) ---\n"
        + research_blob
    )


def _compose_generator_prompt(anchor: str, screen: str, directive: str) -> str:
    """Compose one iteration's generator prompt: the immutable anchor + the screen
    task + ONLY the latest fixer directive (rejected-variant history is never
    accumulated -- R4)."""
    base = f"{anchor}\n\n--- TASK ---\nGenerate the screen: '{screen}'."
    return f"{base}\n\n--- LATEST FIXER DIRECTIVE ---\n{directive}" if directive else base


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

    Chains N1 (Brief Parser) -> N2 (Source Resolver) -> N3a (DDLC Specialist Pipeline).
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
            wrai_report = WebResearchReport(results=[])

        if not source_resolver_gate(tenant_ctx, brief):
            raise ValueError("Source resolver gate failed (no descriptor or design source).")
        project_ctx = await source_resolver_agent(tenant_ctx, brief)
        return brief, project_ctx, wrai_report, plan

    async def run(  # noqa: C901, PLR0912, PLR0915 — core multi-surface convergence loop
        self,
        brief_text: str,  # current implementation: used for trajectory metadata
        tenant_ctx: TenantContext | None = None,
        progress_callback: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        """Run the pipeline from brief text to generated candidates.

        Args:
            brief_text: Raw brief text input.
            tenant_ctx: Tenant context for source resolution. Defaults to a
                placeholder context for local development.
            progress_callback: Optional async callback to stream progress events.

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

        if progress_callback:
            plan_data = plan.model_dump() if hasattr(plan, "model_dump") else {}
            plan_data["surfaces"] = getattr(plan, "surfaces", ["landing page"])
            await progress_callback("plan", plan_data)

        # Import fixer dynamically to avoid circular dependencies
        from atelier.nodes.fixer import FixerAgent  # noqa: PLC0415

        fixer = FixerAgent(self._governor)

        screens_results = {}
        surfaces = getattr(plan, "surfaces", ["landing page"])
        if not surfaces:
            surfaces = ["landing page"]

        for idx, screen in enumerate(surfaces):
            if progress_callback:
                await progress_callback("screen_start", {"screen": screen, "index": idx})

            # Initialize convergence state for this screen.
            # R4: build the immutable anchor once; re-inject it (never accumulate)
            # each iteration so fixer feedback cannot displace the brief/tokens/research.
            anchor = _compose_anchor(brief, project_ctx, wrai_report)
            latest_directive = ""
            generator_prompt = _compose_generator_prompt(anchor, screen, latest_directive)
            best_candidate = None
            convergence_result: dict[str, Any] = {}
            stitch_degraded = False
            degradation_reason = None
            user_message = None
            gate_results_serialized: list[dict[str, Any]] = []
            evaluations_serialized: list[dict[str, Any]] = []
            raw_candidates: list[Any] = []
            exit_reason: StopReason = StopReason.MAX_ITERATIONS
            iteration = 0
            previous_best_score: float | None = None
            seen_fingerprints: set[str] = set()

            for iteration in range(self._max_iterations):
                self._governor._state.record_step(f"convergence_loop_{screen}_{iteration}")

                if progress_callback:
                    await progress_callback(
                        "iteration_start", {"screen": screen, "iteration": iteration}
                    )

                if self._governor._state.is_over_budget():
                    logger.warning("Convergence loop halted: budget exceeded.")
                    # Deprecated legacy USD path (retired by AT-095); kept as an
                    # alias until the per-user token cap replaces the USD governor.
                    exit_reason = StopReason.BUDGET_EXHAUSTED
                    break

                if self._governor._state.is_loop():
                    logger.warning("Convergence loop halted: governor detected infinite loop.")
                    exit_reason = StopReason.GOVERNOR_LOOP_DETECTED
                    break

                # R4: re-inject the immutable anchor + only the latest fixer
                # directive (clear accumulated rejected-variant history).
                generator_prompt = _compose_generator_prompt(anchor, screen, latest_directive)

                # N3a: DDLC Specialist Pipeline (SequentialAgent, AT-020) — governed
                async def _run_ensemble(prompt: str = generator_prompt) -> tuple[list[Any], bool]:
                    pipeline, stitch_degradation = create_specialist_pipeline()
                    adk_runner = Runner(
                        agent=pipeline,
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
                    step_id=f"n3a_specialist_pipeline_{screen}_{iteration}",
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
                            "step_id": f"n3a_specialist_pipeline_{screen}_{iteration}",
                            "budget_used_usd": self._governor._state.total_cost_usd,
                            "budget_cap_usd": self._governor._state.budget_cap_usd,
                        },
                    )
                    exit_reason = StopReason.GOVERNOR_FAIL_SOFT
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

                if progress_callback:
                    await progress_callback(
                        "candidates", {"screen": screen, "candidates": raw_candidates}
                    )

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

                if progress_callback:
                    await progress_callback(
                        "gates_evaluation",
                        {"screen": screen, "gate_results": gate_results_serialized},
                    )
                    await progress_callback(
                        "consensus_evaluation",
                        {"screen": screen, "evaluations": evaluations_serialized},
                    )

                # R1 stop-reason precedence: collapse the post-generation signals to
                # the single highest-precedence reason (converged > max_iterations >
                # no_improvement > duplicate). token_cap_exhausted / governor signals
                # are handled at their own halt points above.
                best_score = float(convergence_result.get("composite_score", 0.0))
                fresh_candidate = best_candidate if isinstance(best_candidate, str) else ""
                signals = StopSignals(
                    converged=bool(convergence_result.get("converged")),
                    max_iterations_reached=iteration == self._max_iterations - 1,
                    no_improvement=is_no_improvement(previous_best_score, best_score),
                    duplicate=bool(fresh_candidate)
                    and is_duplicate(fresh_candidate, seen_fingerprints),
                )
                resolved = resolve_stop_reason(signals)
                if resolved is not None:
                    logger.info(
                        "Loop stop for screen %s at iteration %d: %s (composite=%.3f)",
                        screen,
                        iteration,
                        resolved.value,
                        best_score,
                    )
                    exit_reason = resolved
                    break

                # Not stopping this iteration: record anchors for the next round
                # (R4 re-anchoring of the running best + duplicate fingerprints).
                previous_best_score = best_score
                if fresh_candidate:
                    seen_fingerprints.add(candidate_fingerprint(fresh_candidate))

                # Run FixerAgent for the next iteration.
                if iteration < self._max_iterations - 1:
                    logger.info(
                        "Iteration %d did not converge for screen %s. Running FixerAgent.",
                        iteration,
                        screen,
                    )

                    # Extract outcomes for the best candidate (or first if none)
                    best_evals = convergence_result.get("all_evaluations", [])
                    best_consensus = best_evals[0] if best_evals else None

                    all_gate_results = convergence_result.get("all_gate_results", [])
                    target_gate_outcomes = all_gate_results[0].outcomes if all_gate_results else []

                    directive = await fixer.fix(
                        gate_outcomes=target_gate_outcomes, consensus=best_consensus
                    )

                    if progress_callback:
                        await progress_callback(
                            "fixer_directive",
                            {"screen": screen, "directive": directive.model_dump()},
                        )

                    # Mutate prompt for next iteration
                    amendments = "\n".join(directive.prompt_amendments)
                    # R4: REPLACE the directive (do not accumulate); the anchor is
                    # re-injected fresh next iteration by _compose_generator_prompt.
                    latest_directive = amendments
                    logger.info(
                        "FixerAgent proposed mutations for screen %s: %s",
                        screen,
                        directive.mutations,
                    )

            if progress_callback:
                await progress_callback(
                    "screen_converged",
                    {
                        "screen": screen,
                        "best_candidate": best_candidate,
                        "converged": convergence_result.get("converged", False),
                    },
                )

            # Record this screen's results
            screens_results[screen] = {
                "best_candidate": best_candidate,
                "candidates": raw_candidates,
                "convergence_iteration": iteration,
                "exit_reason": exit_reason.value,
                "converged": convergence_result.get("converged", False),
                "composite_score": convergence_result.get("composite_score", 0.0),
                "candidates_evaluated": convergence_result.get("candidates_evaluated", 0),
                "candidates_passed_gates": convergence_result.get("candidates_passed_gates", 0),
                "gate_results": gate_results_serialized,
                "evaluations": evaluations_serialized,
                "stitch_degraded": stitch_degraded,
                "degradation_reason": degradation_reason,
                "user_message": user_message,
            }

        # Select the first screen as the default top-level result
        first_screen_name = surfaces[0]
        first_screen_res = screens_results[first_screen_name]

        response_payload = {
            "brief": brief,
            "project_context": project_ctx,
            "candidates": first_screen_res["candidates"],
            "best_candidate": first_screen_res["best_candidate"],
            "convergence_iteration": first_screen_res["convergence_iteration"],
            "exit_reason": first_screen_res["exit_reason"],
            "converged": first_screen_res["converged"],
            "composite_score": first_screen_res["composite_score"],
            "candidates_evaluated": first_screen_res["candidates_evaluated"],
            "candidates_passed_gates": first_screen_res["candidates_passed_gates"],
            "gate_results": first_screen_res["gate_results"],
            "evaluations": first_screen_res["evaluations"],
            "stitch_degraded": first_screen_res["stitch_degraded"],
            "degradation_reason": first_screen_res["degradation_reason"],
            "user_message": first_screen_res["user_message"],
            "budget_used_usd": self._governor._state.total_cost_usd,
            "budget_cap_usd": self._governor._state.budget_cap_usd,
            "web_research": wrai_report,
            "session_id": session.id,
            "plan": plan.model_dump() if hasattr(plan, "model_dump") else {},
            "screens": screens_results,
        }

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

        if progress_callback:
            await progress_callback("complete", response_payload)

        return response_payload

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
