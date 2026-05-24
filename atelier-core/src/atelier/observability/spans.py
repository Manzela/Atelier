"""OTel span attribute schema — 15 mandatory attributes per PRD §7.3.

Every span emitted by Atelier MUST include these attributes for:
    - Cloud Trace searchability and filtering
    - Phoenix dev-mode visual inspection
    - Calibration dashboard correlation
    - Cost tracking and budget enforcement

Attribute naming follows OpenTelemetry GenAI semantic conventions:
    - ``gen_ai.*`` — standard GenAI attributes (model, provider, tokens)
    - ``atelier.*`` — Atelier-specific attributes (tenant, surface, judge)

Usage:
    from atelier.observability.spans import set_atelier_span_attrs

    with tracer.start_as_current_span("generate_ui") as span:
        set_atelier_span_attrs(span, tenant_id="tnt_1", ...)

PRD Reference: §7.3 (span attribute schema)
Audit Reference: §3 (C10, FA-007)
ADR Reference: 0006 (Google-native observability stack)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opentelemetry.trace import Span


# ---------------------------------------------------------------------------
# Canonical attribute keys — PRD §7.3 (15 mandatory + 5 recommended)
# ---------------------------------------------------------------------------

# --- Identity attributes (4) ---
ATTR_TENANT_ID = "atelier.tenant_id"
ATTR_USER_ID = "atelier.user_id"
ATTR_PROJECT_ID = "atelier.project_id"
ATTR_SESSION_ID = "atelier.session_id"

# --- Pipeline attributes (5) ---
ATTR_NODE_NAME = "atelier.node_name"
ATTR_SURFACE_ID = "atelier.surface_id"
ATTR_ITERATION = "atelier.iteration"
ATTR_CANDIDATE_ID = "atelier.candidate_id"
ATTR_CAMPAIGN_ID = "atelier.campaign_id"

# --- GenAI attributes (4, per OTel GenAI semconv) ---
ATTR_GEN_AI_SYSTEM = "gen_ai.system"
ATTR_GEN_AI_MODEL = "gen_ai.request.model"
ATTR_GEN_AI_TOKENS_INPUT = "gen_ai.usage.input_tokens"
ATTR_GEN_AI_TOKENS_OUTPUT = "gen_ai.usage.output_tokens"

# --- Quality attributes (2) ---
ATTR_JUDGE_AXIS = "atelier.judge_axis"
ATTR_COMPOSITE_SCORE = "atelier.composite_score"

# --- Recommended attributes (5, optional) ---
ATTR_COST_USD = "atelier.cost_usd"
ATTR_GATE_AXIS = "atelier.gate_axis"
ATTR_GATE_DECISION = "atelier.gate_decision"
ATTR_MUTATION_OP = "atelier.mutation_op"
ATTR_CONVERGENCE_BAR = "atelier.convergence_bar"


# ---------------------------------------------------------------------------
# All mandatory attribute keys (for validation)
# ---------------------------------------------------------------------------

MANDATORY_ATTRS: frozenset[str] = frozenset(
    {
        ATTR_TENANT_ID,
        ATTR_USER_ID,
        ATTR_PROJECT_ID,
        ATTR_SESSION_ID,
        ATTR_NODE_NAME,
        ATTR_SURFACE_ID,
        ATTR_ITERATION,
        ATTR_CANDIDATE_ID,
        ATTR_CAMPAIGN_ID,
        ATTR_GEN_AI_SYSTEM,
        ATTR_GEN_AI_MODEL,
        ATTR_GEN_AI_TOKENS_INPUT,
        ATTR_GEN_AI_TOKENS_OUTPUT,
        ATTR_JUDGE_AXIS,
        ATTR_COMPOSITE_SCORE,
    }
)


def set_atelier_span_attrs(
    span: Span,
    *,
    tenant_id: str = "",
    user_id: str = "",
    project_id: str = "",
    session_id: str = "",
    node_name: str = "",
    surface_id: str = "",
    iteration: int = 0,
    candidate_id: str = "",
    campaign_id: str = "",
    model: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    judge_axis: str = "",
    composite_score: float = 0.0,
    cost_usd: float | None = None,
    gate_axis: str | None = None,
    gate_decision: str | None = None,
    mutation_op: str | None = None,
    convergence_bar: str | None = None,
) -> None:
    """Set all 15 mandatory Atelier span attributes on an OTel span.

    This function is the ONLY way to set Atelier attributes on a span.
    It ensures all 15 mandatory attributes are present, even if empty.

    Args:
        span: The OTel span to annotate.
        tenant_id: Multi-tenant partition key.
        user_id: Authenticated user ID.
        project_id: Project-scoped partition key.
        session_id: Agent session ID.
        node_name: Which DAG node is executing (e.g., ``"n3a_generator"``).
        surface_id: Which surface is being worked on.
        iteration: Current iteration within the surface.
        candidate_id: Current candidate ID.
        campaign_id: Campaign ID (empty for atomic requests).
        model: Vertex AI model ID.
        input_tokens: Number of input tokens consumed.
        output_tokens: Number of output tokens generated.
        judge_axis: D-O-R-A-V axis (empty for non-judge spans).
        composite_score: Composite quality score (0.0 for non-scored spans).
        cost_usd: Optional cost in USD for this span.
        gate_axis: Optional deterministic gate axis.
        gate_decision: Optional gate decision (pass/reject/defer).
        mutation_op: Optional mutation operator applied.
        convergence_bar: Optional convergence bar from BriefSpec.
    """
    # --- Mandatory (15) ---
    span.set_attribute(ATTR_TENANT_ID, tenant_id)
    span.set_attribute(ATTR_USER_ID, user_id)
    span.set_attribute(ATTR_PROJECT_ID, project_id)
    span.set_attribute(ATTR_SESSION_ID, session_id)
    span.set_attribute(ATTR_NODE_NAME, node_name)
    span.set_attribute(ATTR_SURFACE_ID, surface_id)
    span.set_attribute(ATTR_ITERATION, iteration)
    span.set_attribute(ATTR_CANDIDATE_ID, candidate_id)
    span.set_attribute(ATTR_CAMPAIGN_ID, campaign_id)
    span.set_attribute(ATTR_GEN_AI_SYSTEM, "atelier")
    span.set_attribute(ATTR_GEN_AI_MODEL, model)
    span.set_attribute(ATTR_GEN_AI_TOKENS_INPUT, input_tokens)
    span.set_attribute(ATTR_GEN_AI_TOKENS_OUTPUT, output_tokens)
    span.set_attribute(ATTR_JUDGE_AXIS, judge_axis)
    span.set_attribute(ATTR_COMPOSITE_SCORE, composite_score)

    # --- Recommended (optional, only set if provided) ---
    if cost_usd is not None:
        span.set_attribute(ATTR_COST_USD, cost_usd)
    if gate_axis is not None:
        span.set_attribute(ATTR_GATE_AXIS, gate_axis)
    if gate_decision is not None:
        span.set_attribute(ATTR_GATE_DECISION, gate_decision)
    if mutation_op is not None:
        span.set_attribute(ATTR_MUTATION_OP, mutation_op)
    if convergence_bar is not None:
        span.set_attribute(ATTR_CONVERGENCE_BAR, convergence_bar)


def validate_span_attrs(attrs: dict[str, Any]) -> list[str]:
    """Validate that a dict of span attributes contains all 15 mandatory keys.

    Args:
        attrs: Dictionary of attribute key→value pairs.

    Returns:
        List of missing mandatory attribute keys (empty if all present).
    """
    return sorted(MANDATORY_ATTRS - set(attrs.keys()))
