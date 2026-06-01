"""Core data contracts for the Atelier 8-node DAG pipeline.

All models follow architectural invariants invariants:
    - ``ConfigDict(frozen=True, extra='forbid')``
    - ``schema_version: int = 1`` (never decreases, fields never dropped)
    - Pydantic v2 roundtrip: ``model_dump_json()`` ↔ ``model_validate_json()``

PRD Reference: §9 (Data contracts)
PRD Reference: §6.3 (Pipeline nodes)

Import Hierarchy:
    This module imports from ``atelier.models.enums`` only (no circular deps).
    ``BriefSpec`` lives in ``atelier.intake.brief_spec`` and is NOT imported here
    to avoid circular dependencies — downstream consumers import both modules.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from atelier.models.enums import (
    ConsensusDecision,
    GateAxis,
    GateDecision,
    JudgeAxis,
    MutationOp,
    SurfaceType,
    UserSignal,
)

# ---------------------------------------------------------------------------
# Tenant Context
# ---------------------------------------------------------------------------


class AtelierDescriptor(BaseModel):
    """Project-level descriptor inferred by N4 PADI.

    Contains stack detection results, design system tokens, and project metadata.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    framework: str = Field(description="Detected framework (e.g., 'react', 'vue', 'vanilla')")
    css_strategy: str = Field(
        description="CSS approach (e.g., 'tailwind', 'css-modules', 'vanilla')"
    )
    design_tokens_path: str | None = Field(
        default=None,
        description="Path to DESIGN.md or design tokens file if found",
    )
    package_manager: str | None = Field(default=None, description="npm | yarn | pnpm | bun")
    monorepo: bool = Field(default=False, description="Whether project is a monorepo")
    schema_version: int = 1


class TenantContext(BaseModel):
    """Per-request tenant context injected at the API boundary.

    Every agent invocation receives this as part of the session state.

    Usage governance is token-only (AT-095): there is no USD budget on the
    context — the sole cap is the per-user lifetime token cap, enforced
    server-side via :mod:`atelier.durability.usage_counter`.

    Attributes:
        tenant_id: Identity Platform tenant partition key.
        user_id: Authenticated user within the tenant.
        project_id: Project-scoped partition key.
        descriptor: PADI-inferred project descriptor (None until PIP completes).
        schema_version: Forward-compat version marker.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: str
    user_id: str
    project_id: str
    descriptor: AtelierDescriptor | None = None
    schema_version: int = 1


# ---------------------------------------------------------------------------
# Surface / Campaign Models
# ---------------------------------------------------------------------------


class SurfaceState(BaseModel):
    """State of a single design surface within a campaign.

    Tracks iteration progress, gate results, and human approval status.

    Attributes:
        surface_id: Unique identifier for this surface.
        name: Human-readable name (e.g., ``"homepage-hero"``).
        type: Surface type (page, component, template, screen).
        brief: Natural-language description of what this surface should accomplish.
        axes_required: Which deterministic gate axes must pass.
        passes: Whether the surface has converged to the convergence bar.
        iteration_count: Number of generate→judge→fix loops completed.
        human_approved: Explicit human approval (None = not yet reviewed).
        coherence_review_required: Whether cross-surface coherence check is needed.
        started_at: When generation began.
        completed_at: When convergence was declared.
        schema_version: Forward-compat version marker.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_id: UUID
    name: str = Field(min_length=1)
    type: SurfaceType
    brief: str = Field(min_length=1)
    axes_required: list[GateAxis] = Field(default_factory=list)
    passes: bool = False
    iteration_count: int = Field(default=0, ge=0)
    human_approved: bool | None = None
    coherence_review_required: bool = False
    started_at: datetime | None = None
    completed_at: datetime | None = None
    schema_version: int = 1


class SurfaceManifest(BaseModel):
    """Campaign-level manifest of all surfaces and their dependencies.

    The dependency graph enables topological ordering for generation
    (e.g., header component before page that includes it).

    Attributes:
        campaign_id: Unique campaign identifier.
        surfaces: All surfaces in the campaign.
        dependency_graph: ``surface_id → [depends_on_surface_ids]`` for ordering.
        schema_version: Forward-compat version marker.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    campaign_id: UUID
    surfaces: list[SurfaceState]
    dependency_graph: dict[str, list[str]] = Field(
        default_factory=dict,
        description="surface_id → [depends_on_surface_ids]",
    )
    schema_version: int = 1


# ---------------------------------------------------------------------------
# Candidate / Generation Models
# ---------------------------------------------------------------------------


class CandidateUI(BaseModel):
    """A single generated UI candidate from N3a Generator or N5 EvoDesign.

    Artifacts are stored as a dict of ``{filename: content}`` pairs,
    e.g., ``{"index.html": "<!DOCTYPE...", "main.css": "body {..."}}``.

    Attributes:
        candidate_id: Unique candidate identifier.
        surface_id: Which surface this candidate is for.
        iteration: Generation iteration number (0-indexed).
        parent_candidate_id: For crossover mutations — the parent.
        mutation_op: Which mutation operator was applied (None for initial gen).
        artifacts: File contents keyed by filename.
        a2ui_payload: A2UI-native render payload (None if not applicable).
        schema_version: Forward-compat version marker.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: UUID
    surface_id: UUID
    iteration: int = Field(ge=0)
    parent_candidate_id: UUID | None = None
    mutation_op: MutationOp | None = None
    artifacts: dict[str, str] = Field(description="{filename: content}")
    a2ui_payload: dict[str, object] | None = None
    schema_version: int = 1


# ---------------------------------------------------------------------------
# Gate / Judge / Consensus Models (N3c + N3d)
# ---------------------------------------------------------------------------


class GateOutcome(BaseModel):
    """Result of a single deterministic gate evaluation (N3c).

    Attributes:
        candidate_id: Which candidate was evaluated.
        axis: Which gate axis was tested.
        decision: PASS, REJECT, or DEFER.
        score: Numeric score (0-100 for Lighthouse; None for binary axes).
        diagnostic: Human-readable explanation of the gate result.
        schema_version: Forward-compat version marker.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: UUID
    axis: GateAxis
    decision: GateDecision
    score: float | None = Field(default=None, description="0-100 for Lighthouse; None for binary")
    diagnostic: str = Field(min_length=1)
    schema_version: int = 1


class JudgeVote(BaseModel):
    """A single judge's vote on a candidate (N3d ConsensusAgent).

    Each vote includes the judge's reasoning (CoT-before-score per audit §7)
    and provenance variables (DEMAS-D vars the judge was shown).

    Attributes:
        candidate_id: Which candidate was judged.
        judge_axis: Which D-O-R-A-V axis.
        score: Quality score (0.0 to 1.0).
        confidence_interval: Bayesian confidence interval (low, high).
        reasoning: Chain-of-thought reasoning (displayed on calibration dashboard).
        provenance_vars: Which DEMAS-D variables this judge was shown.
        judge_model: Model identifier (e.g., ``"gemini-3-flash"``).
        schema_version: Forward-compat version marker.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: UUID
    judge_axis: JudgeAxis
    score: float = Field(ge=0.0, le=1.0)
    confidence_interval: tuple[float, float] = Field(
        description="Bayesian CI (low, high)",
    )
    reasoning: str = Field(min_length=1, description="CoT reasoning before score")
    provenance_vars: list[str] = Field(
        default_factory=list,
        description="DEMAS-D variables shown to this judge",
    )
    judge_model: str = Field(
        description="Model used (e.g., 'gemini-3-flash' or 'atelier-judge-brand-v3-lora')",
    )
    schema_version: int = 1


class ConsensusResult(BaseModel):
    """Result of the ConsensusAgent (N3d) deliberation across all 5 judges.

    Attributes:
        selected_candidate_id: The winning candidate.
        composite_score: Weighted composite across D-O-R-A-V axes.
        per_axis_scores: Individual JudgeVote per axis.
        decision: CONVERGED, RETRY, or DEFER_HUMAN.
        schema_version: Forward-compat version marker.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    selected_candidate_id: UUID
    composite_score: float = Field(ge=0.0, le=1.0)
    per_axis_scores: dict[JudgeAxis, JudgeVote]
    decision: ConsensusDecision
    schema_version: int = 1


# ---------------------------------------------------------------------------
# Coherence Model (Cross-Surface Coherence Check)
# ---------------------------------------------------------------------------


class CoherenceVerdict(BaseModel):
    """Cross-surface coherence verification result.

    Ensures design tokens, patterns, and decisions are consistent
    across all surfaces in a campaign.

    Attributes:
        surface_id: Which surface was checked.
        token_use_valid: Whether design tokens are used correctly.
        pattern_reuse_rate: Fraction of patterns reused from prior surfaces.
        decisions_md_compliant: Whether output complies with DECISIONS.md.
        regression_check_passed: Whether no regressions from previous iterations.
        violations: List of specific violations found.
        schema_version: Forward-compat version marker.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    surface_id: UUID
    token_use_valid: bool
    pattern_reuse_rate: float = Field(ge=0.0, le=1.0)
    decisions_md_compliant: bool
    regression_check_passed: bool
    violations: list[str] = Field(default_factory=list)
    schema_version: int = 1


# ---------------------------------------------------------------------------
# Trajectory Record (N3h + DPO Flywheel)
# ---------------------------------------------------------------------------


class TrajectoryRecord(BaseModel):
    """Full trajectory record persisted to BigQuery for DPO preference extraction.

    Partitioned by ``DATE(ts)``, clustered by ``tenant_id``.
    This is the data source for ``prepare_dpo_dataset.py`` (audit §5).

    Flywheel tiers (PRD §6.6):
        T1 (production-baseline): All sessions → recorded automatically
        T2 (quality-approved): composite_score ≥ 0.7 AND all det gates pass → "chosen"
        T3 (failure-cases): composite_score < 0.5 OR any det gate fails → "rejected"

    Attributes:
        trajectory_id: Unique trajectory record identifier.
        tenant_id: Tenant partition key.
        project_id: Project partition key.
        campaign_id: Campaign identifier (None for atomic requests).
        surface_id: Which surface this record is for.
        session_id: Agent session identifier.
        ts: UTC timestamp of this record.
        node_name: Which DAG node produced this record.
        iteration: Iteration number within the surface.
        candidates: All candidates generated in this iteration.
        gate_outcomes: Deterministic gate results.
        judge_votes: Judge votes from ConsensusAgent.
        consensus: Consensus result (None if not yet reached).
        coherence: Coherence verdict (None if not checked).
        user_signal: Explicit user accept/reject signal.
        encryption_key_id: KMS key for GDPR right-to-be-forgotten.
        schema_version: Forward-compat version marker.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    trajectory_id: UUID
    tenant_id: str
    project_id: str
    campaign_id: UUID | None = None
    surface_id: UUID
    session_id: str
    ts: datetime
    node_name: str
    iteration: int = Field(ge=0)
    candidates: list[CandidateUI] = Field(default_factory=list)
    gate_outcomes: list[GateOutcome] = Field(default_factory=list)
    judge_votes: list[JudgeVote] = Field(default_factory=list)
    consensus: ConsensusResult | None = None
    coherence: CoherenceVerdict | None = None
    user_signal: UserSignal | None = None
    encryption_key_id: str = Field(
        description="KMS key per subject — revoke for GDPR right-to-be-forgotten",
    )
    schema_version: int = 1
