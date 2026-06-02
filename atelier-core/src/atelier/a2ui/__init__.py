"""Governed A2UI emit layer (ADR-0024).

A2UI is adopted for the **Studio chrome / control layer only** — never the design
deliverable, which stays portable DTCG-tokenized HTML (PRD v2.2 §3.4/§10).

This package builds A2UI **v0.10-SDK / v0.9-wire** surfaces
(``createSurface`` / ``updateComponents`` / ``updateDataModel``) for agent-driven
Studio surfaces and **governs them fail-closed before emit** (G2, ADR-0024 §2).
P0 ships exactly one surface: the AT-044 design-system token panel, built against
the custom Atelier catalog (:data:`atelier.a2ui.catalog.ATELIER_CATALOG_ID`, a
6-component trusted allowlist).

The surface the frontend renders is (re)built at the API boundary
(``api/generate.py:_enrich_complete_payload``) from the run's resolved design
tokens, **passed through** :func:`atelier.a2ui.gate.gate_a2ui_surface` (the
canonical gate site — it runs LAST and overwrites ``a2ui_payload``), then threaded
onto the SSE ``complete`` event alongside ``best_html``. The orchestrator
(``orchestrator/runner.py``) gates the same surface for defense-in-depth. On
REJECT the surface is blanked (``a2ui_payload = []``, frontend fail-soft) and the
custom governance event is carried on ``a2ui_governance``.
``CandidateUI.a2ui_payload`` is the per-candidate carrier slot — also gated in
``nodes/generator.py`` (dropped to ``None`` on REJECT).

Schema source of truth (verified, per ``<no_unverified_apis>``):
  * ``@a2ui/web_core@0.10.0`` → ``src/v0_9/schemas/server_to_client.json``
    (``$id`` ``https://a2ui.org/specification/v0_9/server_to_client.json``).
  * Cross-checked against pinned ``google/A2UI``
    (commit ``0fde624719c500133c526f49df5b007d0392f3cb``) fixtures
    ``agent_sdks/conformance/test_data/simplified_s2c_v09.json`` and
    ``samples/agent/adk/custom-components-example/examples/0.9/contact_list.json``.
"""

from atelier.a2ui.catalog import (
    ALLOWED_COMPONENTS,
    ATELIER_CATALOG_COMPONENTS,
    ATELIER_CATALOG_ID,
)
from atelier.a2ui.gate import (
    A2uiGateResult,
    A2uiRejectReason,
    gate_a2ui_surface,
)
from atelier.a2ui.surface import (
    A2UI_CATALOG_ID,
    A2UI_WIRE_VERSION,
    build_design_system_surface,
)

__all__ = [
    "A2UI_CATALOG_ID",
    "A2UI_WIRE_VERSION",
    "ALLOWED_COMPONENTS",
    "ATELIER_CATALOG_COMPONENTS",
    "ATELIER_CATALOG_ID",
    "A2uiGateResult",
    "A2uiRejectReason",
    "build_design_system_surface",
    "gate_a2ui_surface",
]
