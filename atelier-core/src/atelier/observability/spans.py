"""OTel span attributes schema.

Defines the mandatory attributes required for every span in the pipeline
to ensure consistency in distributed tracing and telemetry downstream.
"""

from __future__ import annotations

from typing import Final

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


def make_span_attrs(**overrides: str) -> dict[str, str]:
    """Return a copy of ATELIER_SPAN_ATTRS with overrides applied."""
    result = ATELIER_SPAN_ATTRS.copy()
    result.update(overrides)
    return result
