"""Vertex AI Model Registry — task-aware model routing for Atelier judges.

Maps each D-O-R-A-V axis (Design, Originality, Relevance, Accessibility, Visual)
to the optimal Gemini model configuration based on the task's capabilities.

This registry is the single source of truth for which model handles which task.
It is consumed by ConsensusAgent (N3d) to route judge calls.

Model Selection Rationale (Audit §7, 2026 best practices):
    - Design (Brand Alignment): Gemini 3 Flash (vision) — fast, visual understanding
    - Originality: Gemini 2.5 Pro (thinking) — deep reasoning for novelty assessment
    - Relevance: Gemini 3 Flash + Grounding — factual accuracy via search
    - Accessibility: DetGate + Gemini 3 Flash Lite — deterministic + fast fallback
    - Visual Clarity: Gemini 3 Flash + Embedding — visual similarity scoring

Cloud Region Selection:
    - us-central1: Primary region (lowest latency for Vertex AI)
    - europe-west1: GDPR-compliant fallback
    - Fallback chain: us-central1 → europe-west4 → europe-west1

PRD Reference: §6.3 (Pipeline nodes)
ADR Reference: 0007 (Gemini-only model strategy)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

#: AT-024 (§22 D5 / G13) — the single served Gemini model id. GA default
#: ``gemini-2.5-pro`` (operator-pinned 2026-05-31; confirmed GA in Vertex Model
#: Garden for atelier-build-2026/us-central1). Override per-env via GEMINI_MODEL_ID.
#: All 3.x-pro ids were preview at pin time, so the GA pro model is the default.
DEFAULT_GEMINI_MODEL_ID: Final[str] = "gemini-2.5-pro"


def resolve_model_id() -> str:
    """Return the pinned served Gemini model id: ``GEMINI_MODEL_ID`` env or the GA default."""
    return os.environ.get("GEMINI_MODEL_ID", DEFAULT_GEMINI_MODEL_ID)


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
# Model Registry — D-O-R-A-V Judge Routing
# ---------------------------------------------------------------------------

# Design (Brand Alignment) — needs visual understanding to assess design quality
JUDGE_MODEL_DESIGN = ModelSpec(
    model_id=resolve_model_id(),
    display_name="Design Judge (Flash Vision)",
    tier=ModelTier.FLASH,
    capabilities=frozenset({ModelCapability.VISION}),
    max_output_tokens=4096,
    temperature=0.3,
)

# Originality — needs deep reasoning to assess creative novelty
JUDGE_MODEL_ORIGINALITY = ModelSpec(
    model_id=resolve_model_id(),
    display_name="Originality Judge (Pro Thinking)",
    tier=ModelTier.PRO,
    capabilities=frozenset({ModelCapability.THINKING}),
    max_output_tokens=4096,
    temperature=0.5,
    thinking_budget=8192,
)

# Relevance — needs search grounding to verify factual accuracy
JUDGE_MODEL_RELEVANCE = ModelSpec(
    model_id=resolve_model_id(),
    display_name="Relevance Judge (Flash + Grounding)",
    tier=ModelTier.FLASH,
    capabilities=frozenset({ModelCapability.GROUNDING}),
    max_output_tokens=4096,
    temperature=0.2,
)

# Accessibility — primarily deterministic gates; LLM fallback for edge cases
JUDGE_MODEL_ACCESSIBILITY = ModelSpec(
    model_id=resolve_model_id(),
    display_name="Accessibility Judge (Flash Lite Fallback)",
    tier=ModelTier.FLASH_LITE,
    capabilities=frozenset(),
    max_output_tokens=2048,
    temperature=0.1,
)

# Visual Clarity — visual similarity scoring via embeddings
JUDGE_MODEL_VISUAL = ModelSpec(
    model_id=resolve_model_id(),
    display_name="Visual Clarity Judge (Flash + Embedding)",
    tier=ModelTier.FLASH,
    capabilities=frozenset({ModelCapability.VISION, ModelCapability.EMBEDDING}),
    max_output_tokens=4096,
    temperature=0.3,
)

# Generator — primary generation model (high creativity, vision for reference images)
GENERATOR_MODEL = ModelSpec(
    model_id=resolve_model_id(),
    display_name="UI Generator (Flash)",
    tier=ModelTier.FLASH,
    capabilities=frozenset({ModelCapability.VISION, ModelCapability.CODE}),
    max_output_tokens=32768,
    temperature=0.8,
)

# Copy Editor — prose quality, grammar, tone
COPY_EDITOR_MODEL = ModelSpec(
    model_id=resolve_model_id(),
    display_name="Copy Editor (Flash)",
    tier=ModelTier.FLASH,
    capabilities=frozenset(),
    max_output_tokens=8192,
    temperature=0.4,
)

# Fixer — targeted code fixes based on gate/judge feedback
FIXER_MODEL = ModelSpec(
    model_id=resolve_model_id(),
    display_name="Fixer (Flash Code)",
    tier=ModelTier.FLASH,
    capabilities=frozenset({ModelCapability.CODE}),
    max_output_tokens=32768,
    temperature=0.3,
)


# ---------------------------------------------------------------------------
# Convenience lookup — used by ConsensusAgent and Orchestrator
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

# All unique model IDs for verification
ALL_MODEL_IDS: frozenset[str] = frozenset(
    spec.model_id
    for spec in [
        *JUDGE_MODEL_CONFIG.values(),
        *NODE_MODEL_CONFIG.values(),
    ]
)

# All regions that need Vertex AI API enabled
ALL_REGIONS: frozenset[str] = frozenset(
    region
    for spec in [*JUDGE_MODEL_CONFIG.values(), *NODE_MODEL_CONFIG.values()]
    for region in (spec.region, *spec.fallback_regions)
)
