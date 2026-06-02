"""Governed A2UI surface builder for the AT-044 design-system panel (ADR-0024).

Pure, typed construction of an A2UI **v0.10-SDK / v0.9-wire** surface for the
agent-driven Studio design-system token panel. No I/O, no LLM calls, no network.

The output is an ordered list of A2UI server-to-client messages:

  1. ``createSurface``    — opens the surface against the **Atelier design-system
     catalog** (:data:`A2UI_CATALOG_ID`, mirrored from
     :data:`atelier.a2ui.catalog.ATELIER_CATALOG_ID`), the custom 6-component
     trusted allowlist that replaces the upstream basic catalog (G4, ADR-0024).
  2. ``updateComponents`` — the declarative component tree (one ``id == "root"``).
  3. ``updateDataModel``  — the token rows the tree's template binds against.

The component tree is *data-driven*: a single ``Row`` template (``token_row``) is
referenced once via a ``ChildList`` template object
(``{"componentId": ..., "path": "/tokens"}``); the client materializes one row per
entry in the ``/tokens`` data-model object. This mirrors the frontend AT-044
``FlatToken`` panel (``atelier-dashboard/src/lib/design-system.ts``): one editable
row per leaf token (``path`` + ``value``).

Schema provenance (verified against live sources this session — ``<no_unverified_apis>``):
  * Wire schema: ``@a2ui/web_core@0.10.0`` ⇒ ``src/v0_9/schemas/server_to_client.json``
    (``$id`` ``https://a2ui.org/specification/v0_9/server_to_client.json``). Each
    message carries ``version: "v0.9"``; ``createSurface`` requires
    ``surfaceId`` + ``catalogId``; ``updateComponents`` requires ``surfaceId`` +
    a non-empty ``components`` array with exactly one ``id == "root"``;
    ``updateDataModel`` requires ``surfaceId`` and carries ``value`` (the data model).
  * Component catalog: the Atelier design-system catalog
    (:data:`atelier.a2ui.catalog.ATELIER_CATALOG_ID`) — a hand-authored 6-component
    trusted allowlist (``Card``/``Column``/``Row``/``Text``/``Divider``/``List``) whose
    per-component schema mirrors ``@a2ui/web_core@0.10.0`` ⇒
    ``src/v0_9/schemas/basic_catalog.json`` field-for-field so the wire tree below
    validates against the renderer unchanged (``Text.text`` is a ``DynamicString`` =
    literal or ``{"path": ...}`` ``DataBinding``; ``ChildList`` may be a template
    object ``{"componentId", "path"}``).
  * Template-binding pattern: pinned ``google/A2UI`` (commit
    ``0fde624719c500133c526f49df5b007d0392f3cb``)
    ``samples/agent/adk/custom-components-example/examples/0.9/contact_list.json``.

PRD Reference: §3.4/§10 (output stays HTML); ADR-0024 (Governed A2UI, control layer).
"""

from __future__ import annotations

import logging
from typing import Any

from atelier.a2ui.catalog import ATELIER_CATALOG_ID

logger = logging.getLogger(__name__)

#: The A2UI **wire** protocol version string. NOTE: the renderer *SDK* is at
#: ``0.10.0`` (``@a2ui/react`` / ``@a2ui/web_core``), but the on-the-wire
#: ``version`` const it validates against is ``"v0.9"`` — confirmed in both the
#: npm-shipped ``server_to_client.json`` and the pinned repo conformance fixture
#: ``simplified_s2c_v09.json``. Do not change to ``"v0.10"`` without re-verifying
#: against the renderer's schema; the renderer rejects an unknown version const.
A2UI_WIRE_VERSION: str = "v0.9"

#: The Atelier design-system catalog the panel renders against (G4, ADR-0024).
#: This is the **wire-emit** alias of :data:`atelier.a2ui.catalog.ATELIER_CATALOG_ID`
#: — re-exported here (not re-declared) so the ``createSurface.catalogId`` the
#: backend emits can never byte-diverge from the gate's allowlist constant or the
#: frontend's registered catalog id. It is an OPAQUE IDENTIFIER (never fetched);
#: the renderer matches ``createSurface.catalogId`` against the registered
#: ``atelierCatalog.id``, so this string MUST equal that catalog's id exactly.
A2UI_CATALOG_ID: str = ATELIER_CATALOG_ID

#: Component IDs used in the design-system surface tree. Kept as constants so the
#: tree and any future ``userAction`` ownership checks reference the same names.
_ROOT_ID = "root"
_TITLE_ID = "ds_title"
_DIVIDER_ID = "ds_divider"
_LIST_ID = "ds_token_list"
_ROW_TEMPLATE_ID = "token_row"
_ROW_PATH_TEXT_ID = "token_row_path"
_ROW_VALUE_TEXT_ID = "token_row_value"

#: Data-model key holding the token-row collection that the ``token_row`` template
#: binds against (``ChildList.path == "/tokens"``).
_DATA_TOKENS_KEY = "tokens"


def _coerce_token_value(value: object) -> str:
    """Coerce a design-token value to a display string for the data model.

    Token values arriving from ``ProjectContext.design_tokens`` are typically
    strings (hex colors, font stacks), but the contract is ``dict[str, Any]`` —
    a list (e.g. a font stack) or number is possible. Lists become a comma list
    (mirroring the Style-Dictionary CSS emit used by the frontend
    ``formatTokenValue`` helper); everything else is ``str()``-ified.

    Args:
        value: The raw token value.

    Returns:
        A display string safe to place in the A2UI data model.
    """
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _build_token_rows(design_tokens: dict[str, Any]) -> list[dict[str, str]]:
    """Build the ``/tokens`` data-model array from a flat design-token dict.

    Mirrors the frontend AT-044 panel rows (one row per leaf token). Keys whose
    name starts with ``_`` are excluded — these are intake metadata (e.g.
    ``_source`` from :func:`atelier.intake.source_resolver.pull_design_tokens`),
    not real design tokens.

    The result is a JSON **array** of row records. This is load-bearing: the
    ``@a2ui/web_core@0.10.0`` renderer instantiates a ``ChildList`` template only
    over an array — ``generic-binder.js`` does
    ``const arr = Array.isArray(newVal) ? newVal : []`` and maps each index to a
    child whose ``basePath`` is ``/tokens/<i>`` (so the row's ``{"path": "/path"}``
    binding resolves to ``/tokens/<i>/path``). A data-model *object* (as in the
    looser upstream ``contact_list.json`` sample) renders **zero** rows. The
    renderer source is authoritative over the sample here.

    Args:
        design_tokens: Flat ``{token_name: value}`` mapping from
            ``ProjectContext.design_tokens``.

    Returns:
        ``[{"path": token_name, "value": <display string>}, ...]`` for each
        non-metadata token, in insertion order.
    """
    rows: list[dict[str, str]] = []
    for name, value in design_tokens.items():
        if name.startswith("_"):
            continue
        rows.append({"path": name, "value": _coerce_token_value(value)})
    return rows


def _build_components() -> list[dict[str, Any]]:
    """Build the declarative A2UI component tree for the design-system panel.

    The tree is static (data flows in via the data model), so it is independent
    of the token set. Shape:

        Card(root) → Column → [Text(title), Divider, List(token rows)]
                                                      └─ template: Row → [Text(path), Text(value)]

    The ``List.children`` is a ``ChildList`` *template object* bound to
    ``/tokens``; the client instantiates ``token_row`` once per ``/tokens`` entry,
    resolving the row's ``{"path": "/path"}`` / ``{"path": "/value"}`` bindings
    against each entry.

    Returns:
        The ``components`` array for the ``updateComponents`` message. Exactly one
        component has ``id == "root"`` (schema-required).

    Every ``component`` type used here is a member of the Atelier catalog allowlist
    :data:`atelier.a2ui.catalog.ATELIER_CATALOG_COMPONENTS`
    (``{Card, Column, Row, Text, Divider, List}``) — the gate's security-perimeter
    source of truth. The fail-closed gate (:func:`atelier.a2ui.gate.gate_a2ui_surface`)
    REJECTS any surface whose component falls outside that set, so this tree must
    only ever emit those 6 types.
    """
    return [
        {
            "id": _ROOT_ID,
            "component": "Card",
            "child": "ds_column",
        },
        {
            "id": "ds_column",
            "component": "Column",
            "children": [_TITLE_ID, _DIVIDER_ID, _LIST_ID],
            "align": "stretch",
        },
        {
            "id": _TITLE_ID,
            "component": "Text",
            "variant": "h3",
            "text": "Design System",
        },
        {
            "id": _DIVIDER_ID,
            "component": "Divider",
            "axis": "horizontal",
        },
        {
            "id": _LIST_ID,
            "component": "List",
            "direction": "vertical",
            # ChildList template: materialize one `token_row` per `/tokens` entry.
            "children": {
                "componentId": _ROW_TEMPLATE_ID,
                "path": f"/{_DATA_TOKENS_KEY}",
            },
        },
        {
            "id": _ROW_TEMPLATE_ID,
            "component": "Row",
            "children": [_ROW_PATH_TEXT_ID, _ROW_VALUE_TEXT_ID],
            "justify": "spaceBetween",
            "align": "center",
        },
        {
            "id": _ROW_PATH_TEXT_ID,
            "component": "Text",
            "variant": "body",
            # RELATIVE DataBinding — resolved against each /tokens/<i> item scope.
            # MUST be slash-less: the renderer's DataContext.resolvePath treats a
            # leading-slash path as ABSOLUTE-from-root (verified in
            # @a2ui/web_core .../rendering/data-context.js: `if
            # (path.startsWith('/')) return path`), which would resolve "/path"
            # to the data-model root (undefined) and render an empty row. A
            # slash-less "path" is joined onto the item basePath → /tokens/<i>/path.
            "text": {"path": "path"},
        },
        {
            "id": _ROW_VALUE_TEXT_ID,
            "component": "Text",
            "variant": "caption",
            # RELATIVE binding (see note above): "value" → /tokens/<i>/value.
            "text": {"path": "value"},
        },
    ]


def build_design_system_surface(
    design_tokens: dict[str, Any],
    *,
    surface_id: str = "atelier-design-system",
) -> list[dict[str, Any]]:
    """Build the A2UI v0.10-SDK/v0.9-wire surface for the AT-044 design-system panel.

    Pure and deterministic: the same ``design_tokens`` always produce the same
    ordered message list. The caller's ``design_tokens`` dict is **never mutated**.

    The deliverable design (``best_html``) is untouched — this surface is the
    governed Studio *chrome* (ADR-0024), not the design output.

    Args:
        design_tokens: Flat ``{token_name: value}`` mapping (the shape carried by
            ``atelier.intake.source_resolver.ProjectContext.design_tokens``).
            Metadata keys (``_``-prefixed) are excluded from the rendered rows.
        surface_id: The A2UI surface identifier. Stable per panel; the frontend
            renderer mounts against this id.

    Returns:
        An ordered list of A2UI server-to-client messages:
        ``[createSurface, updateComponents, updateDataModel]``. Every message
        carries ``version == "v0.9"`` (see :data:`A2UI_WIRE_VERSION`).

    The ``design_tokens`` contract is ``dict[str, Any]``; the three call sites
    (generator, runner, API enrichment) all coerce to a dict before calling
    (e.g. ``getattr(ctx, "design_tokens", None) or {}``), so a non-mapping never
    reaches here — there is no silent fallback that would mask a contract break.
    """
    token_rows = _build_token_rows(design_tokens)
    logger.debug(
        "atelier.a2ui.surface.built",
        extra={"surface_id": surface_id, "token_count": len(token_rows)},
    )

    return [
        {
            "version": A2UI_WIRE_VERSION,
            "createSurface": {
                "surfaceId": surface_id,
                "catalogId": A2UI_CATALOG_ID,
            },
        },
        {
            "version": A2UI_WIRE_VERSION,
            "updateComponents": {
                "surfaceId": surface_id,
                "components": _build_components(),
            },
        },
        {
            "version": A2UI_WIRE_VERSION,
            "updateDataModel": {
                "surfaceId": surface_id,
                "path": "/",
                "value": {_DATA_TOKENS_KEY: token_rows},
            },
        },
    ]
