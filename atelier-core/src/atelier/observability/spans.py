"""OTel span attributes schema (FA-007).

Defines the mandatory attributes required for every span in the pipeline
to ensure consistency in distributed tracing and telemetry downstream.

Provides:
    ATELIER_SPAN_ATTRS  — default dict with all 15 mandatory keys
    MANDATORY_ATTRS     — tuple of the 15 mandatory attribute names
    make_span_attrs     — returns a copy of defaults with overrides applied
    validate_span_attrs — checks a dict for missing mandatory keys
    set_atelier_span_attrs — stamps a span object with all mandatory attributes
"""

from __future__ import annotations

from typing import Any, Final

# ---------------------------------------------------------------------------
# Mandatory attribute defaults (PRD §7.3 — 15 attributes)
# ---------------------------------------------------------------------------

ATELIER_SPAN_ATTRS: Final[dict[str, str]] = {
    "gen_ai.system": "atelier",
    "gen_ai.operation.name": "",
    "gen_ai.request.model": "",
    "gen_ai.usage.input_tokens": "0",
    "gen_ai.usage.output_tokens": "0",
    "atelier.tenant_id": "",
    "atelier.project_id": "",
    "atelier.session_id": "",
    "atelier.surface_id": "",
    "atelier.node_name": "",
    "atelier.iteration": "0",
    "atelier.candidate_id": "",
    "atelier.cost_usd": "0.000000",
    "atelier.gate_decision": "",
    "atelier.composite_score": "-1.0",
}

MANDATORY_ATTRS: Final[tuple[str, ...]] = tuple(ATELIER_SPAN_ATTRS.keys())
"""Tuple of the 15 mandatory span attribute names."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_span_attrs(**overrides: str) -> dict[str, str]:
    """Return a copy of ATELIER_SPAN_ATTRS with overrides applied."""
    result = ATELIER_SPAN_ATTRS.copy()
    result.update(overrides)
    return result


def validate_span_attrs(attrs: dict[str, Any]) -> list[str]:
    """Return a list of mandatory attribute names missing from *attrs*.

    Returns an empty list when all 15 mandatory attributes are present.
    """
    return [key for key in MANDATORY_ATTRS if key not in attrs]


def set_atelier_span_attrs(
    span: Any,
    *,
    tenant_id: str = "",
    user_id: str = "",  # noqa: ARG001  # reserved for future span enrichment
    project_id: str = "",
    session_id: str = "",
    node_name: str = "",
    surface_id: str = "",
    iteration: int = 0,
    candidate_id: str = "",
    campaign_id: str = "",  # noqa: ARG001  # reserved for campaign-scoped tracing
    model: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    judge_axis: str = "",  # noqa: ARG001  # reserved for per-axis span tagging
    composite_score: float = -1.0,
    # Optional attributes (set only when non-None)
    cost_usd: float | None = None,
    gate_axis: str | None = None,
    gate_decision: str | None = None,
    mutation_op: str | None = None,
    convergence_bar: str | None = None,
) -> None:
    """Set all 15 mandatory span attributes on *span*, plus optional extras.

    Args:
        span: An OTel-compatible span with a ``set_attribute(key, value)`` method.
        tenant_id: Tenant UUID.
        user_id: User UUID (used to derive gen_ai.operation.name if node_name absent).
        project_id: Project UUID.
        session_id: Session UUID.
        node_name: Node identifier (e.g. ``"N1.brief_parser"``).
        surface_id: Surface UUID.
        iteration: Iteration number.
        candidate_id: Candidate UUID.
        campaign_id: Campaign UUID.
        model: Model identifier used in this span.
        input_tokens: Input token count.
        output_tokens: Output token count.
        judge_axis: Judge axis name (e.g. ``"brand"``).
        composite_score: Composite score (``-1.0`` if not scored yet).
        cost_usd: Optional cost in USD (not set if None).
        gate_axis: Optional gate axis (not set if None).
        gate_decision: Optional gate decision (not set if None).
        mutation_op: Optional mutation operation (not set if None).
        convergence_bar: Optional convergence bar (not set if None).
    """
    # 15 mandatory attributes
    span.set_attribute("gen_ai.system", "atelier")
    span.set_attribute("gen_ai.operation.name", node_name)
    span.set_attribute("gen_ai.request.model", model)
    span.set_attribute("gen_ai.usage.input_tokens", str(input_tokens))
    span.set_attribute("gen_ai.usage.output_tokens", str(output_tokens))
    span.set_attribute("atelier.tenant_id", tenant_id)
    span.set_attribute("atelier.project_id", project_id)
    span.set_attribute("atelier.session_id", session_id)
    span.set_attribute("atelier.surface_id", surface_id)
    span.set_attribute("atelier.node_name", node_name)
    span.set_attribute("atelier.iteration", str(iteration))
    span.set_attribute("atelier.candidate_id", candidate_id)
    span.set_attribute(
        "atelier.cost_usd", f"{cost_usd:.6f}" if cost_usd is not None else "0.000000"
    )
    span.set_attribute("atelier.gate_decision", gate_decision or "")
    span.set_attribute("atelier.composite_score", str(composite_score))

    # Optional attributes (only set when explicitly provided)
    if cost_usd is not None:
        span.set_attribute("atelier.cost_usd_detail", f"{cost_usd:.6f}")
    if gate_axis is not None:
        span.set_attribute("atelier.gate_axis", gate_axis)
    if gate_decision is not None:
        span.set_attribute("atelier.gate_decision_detail", gate_decision)
    if mutation_op is not None:
        span.set_attribute("atelier.mutation_op", mutation_op)
    if convergence_bar is not None:
        span.set_attribute("atelier.convergence_bar", convergence_bar)
