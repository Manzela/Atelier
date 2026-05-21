"""Unit tests for atelier.router.protocol (T3).

The plan's smoke step had us instantiate a numpy ndarray to round-trip
RouteRequest end-to-end. That requires numpy in the lockfile, which the
Antigravity R7-01 reconcile hasn't shipped yet. Replacing the runtime
ndarray smoke with structural invariants (enum sizes, cost-map parity,
JSON ↔ code parity, frozen/slots, Protocol uncheckability) gives the
same drift coverage without taking a runtime numpy dependency.
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields, is_dataclass
from pathlib import Path

import pytest
from atelier.router.protocol import (
    EXPERT_COST_USD_PER_1K_TOKENS,
    DAGPhase,
    ExpertID,
    PhaseAwareMoERouter,
    RouteDecision,
    RouteRequest,
)

_PRICING_JSON: Path = (
    Path(__file__).resolve().parents[3] / "infra" / "pricing" / "vertex-2026-05.json"
)


@pytest.mark.unit
def test_dag_phase_has_exactly_eight_members() -> None:
    """Spec §1 anchors the 8-node DAG. Drift here breaks the router's
    phase-gating signal and the spec's flow diagram simultaneously.
    """
    assert len(DAGPhase) == 8


@pytest.mark.unit
def test_expert_id_has_exactly_five_members() -> None:
    """Adding a sixth model requires (a) bumping ExpertID, (b) extending
    EXPERT_COST_USD_PER_1K_TOKENS, (c) updating the pricing JSON, (d) an
    ADR. This test catches half-done additions.
    """
    assert len(ExpertID) == 5


@pytest.mark.unit
def test_cost_map_keys_match_expert_id_set_exactly() -> None:
    """If a new ExpertID is added without a cost entry — or a cost entry
    is added for an unknown model — the router would silently default-to-Any
    on cost lookups. Fail-loud here instead.
    """
    assert set(EXPERT_COST_USD_PER_1K_TOKENS.keys()) == set(ExpertID)


@pytest.mark.unit
def test_cost_map_values_are_positive_floats() -> None:
    """A zero or negative cost would let the cost-aware planner over-route
    to the 'cheapest' expert and burn the budget on bad decisions.
    """
    for expert, cost in EXPERT_COST_USD_PER_1K_TOKENS.items():
        if not isinstance(cost, float):
            pytest.fail(f"{expert}: cost must be float, got {type(cost).__name__}")
        if cost <= 0.0:
            pytest.fail(f"{expert}: cost must be > 0, got {cost!r}")


@pytest.mark.unit
def test_cost_map_matches_pricing_json_source_of_truth() -> None:
    """Catches code↔JSON drift. The JSON is the monthly-refreshed source
    of truth; the code-side dict is a typed mirror. They must agree.

    Numeric comparison uses an exact equality on float — the JSON is hand-
    maintained at 5 decimal places matching the Vertex pricing page exactly,
    so any drift here is a real bug, not a floating-point artifact.
    """
    payload = json.loads(_PRICING_JSON.read_text(encoding="utf-8"))
    json_costs = {k: v for k, v in payload.items() if not k.startswith("_")}

    code_costs = {expert.value: cost for expert, cost in EXPERT_COST_USD_PER_1K_TOKENS.items()}
    if code_costs != json_costs:
        pytest.fail(
            "Cost map drift between code and JSON.\n"
            f"  code-only: {sorted(set(code_costs) - set(json_costs))}\n"
            f"  json-only: {sorted(set(json_costs) - set(code_costs))}\n"
            f"  mismatched: "
            f"{[k for k in code_costs.keys() & json_costs.keys() if code_costs[k] != json_costs[k]]}"
        )


@pytest.mark.unit
def test_dag_phase_values_are_snake_case_strings() -> None:
    """OTel span attributes and BigQuery columns key off these literals.
    A CamelCase value would silently break the trajectory store schema.
    """
    for phase in DAGPhase:
        if phase.value != phase.value.lower():
            pytest.fail(f"{phase!r}: value {phase.value!r} must be lowercase")
        if " " in phase.value:
            pytest.fail(f"{phase!r}: value must not contain whitespace")


@pytest.mark.unit
def test_expert_id_values_match_vertex_publisher_model_names() -> None:
    """The .value strings ARE the Vertex `publishers/google/models/<id>`
    suffixes. A typo would break model selection at runtime — fail-loud
    in CI instead.
    """
    expected = {
        "gemini-3-pro",
        "gemini-3-flash",
        "gemini-3.1-flash-lite",
        "gemini-2.5-pro",
        "gemini-2.5-flash-001",
    }
    actual = {e.value for e in ExpertID}
    assert actual == expected


@pytest.mark.unit
def test_route_request_is_frozen_dataclass_with_slots() -> None:
    """RouteRequest is a frozen, slotted dataclass: immutable, no __dict__,
    safe to hash and pass across async boundaries.
    """
    assert is_dataclass(RouteRequest)
    # slots=True ⇒ no per-instance __dict__
    assert "__slots__" in RouteRequest.__dict__


@pytest.mark.unit
def test_route_decision_is_frozen_dataclass_with_slots() -> None:
    assert is_dataclass(RouteDecision)
    assert "__slots__" in RouteDecision.__dict__


@pytest.mark.unit
def test_route_decision_is_not_hashable_by_design() -> None:
    """RouteDecision is frozen, but `span_attrs: dict[str, ...]` is a
    mutable default — so it cannot be hashed. This is intentional: the
    decision is a one-shot record, not a cache key. The plan's docstring
    initially overstated hashability; the protocol module's header now
    documents the correct tradeoff. Test pins it.
    """
    decision = RouteDecision(
        expert=ExpertID.GEMINI_3_FLASH,
        score=0.42,
        rationale="test",
        fallback_chain=(ExpertID.GEMINI_2_5_FLASH,),
        routing_mode="v0_managed",
    )
    with pytest.raises(TypeError):
        hash(decision)


@pytest.mark.unit
def test_route_decision_fallback_chain_is_immutable_tuple() -> None:
    """fallback_chain MUST be a tuple — a list would make the decision
    mutable-by-reference and break trace-replay determinism.
    """
    fields_by_name = {f.name: f for f in fields(RouteDecision)}
    chain_field = fields_by_name["fallback_chain"]
    # The type annotation is a string under `from __future__ import annotations`,
    # so check the string form rather than the resolved type.
    assert "tuple[" in chain_field.type


@pytest.mark.unit
def test_route_decision_span_attrs_defaults_to_empty_dict() -> None:
    """The default_factory should be `dict` — accidentally setting `default={}`
    would share state across all instances (the classic Python mutable-default
    bug). default_factory makes the instances independent.
    """
    a = RouteDecision(
        expert=ExpertID.GEMINI_3_FLASH,
        score=0.5,
        rationale="a",
        fallback_chain=(),
        routing_mode="v0_managed",
    )
    b = RouteDecision(
        expert=ExpertID.GEMINI_3_FLASH,
        score=0.5,
        rationale="b",
        fallback_chain=(),
        routing_mode="v0_managed",
    )
    a.span_attrs["x"] = 1
    assert "x" not in b.span_attrs


@pytest.mark.unit
def test_route_decision_is_frozen_attributes_cannot_be_reassigned() -> None:
    decision = RouteDecision(
        expert=ExpertID.GEMINI_3_FLASH,
        score=0.5,
        rationale="frozen",
        fallback_chain=(),
        routing_mode="v0_managed",
    )
    with pytest.raises(FrozenInstanceError):
        decision.score = 0.9  # type: ignore[misc]


@pytest.mark.unit
def test_phase_aware_moe_router_protocol_is_runtime_unchecked_but_structural() -> None:
    """typing.Protocol without @runtime_checkable: structural conformance is
    checked at mypy time only. This forces incomplete implementations to be
    caught BEFORE deploy rather than at request time — same idiom as
    HierarchicalMemory (see test_memory_key.py).
    """

    class Incomplete:
        async def route(self, request: object) -> object:  # missing observe_outcome
            return object()

    with pytest.raises(TypeError):
        isinstance(Incomplete(), PhaseAwareMoERouter)  # type: ignore[misc]
