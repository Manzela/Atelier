"""Vertex AI Model Registry — task-aware model routing for Atelier specialists and judges.

Every pipeline task is routed to the optimal Gemini model tier based on the
task's quality requirements and token-cost profile. This is the single source of
truth for model assignment — consumed by the DDLC specialist pipeline (N3a),
the D-O-R-A-V consensus agent (N3d), the planner (N0), and any helper node.

Model Selection Rationale (confirmed against Vertex AI 2026 pricing):

    gemini-2.5-pro  — $1.25/M in | $10.00/M out  — 1M context
        Deep reasoning, planning, creative-novelty judging. Used only where
        quality gap vs Flash is measurable (planner routing, originality judge,
        clarify gate).

    gemini-2.5-flash  — $0.30/M in | $2.50/M out  — 1M context
        Generation, visual assessment, IA/flows/wireframe. Cost-effective at
        the volume Atelier generates (6 candidates x 6 specialists per run).

    gemini-2.5-flash-lite  — $0.10/M in | $0.40/M out  — 1M context
        Cheap extraction and deterministic-adjacent tasks: brief parsing, token
        extraction, copy editing, accessibility LLM fallback. 12.5x cheaper
        than Pro; quality adequate for classification and short-output tasks.

Per-user lifetime token caps (user.spec):
    Pro        ->  5_000_000 tokens
    Flash      -> 15_000_000 tokens
    Flash-Lite -> 60_000_000 tokens

These are enforced by MetacognitiveGovernor (atelier.orchestrator.governor) and
tracked per-tier by UsageCounterStore (atelier.durability.usage_counter).

PRD Reference: §6.3 (Pipeline nodes), §13.2 (usage governance)
ADR Reference: 0007 (Gemini-only model strategy)
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

logger = logging.getLogger(__name__)

#: AT-024 (§22 D5 / G13) — GA Gemini Pro model id, operator-pinned 2026-05-31.
#: Override per-env via GEMINI_MODEL_ID (overrides ALL calibrated models — used
#: for hermetic testing only; production relies on per-task calibration).
DEFAULT_GEMINI_MODEL_ID: Final[str] = "gemini-2.5-pro"

#: GA Flash model id (Vertex AI 2026-06). Confirmed GA; stable alias (no preview suffix).
GEMINI_FLASH_MODEL_ID: Final[str] = "gemini-2.5-flash"

#: GA Flash-Lite model id (Vertex AI 2026-06). preview-09-2025 suffix retired Jul 2026;
#: stable alias is the correct production string.
GEMINI_FLASH_LITE_MODEL_ID: Final[str] = "gemini-2.5-flash-lite"

# ---------------------------------------------------------------------------
# Per-tier lifetime token caps (user.spec: Pro 5M, Flash 15M, Flash-Lite 60M)
# ---------------------------------------------------------------------------

#: Per-model-tier per-user lifetime token caps.  Keyed by the tier string
#: returned by :func:`model_tier_for_id`.  These are the SOLE V1 usage caps —
#: no per-run USD cap, no aggregate-fleet cap beyond AT-097's circuit-breaker.
TIER_TOKEN_CAPS: Final[dict[str, int]] = {
    "pro": 5_000_000,
    "flash": 15_000_000,
    "flash_lite": 60_000_000,
}


def model_tier_for_id(model_id: str) -> str:
    """Map a Gemini model ID to its tier string for token-cap tracking.

    Returns one of ``"pro"``, ``"flash"``, or ``"flash_lite"``. Unknown IDs
    fall back to ``"pro"`` (most restrictive cap — fail-closed on unrecognized
    models so the cap is never bypassed by an unrouted ID).
    """
    lower = model_id.lower()
    if "flash-lite" in lower or "flash_lite" in lower:
        return "flash_lite"
    if "flash" in lower:
        return "flash"
    return "pro"


# ---------------------------------------------------------------------------
# Task types — the routing vocabulary
# ---------------------------------------------------------------------------


class TaskType(StrEnum):
    """Every pipeline task that has a calibrated model assignment.

    Adding a new task here + a corresponding entry in :data:`TASK_MODEL_ROUTING`
    is the complete change to route a new node to a non-default model.
    """

    # N0 — planner decides the whole DAG shape
    PLANNER = "planner"

    # N1 — brief extraction (short-form, structured output)
    BRIEF_PARSE = "brief_parse"

    # N14 / WRAI — web research augmented intake
    WEB_RESEARCH = "web_research"

    # AT-030 clarify gate — uncertainty gap analysis
    CLARIFY = "clarify"

    # N3a DDLC specialists (in pipeline order)
    UX_RESEARCH = "ux_research"
    IA_FLOW = "ia_flow"
    WIREFRAME = "wireframe"
    UI_DESIGN = "ui_design"
    INTERACTION = "interaction"
    TOKEN_GEN = "token_gen"  # noqa: S105

    # N3b / N3e — fixes
    FIXER = "fixer"
    COPY_EDITOR = "copy_editor"

    # N3d D-O-R-A-V judges
    JUDGE_DESIGN = "judge_design"
    JUDGE_ORIGINALITY = "judge_originality"
    JUDGE_RELEVANCE = "judge_relevance"
    JUDGE_ACCESSIBILITY = "judge_accessibility"
    JUDGE_VISUAL = "judge_visual"


# ---------------------------------------------------------------------------
# Task → model routing table (proactive calibration)
# ---------------------------------------------------------------------------

#: Single-source-of-truth routing table.  Every task has an explicit assignment
#: — no implicit defaults — so routing decisions are visible and testable.
TASK_MODEL_ROUTING: Final[dict[TaskType, str]] = {
    # --- gemini-2.5-pro (5M cap) -------------------------------------------
    # Deep reasoning: planning the whole DAG shape (wrong plan = all downstream
    # work wasted) and novelty judging (shallow model scores mid-tier designs
    # as "original" because it lacks the reference depth to know better).
    TaskType.PLANNER: DEFAULT_GEMINI_MODEL_ID,
    TaskType.JUDGE_ORIGINALITY: DEFAULT_GEMINI_MODEL_ID,
    TaskType.CLARIFY: DEFAULT_GEMINI_MODEL_ID,
    # --- gemini-2.5-flash (15M cap) ----------------------------------------
    # Generation and judging: the win-critical HTML output and quality scoring
    # stay on Flash. Flash is 4x cheaper than Pro per output token and produces
    # indistinguishable HTML for role-specialist tasks with structured context.
    TaskType.WIREFRAME: GEMINI_FLASH_MODEL_ID,
    TaskType.UI_DESIGN: GEMINI_FLASH_MODEL_ID,
    TaskType.INTERACTION: GEMINI_FLASH_MODEL_ID,
    # FIXER stays on Flash: it rewrites failing HTML to pass the gates, so its
    # quality directly drives convergence — a Flash-Lite fixer regressed live runs
    # to exit_reason=no_improvement (composite 0.0). 429 relief comes from the
    # research tasks below, not the fixer.
    TaskType.FIXER: GEMINI_FLASH_MODEL_ID,
    TaskType.JUDGE_DESIGN: GEMINI_FLASH_MODEL_ID,
    TaskType.JUDGE_RELEVANCE: GEMINI_FLASH_MODEL_ID,
    TaskType.JUDGE_VISUAL: GEMINI_FLASH_MODEL_ID,
    # --- gemini-2.5-flash-lite (60M cap) ------------------------------------
    # Cheap extraction and deterministic-adjacent tasks: structured short
    # outputs, classification, grammar — quality gap vs Flash is negligible.
    # 12.5x cheaper than Pro, 3x cheaper than Flash.
    TaskType.BRIEF_PARSE: GEMINI_FLASH_LITE_MODEL_ID,
    TaskType.TOKEN_GEN: GEMINI_FLASH_LITE_MODEL_ID,
    TaskType.COPY_EDITOR: GEMINI_FLASH_LITE_MODEL_ID,
    TaskType.JUDGE_ACCESSIBILITY: GEMINI_FLASH_LITE_MODEL_ID,
    # Research / IA / web-research moved to Flash-Lite (60M cap, ~12x Pro / ~4x
    # Flash QPM headroom) to spread load off Flash and relieve the Vertex 429
    # RESOURCE_EXHAUSTED pressure under load — these reasoning/research tasks
    # tolerate Flash-Lite; generation, the fixer, and judging stay on Flash.
    # Tunable per-task via Firebase Remote Config.
    TaskType.UX_RESEARCH: GEMINI_FLASH_LITE_MODEL_ID,
    TaskType.IA_FLOW: GEMINI_FLASH_LITE_MODEL_ID,
    TaskType.WEB_RESEARCH: GEMINI_FLASH_LITE_MODEL_ID,
}


# ---------------------------------------------------------------------------
# Dynamic model routing via Firebase Remote Config (operator override)
# ---------------------------------------------------------------------------
#
# Operators can override the pinned TASK_MODEL_ROUTING table without a redeploy
# by setting ``model_routing_<task>`` parameters in Firebase Remote Config.
# These are loaded ONCE at application startup (:func:`warm_remote_config_routes`,
# invoked from the FastAPI lifespan) into a process-local cache; the hot-path
# :func:`calibrate_model` reads that cache synchronously and never touches the
# network. firebase-admin 7.x exposes server-side templates via the async
# ``get_server_template()``; the pre-7.x management ``get_template()`` was removed
# (calling it raised AttributeError on every lookup — silently disabling overrides
# and emitting a traceback per model resolution until this was fixed).

#: Resolved, allow-list-validated overrides keyed by ``TaskType.value``. Empty
#: until :func:`warm_remote_config_routes` populates it; an empty cache means
#: every task falls through to its pinned route.
_REMOTE_ROUTE_CACHE: dict[str, str] = {}

#: Startup-warm timeout. Remote Config must never delay Cloud Run readiness, so a
#: slow/unreachable backend is abandoned and the pinned routes are used.
_REMOTE_CONFIG_WARM_TIMEOUT_S: Final[float] = 5.0


def _allowed_model_ids() -> frozenset[str]:
    """Return the set of model ids a Remote Config override may name."""
    return ALL_MODEL_IDS | {
        DEFAULT_GEMINI_MODEL_ID,
        GEMINI_FLASH_MODEL_ID,
        GEMINI_FLASH_LITE_MODEL_ID,
    }


async def warm_remote_config_routes() -> None:
    """Load operator model-routing overrides from Firebase Remote Config.

    Called once at application startup (FastAPI lifespan). Fully fail-soft: any
    error — Firebase uninitialized, no credentials, backend outage, timeout —
    leaves the cache empty so the pinned :data:`TASK_MODEL_ROUTING` table is
    used. A misconfigured (non-allow-listed) parameter is logged once here, at
    warm time, rather than on every hot-path lookup.
    """
    try:
        from firebase_admin import remote_config  # noqa: PLC0415

        from atelier.auth.firebase import _init_firebase  # noqa: PLC0415

        # firebase-admin <7 had get_template(); 7.x replaced it with the async
        # server-side get_server_template(). Guard so neither SDK line errors.
        if not hasattr(remote_config, "get_server_template"):
            return

        _init_firebase()
        template = await asyncio.wait_for(
            remote_config.get_server_template(),
            timeout=_REMOTE_CONFIG_WARM_TIMEOUT_S,
        )
        config = template.evaluate()

        allowed = _allowed_model_ids()
        resolved: dict[str, str] = {}
        for task_type in TaskType:
            param_name = f"model_routing_{task_type.value}"
            raw = config.get_string(param_name)
            cleaned = raw.strip() if isinstance(raw, str) else ""
            if not cleaned:
                continue
            normalized = normalize_model_id(cleaned)
            # A Remote Config value flows straight into LlmAgent(model=...); only
            # honor it when it names a known model id. An unrecognized string must
            # fall back to the pinned route, never be served.
            if normalized in allowed:
                resolved[task_type.value] = normalized
            else:
                logger.warning(
                    "Remote Config model_routing_%s=%r is not an allow-listed "
                    "model id; ignoring and using the pinned route.",
                    task_type.value,
                    cleaned,
                )

        _REMOTE_ROUTE_CACHE.clear()
        _REMOTE_ROUTE_CACHE.update(resolved)
        if resolved:
            logger.info(
                "Remote Config model routing loaded: %d override(s) active.",
                len(resolved),
            )
    except Exception:  # noqa: BLE001
        # Fail-soft: routing must survive a Remote Config outage. Logged at debug
        # (not warning-with-traceback) because the pinned table is a correct,
        # expected fallback — e.g. local/hermetic runs with no Firebase creds.
        logger.debug(
            "Remote Config routing warm-up skipped; using pinned routes.",
            exc_info=True,
        )


def fetch_calibrated_model_from_remote_config(task_type: TaskType) -> str | None:
    """Return the cached Remote Config model override for a task, if any.

    Pure, synchronous cache read — the cache is populated once at startup by
    :func:`warm_remote_config_routes`. Never touches the network and never
    raises, so it is safe in the per-agent-construction hot path. Returns
    ``None`` when no override is configured (the pinned route is then used).
    """
    return _REMOTE_ROUTE_CACHE.get(task_type.value)


def normalize_model_id(model_id: str) -> str:
    """Normalize a model ID string, ensuring compatibility with Vertex AI.

    Specifically maps 'gemini-2.5-flash-001' to 'gemini-2.5-flash'.
    """
    if model_id == "gemini-2.5-flash-001":
        return "gemini-2.5-flash"
    return model_id


def calibrate_model(task_type: TaskType) -> str:
    """Return the optimal model ID for the given pipeline task.

    In production: resolves from Remote Config (fail-soft to :data:`TASK_MODEL_ROUTING`).
    In hermetic test environments: ``GEMINI_MODEL_ID`` env var overrides ALL
    calibrated models so tests can inject a single mock model without needing
    to patch every specialist separately.

    Args:
        task_type: The pipeline task being routed.

    Returns:
        A Vertex AI model ID string ready to pass to ``LlmAgent(model=...)``.
    """
    override = os.environ.get("GEMINI_MODEL_ID")
    if override and override.strip():
        return normalize_model_id(override.strip())

    # Dynamic routing override via Remote Config
    remote_model_id = fetch_calibrated_model_from_remote_config(task_type)
    if remote_model_id:
        return normalize_model_id(remote_model_id)

    return normalize_model_id(TASK_MODEL_ROUTING[task_type])


def resolve_model_id() -> str:
    """Return the operator-pinned Gemini model id (backwards-compat shim).

    New code should call :func:`calibrate_model` with an explicit
    :class:`TaskType`.  This shim is kept for call sites that pre-date the
    tiered routing (e.g. the agent-engine deploy module and legacy tests).
    """
    return normalize_model_id(os.environ.get("GEMINI_MODEL_ID", DEFAULT_GEMINI_MODEL_ID))


# ---------------------------------------------------------------------------
# ModelTier + ModelCapability — structural metadata
# ---------------------------------------------------------------------------


class ModelTier(StrEnum):
    """Vertex AI model tier — determines pricing and capability."""

    FLASH = "flash"
    FLASH_LITE = "flash-lite"
    PRO = "pro"
    FLASH_THINKING = "flash-thinking"


class ModelCapability(StrEnum):
    """Special capabilities that can be enabled per-model."""

    VISION = "vision"
    GROUNDING = "grounding"
    THINKING = "thinking"
    EMBEDDING = "embedding"
    CODE = "code"


@dataclass(frozen=True)
class ModelSpec:
    """Specification for a Vertex AI model deployment.

    Attributes:
        model_id: Vertex AI model resource name.
        display_name: Human-readable name for logging/dashboard.
        tier: Pricing/capability tier.
        region: Primary deployment region.
        fallback_regions: Ordered list of fallback regions.
        capabilities: Set of enabled capabilities.
        max_output_tokens: Maximum output tokens for this model.
        temperature: Default temperature for this model's task.
        thinking_budget: Token budget for thinking mode (None if not enabled).
    """

    model_id: str
    display_name: str
    tier: ModelTier
    region: str = "us-central1"
    fallback_regions: tuple[str, ...] = ("europe-west4", "europe-west1")
    capabilities: frozenset[ModelCapability] = frozenset()
    max_output_tokens: int = 8192
    temperature: float = 0.7
    thinking_budget: int | None = None


# ---------------------------------------------------------------------------
# ModelSpec instances — D-O-R-A-V judge routing (legacy; canonical routing is
# now TASK_MODEL_ROUTING above — these ModelSpec instances remain for the
# ConsensusAgent's generate_content_config lookup)
# ---------------------------------------------------------------------------

JUDGE_MODEL_DESIGN = ModelSpec(
    model_id=calibrate_model(TaskType.JUDGE_DESIGN),
    display_name="Design Judge (Flash Vision)",
    tier=ModelTier.FLASH,
    capabilities=frozenset({ModelCapability.VISION}),
    max_output_tokens=4096,
    temperature=0.3,
)

JUDGE_MODEL_ORIGINALITY = ModelSpec(
    model_id=calibrate_model(TaskType.JUDGE_ORIGINALITY),
    display_name="Originality Judge (Pro Thinking)",
    tier=ModelTier.PRO,
    capabilities=frozenset({ModelCapability.THINKING}),
    max_output_tokens=4096,
    temperature=0.5,
    thinking_budget=8192,
)

JUDGE_MODEL_RELEVANCE = ModelSpec(
    model_id=calibrate_model(TaskType.JUDGE_RELEVANCE),
    display_name="Relevance Judge (Flash + Grounding)",
    tier=ModelTier.FLASH,
    capabilities=frozenset({ModelCapability.GROUNDING}),
    max_output_tokens=4096,
    temperature=0.2,
)

JUDGE_MODEL_ACCESSIBILITY = ModelSpec(
    model_id=calibrate_model(TaskType.JUDGE_ACCESSIBILITY),
    display_name="Accessibility Judge (Flash-Lite Fallback)",
    tier=ModelTier.FLASH_LITE,
    capabilities=frozenset(),
    max_output_tokens=2048,
    temperature=0.1,
)

JUDGE_MODEL_VISUAL = ModelSpec(
    model_id=calibrate_model(TaskType.JUDGE_VISUAL),
    display_name="Visual Clarity Judge (Flash + Embedding)",
    tier=ModelTier.FLASH,
    capabilities=frozenset({ModelCapability.VISION, ModelCapability.EMBEDDING}),
    max_output_tokens=4096,
    temperature=0.3,
)

GENERATOR_MODEL = ModelSpec(
    model_id=calibrate_model(TaskType.UI_DESIGN),
    display_name="UI Generator (Flash)",
    tier=ModelTier.FLASH,
    capabilities=frozenset({ModelCapability.VISION, ModelCapability.CODE}),
    max_output_tokens=65536,
    temperature=0.8,
)

COPY_EDITOR_MODEL = ModelSpec(
    model_id=calibrate_model(TaskType.COPY_EDITOR),
    display_name="Copy Editor (Flash-Lite)",
    tier=ModelTier.FLASH_LITE,
    capabilities=frozenset(),
    max_output_tokens=8192,
    temperature=0.4,
)

FIXER_MODEL = ModelSpec(
    model_id=calibrate_model(TaskType.FIXER),
    display_name="Fixer (Flash Code)",
    tier=ModelTier.FLASH,
    capabilities=frozenset({ModelCapability.CODE}),
    max_output_tokens=65536,
    temperature=0.3,
)

# ---------------------------------------------------------------------------
# Convenience lookups — used by ConsensusAgent and Orchestrator
# ---------------------------------------------------------------------------

JUDGE_MODEL_CONFIG: dict[str, ModelSpec] = {
    "brand": JUDGE_MODEL_DESIGN,
    "originality": JUDGE_MODEL_ORIGINALITY,
    "relevance": JUDGE_MODEL_RELEVANCE,
    "accessibility": JUDGE_MODEL_ACCESSIBILITY,
    "visual_clarity": JUDGE_MODEL_VISUAL,
}

NODE_MODEL_CONFIG: dict[str, ModelSpec] = {
    "n3a_generator": GENERATOR_MODEL,
    "n3b_copy_editor": COPY_EDITOR_MODEL,
    "n3e_fixer": FIXER_MODEL,
}

ALL_MODEL_IDS: frozenset[str] = frozenset(
    spec.model_id
    for spec in [
        *JUDGE_MODEL_CONFIG.values(),
        *NODE_MODEL_CONFIG.values(),
    ]
)

ALL_REGIONS: frozenset[str] = frozenset(
    region
    for spec in [*JUDGE_MODEL_CONFIG.values(), *NODE_MODEL_CONFIG.values()]
    for region in (spec.region, *spec.fallback_regions)
)


# ---------------------------------------------------------------------------
# Model catalog — model-id-centric view of TASK_MODEL_ROUTING
# ---------------------------------------------------------------------------

#: Human-readable display name per GA model id, used by the model catalog and
#: any dashboard/agent-registry surface. Keyed by the *static* routing target so
#: the catalog has a stable label even when ``calibrate_model`` resolves a
#: Remote-Config override at runtime.
_MODEL_DISPLAY_NAMES: Final[dict[str, str]] = {
    DEFAULT_GEMINI_MODEL_ID: "Gemini 2.5 Pro",
    GEMINI_FLASH_MODEL_ID: "Gemini 2.5 Flash",
    GEMINI_FLASH_LITE_MODEL_ID: "Gemini 2.5 Flash-Lite",
}


@dataclass(frozen=True)
class ModelCatalogEntry:
    """One model id grouped with the tasks it serves and its cost envelope.

    A model-id-centric inversion of :data:`TASK_MODEL_ROUTING`: instead of
    "which model does this task use", this answers "which tasks does this model
    serve, at what tier, with what lifetime token cap". Consumed by the agent
    registry and any read-only model/usage dashboard.

    Attributes:
        model_id: The Vertex AI Gemini model id (the static routing target).
        display_name: Human-readable label for logging/dashboard.
        tier: Tier string from :func:`model_tier_for_id` (``pro`` / ``flash`` /
            ``flash_lite``) — the same key used by :data:`TIER_TOKEN_CAPS`.
        token_cap: Per-user lifetime token cap for this tier
            (:data:`TIER_TOKEN_CAPS`).
        task_types: Sorted tuple of :class:`TaskType` values statically routed
            to this model id.
    """

    model_id: str
    display_name: str
    tier: str
    token_cap: int
    task_types: tuple[TaskType, ...]


def get_model_catalog() -> tuple[ModelCatalogEntry, ...]:
    """Group :data:`TASK_MODEL_ROUTING` by model id (read-only catalog view).

    Single source of truth for "which Gemini models does Atelier route to, and
    what does each serve". Built purely from :data:`TASK_MODEL_ROUTING` so it
    can never drift from the routing table; each entry attaches the tier
    (:func:`model_tier_for_id`), the per-tier lifetime cap
    (:data:`TIER_TOKEN_CAPS`), and a stable display name.

    Returns:
        A tuple of :class:`ModelCatalogEntry`, one per distinct model id,
        ordered by tier cost (Pro, then Flash, then Flash-Lite) and then by
        model id for determinism.
    """
    by_model: dict[str, list[TaskType]] = {}
    for task_type, model_id in TASK_MODEL_ROUTING.items():
        by_model.setdefault(model_id, []).append(task_type)

    # Order Pro -> Flash -> Flash-Lite (most to least expensive) for a stable,
    # human-meaningful catalog ordering.
    tier_order: dict[str, int] = {"pro": 0, "flash": 1, "flash_lite": 2}

    entries: list[ModelCatalogEntry] = []
    for model_id, task_types in by_model.items():
        tier = model_tier_for_id(model_id)
        entries.append(
            ModelCatalogEntry(
                model_id=model_id,
                display_name=_MODEL_DISPLAY_NAMES.get(model_id, model_id),
                tier=tier,
                token_cap=TIER_TOKEN_CAPS[tier],
                task_types=tuple(sorted(task_types, key=lambda t: t.value)),
            )
        )

    entries.sort(key=lambda e: (tier_order.get(e.tier, 99), e.model_id))
    return tuple(entries)
