"""Unit tests for the fail-closed Governed A2UI gate (G2 — ADR-0024 §2).

The gate (:func:`atelier.a2ui.gate.gate_a2ui_surface`) validates an A2UI
server-to-client message list before it is emitted. These tests pin the
fail-closed contract:

  * the live design-system surface PASSES all four validators (identity — the
    current panel must keep rendering, a competition-visible non-regression);
  * an out-of-catalog component → catalog REJECT with the RFC-6901 json-pointer;
  * a component missing a required prop → catalog REJECT;
  * a declared-but-empty accessibility block → accessible_name REJECT;
  * a contrived contrast-failing token pair → contrast REJECT;
  * the governance event matches the CUSTOM + VALIDATION_FAILED contract;
  * a PASS leaves the surface untouched (identity transform).
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

# A flat design-token set mirroring ProjectContext.design_tokens.
_TOKENS: dict[str, Any] = {
    "primary_color": "#1a73e8",
    "font": "Inter",
    "color_surface": "#ffffff",
}

_SURFACE_ID = "atelier-design-system"


def _live_surface() -> list[dict[str, Any]]:
    """Build the real design-system surface the production code emits."""
    from atelier.a2ui.surface import build_design_system_surface

    return build_design_system_surface(_TOKENS, surface_id=_SURFACE_ID)


# ---------------------------------------------------------------------------
# (a) Identity — the live surface passes all four validators, untouched.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_live_design_system_surface_passes_all_validators() -> None:
    """The current design-system panel must PASS the gate (fail-closed identity)."""
    from atelier.a2ui.gate import gate_a2ui_surface

    surface = _live_surface()
    result = gate_a2ui_surface(surface, design_tokens=_TOKENS, surface_id=_SURFACE_ID)

    assert result.passed is True
    assert result.reasons == []
    assert result.governance_messages == []


@pytest.mark.unit
def test_pass_leaves_surface_untouched_identity() -> None:
    """A PASS must not mutate the input message list (identity transform)."""
    from atelier.a2ui.gate import gate_a2ui_surface

    surface = _live_surface()
    snapshot = copy.deepcopy(surface)
    result = gate_a2ui_surface(surface, design_tokens=_TOKENS, surface_id=_SURFACE_ID)

    assert result.passed is True
    # The gate is pure: the caller's surface is byte-identical after gating.
    assert surface == snapshot


# ---------------------------------------------------------------------------
# (b) Out-of-catalog component → catalog REJECT + correct json-pointer.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_out_of_catalog_component_rejected_with_pointer() -> None:
    """A component outside the Atelier allowlist → REJECT pointing at it."""
    from atelier.a2ui.gate import gate_a2ui_surface

    surface = _live_surface()
    surface[1]["updateComponents"]["components"].append({"id": "rogue", "component": "Frobnicate"})

    result = gate_a2ui_surface(surface, design_tokens=_TOKENS, surface_id=_SURFACE_ID)

    assert result.passed is False
    catalog_reasons = [r for r in result.reasons if r.validator == "catalog"]
    assert catalog_reasons, "expected a catalog REJECT reason"
    # The pointer locates the offending component's `component` field (last index).
    last_index = len(surface[1]["updateComponents"]["components"]) - 1
    assert any(
        r.json_pointer == f"/1/updateComponents/components/{last_index}/component"
        for r in catalog_reasons
    )


# ---------------------------------------------------------------------------
# (c) Missing required prop → catalog REJECT.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_text_without_text_prop_rejected() -> None:
    """A Text component missing its required `text` prop → catalog REJECT."""
    from atelier.a2ui.gate import gate_a2ui_surface

    surface = _live_surface()
    components = surface[1]["updateComponents"]["components"]
    title = next(c for c in components if c["component"] == "Text")
    del title["text"]  # strip the required content slot

    result = gate_a2ui_surface(surface, design_tokens=_TOKENS, surface_id=_SURFACE_ID)

    assert result.passed is False
    assert any(r.validator == "catalog" and "text" in r.message for r in result.reasons)


@pytest.mark.unit
def test_card_without_child_prop_rejected() -> None:
    """A Card missing its required `child` prop → catalog REJECT."""
    from atelier.a2ui.gate import gate_a2ui_surface

    surface = _live_surface()
    components = surface[1]["updateComponents"]["components"]
    root = next(c for c in components if c["id"] == "root")
    assert root["component"] == "Card"
    del root["child"]

    result = gate_a2ui_surface(surface, design_tokens=_TOKENS, surface_id=_SURFACE_ID)

    assert result.passed is False
    assert any(r.validator == "catalog" and "child" in r.message for r in result.reasons)


# ---------------------------------------------------------------------------
# (d) Declared-but-empty accessibility block → accessible_name REJECT.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_accessibility_label_rejected() -> None:
    """A declared accessibility block with no name → accessible_name REJECT."""
    from atelier.a2ui.gate import gate_a2ui_surface

    surface = _live_surface()
    components = surface[1]["updateComponents"]["components"]
    title = next(c for c in components if c["component"] == "Text")
    title["accessibility"] = {"label": "   "}  # whitespace-only = empty name

    result = gate_a2ui_surface(surface, design_tokens=_TOKENS, surface_id=_SURFACE_ID)

    assert result.passed is False
    assert any(r.validator == "accessible_name" for r in result.reasons)


@pytest.mark.unit
def test_nonempty_accessibility_label_passes() -> None:
    """A declared accessibility block WITH a name does not trip the validator."""
    from atelier.a2ui.gate import gate_a2ui_surface

    surface = _live_surface()
    components = surface[1]["updateComponents"]["components"]
    title = next(c for c in components if c["component"] == "Text")
    title["accessibility"] = {"label": "Design system heading"}

    result = gate_a2ui_surface(surface, design_tokens=_TOKENS, surface_id=_SURFACE_ID)

    assert result.passed is True


# ---------------------------------------------------------------------------
# (e) Contrived contrast-failing token pair → contrast REJECT.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_low_contrast_token_pair_rejected() -> None:
    """An inferable fg/bg token pair below AA → contrast REJECT naming the ratio."""
    from atelier.a2ui.gate import gate_a2ui_surface

    surface = _live_surface()
    # Inject a foreground/background pair that fails AA (#777 on #888 ≈ 1.3:1).
    rows = surface[2]["updateDataModel"]["value"]["tokens"]
    rows.append({"path": "brand-foreground", "value": "#777777"})
    rows.append({"path": "brand-background", "value": "#888888"})

    result = gate_a2ui_surface(surface, design_tokens=_TOKENS, surface_id=_SURFACE_ID)

    assert result.passed is False
    contrast_reasons = [r for r in result.reasons if r.validator == "contrast"]
    assert contrast_reasons, "expected a contrast REJECT reason"
    assert "brand-foreground" in contrast_reasons[0].message
    assert ":1" in contrast_reasons[0].message  # the ratio is named


@pytest.mark.unit
def test_high_contrast_token_pair_passes() -> None:
    """An inferable fg/bg token pair clearing AA does not trip the contrast gate."""
    from atelier.a2ui.gate import gate_a2ui_surface

    surface = _live_surface()
    rows = surface[2]["updateDataModel"]["value"]["tokens"]
    rows.append({"path": "brand-foreground", "value": "#000000"})
    rows.append({"path": "brand-background", "value": "#ffffff"})  # 21:1

    result = gate_a2ui_surface(surface, design_tokens=_TOKENS, surface_id=_SURFACE_ID)

    assert result.passed is True


# ---------------------------------------------------------------------------
# (f) Governance-event shape matches the CUSTOM + VALIDATION_FAILED contract.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_governance_message_shape_matches_contract() -> None:
    """The REJECT governance event matches the ADR-0024 §2 custom-event contract."""
    from atelier.a2ui.gate import gate_a2ui_surface

    surface = _live_surface()
    surface[1]["updateComponents"]["components"].append({"id": "rogue", "component": "Frobnicate"})

    result = gate_a2ui_surface(surface, design_tokens=_TOKENS, surface_id=_SURFACE_ID)

    assert result.passed is False
    assert len(result.governance_messages) == 1
    event = result.governance_messages[0]
    assert event["version"] == "v0.9"
    custom = event["custom"]
    assert custom["surfaceId"] == _SURFACE_ID
    assert custom["name"] == "atelier/governance.rejected"
    payload = custom["payload"]
    assert payload["decision"] == "REJECT"
    assert payload["gate"] == "governed-a2ui"
    errors = payload["errors"]
    assert isinstance(errors, list)
    assert errors, "at least one VALIDATION_FAILED error expected"
    first = errors[0]
    assert first["code"] == "VALIDATION_FAILED"
    assert first["surfaceId"] == _SURFACE_ID
    # path is an RFC-6901 JSON pointer (starts with '/' for a located node).
    assert isinstance(first["path"], str)
    assert first["path"].startswith("/")
    assert isinstance(first["message"], str)
    assert first["message"]


# ---------------------------------------------------------------------------
# (g) Envelope floor — empty / malformed surfaces fail closed.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_surface_rejected_envelope() -> None:
    """An empty message list → envelope REJECT (fail-closed floor)."""
    from atelier.a2ui.gate import gate_a2ui_surface

    result = gate_a2ui_surface([], design_tokens=_TOKENS, surface_id=_SURFACE_ID)

    assert result.passed is False
    assert any(r.validator == "envelope" for r in result.reasons)
    assert result.governance_messages


@pytest.mark.unit
def test_wrong_wire_version_rejected_envelope() -> None:
    """A message with the wrong wire version → envelope REJECT."""
    from atelier.a2ui.gate import gate_a2ui_surface

    surface = _live_surface()
    surface[0]["version"] = "v0.10"  # the renderer rejects an unknown version const

    result = gate_a2ui_surface(surface, design_tokens=_TOKENS, surface_id=_SURFACE_ID)

    assert result.passed is False
    assert any(r.validator == "envelope" and "version" in r.json_pointer for r in result.reasons)


@pytest.mark.unit
def test_two_roots_rejected_envelope() -> None:
    """More than one id=='root' → envelope REJECT."""
    from atelier.a2ui.gate import gate_a2ui_surface

    surface = _live_surface()
    surface[1]["updateComponents"]["components"].append(
        {"id": "root", "component": "Card", "child": "ds_column"}
    )

    result = gate_a2ui_surface(surface, design_tokens=_TOKENS, surface_id=_SURFACE_ID)

    assert result.passed is False
    assert any(r.validator == "envelope" and "root" in r.message for r in result.reasons)


@pytest.mark.unit
def test_allowed_components_override_is_honored() -> None:
    """A caller-supplied allowlist overrides the default Atelier catalog map."""
    from atelier.a2ui.gate import gate_a2ui_surface

    surface = _live_surface()
    # An allowlist that excludes Card → the root Card is now out-of-catalog.
    restrictive: dict[str, frozenset[str]] = {
        "Column": frozenset({"children"}),
        "Row": frozenset({"children"}),
        "Text": frozenset({"text"}),
        "Divider": frozenset(),
        "List": frozenset({"children"}),
    }

    result = gate_a2ui_surface(
        surface,
        design_tokens=_TOKENS,
        surface_id=_SURFACE_ID,
        allowed_components=restrictive,
    )

    assert result.passed is False
    assert any(r.validator == "catalog" and "Card" in r.message for r in result.reasons)
