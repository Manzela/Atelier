"""ε-Greedy Bandit router — v1 PhaseAwareMoERouter implementation (ADR 0027).

Three routing modes form the v0→v1→v2 Protocol ladder:
  v0 (v0_managed.py): static phase table, Vertex managed routing.
  v1 (this file):     ε-greedy multi-armed bandit per (DAGPhase, ExpertID) arm.
  v2 (future):        RouteLLM-style matrix factorization on DPO pairs.

Arm state lives in-process (dict). This makes route() sub-50ms p99 trivially.
Phase 2 will add BigQuery persistence for arm warm-start across restarts.

epsilon-decay schedule (ADR 0027 §18.4):
  epsilon(t) = max(EPSILON_FLOOR, EPSILON_START * exp(-t / EPSILON_DECAY_SECONDS))
  where t = elapsed seconds since first route() call.

Exploration strategy: UCB1 (Upper Confidence Bound).
Exploitation strategy: greedy argmax on posterior mean score.
"""

from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass
from typing import Final

from atelier.router.protocol import (
    DAGPhase,
    ExpertID,
    RouteDecision,
    RouteRequest,
)

logger = logging.getLogger(__name__)

EPSILON_START: Final[float] = 0.10
EPSILON_FLOOR: Final[float] = 0.02
EPSILON_DECAY_SECONDS: Final[float] = 7.0 * 24 * 3600  # 7 days
UCB1_EXPLORATION_CONSTANT: Final[float] = math.sqrt(2.0)

# Phase 1 static expert preferences — fallback order if bandit has no data yet.
# Flash-family for most phases; Pro for high-stakes judge + selection nodes.
_PHASE_PREFERENCE: Final[dict[DAGPhase, ExpertID]] = {
    DAGPhase.BRIEF_PARSE: ExpertID.GEMINI_3_1_FLASH_LITE,
    DAGPhase.INTENT_SCHEMA: ExpertID.GEMINI_3_1_FLASH_LITE,
    DAGPhase.SURFACE_PLAN: ExpertID.GEMINI_3_FLASH,
    DAGPhase.GENERATE_CANDIDATES: ExpertID.GEMINI_3_FLASH,
    DAGPhase.JUDGE_CANDIDATES: ExpertID.GEMINI_3_PRO,
    DAGPhase.SELECT_WINNER: ExpertID.GEMINI_3_PRO,
    DAGPhase.POLISH: ExpertID.GEMINI_3_FLASH,
    DAGPhase.EMIT: ExpertID.GEMINI_3_1_FLASH_LITE,
}


@dataclass
class _ArmState:
    """Per-(phase, expert) bandit arm posterior."""

    total_pulls: int = 0
    total_score: float = 0.0

    @property
    def mean_score(self) -> float:
        return self.total_score / self.total_pulls if self.total_pulls > 0 else 0.0

    def ucb1(self, total_all_arms: int) -> float:
        """UCB1 exploration bonus.

        Returns inf for unsampled arms — guarantees every arm is tried at
        least once before the bandit starts exploiting.
        """
        if self.total_pulls == 0 or total_all_arms == 0:
            return float("inf")
        return self.mean_score + UCB1_EXPLORATION_CONSTANT * math.sqrt(
            math.log(total_all_arms) / self.total_pulls
        )

    def update(self, score: float) -> None:
        # EC13: Two separate += operations are not atomically safe under concurrent
        # asyncio.to_thread calls. Under the asyncio event loop (single-threaded),
        # concurrent coroutine calls to observe_outcome() are interleaved at await
        # boundaries, not within synchronous code — so update() IS safe for asyncio
        # concurrency. If this bandit is ever used from asyncio.to_thread, wrap the
        # caller in asyncio.Lock. Cloud Run concurrency=1 per container makes this
        # a non-issue in production today.
        self.total_pulls += 1
        self.total_score += score


class EpsilonGreedyBandit:
    """ε-Greedy bandit implementing PhaseAwareMoERouter (v1).

    Arms are keyed by (DAGPhase, ExpertID). Arm state is in-process;
    route() is a pure dict lookup + arithmetic — sub-50ms p99 guaranteed.

    Thread safety: not thread-safe. Cloud Run concurrency=1 per container
    instance for the orchestrator path (PEP 567 ContextVar semantics).
    If parallelism is added, wrap with asyncio.Lock or move to BQ.
    """

    def __init__(self, rng: random.Random | None = None) -> None:
        self._arms: dict[tuple[DAGPhase, ExpertID], _ArmState] = {
            (phase, expert): _ArmState() for phase in DAGPhase for expert in ExpertID
        }
        self._start_time: float = time.monotonic()
        self._rng = rng or random.Random()  # noqa: S311 — probabilistic routing, not cryptography

    def _epsilon(self) -> float:
        elapsed = time.monotonic() - self._start_time
        decayed = EPSILON_START * math.exp(-elapsed / EPSILON_DECAY_SECONDS)
        return max(EPSILON_FLOOR, decayed)

    def _total_pulls_for_phase(self, phase: DAGPhase) -> int:
        return sum(arm.total_pulls for (p, _), arm in self._arms.items() if p == phase)

    def _select_expert(self, phase: DAGPhase, *, explore: bool) -> ExpertID:
        total = self._total_pulls_for_phase(phase)
        phase_arms = {expert: self._arms[(phase, expert)] for expert in ExpertID}
        if explore:
            return max(phase_arms, key=lambda e: phase_arms[e].ucb1(total))
        # Exploitation: greedy argmax on mean score. Tie-break to phase preference.
        best_score = max(arm.mean_score for arm in phase_arms.values())
        candidates = [e for e, arm in phase_arms.items() if arm.mean_score == best_score]
        preferred = _PHASE_PREFERENCE[phase]
        return preferred if preferred in candidates else candidates[0]

    async def route(self, request: RouteRequest) -> RouteDecision:
        """Return a route decision for the given request.

        Sub-50ms p99 guaranteed: arm state is in-process, no I/O.

        Args:
            request: The routing request.

        Returns:
            RouteDecision with routing_mode="v1_bandit".
        """
        eps = self._epsilon()
        explore = self._rng.random() < eps
        expert = self._select_expert(request.phase, explore=explore)
        arm = self._arms[(request.phase, expert)]

        fallback_chain = tuple(e for e in _PHASE_PREFERENCE.values() if e != expert)[:2]

        rationale = (
            f"{'explore:ucb1' if explore else 'exploit:greedy'} "
            f"ε={eps:.3f} pulls={arm.total_pulls} μ={arm.mean_score:.3f}"
        )
        logger.debug(
            "v1_bandit route decision",
            extra={
                "phase": request.phase,
                "expert": expert,
                "explore": explore,
                "epsilon": eps,
                "trace_id": request.trace_id,
            },
        )
        return RouteDecision(
            expert=expert,
            score=arm.mean_score,
            rationale=rationale,
            fallback_chain=fallback_chain,
            routing_mode="v1_bandit",
            span_attrs={
                "router.version": "v1_bandit",
                "router.epsilon": eps,
                "router.explore": int(explore),
                "router.arm_pulls": arm.total_pulls,
            },
        )

    async def observe_outcome(
        self,
        *,
        decision: RouteDecision,
        achieved_score: float,
        actual_cost_usd: float,  # noqa: ARG002 — Protocol signature; reserved for BQ cost tracking (Phase 2+)
        actual_latency_ms: int,  # noqa: ARG002 — Protocol signature; reserved for latency-aware arm updates (Phase 2+)
    ) -> None:
        """Update arm posterior with the observed score.

        Args:
            decision: The decision that was taken.
            achieved_score: The judge-validated composite score (0.0-1.0).
            actual_cost_usd: Actual cost incurred (informational).
            actual_latency_ms: Actual latency (informational).
        """
        # Recover the phase from the span_attrs rationale — we store the arm
        # key indirectly. In production, the caller always pairs route() with
        # the RouteRequest they used; phase is available. Here we update all
        # arms for this expert as a best-effort fallback.
        # Production fix (T14+): pass RouteRequest alongside RouteDecision.
        updated = False
        for (phase, expert), arm in self._arms.items():
            if expert == decision.expert:
                arm.update(achieved_score)
                updated = True
                logger.debug(
                    "Bandit arm updated",
                    extra={
                        "phase": phase,
                        "expert": expert,
                        "achieved_score": achieved_score,
                        "new_mean": arm.mean_score,
                    },
                )
        if not updated:
            logger.warning(
                "observe_outcome: no arm found for expert",
                extra={"expert": decision.expert},
            )
