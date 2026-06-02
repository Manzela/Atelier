"""Atelier custom A2UI catalog — the production trusted allowlist (G4, ADR-0024).

This module is the **machine-readable, single source of truth** for the Atelier
design-system A2UI catalog on the Python side. It mirrors the TypeScript catalog
(``atelier-dashboard/src/components/a2ui/atelierCatalog.ts``) so the backend
surface builder (:mod:`atelier.a2ui.surface`) and the fail-closed gate
(:mod:`atelier.a2ui.gate`) cannot drift from the frontend's registered catalog.

Three things are declared here:

* :data:`ATELIER_CATALOG_ID` — the opaque catalog identifier string. It is a
  *label* only: the frontend ``MessageProcessor`` matches ``createSurface.catalogId``
  against the registered catalog's ``.id`` (it is never fetched over the network).
  This string MUST be byte-identical to the TS ``ATELIER_CATALOG_ID`` and the PY
  ``A2UI_CATALOG_ID`` re-exported by :mod:`atelier.a2ui.surface`.
* :data:`ATELIER_CATALOG_COMPONENTS` — the trusted component-type allowlist (the
  security perimeter). Exactly the 6 component types the AT-044 surface emits.
* :data:`ALLOWED_COMPONENTS` — the per-component **required-prop** contract the
  gate consumes (``componentType -> frozenset[required-prop-names]``). This is the
  design contract: a surface whose component is outside the allowlist, or omits a
  required prop, is REJECTed fail-closed by :func:`atelier.a2ui.gate.gate_a2ui_surface`.

Schema provenance (verified against the published schema): the required-prop sets
mirror ``@a2ui/web_core@0.10.0`` ⇒ ``src/v0_9/schemas/basic_catalog.json`` component
shapes (Text needs ``text``; Card needs ``child``; Row/Column/List need ``children``;
Divider's ``axis`` is optional). The upstream JSON-schema ``required`` arrays are
empty (the wire schemas validate field *shape*, not presence); the Atelier catalog
makes presence of each component's content slot a hard requirement so a content-less
component (which would render an empty/meaningless node) is caught at the gate.
"""

from __future__ import annotations

from collections.abc import Mapping

#: The Atelier design-system catalog identifier (opaque label, never fetched).
#: MUST be byte-identical across the three mirrored declarations:
#:   * TS  ``ATELIER_CATALOG_ID``  — atelier-dashboard/src/components/a2ui/atelierCatalog.ts
#:   * PY  ``A2UI_CATALOG_ID``     — atelier.a2ui.surface  (the wire-emit constant)
#:   * PY  ``ATELIER_CATALOG_ID``  — this module           (the gate/allowlist constant)
ATELIER_CATALOG_ID: str = "https://atelier.autonomous-agent.dev/a2ui/catalogs/design-system/v1.json"

#: The trusted component-type allowlist — the security perimeter. The agent and
#: backend may emit ONLY these 6 component types; the gate REJECTS anything else.
#: Mirrors ``atelierCatalog.components`` keys on the TS side.
ATELIER_CATALOG_COMPONENTS: frozenset[str] = frozenset(
    {"Card", "Column", "Row", "Text", "Divider", "List"}
)

#: Per-component required-prop contract consumed by the gate
#: (``componentType -> frozenset[required-prop-names]``). A component instance must
#: declare every prop named here or the surface is REJECTed (fail-closed).
#:
#:   * ``Text``    requires ``text``     (the content slot — a DynamicString).
#:   * ``Column``  requires ``children`` (a ChildList).
#:   * ``Row``     requires ``children`` (a ChildList).
#:   * ``List``    requires ``children`` (a ChildList — literal array or template).
#:   * ``Card``    requires ``child``    (a single ComponentId).
#:   * ``Divider`` requires nothing     (``axis`` is optional, defaults horizontal).
#:
#: ``ALLOWED_COMPONENTS.keys()`` is exactly :data:`ATELIER_CATALOG_COMPONENTS`; the
#: gate uses ``.keys()`` as the allowlist and the values as the required-prop check.
ALLOWED_COMPONENTS: Mapping[str, frozenset[str]] = {
    "Card": frozenset({"child"}),
    "Column": frozenset({"children"}),
    "Row": frozenset({"children"}),
    "Text": frozenset({"text"}),
    "Divider": frozenset(),
    "List": frozenset({"children"}),
}

__all__ = [
    "ALLOWED_COMPONENTS",
    "ATELIER_CATALOG_COMPONENTS",
    "ATELIER_CATALOG_ID",
]
