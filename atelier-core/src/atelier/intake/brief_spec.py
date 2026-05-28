"""BriefSpec — immutable JSON contract produced by PIP, frozen at user approval.

Per ADR 0004 (Pre-Generation Intake Protocol):
    This is the contract Atelier commits to for the duration of the project.
    Spec changes require an explicit ``atelier amend`` command + re-approval;
    no silent drift.

Per architectural invariants invariants:
    - ``ConfigDict(frozen=True, extra='forbid')`` enforces immutability + schema strictness
    - ``schema_version: int = 1`` present on every model for forward-compatible evolution

Hierarchy:
    ``BriefSpec``
    ├── ``IntakeAnswer[]`` — PIP conversation transcript
    ├── ``CampaignScope?`` — Multi-surface campaign parameters (None for atomic)
    └── Scalar fields (intent, visual_register, stack, compliance, convergence, etc.)

See Also:
    - PRD §9 (BriefSpec schema definition)
    - ADR 0004 (Pre-Generation Intake Protocol)
    - ADR 0012 (Anchor Discipline — BriefSpec in every subagent prefix)
    - ``atelier.data_contracts`` for downstream models (SurfaceManifest, JudgeVote, etc.)
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Enums — exhaustive, string-valued for JSON serialization
# ---------------------------------------------------------------------------


class VisualRegister(StrEnum):
    """Visual style register that governs CSC-D constitution selection (N6).

    Each register maps to a different judge weighting profile via N15 MJG
    (axis_weights_heuristic.yaml). See ADR 0013.
    """

    EDITORIAL = "editorial"
    DENSE_DATA = "dense-data"
    PLAYFUL = "playful"
    BRUTALIST = "brutalist"
    CORPORATE = "corporate"
    CUSTOM = "custom"


class StackChoice(StrEnum):
    """Technology stack for generated output.

    ``INFER_FROM_PATH`` triggers N4 PADI (Project-Agnostic Descriptor Inference)
    to auto-detect the stack from the project's file structure.
    """

    VANILLA_HTML = "vanilla-html"
    REACT_TAILWIND = "react-tailwind"
    NEXTJS_TAILWIND = "nextjs-tailwind"
    VUE = "vue"
    SVELTE = "svelte"
    ASTRO = "astro"
    SAGE_PHP = "sage-php"
    INFER_FROM_PATH = "infer"


class ComplianceLevel(StrEnum):
    """Accessibility and regulatory compliance tier.

    Drives deterministic gate thresholds in N3c:
    - ``NONE``: No accessibility enforcement
    - ``WCAG_AA``: WCAG 2.2 Level AA (Lighthouse ≥ 90)
    - ``WCAG_AAA``: WCAG 2.2 Level AAA (Lighthouse ≥ 95)
    - ``REGULATORY``: Full Pa11y + regulatory audit (e.g., Section 508, EN 301 549)
    """

    NONE = "none"
    WCAG_AA = "wcag-aa"
    WCAG_AAA = "wcag-aaa"
    REGULATORY = "regulatory"


class ConvergenceBar(StrEnum):
    """Quality threshold the agent must reach before declaring convergence.

    - ``SHIP_IT``: ≥ 85% composite score across all D-O-R-A-V axes
    - ``PRODUCTION``: ≥ 95% — default for paying customers
    - ``PERFECTIONIST``: 100% — may not converge; useful for benchmarks
    """

    SHIP_IT = "ship-it"
    PRODUCTION = "production"
    PERFECTIONIST = "perfectionist"


# ---------------------------------------------------------------------------
# Sub-models — frozen, schema-versioned
# ---------------------------------------------------------------------------


class IntakeAnswer(BaseModel):
    """A single Q&A exchange from the PIP conversation.

    Attributes:
        question_id: Stable identifier (e.g., ``"q_intent"``, ``"q_stack"``).
        answer_text: User's natural-language response.
        answer_value: Structured value extracted by the intent classifier (optional).
        visual_option_selected: If the question offered visual swatches, the chosen one.
        schema_version: Forward-compat version marker.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str
    answer_text: str
    answer_value: Any | None = None
    visual_option_selected: str | None = None
    schema_version: int = 1


class CampaignScope(BaseModel):
    """Parameters for multi-surface campaign orchestration (N12 RLRD).

    Only present when the user requests a campaign (12+ surfaces).
    Atomic (single-surface) requests set ``BriefSpec.campaign_scope = None``.

    Attributes:
        surface_count_estimate: Expected number of surfaces (pages/sections).
        timeline: Urgency signal — one of ``today | this-week | multi-week | no-rush``.
        budget_per_session_usd: Max spend per individual surface generation session.
        budget_per_campaign_usd: Max total spend across the entire campaign.
        failure_policy: What to do when a surface fails to converge —
            ``skip`` | ``ask-help`` | ``best-effort-and-flag``.
        schema_version: Forward-compat version marker.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_count_estimate: int = Field(ge=1, description="Expected number of surfaces")
    timeline: str = Field(description="Urgency: today | this-week | multi-week | no-rush")
    budget_per_session_usd: float = Field(ge=0.0, description="Max USD per session")
    budget_per_campaign_usd: float = Field(ge=0.0, description="Max USD for entire campaign")
    failure_policy: str = Field(
        description="skip | ask-help | best-effort-and-flag",
    )
    schema_version: int = 1


# ---------------------------------------------------------------------------
# BriefSpec — the root contract
# ---------------------------------------------------------------------------


class BriefSpec(BaseModel):
    """Immutable specification the agent commits to for the entire project.

    Produced by the PIP (Pre-Generation Intake Protocol) layer and frozen at
    user approval. Every downstream node in the 8-node DAG receives a copy of
    this spec in its cached prefix (ADR 0012 Anchor Discipline).

    Lifecycle:
        1. PIP conversation → draft BriefSpec
        2. WRAI augmentation (N14) → enriched BriefSpec
        3. User reviews + approves → BriefSpec locked (``approved_at`` set)
        4. Agent executes against locked spec
        5. Amendments require explicit ``atelier amend`` + re-approval

    Attributes:
        spec_id: Globally unique identifier (UUID4).
        tenant_id: Multi-tenant partition key.
        project_id: Project-scoped partition key.
        intent: The ONE thing this design should make easier.
        visual_register: Style register governing constitution selection.
        stack: Technology stack for output.
        design_system_source: Path to DESIGN.md or ``"infer"`` for PADI.
        compliance_level: Accessibility/regulatory tier.
        convergence_bar: Quality threshold for convergence declaration.
        reference_artifacts: List of file paths or URLs provided as reference.
        campaign_scope: Multi-surface parameters (None for atomic requests).
        intake_transcript: Full PIP conversation history.
        schema_version: Forward-compat version marker (always ``1`` for v1).
        approved_at: UTC timestamp of user approval.
        approved_by_user_id: Identity Platform user ID who approved.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # --- Identity ---
    spec_id: UUID = Field(description="Globally unique BriefSpec identifier (UUID4)")
    tenant_id: str = Field(description="Multi-tenant partition key")
    project_id: str = Field(description="Project-scoped partition key")

    # --- Design Intent ---
    intent: str = Field(
        description="The ONE thing this design should make easier",
        min_length=1,
    )
    visual_register: VisualRegister
    stack: StackChoice
    design_system_source: str | None = Field(
        default=None,
        description="Path to DESIGN.md or 'infer' for PADI auto-detection",
    )

    # --- Quality Parameters ---
    compliance_level: ComplianceLevel
    convergence_bar: ConvergenceBar

    # --- Context ---
    reference_artifacts: list[str] = Field(
        default_factory=list,
        description="File paths or URLs provided as design reference",
    )
    campaign_scope: CampaignScope | None = Field(
        default=None,
        description="Multi-surface campaign params; None for atomic requests",
    )
    intake_transcript: list[IntakeAnswer] = Field(
        default_factory=list,
        description="Full PIP conversation history",
    )

    # --- Metadata ---
    schema_version: int = Field(default=1, description="Schema version for forward compat")
    approved_at: datetime = Field(description="UTC timestamp of user approval")
    approved_by_user_id: str = Field(description="Identity Platform user ID who approved")
