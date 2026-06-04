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

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

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
    # Generation and visual: the bulk of token spend lives here.  Flash is
    # 4x cheaper than Pro per output token and produces indistinguishable HTML
    # quality for role-specialist tasks that have structured upstream context.
    TaskType.UX_RESEARCH: GEMINI_FLASH_MODEL_ID,
    TaskType.IA_FLOW: GEMINI_FLASH_MODEL_ID,
    TaskType.WIREFRAME: GEMINI_FLASH_MODEL_ID,
    TaskType.UI_DESIGN: GEMINI_FLASH_MODEL_ID,
    TaskType.INTERACTION: GEMINI_FLASH_MODEL_ID,
    TaskType.WEB_RESEARCH: GEMINI_FLASH_MODEL_ID,
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
}


def calibrate_model(task_type: TaskType) -> str:
    """Return the optimal model ID for the given pipeline task.

    In production: resolves from :data:`TASK_MODEL_ROUTING`.
    In hermetic test environments: ``GEMINI_MODEL_ID`` env var overrides ALL
    calibrated models so tests can inject a single mock model without needing
    to patch every specialist separately.

    Args:
        task_type: The pipeline task being routed.

    Returns:
        A Vertex AI model ID string ready to pass to ``LlmAgent(model=...)``.
    """
    override = os.environ.get("GEMINI_MODEL_ID")
    if override:
        return override
    return TASK_MODEL_ROUTING[task_type]


def resolve_model_id() -> str:
    """Return the operator-pinned Gemini model id (backwards-compat shim).

    New code should call :func:`calibrate_model` with an explicit
    :class:`TaskType`.  This shim is kept for call sites that pre-date the
    tiered routing (e.g. the agent-engine deploy module and legacy tests).
    """
    return os.environ.get("GEMINI_MODEL_ID", DEFAULT_GEMINI_MODEL_ID)


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
