"""Atelier Pipeline Runner — N1 → N2 → N3a → N3c → N3d + Governor + SessionBackend.

Full 8-node DAG:
    N1  BriefParserGate + BriefParserAgent
    N14 WRAI — web research augmented intake (parallel)
    N2  SourceResolverGate + SourceResolverAgent
    N3a DDLC Specialist Pipeline (SequentialAgent of 6 role specialists — AT-020)
    N3c Deterministic Gates (6 gates per candidate — fast, hallucination-free filter)
    N3d ConsensusAgent (D-O-R-A-V multi-judge evaluation on passing candidates)
    N4  Final scoring and convergence decision

All LLM steps execute under MetacognitiveGovernor governance:
    - Fail-loud at the per-user lifetime 5M-token cap (GovernorTokenCapExceeded, AT-095)
    - Self-heal on 429/503 transients (3 retries, exponential backoff)
    - Fail-soft on tool degradation (log + degrade, do not crash)

Session service injectable via ``SessionBackend`` Protocol (B4):
    - Production: ``BigQuerySessionBackend`` (BQ-backed, cross-instance resumption)
    - Local dev:  ``InMemorySessionService`` (ephemeral, default fallback)

PRD Reference: §6.3 (N1-N4), §21 (Failure Trichotomy)
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import uuid
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.adk.runners import Runner
from google.genai import types as genai_types

if TYPE_CHECKING:
    from google.adk.sessions import BaseSessionService
    from google.adk.tools.tool_confirmation import ToolConfirmation

    from atelier.nodes.llm_judge import JudgeClient

from atelier.durability.usage_counter import UsageCounterStore, get_usage_store
from atelier.gates.runner import run_gates
from atelier.gates.signoff import (
    AWAIT_SIGNOFF_TOOL,
    CHECKPOINT_KEY,
    SIGNOFF_STAGE_ID,
    SIGNOFF_STATUS_KEY,
    STATUS_APPROVED,
    STATUS_AWAITING,
    STATUS_COMPLETED,
    await_signoff,
    is_signoff_confirmed,
)
from atelier.intake.brief_parser import BriefParserAgent, BriefParserGate
from atelier.intake.brief_spec import BriefSpec
from atelier.intake.source_resolver import (
    ProjectContext,
    source_resolver_agent,
    source_resolver_gate,
)
from atelier.intake.web_research import (
    WebResearchReport,
    WebResearchResult,
    research_brief,
)
from atelier.models.axis_weights import AxisWeights
from atelier.models.data_contracts import CandidateUI, TenantContext
from atelier.models.enums import GateAxis, GateDecision
from atelier.nodes.consensus import evaluate_candidate
from atelier.orchestrator.governor import (
    TOKEN_CAP_MESSAGE,
    GovernorState,
    MetacognitiveGovernor,
)
from atelier.orchestrator.planner import PlanStep
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

# N3c gate axes — all 6 run
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

# AT-031 stable stage ids for the per-stage accumulators (GovernorState). These are
# NOT iteration-specific — the durability oracle asserts completed-stage counts are
# unchanged (delta 0) across a halt/crash/resume cycle, so they must be stable.
STAGE_N1_BRIEF_PARSE: str = "n1_brief_parse"
STAGE_N2_SOURCE_RESOLVE: str = "n2_source_resolve"
STAGE_N3A_SPECIALIST_PIPELINE: str = "n3a_specialist_pipeline"

# Nominal token attribution per stage call. The accumulator's purpose is the
# resume-delta oracle (pre-signoff stages frozen, post-signoff stages > 0), not a
# precise token meter; ADK does not surface a deterministic offline token count for
# the faked model surface, so a fixed per-call attribution keeps the delta check
# meaningful and deterministic. This is the AT-031 durability oracle, independent
# of the AT-095 user-lifetime token cap below.
STAGE_TOKEN_ATTRIBUTION: int = 1


def _usage_from_event(event: Any) -> tuple[int, int, int]:
    """Extract (input, output, thinking) tokens from one ADK event's usage_metadata.

    Returns ``(0, 0, 0)`` when the event carries no usage (e.g. the faked offline
    model surface) — the caller estimates deterministically in that case.
    """
    usage = getattr(event, "usage_metadata", None)
    if usage is None:
        return (0, 0, 0)
    return (
        int(getattr(usage, "prompt_token_count", 0) or 0),
        int(getattr(usage, "candidates_token_count", 0) or 0),
        int(getattr(usage, "thoughts_token_count", 0) or 0),
    )


def _estimate_tokens(prompt: str, candidates: list[Any]) -> tuple[int, int, int]:
    """Deterministic offline token estimate (~4 chars/token) for the AT-095 counter.

    Used only when the model surface surfaces no ``usage_metadata`` (the hermetic
    ``make verify`` / ``make replay`` lane). Deterministic for identical inputs so
    the token meter is byte-stable (PRD §13.3). Thinking tokens are 0 offline —
    real ``thoughts_token_count`` is counted whenever Vertex surfaces it.
    """
    input_tokens = max(1, len(prompt) // 4)
    output_tokens = sum(max(1, len(str(c)) // 4) for c in candidates) if candidates else 0
    return (input_tokens, output_tokens, 0)


def _require_user_id(tenant_ctx: TenantContext) -> str:
    """Return the non-empty Firebase uid for token-cap accounting, or fail loud.

    AT-095: the cap and the rate limiter are keyed on the uid. A missing/empty
    uid must NEVER silently collapse into a shared bucket (which would let
    unrelated callers share one 5M counter — a cross-caller DoS). The public API
    always supplies a verified uid (Depends(require_auth)); this guards the
    programmatic / default-context paths.
    """
    uid = tenant_ctx.user_id
    if not uid:
        raise ValueError(
            "AT-095: TenantContext.user_id is required for per-user token-cap accounting; "
            "refusing to bucket usage into a shared anonymous counter."
        )
    return uid


def _serialize_checkpoint(
    *,
    brief: BriefSpec,
    project_ctx: ProjectContext,
    wrai_report: WebResearchReport,
    plan: PlanStep,
    surfaces: list[str],
    session_id: str,
    brief_text: str,
    stage_call_counts: dict[str, int],
    stage_token_counts: dict[str, int],
) -> dict[str, Any]:
    """Serialize the pre-signoff pipeline outputs into a JSON-safe checkpoint dict.

    Stored under ``session.state[CHECKPOINT_KEY]`` so a fresh ``AtelierRunner`` sharing
    the same session service can reconstruct N1/N2 outputs after a crash without
    re-running them. ``BriefSpec``/``ProjectContext``/``PlanStep`` are Pydantic
    (``model_dump(mode="json")``); ``WebResearchReport`` is a dataclass
    (``dataclasses.asdict``).
    """
    return {
        "brief": brief.model_dump(mode="json"),
        "project_ctx": project_ctx.model_dump(mode="json"),
        "wrai_report": dataclasses.asdict(wrai_report),
        "plan": plan.model_dump(mode="json"),
        "surfaces": list(surfaces),
        "session_id": session_id,
        "brief_text": brief_text,
        "stage_call_counts": dict(stage_call_counts),
        "stage_token_counts": dict(stage_token_counts),
    }


def _deserialize_checkpoint(
    payload: dict[str, Any],
) -> tuple[BriefSpec, ProjectContext, WebResearchReport, PlanStep, list[str], str, str]:
    """Reconstruct the pre-signoff outputs from a serialized checkpoint.

    Inverse of :func:`_serialize_checkpoint`. Reconstructs the dataclass
    ``WebResearchReport`` (and its ``WebResearchResult`` items) and the Pydantic
    models. Returns ``(brief, project_ctx, wrai_report, plan, surfaces, session_id,
    brief_text)``. The stage accumulators are restored separately by the caller into
    the governor state.
    """
    brief = BriefSpec.model_validate(payload["brief"])
    project_ctx = ProjectContext.model_validate(payload["project_ctx"])
    wrai_raw = payload["wrai_report"]
    wrai_report = WebResearchReport(
        results=[WebResearchResult(**item) for item in wrai_raw.get("results", [])],
        denied_count=wrai_raw.get("denied_count", 0),
        total_queries=wrai_raw.get("total_queries", 0),
    )
    plan = PlanStep.model_validate(payload["plan"])
    surfaces = list(payload["surfaces"])
    return (
        brief,
        project_ctx,
        wrai_report,
        plan,
        surfaces,
        str(payload["session_id"]),
        str(payload["brief_text"]),
    )


#: Synthetic function_call_id for the production halt path. The native ADK runner
#: assigns a real id when a tool call is dispatched (see the AT-031 integration test,
#: which exercises the genuine LongRunningFunctionTool + Runner path); the production
#: halt only needs request_confirmation to register a ToolConfirmation, which requires
#: a non-empty function_call_id.
_SIGNOFF_FUNCTION_CALL_ID: str = "atelier_signoff"


class _SignoffToolContext:
    """Minimal tool-context shim for the production sign-off halt.

    ``await_signoff`` is generic over any context exposing ``function_call_id`` and a
    ``request_confirmation(*, hint, payload)`` method. In the AT-031 integration test the
    real ``ToolContext`` (built by the ADK ``Runner``) is used end-to-end, proving the
    native ``adk_request_confirmation`` halt. In production ``run()`` does not spin up an
    autonomous agent loop to fire the confirmation (that would issue model calls during
    the halt window), so this shim records the confirmation request with the exact
    semantics verified in ``google.adk.tools.tool_context.ToolContext.request_confirmation``
    against google-adk==2.1.0: it writes a ``ToolConfirmation`` into
    ``EventActions.requested_tool_confirmations[function_call_id]``.
    """

    def __init__(self, *, actions: EventActions) -> None:
        self._event_actions = actions
        self.function_call_id = _SIGNOFF_FUNCTION_CALL_ID

    def request_confirmation(
        self,
        *,
        hint: str | None = None,
        payload: Any | None = None,
    ) -> None:
        """Register a confirmation request (mirrors ADK 2.1.0 ToolContext semantics).

        Unlike the real ``ToolContext.request_confirmation`` — which raises ``ValueError``
        when ``function_call_id`` is empty — this shim always supplies a non-empty
        ``function_call_id`` (``_SIGNOFF_FUNCTION_CALL_ID``) by construction, so the genuine
        empty-id guard is unreachable here. That native guard is exercised end-to-end by
        oracle 1's real ``Runner`` + ``LongRunningFunctionTool`` path, not by this shim.
        """
        from google.adk.tools.tool_confirmation import ToolConfirmation  # noqa: PLC0415

        self._event_actions.requested_tool_confirmations[self.function_call_id] = ToolConfirmation(
            hint=hint, payload=payload
        )


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


def _build_iteration_dorav(
    evaluations_serialized: list[dict[str, Any]],
    composite_score: float,
) -> dict[str, Any]:
    """Build a per-axis D-O-R-A-V payload for an in-progress iteration.

    Mirrors the extraction logic in ``generate._enrich_complete_payload`` so that
    the per-iteration ``iteration_score`` SSE event carries the same shape as the
    final ``complete`` event's ``dorav`` field.  This is intentionally a module-level
    helper so it can be unit-tested independently of the runner.

    Args:
        evaluations_serialized: The list of serialized evaluation dicts as built in
            ``_run_surfaces_and_assemble`` — each entry has ``composite_score``,
            ``passed``, and ``votes`` (a dict mapping axis name to ``{"score": float}``).
        composite_score: The composite score for the current iteration's best candidate
            (may be 0.0 when no candidate passed the gates).

    Returns:
        A dict with per-axis float scores keyed by axis name, a ``composite`` key, and a
        ``failing_axis`` key containing the name of the axis with the lowest score (or
        ``None`` when no per-axis data is available).
    """
    best_eval: dict[str, Any] = evaluations_serialized[0] if evaluations_serialized else {}
    raw_votes: dict[str, Any] = best_eval.get("votes", {})
    dorav: dict[str, float] = {
        axis: float(v["score"]) if isinstance(v, dict) else float(v)
        for axis, v in raw_votes.items()
    }
    dorav["composite"] = float(best_eval.get("composite_score", composite_score))

    # Determine the failing axis (lowest per-axis score, excluding composite).
    failing_axis: str | None = None
    per_axis = {k: v for k, v in dorav.items() if k != "composite"}
    if per_axis:
        failing_axis = min(per_axis, key=lambda k: per_axis[k])

    return {**dorav, "failing_axis": failing_axis}


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
    """Pipeline Runner with Governor + injectable SessionBackend.

    Chains N1 (Brief Parser) -> N2 (Source Resolver) -> N3a (DDLC Specialist Pipeline).
    All LLM calls are governed by the budget cap and failure trichotomy.

    The session service is injectable via the ``SessionBackend`` Protocol (B4).
    Default: ``BigQuerySessionBackend`` -> ``InMemorySessionService`` fallback.
    """

    def __init__(
        self,
        *,
        session_service: BaseSessionService | None = None,
        judge_client: JudgeClient | None = None,
        usage_store: UsageCounterStore | None = None,
        max_iterations: int = 3,
    ) -> None:
        """Initialize the runner with a governor, session service, and optional judge client.

        Args:
            session_service: Injectable session service. Defaults to
                BigQuerySessionBackend (with InMemorySessionService fallback).
            judge_client: Injectable LLM judge client. When ``None`` and
                ``ATELIER_JUDGE_MODE`` is ``"llm"`` or ``"hybrid"``,
                auto-constructs a :class:`VertexAIJudgeClient` using
                ``ATELIER_GCP_PROJECT`` (default ``"atelier-build-2026"``).
                Pass an explicit client in tests to avoid network I/O.
            usage_store: Injectable per-user lifetime token-cap store (AT-095).
                Defaults to the process-wide singleton (Firestore in production,
                in-memory in the hermetic / dev lane). Pass an explicit
                in-memory store in tests.
        """
        state = GovernorState()
        self._governor = MetacognitiveGovernor(state=state)
        self._usage_store = usage_store or get_usage_store()
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

    def _seed_lifetime_counter(self, user_id: str) -> None:
        """AT-095: bind the governor's token-cap state to ``user_id`` and seed the
        cumulative count from the persisted store so the cap spans runs.

        Idempotent — always reflects the current persisted total. A persistence
        read failure (or a corrupt counter) raises :class:`GovernorUsageUnavailable`
        (fail-closed, retryable 503) from the store — distinct from a real cap breach.
        """
        self._governor._state.user_id = user_id
        self._governor._state.token_cap = self._usage_store.token_cap
        self._governor._state.cumulative_user_tokens = self._usage_store.get_total(user_id)

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

        # AT-097: total N3d (D-O-R-A-V judge) token spend across every evaluated
        # candidate this iteration. 0 in heuristic mode (no LLM call); > 0 when
        # ATELIER_JUDGE_MODE routes axes through Vertex judges. The runner charges
        # this to the per-user lifetime cap (closes the AT-095 N3a-only under-count).
        return {
            "best_candidate": best_candidate,
            "all_gate_results": gate_results,
            "all_evaluations": [e for e, _ in evaluations],
            "converged": converged,
            "composite_score": best_score,
            "candidates_evaluated": len(raw_candidates),
            "candidates_passed_gates": candidates_passed_gates,
            "judge_input_tokens": sum(e.total_input_tokens for e, _ in evaluations),
            "judge_output_tokens": sum(e.total_output_tokens for e, _ in evaluations),
            "judge_thinking_tokens": sum(e.total_thinking_tokens for e, _ in evaluations),
        }

    async def _run_n1_n2(
        self,
        brief_text: str,  # used for trajectory metadata
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
        # AT-031: record the N1 completed-stage call on a stable id. Captured into the
        # sign-off checkpoint and restored on resume so N1 never re-runs (delta 0).
        self._governor._state.record_stage_call(
            STAGE_N1_BRIEF_PARSE, tokens=STAGE_TOKEN_ATTRIBUTION
        )

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
        # AT-031: record the N2 completed-stage call (stable id; frozen across resume).
        self._governor._state.record_stage_call(
            STAGE_N2_SOURCE_RESOLVE, tokens=STAGE_TOKEN_ATTRIBUTION
        )
        return brief, project_ctx, wrai_report, plan

    async def run(
        self,
        brief_text: str,  # used for trajectory metadata
        tenant_ctx: TenantContext | None = None,
        progress_callback: Callable[[str, dict[str, Any]], Any] | None = None,
        *,
        require_signoff: bool = False,
    ) -> dict[str, Any]:
        """Run the pipeline from brief text to generated candidates.

        Args:
            brief_text: Raw brief text input.
            tenant_ctx: Tenant context for source resolution. Defaults to a
                placeholder context for local development.
            progress_callback: Optional async callback to stream progress events.
            require_signoff: AT-031 opt-in human-in-the-loop gate. When ``True``,
                the pipeline locks the plan/scope (N0/N1/N2), persists an idempotent
                ``AWAITING_SIGNOFF`` checkpoint into session state, fires the native
                ``await_signoff`` confirmation request, and RETURNS a halt sentinel
                *before* any screen generation (N3a). Resume via :meth:`resume` with
                a confirmed ``ToolConfirmation``. Defaults to ``False`` (no gate; the
                pre-AT-031 behaviour every existing caller relies on).

        Returns:
            When not gated (or when the gate is already approved inline), the full
            response payload (brief, project context, candidates, ...). When gated
            and awaiting sign-off, a halt sentinel
            ``{"status": "awaiting_signoff", "session_id": ..., "signoff": {...}}``.

        Raises:
            GovernorTokenCapExceeded: When the user's cumulative lifetime token
                count is at/over the 5M cap (AT-095). Fail-loud per PRD §21/§13.
            GovernorRateLimitExceeded: When the user exceeds the request-rate
                limit (AT-095/097). Fail-loud reject of the offending request.
            ValueError: When brief fails the deterministic gate.
        """
        if tenant_ctx is None:
            tenant_ctx = TenantContext(
                tenant_id="t1",
                user_id="u1",
                project_id="p1",
            )

        # AT-095 (§13.2 / G16): per-user lifetime token cap, enforced server-side
        # PRE-FLIGHT — before any Vertex call (N1/N2 included). Seed the cumulative
        # count from the persisted store (spans runs), rate-limit this request so the
        # cap cannot be burned in seconds (acceptance (f)), then fail-loud if already
        # at/over the cap (acceptance (c): no Vertex spend once at cap).
        user_id = _require_user_id(tenant_ctx)
        self._usage_store.check_rate_limit(user_id)
        # AT-097: the fleet-wide token circuit-breaker — reject before N1/N2 (the
        # first Vertex spend) if aggregate consumption across all users tripped it.
        self._usage_store.check_circuit_breaker()
        self._seed_lifetime_counter(user_id)
        self._governor._check_token_budget()

        brief, project_ctx, wrai_report, plan = await self._run_n1_n2(brief_text, tenant_ctx)

        # Create a session via the injected session service (B4)
        session_id = str(uuid.uuid4())
        session = await self._session_service.create_session(
            app_name=_APP_NAME,
            user_id=user_id,
            state={"brief_text": brief_text[:500]},  # Truncate for state storage
            session_id=session_id,
        )

        if progress_callback:
            plan_data = plan.model_dump() if hasattr(plan, "model_dump") else {}
            plan_data["surfaces"] = getattr(plan, "surfaces", ["landing page"])
            await progress_callback("plan", plan_data)

        surfaces = getattr(plan, "surfaces", ["landing page"])
        if not surfaces:
            surfaces = ["landing page"]

        # AT-031 (PRD §1 / §16 / R5): fail-closed human sign-off gate. After the plan
        # and scope are locked and BEFORE the screen loop (N3a), halt for an explicit
        # human approval. Opt-in (default False preserves the pre-AT-031 path). The
        # halt is durable: an idempotent AWAITING_SIGNOFF checkpoint is persisted into
        # session state so a crashed runner resumes from here with zero re-execution.
        if require_signoff and session.state.get(SIGNOFF_STATUS_KEY) != STATUS_APPROVED:
            return await self._halt_for_signoff(
                session=session,
                brief=brief,
                project_ctx=project_ctx,
                wrai_report=wrai_report,
                plan=plan,
                surfaces=surfaces,
                brief_text=brief_text,
                progress_callback=progress_callback,
            )

        return await self._run_surfaces_and_assemble(
            brief=brief,
            project_ctx=project_ctx,
            wrai_report=wrai_report,
            plan=plan,
            surfaces=surfaces,
            session_id=session.id,
            tenant_ctx=tenant_ctx,
            brief_text=brief_text,
            progress_callback=progress_callback,
        )

    async def _halt_for_signoff(
        self,
        *,
        session: Any,
        brief: BriefSpec,
        project_ctx: ProjectContext,
        wrai_report: WebResearchReport,
        plan: PlanStep,
        surfaces: list[str],
        brief_text: str,
        progress_callback: Callable[[str, dict[str, Any]], Any] | None,
    ) -> dict[str, Any]:
        """Persist the AWAITING_SIGNOFF checkpoint, fire the native confirmation, halt.

        Serializes the pre-signoff outputs (N1/N2 results, plan, surfaces, and the
        per-stage accumulators) into ``session.state`` via a durable ADK ``state_delta``,
        invokes the native ``await_signoff`` confirmation request to demonstrate a real
        ``requested_tool_confirmations`` halt, emits a ``"signoff"`` progress event, and
        returns the halt sentinel — stopping before N3a.
        """
        scope_summary = ", ".join(surfaces)
        checkpoint = _serialize_checkpoint(
            brief=brief,
            project_ctx=project_ctx,
            wrai_report=wrai_report,
            plan=plan,
            surfaces=surfaces,
            session_id=session.id,
            brief_text=brief_text,
            stage_call_counts=self._governor._state.stage_call_counts,
            stage_token_counts=self._governor._state.stage_token_counts,
        )
        await self._persist_signoff_state(
            session=session,
            status=STATUS_AWAITING,
            checkpoint=checkpoint,
        )

        # Fire the native ADK confirmation request so a real
        # requested_tool_confirmations / is_long_running halt is demonstrable. The
        # confirmation is captured on a throwaway EventActions: production resume is
        # driven by resume() supplying a confirmed ToolConfirmation, not by an
        # autonomous agent loop here (which would issue model calls during the halt).
        signoff_actions = EventActions()
        ctx = _SignoffToolContext(actions=signoff_actions)
        signoff_response = await_signoff(ctx, scope_summary=scope_summary)  # type: ignore[arg-type]
        requested = signoff_actions.requested_tool_confirmations
        signoff_event = {
            "status": signoff_response["status"],
            "stage": signoff_response["stage"],
            "requested_tool_confirmations": list(requested.keys()),
            # Source the long-running flag from the tool object itself (the native
            # LongRunningFunctionTool) rather than hardcoding it, so the sentinel
            # stays correct if the tool's nature ever changes.
            "is_long_running": AWAIT_SIGNOFF_TOOL.is_long_running,
            "hint": next(iter(requested.values())).hint if requested else None,
        }

        if progress_callback:
            await progress_callback("signoff", signoff_event)

        logger.info(
            "AT-031: pipeline halted for human sign-off (session=%s, surfaces=%s)",
            session.id,
            surfaces,
        )
        return {
            "status": "awaiting_signoff",
            "session_id": session.id,
            "signoff": signoff_event,
        }

    async def _persist_signoff_state(
        self,
        *,
        session: Any,
        status: str,
        checkpoint: dict[str, Any] | None = None,
    ) -> None:
        """Durably persist the sign-off status (and optional checkpoint) into session state.

        Uses an ADK ``append_event`` with a ``state_delta`` so a fresh ``AtelierRunner``
        reading the same session service after a crash observes the persisted state. The
        in-memory ``session.state`` mapping is also updated so the same-process idempotency
        check (``session.state.get(SIGNOFF_STATUS_KEY)``) sees the write immediately.
        """
        state_delta: dict[str, Any] = {SIGNOFF_STATUS_KEY: status}
        if checkpoint is not None:
            state_delta[CHECKPOINT_KEY] = checkpoint
        event = Event(author=_APP_NAME, actions=EventActions(state_delta=state_delta))
        await self._session_service.append_event(session=session, event=event)
        # append_event applies the delta to the passed session in ADK >=2.0; mirror it
        # defensively so callers reading session.state in-process do not depend on that.
        session.state.update(state_delta)

    async def resume(
        self,
        session_id: str,
        confirmation: ToolConfirmation,
        tenant_ctx: TenantContext | None = None,
        progress_callback: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        """Resume a sign-off-halted run from its durable checkpoint (AT-031).

        This is the crash-recovery path: a FRESH ``AtelierRunner`` constructed with the
        same ``session_service`` can call ``resume`` to reload the ``AWAITING_SIGNOFF``
        checkpoint, restore the per-stage accumulators (so completed N1/N2 stages are NOT
        re-incremented), and — only when ``confirmation.confirmed is True`` — run the
        screen loop + payload assembly using the checkpointed outputs (N1/N2 do not
        re-run, so their ``stage_call_counts`` delta is 0).

        ``resume()`` expects a FRESH runner: it treats the checkpoint's persisted
        accumulators as authoritative and REPLACES the in-runner
        ``stage_call_counts``/``stage_token_counts`` with them. Any prior in-runner
        accumulator values (if ``resume`` were called on a non-fresh runner) are
        intentionally discarded — the durable checkpoint is the single source of truth.

        Terminal-state re-entry guard (PRD P4 "crash -> resume, no double-charge"): a
        SECOND confirmed resume on a session whose ``signoff_status`` is already
        ``APPROVED`` or ``COMPLETED`` (approval-webhook redelivery, a UI double-click, or
        a crash AFTER the APPROVED write) must NOT re-run the surface loop — that would be
        real duplicated model spend. Such a re-entry fails closed: it returns an
        ``{"status": "already_resumed", ...}`` sentinel WITHOUT re-running surfaces. Note:

          * Mid-N3a crash recovery — a crash DURING the surface loop, leaving the session
            ``APPROVED`` but with surfaces only partially generated — is intentionally OUT
            of AT-031 scope. The guard fails closed (no re-run, no double-charge) rather
            than auto-resuming partial work; finer-grained mid-surface checkpointing is
            future scope.
          * The guard is NOT concurrency-safe against two genuinely simultaneous resumes:
            the session service offers no compare-and-set, so two callers that both read
            ``AWAITING_SIGNOFF`` before either writes ``APPROVED`` could both proceed.
            Single-flight serialization of resumes is out of AT-031 scope.

        Args:
            session_id: The session id returned in the halt sentinel.
            confirmation: The human's ``ToolConfirmation``. Fail-closed: only
                ``confirmed is True`` advances; ``confirmed is False`` (or absent) leaves
                the run ``AWAITING_SIGNOFF`` and returns the halt sentinel unchanged.
            tenant_ctx: Tenant context. Defaults to the same placeholder as :meth:`run`.
            progress_callback: Optional async progress callback.

        Returns:
            The full response payload on first approval; the halt sentinel on denial;
            an ``{"status": "already_resumed", ...}`` sentinel on re-entry of an
            already-APPROVED/COMPLETED session.

        Raises:
            ValueError: When no AWAITING_SIGNOFF checkpoint exists for ``session_id``.
        """
        if tenant_ctx is None:
            tenant_ctx = TenantContext(
                tenant_id="t1",
                user_id="u1",
                project_id="p1",
            )

        session = await self._session_service.get_session(
            app_name=_APP_NAME,
            user_id=_require_user_id(tenant_ctx),
            session_id=session_id,
        )
        if session is None:
            raise ValueError(f"resume: no session found for session_id={session_id}")
        raw_checkpoint = session.state.get(CHECKPOINT_KEY)
        # Absent or non-dict checkpoint both mean "nothing to resume" — a domain
        # precondition failure, not a caller type-contract violation.
        checkpoint_present = isinstance(raw_checkpoint, dict)
        if not checkpoint_present:
            raise ValueError(f"resume: no AWAITING_SIGNOFF checkpoint for session_id={session_id}")
        checkpoint = cast("dict[str, Any]", raw_checkpoint)

        (
            brief,
            project_ctx,
            wrai_report,
            plan,
            surfaces,
            _ckpt_session_id,
            brief_text,
        ) = _deserialize_checkpoint(checkpoint)

        # Restore the pre-signoff stage accumulators so completed stages are not
        # re-incremented (idempotent resume — completed-stage delta 0). The checkpoint is
        # authoritative for a FRESH runner; any prior in-runner accumulators are discarded.
        self._governor._state.stage_call_counts = dict(checkpoint.get("stage_call_counts", {}))
        self._governor._state.stage_token_counts = dict(checkpoint.get("stage_token_counts", {}))

        # Terminal-state re-entry guard (PRD P4 — no double-charge). If the session is
        # already APPROVED or COMPLETED, a second confirmed resume (webhook redelivery,
        # double-click, or a crash after the APPROVED write) must NOT re-run the surface
        # loop. Fail closed: return an idempotent sentinel without re-running surfaces /
        # re-recording N3a calls. (See the method docstring for the mid-surface-crash and
        # concurrency caveats — both intentionally out of AT-031 scope.)
        current_status = session.state.get(SIGNOFF_STATUS_KEY)
        if current_status in (STATUS_APPROVED, STATUS_COMPLETED):
            logger.info(
                "AT-031: resume re-entry on already-%s session %s — no surface re-run "
                "(fail-closed, no double-charge)",
                current_status,
                session_id,
            )
            return {
                "status": "already_resumed",
                "session_id": session_id,
                "signoff_status": current_status,
            }

        # Fail-closed negative arm: without an explicit confirmed sign-off, stay
        # AWAITING_SIGNOFF and do not advance.
        if not is_signoff_confirmed(confirmation):
            await self._persist_signoff_state(session=session, status=STATUS_AWAITING)
            logger.info(
                "AT-031: resume denied (confirmation not confirmed); session %s stays %s",
                session_id,
                STATUS_AWAITING,
            )
            scope_summary = ", ".join(surfaces)
            return {
                "status": "awaiting_signoff",
                "session_id": session_id,
                "signoff": {
                    "status": STATUS_AWAITING,
                    "stage": SIGNOFF_STAGE_ID,
                    "scope_summary": scope_summary,
                },
            }

        # Mark APPROVED before running surfaces so a crash mid-surface leaves a terminal
        # status the re-entry guard treats as "do not re-run" (fail-closed, no
        # double-charge) — see the re-entry guard above and the docstring caveats.
        await self._persist_signoff_state(session=session, status=STATUS_APPROVED)
        if progress_callback:
            await progress_callback(
                "signoff_approved", {"session_id": session_id, "stage": SIGNOFF_STAGE_ID}
            )
        logger.info("AT-031: sign-off APPROVED for session %s; resuming N3a", session_id)

        payload = await self._run_surfaces_and_assemble(
            brief=brief,
            project_ctx=project_ctx,
            wrai_report=wrai_report,
            plan=plan,
            surfaces=surfaces,
            session_id=session_id,
            tenant_ctx=tenant_ctx,
            brief_text=brief_text,
            progress_callback=progress_callback,
        )

        # Record the terminal state once surfaces finish. A subsequent confirmed resume
        # now hits the COMPLETED arm of the re-entry guard (no surface re-run).
        await self._persist_signoff_state(session=session, status=STATUS_COMPLETED)
        return payload

    async def _run_surfaces_and_assemble(  # noqa: C901, PLR0912, PLR0915 — core multi-surface convergence loop
        self,
        *,
        brief: BriefSpec,
        project_ctx: ProjectContext,
        wrai_report: WebResearchReport,
        plan: PlanStep,
        surfaces: list[str],
        session_id: str,
        tenant_ctx: TenantContext,
        brief_text: str,
        progress_callback: Callable[[str, dict[str, Any]], Any] | None,
    ) -> dict[str, Any]:
        """Run the per-surface convergence loop (N3a..N4) and assemble the payload.

        Shared by :meth:`run` (non-signoff and approved-inline paths) and
        :meth:`resume` (post-approval path). The N1/N2 outputs are passed in already
        resolved; this helper never re-runs them, so their per-stage accumulators are
        unchanged across a sign-off halt/resume.
        """
        # Import fixer dynamically to avoid circular dependencies
        from atelier.nodes.fixer import FixerAgent  # noqa: PLC0415

        fixer = FixerAgent(self._governor)

        screens_results = {}
        user_id = _require_user_id(tenant_ctx)

        # AT-095: (re)seed the lifetime counter from the persisted store and
        # pre-flight the cap on every entry to the generation loop. This covers the
        # resume() path (which calls this helper directly) as well as run(): a resume
        # that would start past the cap is rejected before any screen renders.
        # AT-097: re-check the fleet circuit-breaker here too, so a resume() (which
        # enters this helper directly, bypassing run()'s pre-flight) is also gated.
        self._seed_lifetime_counter(user_id)
        self._usage_store.check_circuit_breaker()
        self._governor._check_token_budget()

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

                if self._governor._state.is_over_token_cap():
                    # AT-095 graceful in-flight stop: the previous iteration's
                    # completed unit pushed cumulative usage to the cap. Stop cleanly
                    # BEFORE starting another (expensive) generation — finish-the-unit,
                    # then a single branded message (never a raw quota error or hang).
                    logger.warning(
                        "Convergence loop graceful stop: per-user token cap reached.",
                        extra={
                            "user_id": user_id,
                            "cumulative_user_tokens": self._governor._state.cumulative_user_tokens,
                            "token_cap": self._governor._state.token_cap,
                        },
                    )
                    exit_reason = StopReason.TOKEN_CAP_EXHAUSTED
                    user_message = TOKEN_CAP_MESSAGE
                    break

                if self._governor._state.is_loop():
                    logger.warning("Convergence loop halted: governor detected infinite loop.")
                    exit_reason = StopReason.GOVERNOR_LOOP_DETECTED
                    break

                # R4: re-inject the immutable anchor + only the latest fixer
                # directive (clear accumulated rejected-variant history).
                generator_prompt = _compose_generator_prompt(anchor, screen, latest_directive)

                # N3a: DDLC Specialist Pipeline (SequentialAgent, AT-020) — governed.
                # Also tallies (input, output, thinking) tokens from each ADK event's
                # usage_metadata for the AT-095 lifetime counter; falls back to a
                # deterministic estimate when the offline model surface reports none.
                async def _run_ensemble(
                    prompt: str = generator_prompt,
                ) -> tuple[list[Any], bool, tuple[int, int, int]]:
                    pipeline, stitch_degradation = create_specialist_pipeline()
                    adk_runner = Runner(
                        agent=pipeline,
                        session_service=self._session_service,
                        app_name=_APP_NAME,
                    )

                    candidates: list[Any] = []
                    usage_in = usage_out = usage_think = 0
                    async for event in adk_runner.run_async(
                        user_id=user_id,
                        session_id=session_id,
                        new_message=genai_types.Content(
                            role="user",
                            parts=[genai_types.Part(text=prompt)],
                        ),
                    ):
                        candidates.extend(_extract_text_from_event(event))
                        ein, eout, ethink = _usage_from_event(event)
                        usage_in += ein
                        usage_out += eout
                        usage_think += ethink

                    if usage_in + usage_out + usage_think == 0:
                        usage_in, usage_out, usage_think = _estimate_tokens(prompt, candidates)

                    return (
                        candidates,
                        stitch_degradation.is_degraded,
                        (usage_in, usage_out, usage_think),
                    )

                governed_result = await self._governor.run_with_governance(
                    _run_ensemble,
                    step_id=f"n3a_specialist_pipeline_{screen}_{iteration}",
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
                            "cumulative_user_tokens": self._governor._state.cumulative_user_tokens,
                            "token_cap": self._governor._state.token_cap,
                        },
                    )
                    exit_reason = StopReason.GOVERNOR_FAIL_SOFT
                    break
                raw_candidates, stitch_degraded, token_usage = governed_result
                # AT-095: attribute this N3a generation's tokens to the user's lifetime
                # counter, persist them (atomic, spans runs), and emit a token_delta so
                # the Studio meter ticks live (§13.3). input + output + thinking.
                tok_in, tok_out, tok_think = token_usage
                self._governor._state.add_user_tokens(
                    input_tokens=tok_in, output_tokens=tok_out, thinking_tokens=tok_think
                )
                self._usage_store.add(
                    user_id,
                    input_tokens=tok_in,
                    output_tokens=tok_out,
                    thinking_tokens=tok_think,
                )
                if progress_callback:
                    await progress_callback(
                        "token_delta",
                        {
                            "input": tok_in,
                            "output": tok_out,
                            "thinking": tok_think,
                            "cumulative_user_tokens": self._governor._state.cumulative_user_tokens,
                        },
                    )
                # AT-031: record the N3a post-signoff stage call on a stable id. This is
                # the "post-signoff stages" side of the resume oracle — its token count
                # must be > 0 after approval, while N1/N2 remain frozen at their
                # checkpointed values. Independent of the AT-095 lifetime counter above.
                self._governor._state.record_stage_call(
                    STAGE_N3A_SPECIALIST_PIPELINE, tokens=STAGE_TOKEN_ATTRIBUTION
                )
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
                # AT-097: charge N3d (D-O-R-A-V judge) token spend to the user's
                # lifetime counter too — not just N3a. Mirrors the N3a attribution
                # above so the cap, the persisted counter, and the live meter all
                # include judge spend (closes the AT-095 N3a-only under-count). 0 in
                # heuristic mode → the guard skips the no-op add + event.
                judge_in = int(convergence_result.get("judge_input_tokens", 0))
                judge_out = int(convergence_result.get("judge_output_tokens", 0))
                judge_think = int(convergence_result.get("judge_thinking_tokens", 0))
                if judge_in or judge_out or judge_think:
                    self._governor._state.add_user_tokens(
                        input_tokens=judge_in,
                        output_tokens=judge_out,
                        thinking_tokens=judge_think,
                    )
                    self._usage_store.add(
                        user_id,
                        input_tokens=judge_in,
                        output_tokens=judge_out,
                        thinking_tokens=judge_think,
                    )
                    if progress_callback:
                        await progress_callback(
                            "token_delta",
                            {
                                "input": judge_in,
                                "output": judge_out,
                                "thinking": judge_think,
                                "cumulative_user_tokens": (
                                    self._governor._state.cumulative_user_tokens
                                ),
                            },
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

                    # AT-093: emit per-iteration D-O-R-A-V scores so the Studio
                    # scorecard can animate convergence in real-time.  The payload
                    # shape matches the ``dorav`` key in the final ``complete`` event
                    # plus a ``failing_axis`` key for the amber highlight.
                    iter_dorav = _build_iteration_dorav(
                        evaluations_serialized,
                        float(convergence_result.get("composite_score", 0.0)),
                    )
                    await progress_callback(
                        "iteration_score",
                        {
                            "screen": screen,
                            "iteration": iteration,
                            "dorav": {k: v for k, v in iter_dorav.items() if k != "failing_axis"},
                            "composite": iter_dorav.get("composite", 0.0),
                            "failing_axis": iter_dorav.get("failing_axis"),
                        },
                    )

                # R1 stop-reason precedence: collapse the post-generation signals to
                # the single highest-precedence reason. token_cap_exhausted always
                # wins (fail-loud security cap) — checked here too so a cap crossed
                # DURING this iteration stops cleanly without one more generation.
                best_score = float(convergence_result.get("composite_score", 0.0))
                fresh_candidate = best_candidate if isinstance(best_candidate, str) else ""
                signals = StopSignals(
                    token_cap_exhausted=self._governor._state.is_over_token_cap(),
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
                    if resolved is StopReason.TOKEN_CAP_EXHAUSTED:
                        # The single branded cap message (acceptance (b)); never a raw
                        # quota error. Shown once via the response/complete payload.
                        user_message = TOKEN_CAP_MESSAGE
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

        # AT-095: the per-user token cap is the highest-precedence outcome and
        # spans surfaces. If ANY surface hit the cap (e.g. surface 1 finished
        # under the cap but surface 2 crossed it), surface the cap signal at the
        # TOP level so the branded message renders exactly once (acceptance (b))
        # instead of being masked by surface 1's non-cap exit_reason.
        cap_hit_any_surface = any(
            res["exit_reason"] == StopReason.TOKEN_CAP_EXHAUSTED.value
            for res in screens_results.values()
        )
        top_exit_reason = (
            StopReason.TOKEN_CAP_EXHAUSTED.value
            if cap_hit_any_surface
            else first_screen_res["exit_reason"]
        )
        top_user_message = (
            TOKEN_CAP_MESSAGE if cap_hit_any_surface else first_screen_res["user_message"]
        )

        response_payload = {
            "brief": brief,
            "project_context": project_ctx,
            "candidates": first_screen_res["candidates"],
            "best_candidate": first_screen_res["best_candidate"],
            "convergence_iteration": first_screen_res["convergence_iteration"],
            "exit_reason": top_exit_reason,
            "converged": first_screen_res["converged"],
            "composite_score": first_screen_res["composite_score"],
            "candidates_evaluated": first_screen_res["candidates_evaluated"],
            "candidates_passed_gates": first_screen_res["candidates_passed_gates"],
            "gate_results": first_screen_res["gate_results"],
            "evaluations": first_screen_res["evaluations"],
            "stitch_degraded": first_screen_res["stitch_degraded"],
            "degradation_reason": first_screen_res["degradation_reason"],
            "user_message": top_user_message,
            # AT-095: token-only usage governance — no USD. tokens_used is the
            # user's cumulative lifetime total (spans runs); the meter (AT-096)
            # rides this + the per-iteration token_delta events.
            "tokens_used": self._governor._state.cumulative_user_tokens,
            "token_cap": self._governor._state.token_cap,
            "web_research": wrai_report,
            "session_id": session_id,
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
                session_id=session_id,
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
    def tokens_used(self) -> int:
        """User's cumulative lifetime token count tracked by the governor (AT-095)."""
        return self._governor._state.cumulative_user_tokens

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
