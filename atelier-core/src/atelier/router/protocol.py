"""Phase-Aware MoE Router — typed Protocol surface (ADR 0027).

v0 implementation: thin wrapper over Vertex AI GenerationConfigRoutingConfig.
v1 implementation: epsilon-greedy multi-armed bandit over the EvoDesign
    trajectory store (BigQuery-backed arms, per spec §18.4).
v2 implementation: RouteLLM-style matrix-factorization router trained on
    Atelier DPO pairs (Phase-2 stretch, per spec §18.5).

All three implementations satisfy the same Protocol — the EvoDesign loop is
agnostic to which router is wired in. Adding a fourth router (e.g.
contextual bandit) only requires another Protocol implementation; no
orchestrator change.

numpy is TYPE_CHECKING-gated by design (not as a workaround). This is the
Protocol surface — it defines the type contract. `task_embedding: NDArray[np.float32]`
carries meaning for static analysis; Python does not enforce annotation types at
runtime so the import is not needed there. Ruff TC002 enforces this pattern:
third-party imports used only for annotations belong in TYPE_CHECKING. Router
implementations (v0_managed.py, v1_bandit.py, v2_matrix.py) construct
RouteRequest in tests and callers that own numpy at runtime. numpy 2.4.6 is in
the requirements.lock since the numpy lockfile add.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Literal, Protocol

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


class DAGPhase(StrEnum):
    """Atelier's 8-node DAG phases — used as gating signal in the router."""

    BRIEF_PARSE = "brief_parse"
    INTENT_SCHEMA = "intent_schema"
    SURFACE_PLAN = "surface_plan"
    GENERATE_CANDIDATES = "generate_candidates"
    JUDGE_CANDIDATES = "judge_candidates"
    SELECT_WINNER = "select_winner"
    POLISH = "polish"
    EMIT = "emit"


class ExpertID(StrEnum):
    """Stable identifiers for routable model endpoints.

    Adding a new expert requires (a) bumping this enum, (b) updating
    `EXPERT_COST_USD_PER_1K_TOKENS` AND `infra/pricing/vertex-2026-05.json`
    (cost-map drift between code and JSON breaks the T3 parity unit test),
    (c) an ADR if it changes the cost profile materially.
    """

    GEMINI_3_PRO = "gemini-3-pro"
    GEMINI_3_FLASH = "gemini-3-flash"
    GEMINI_3_1_FLASH_LITE = "gemini-3.1-flash-lite"
    GEMINI_2_5_PRO = "gemini-2.5-pro"
    GEMINI_2_5_FLASH = "gemini-2.5-flash-001"


# Source-of-truth: `infra/pricing/vertex-2026-05.json` (refreshed monthly).
# Values reflect live Vertex pricing as fetched 2026-05-21 — spec §18.3
# NEEDS-VERIFICATION values were stale; the JSON's _plan_drift_disclosure
# documents the deltas. T3 parity test enforces code↔JSON alignment.
EXPERT_COST_USD_PER_1K_TOKENS: Final[dict[ExpertID, float]] = {
    ExpertID.GEMINI_3_PRO: 0.002,
    ExpertID.GEMINI_3_FLASH: 0.0005,
    ExpertID.GEMINI_3_1_FLASH_LITE: 0.00025,
    ExpertID.GEMINI_2_5_PRO: 0.00125,
    ExpertID.GEMINI_2_5_FLASH: 0.0003,
}


@dataclass(frozen=True, slots=True)
class RouteRequest:
    """Inputs the router observes before deciding.

    `task_embedding` is the 768-dim `text-embedding-005` projection of the
    brief + node-name + (optional) prior-iteration delta. The router treats
    it as opaque; only the v2 matrix-factorization router actually consumes
    the vector — v0/v1 use it only for diagnostics + cache keying.
    """

    phase: DAGPhase
    task_embedding: NDArray[np.float32]
    cost_budget_remaining_usd: float
    latency_target_ms: int
    prior_judge_kappa: float | None
    trace_id: str
    tenant_id: str


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """Outputs the router commits to.

    `fallback_chain` is a tuple (immutable) so the chain is stable for
    trace-replay diffing. `span_attrs` is a mutable dict by necessity (OTel
    span attributes accumulate during the request) — this means
    RouteDecision is NOT hashable, which is the intended tradeoff: the
    decision is a one-shot record, not a cache key.

    `routing_mode` is a frozen Literal so changing the set of routing-mode
    values forces a type-check failure at every call site — prevents
    silent drift when a new router lands.
    """

    expert: ExpertID
    phase: DAGPhase
    score: float
    rationale: str
    fallback_chain: tuple[ExpertID, ...]
    routing_mode: Literal["v0_managed", "v1_bandit", "v2_matrix_factorization"]
    span_attrs: dict[str, str | int | float] = field(default_factory=dict)


class PhaseAwareMoERouter(Protocol):
    """All v0/v1/v2 implementations satisfy this Protocol."""

    async def route(self, request: RouteRequest) -> RouteDecision:
        """Return a route decision.

        MUST be sub-50ms p99 — routing must not become the bottleneck of
        the EvoDesign loop. v0 hits this trivially (in-process dict
        lookup); v1 needs BigQuery arm-state cache; v2 needs a hot
        in-process matrix.
        """
        ...

    async def observe_outcome(
        self,
        *,
        decision: RouteDecision,
        achieved_score: float,
        actual_cost_usd: float,
        actual_latency_ms: int,
    ) -> None:
        """Feedback channel for the router to update its internal state.

        v0 implementation is a no-op (Vertex's managed router is
        closed-loop). v1 updates the ε-greedy bandit arm posteriors. v2
        appends to the DPO-pair queue for the next matrix re-factorization.
        """
        ...
