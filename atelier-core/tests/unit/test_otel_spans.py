from __future__ import annotations

from atelier.observability.spans import ATELIER_SPAN_ATTRS, make_span_attrs


def test_all_15_mandatory_keys_present() -> None:
    assert len(ATELIER_SPAN_ATTRS) == 15


def test_make_span_attrs_override_merges() -> None:
    overrides = make_span_attrs(**{"gen_ai.system": "custom", "atelier.node_name": "N1"})
    assert overrides["gen_ai.system"] == "custom"
    assert overrides["atelier.node_name"] == "N1"
    # Ensure original is not mutated
    assert ATELIER_SPAN_ATTRS["gen_ai.system"] == "atelier"
    assert ATELIER_SPAN_ATTRS["atelier.node_name"] == ""


def test_gen_ai_system_is_atelier() -> None:
    assert ATELIER_SPAN_ATTRS["gen_ai.system"] == "atelier"
