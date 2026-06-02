"""Unit tests for the Governed A2UI surface builder (P0.4 — ADR-0024).

These tests pin the A2UI **v0.10 SDK / v0.9 wire-protocol** message shape that
``@a2ui/web_core@0.10.0`` renders. The wire schema is the authoritative
``server_to_client.json`` shipped inside that npm package (``$id``
``https://a2ui.org/specification/v0_9/server_to_client.json``), cross-checked
against the pinned ``google/A2UI`` repo
(commit ``0fde624719c500133c526f49df5b007d0392f3cb``) conformance fixture
``agent_sdks/conformance/test_data/simplified_s2c_v09.json``.

Verified facts the assertions below encode (no guessing — per ``<no_unverified_apis>``):
  * Every message carries ``version: "v0.9"`` (the SDK is 0.10.0; the *wire*
    version string is ``"v0.9"`` in both the npm schema and the repo fixture).
  * A full surface is an *ordered list* of messages: ``createSurface`` first,
    then ``updateComponents``, then ``updateDataModel``.
  * ``createSurface`` requires ``surfaceId`` + ``catalogId`` (``theme`` optional).
  * ``updateComponents`` requires ``surfaceId`` + a non-empty ``components`` array;
    exactly one component MUST have ``id == "root"``.
  * ``updateDataModel`` requires ``surfaceId``; ``value`` carries the data model
    that a ``{"path": ...}`` ``DataBinding`` (DynamicString) resolves against.
"""

from __future__ import annotations

from typing import Any

import pytest

# ---------------------------------------------------------------------------
# A known design-token set mirroring ProjectContext.design_tokens
# (intake/source_resolver.py) — a flat {name: value} dict.
# ---------------------------------------------------------------------------

_TOKENS: dict[str, Any] = {
    "primary_color": "#1a73e8",
    "font": "Inter",
    "color_surface": "#ffffff",
    "_source": "DESIGN.md",  # underscore-prefixed meta key — must be excluded
}


@pytest.mark.unit
def test_surface_builder_returns_ordered_message_list() -> None:
    """build_design_system_surface must return an ordered A2UI message list."""
    from atelier.a2ui.surface import build_design_system_surface

    surface = build_design_system_surface(_TOKENS, surface_id="design-system")

    assert isinstance(surface, list)
    # createSurface, updateComponents, updateDataModel — at minimum, in order.
    assert len(surface) >= 3
    assert "createSurface" in surface[0]
    assert "updateComponents" in surface[1]
    assert "updateDataModel" in surface[2]


@pytest.mark.unit
def test_every_message_carries_wire_version() -> None:
    """Every A2UI message must carry the v0.9 wire-version const (SDK 0.10.0)."""
    from atelier.a2ui.surface import A2UI_WIRE_VERSION, build_design_system_surface

    assert A2UI_WIRE_VERSION == "v0.9"
    surface = build_design_system_surface(_TOKENS, surface_id="design-system")
    for msg in surface:
        assert msg["version"] == "v0.9"


@pytest.mark.unit
def test_create_surface_message_shape() -> None:
    """createSurface must carry surfaceId + the Atelier catalogId."""
    from atelier.a2ui.catalog import ATELIER_CATALOG_ID
    from atelier.a2ui.surface import A2UI_CATALOG_ID, build_design_system_surface

    surface = build_design_system_surface(_TOKENS, surface_id="design-system")
    create = surface[0]["createSurface"]

    assert create["surfaceId"] == "design-system"
    # The emitted catalogId is the Atelier design-system catalog id — byte-identical
    # to the catalog module's constant (single source of truth, no drift).
    assert create["catalogId"] == ATELIER_CATALOG_ID
    assert A2UI_CATALOG_ID == ATELIER_CATALOG_ID
    # additionalProperties:false — only the schema-allowed keys may appear.
    assert set(create.keys()) <= {"surfaceId", "catalogId", "theme", "sendDataModel"}


@pytest.mark.unit
def test_update_components_has_exactly_one_root() -> None:
    """updateComponents.components must be non-empty with exactly one id=='root'."""
    from atelier.a2ui.surface import build_design_system_surface

    surface = build_design_system_surface(_TOKENS, surface_id="design-system")
    update = surface[1]["updateComponents"]

    assert update["surfaceId"] == "design-system"
    components = update["components"]
    assert isinstance(components, list)
    assert len(components) >= 1
    roots = [c for c in components if c.get("id") == "root"]
    assert len(roots) == 1, "exactly one component must have id 'root'"
    # Every component carries an id (ComponentCommon requires it) and a component type.
    for comp in components:
        assert isinstance(comp.get("id"), str)
        assert comp["id"]
        assert isinstance(comp.get("component"), str)
        assert comp["component"]
    # All catalog component types used MUST be from the TIGHTER Atelier catalog
    # allowlist (the 6-component security perimeter), not the upstream 18-name
    # basic catalog. This enforces the production trusted set as the source of truth.
    from atelier.a2ui.catalog import ATELIER_CATALOG_COMPONENTS

    for comp in components:
        assert comp["component"] in ATELIER_CATALOG_COMPONENTS, (
            f"component {comp['component']!r} is outside the Atelier catalog allowlist "
            f"{sorted(ATELIER_CATALOG_COMPONENTS)}"
        )


@pytest.mark.unit
def test_every_component_is_in_atelier_catalog_allowlist() -> None:
    """Security-perimeter invariant: the surface emits ONLY allowlisted components."""
    from atelier.a2ui.catalog import ATELIER_CATALOG_COMPONENTS
    from atelier.a2ui.surface import build_design_system_surface

    # The Atelier catalog is exactly the 6 trusted component types.
    expected_allowlist = frozenset({"Card", "Column", "Row", "Text", "Divider", "List"})
    assert set(ATELIER_CATALOG_COMPONENTS) == set(expected_allowlist)

    surface = build_design_system_surface(_TOKENS, surface_id="design-system")
    components = surface[1]["updateComponents"]["components"]
    emitted_types = {c["component"] for c in components}
    # Every emitted type is allowlisted (subset), and the surface exercises the
    # whole allowlist (the panel uses all 6 types).
    assert emitted_types <= ATELIER_CATALOG_COMPONENTS
    assert emitted_types == ATELIER_CATALOG_COMPONENTS


@pytest.mark.unit
def test_data_model_carries_one_row_per_token_excluding_meta() -> None:
    """updateDataModel.value must carry a token row list (meta keys excluded)."""
    from atelier.a2ui.surface import build_design_system_surface

    surface = build_design_system_surface(_TOKENS, surface_id="design-system")
    data = surface[2]["updateDataModel"]

    assert data["surfaceId"] == "design-system"
    value = data["value"]
    assert isinstance(value, dict)
    rows = value["tokens"]
    assert isinstance(rows, list)
    # 3 real tokens (primary_color, font, color_surface); the "_source" meta key
    # is excluded.
    paths = {row["path"] for row in rows}
    assert paths == {"primary_color", "font", "color_surface"}
    for row in rows:
        assert isinstance(row["path"], str)
        assert isinstance(row["value"], str)


@pytest.mark.unit
def test_children_template_binds_to_data_model_path() -> None:
    """The repeated token row must be a ChildList template bound to /tokens."""
    from atelier.a2ui.surface import build_design_system_surface

    surface = build_design_system_surface(_TOKENS, surface_id="design-system")
    components = surface[1]["updateComponents"]["components"]
    by_id = {c["id"]: c for c in components}

    # The token list/column references a template {componentId, path} so the
    # client generates one row per data-model entry (DTCG-style, data-driven).
    template_holders = [c for c in components if isinstance(c.get("children"), dict)]
    assert template_holders, "expected a ChildList template object for token rows"
    tmpl = template_holders[0]["children"]
    assert tmpl["path"] == "/tokens"
    assert tmpl["componentId"] in by_id


@pytest.mark.unit
def test_builder_is_pure_does_not_mutate_input() -> None:
    """The builder must not mutate the caller's token dict."""
    from atelier.a2ui.surface import build_design_system_surface

    tokens = dict(_TOKENS)
    snapshot = dict(tokens)
    build_design_system_surface(tokens, surface_id="design-system")
    assert tokens == snapshot


@pytest.mark.unit
def test_builder_handles_empty_tokens() -> None:
    """Empty token set still yields a valid surface (empty row list, one root)."""
    from atelier.a2ui.surface import build_design_system_surface

    surface = build_design_system_surface({}, surface_id="design-system")
    assert "createSurface" in surface[0]
    roots = [c for c in surface[1]["updateComponents"]["components"] if c.get("id") == "root"]
    assert len(roots) == 1
    assert surface[2]["updateDataModel"]["value"]["tokens"] == []
