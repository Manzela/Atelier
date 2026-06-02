"""Governed A2UI emit layer (ADR-0011).

A2UI is adopted for the **Studio chrome / control layer only** — never the design
deliverable, which stays portable DTCG-tokenized HTML (PRD v2.2 §3.4/§10).

This package builds A2UI **v0.10-SDK / v0.9-wire** surfaces
(``createSurface`` / ``updateComponents`` / ``updateDataModel``) for agent-driven
Studio surfaces. P0 ships exactly one surface: the AT-044 design-system token
panel, emitted into ``CandidateUI.a2ui_payload`` and threaded onto the SSE
``complete`` event alongside ``best_html``.

Schema source of truth (verified, per ``<no_unverified_apis>``):
  * ``@a2ui/web_core@0.10.0`` → ``src/v0_9/schemas/server_to_client.json``
    (``$id`` ``https://a2ui.org/specification/v0_9/server_to_client.json``).
  * Cross-checked against pinned ``google/A2UI``
    (commit ``0fde624719c500133c526f49df5b007d0392f3cb``) fixtures
    ``agent_sdks/conformance/test_data/simplified_s2c_v09.json`` and
    ``samples/agent/adk/custom-components-example/examples/0.9/contact_list.json``.
"""

from atelier.a2ui.surface import (
    A2UI_BASIC_CATALOG_ID,
    A2UI_WIRE_VERSION,
    build_design_system_surface,
)

__all__ = [
    "A2UI_BASIC_CATALOG_ID",
    "A2UI_WIRE_VERSION",
    "build_design_system_surface",
]
