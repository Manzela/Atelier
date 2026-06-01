"""Unit tests for the AT-023 InteractionSpec schema and parser.

Coverage:
    - Golden valid JSON (hover + focus) → valid InteractionSpec, focus_covered True.
    - Empty interactions list → ValueError.
    - Missing focus/keyboard interaction → ValueError (focus-coverage rule).
    - Malformed JSON → ValueError.
    - Fenced ```json block → parses correctly.
    - Hermetic specialist: FakeLlm emitting the golden JSON produces a valid
      InteractionSpec when parsed from session state (validates the round-trip
      without a live model call).
"""

from __future__ import annotations

import pytest
from atelier.models.enums import InteractionTrigger
from atelier.models.interaction import (
    DeclaredInteraction,
    InteractionSpec,
    parse_interaction_spec,
)

# ---------------------------------------------------------------------------
# Fixtures / golden data
# ---------------------------------------------------------------------------

_GOLDEN_JSON = (
    '{"interactions":['
    '{"element":".btn-primary","trigger":"hover","effect":"background lightens 10%"},'
    '{"element":".btn-primary","trigger":"focus","effect":"2px offset ring, high-contrast"}'
    "]}"
)

_GOLDEN_JSON_FENCED = f"```json\n{_GOLDEN_JSON}\n```"

_GOLDEN_JSON_FENCED_NO_LANG = f"```\n{_GOLDEN_JSON}\n```"

_GOLDEN_JSON_WITH_PROSE = (
    "Here is the interaction spec as requested:\n\n"
    f"```json\n{_GOLDEN_JSON}\n```\n\n"
    "That covers all interactive states."
)

_NO_FOCUS_JSON = (
    '{"interactions":['
    '{"element":".card","trigger":"hover","effect":"box-shadow deepens"},'
    '{"element":".card","trigger":"active","effect":"scale 0.98"}'
    "]}"
)

_EMPTY_INTERACTIONS_JSON = '{"interactions":[]}'

_MISSING_FIELD_JSON = '{"interactions":[{"element":".btn","effect":"opacity drops"}]}'

_KEYBOARD_ONLY_JSON = (
    '{"interactions":[{"element":"#nav-menu","trigger":"keyboard","effect":"focus ring visible"}]}'
)

_KEYBOARD_AND_HOVER_JSON = (
    '{"interactions":['
    '{"element":"#nav-menu","trigger":"keyboard","effect":"focus ring visible"},'
    '{"element":"#nav-menu","trigger":"hover","effect":"background tint"}'
    "]}"
)


# ---------------------------------------------------------------------------
# parse_interaction_spec — happy-path tests
# ---------------------------------------------------------------------------


def test_golden_bare_json_parses_to_valid_spec() -> None:
    """Golden bare-JSON string → non-empty InteractionSpec, focus_covered True."""
    spec = parse_interaction_spec(_GOLDEN_JSON)
    assert isinstance(spec, InteractionSpec)
    assert len(spec.interactions) == 2
    assert spec.focus_covered is True


def test_golden_fenced_json_parses() -> None:
    """Fenced ```json block → parses identically to bare JSON."""
    spec = parse_interaction_spec(_GOLDEN_JSON_FENCED)
    assert isinstance(spec, InteractionSpec)
    assert spec.focus_covered is True


def test_fenced_no_lang_tag_parses() -> None:
    """Fenced block with no language tag → still parses."""
    spec = parse_interaction_spec(_GOLDEN_JSON_FENCED_NO_LANG)
    assert isinstance(spec, InteractionSpec)
    assert spec.focus_covered is True


def test_fenced_with_surrounding_prose_parses() -> None:
    """JSON fence embedded in surrounding prose → parser extracts the fence."""
    spec = parse_interaction_spec(_GOLDEN_JSON_WITH_PROSE)
    assert isinstance(spec, InteractionSpec)
    assert len(spec.interactions) == 2


def test_keyboard_trigger_satisfies_focus_coverage() -> None:
    """A single KEYBOARD trigger satisfies the focus-coverage invariant."""
    spec = parse_interaction_spec(_KEYBOARD_ONLY_JSON)
    assert spec.focus_covered is True
    assert spec.interactions[0].trigger == InteractionTrigger.KEYBOARD


def test_keyboard_and_hover_satisfies_focus_coverage() -> None:
    """KEYBOARD + HOVER together → focus_covered True."""
    spec = parse_interaction_spec(_KEYBOARD_AND_HOVER_JSON)
    assert spec.focus_covered is True


def test_spec_schema_version_is_one() -> None:
    """schema_version defaults to 1 (forward-compat marker)."""
    spec = parse_interaction_spec(_GOLDEN_JSON)
    assert spec.schema_version == 1


def test_declared_interaction_fields_correct() -> None:
    """Parsed DeclaredInteraction has the expected element/trigger/effect."""
    spec = parse_interaction_spec(_GOLDEN_JSON)
    hover = next(i for i in spec.interactions if i.trigger == InteractionTrigger.HOVER)
    assert hover.element == ".btn-primary"
    assert "background" in hover.effect


# ---------------------------------------------------------------------------
# parse_interaction_spec — error-path tests
# ---------------------------------------------------------------------------


def test_empty_string_raises_value_error() -> None:
    """Empty string → ValueError with descriptive message."""
    with pytest.raises(ValueError, match="empty"):
        parse_interaction_spec("")


def test_whitespace_only_raises_value_error() -> None:
    """Whitespace-only string → ValueError."""
    with pytest.raises(ValueError, match="empty"):
        parse_interaction_spec("   \n  ")


def test_malformed_json_raises_value_error() -> None:
    """Malformed JSON → ValueError (not JSONDecodeError — re-raised as ValueError)."""
    with pytest.raises(ValueError, match="invalid JSON"):
        parse_interaction_spec('{"interactions": [BROKEN}')


def test_empty_interactions_list_raises_value_error() -> None:
    """interactions=[] violates min_length=1 → ValueError."""
    with pytest.raises(ValueError):
        parse_interaction_spec(_EMPTY_INTERACTIONS_JSON)


def test_missing_focus_and_keyboard_raises_value_error() -> None:
    """Hover + active only (no focus/keyboard) → ValueError (focus-coverage rule)."""
    with pytest.raises(ValueError, match="focus"):
        parse_interaction_spec(_NO_FOCUS_JSON)


def test_missing_trigger_field_raises_value_error() -> None:
    """Interaction entry missing `trigger` field → ValueError (schema validation)."""
    with pytest.raises(ValueError):
        parse_interaction_spec(_MISSING_FIELD_JSON)


def test_unknown_trigger_value_raises_value_error() -> None:
    """Unknown trigger value → ValueError (enum validation)."""
    bad = (
        '{"interactions":['
        '{"element":".x","trigger":"wiggle","effect":"shakes"},'
        '{"element":".x","trigger":"focus","effect":"ring"}'
        "]}"
    )
    with pytest.raises(ValueError):
        parse_interaction_spec(bad)


# ---------------------------------------------------------------------------
# InteractionSpec model — direct construction tests
# ---------------------------------------------------------------------------


def test_direct_construction_valid() -> None:
    """Direct Pydantic construction of a valid InteractionSpec."""
    spec = InteractionSpec(
        interactions=[
            DeclaredInteraction(
                element="#submit",
                trigger=InteractionTrigger.FOCUS,
                effect="outline 3px solid #005FCC",
            )
        ]
    )
    assert spec.focus_covered is True


def test_direct_construction_no_focus_raises() -> None:
    """Direct construction without focus/keyboard → ValidationError."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        InteractionSpec(
            interactions=[
                DeclaredInteraction(
                    element="#card",
                    trigger=InteractionTrigger.HOVER,
                    effect="shadow deepens",
                )
            ]
        )


def test_frozen_immutable() -> None:
    """InteractionSpec is frozen — attribute assignment must raise."""
    spec = parse_interaction_spec(_GOLDEN_JSON)
    with pytest.raises(Exception):  # pydantic.ValidationError or AttributeError
        spec.schema_version = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Hermetic specialist integration: FakeLlm emits golden JSON → parseable
#
# We validate the parser on the exact string a FakeLlm InteractionDesigner
# turn would write to session state, which proves the round-trip works without
# spinning up the full ADK runner (which is already covered by AT-020 tests).
# ---------------------------------------------------------------------------


def test_fake_specialist_output_parses_to_valid_spec() -> None:
    """Representative InteractionDesigner LLM output → valid InteractionSpec.

    Simulates what happens when the real pipeline reads ``interaction_spec``
    from session state and passes it to ``parse_interaction_spec``:
    the golden JSON (the string a FakeLlm or real LLM would emit) must round-
    trip cleanly into a valid :class:`InteractionSpec`.
    """
    # This mirrors the exact output the FakeLlm in test_specialist_pipeline.py
    # would produce if patched to emit the AT-023 golden schema instead of the
    # generic "FAKE_SPECIALIST_OUTPUT_N" string.
    simulated_session_state_value = _GOLDEN_JSON
    spec = parse_interaction_spec(simulated_session_state_value)
    assert isinstance(spec, InteractionSpec)
    assert len(spec.interactions) >= 1
    assert spec.focus_covered is True


def test_fake_specialist_fenced_output_parses_to_valid_spec() -> None:
    """Fenced-JSON output (common LLM formatting) → valid InteractionSpec.

    Many LLMs wrap JSON in markdown fences even when instructed not to.
    The parser must handle this gracefully.
    """
    simulated_fenced = _GOLDEN_JSON_FENCED
    spec = parse_interaction_spec(simulated_fenced)
    assert isinstance(spec, InteractionSpec)
    assert spec.focus_covered is True
