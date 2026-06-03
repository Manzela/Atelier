"""AT-053 — end-to-end design-system enforcement through the real call sites.

Unlike ``tests/unit/test_design_system_persistence.py`` (which exercises the
persister + gate in isolation), this suite drives the *integration* seams:

* the N2 ``source_resolver_agent`` auto-applies a persisted system into a real
  ``ProjectContext`` (run #2 inherits run #1 with no re-specification); and
* the canonical API enrichment boundary
  (``atelier.api.generate._enrich_complete_payload``) — the single gate site the
  frontend actually renders — REJECTs an off-system literal when the tenant has a
  persisted system, and PASSes the in-system surface.

Fully offline (file backend, no GCP creds, no live model).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from atelier.api.generate import _enrich_complete_payload
from atelier.durability.design_system_persister import persist_design_system
from atelier.intake.brief_spec import (
    BriefSpec,
    ComplianceLevel,
    ConvergenceBar,
    StackChoice,
    VisualRegister,
)
from atelier.intake.source_resolver import ProjectContext, source_resolver_agent
from atelier.models.data_contracts import TenantContext

TENANT = "tnt_brandco"
SYSTEM_TOKENS = {
    "primary_color": "#1a73e8",
    "surface_background": "#ffffff",
    "surface_foreground": "#202124",
    "font": "Inter",
}


@pytest.fixture
def offline_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ATELIER_DESIGN_SYSTEM_BACKEND", "file")
    monkeypatch.setenv("ATELIER_DESIGN_SYSTEM_DIR", str(tmp_path))
    return tmp_path


def _brief() -> BriefSpec:
    return BriefSpec(  # type: ignore[call-arg]
        spec_id=uuid4(),
        tenant_id=TENANT,
        project_id="prj",
        intent="a landing page",
        visual_register=VisualRegister.EDITORIAL,
        stack=StackChoice.VANILLA_HTML,
        design_system_source=None,
        compliance_level=ComplianceLevel.WCAG_AA,
        convergence_bar=ConvergenceBar.PRODUCTION,
        reference_artifacts=[],
        campaign_scope=None,
        intake_transcript=[],
        approved_at=datetime.now(UTC),
        approved_by_user_id="usr",
    )


def _tenant_ctx() -> TenantContext:
    return TenantContext(tenant_id=TENANT, user_id="usr", project_id="prj")


@pytest.mark.integration
def test_run2_source_resolver_inherits_persisted_system(offline_dir: Path) -> None:
    """Run #2's N2 resolver auto-applies run #1's persisted system (no re-spec)."""

    async def _run() -> None:
        # Run #1 signed off → system persisted.
        await persist_design_system(
            tenant_id=TENANT,
            tokens=SYSTEM_TOKENS,
            constitution="Stay on brand.",
            standards=[],
            run_id="run-1",
        )

        # Run #2: resolve from a brief that specifies NO design source.
        ctx = await source_resolver_agent(_tenant_ctx(), _brief())
        assert isinstance(ctx, ProjectContext)
        # Persisted tokens are auto-applied as the run's defaults...
        assert ctx.design_tokens.get("primary_color") == "#1a73e8"
        assert ctx.design_tokens.get("font") == "Inter"
        # ...and the authorized set is threaded for enforcement.
        assert ctx.persisted_design_tokens is not None
        assert ctx.persisted_design_tokens["primary_color"] == "#1a73e8"
        # ...and the priors carry the system for the generator anchor.
        assert any("#1a73e8" in p for p in ctx.memory_bank_priors)

    asyncio.run(_run())


@pytest.mark.integration
def test_first_run_has_no_persisted_system_and_is_not_blocked(offline_dir: Path) -> None:
    """A tenant's first run: no persisted system, no enforcement, never blocked."""

    async def _run() -> None:
        ctx = await source_resolver_agent(_tenant_ctx(), _brief())
        assert ctx.persisted_design_tokens is None  # nothing persisted yet
        # The canonical gate site passes (no system to enforce against).
        payload = {"project_context": ctx, "best_candidate": ""}
        enriched = _enrich_complete_payload(payload)
        # Off-system enforcement did not fire → no governance rejection event.
        assert "a2ui_governance" not in enriched

    asyncio.run(_run())


@pytest.mark.integration
def test_off_system_literal_rejected_at_canonical_gate_site(offline_dir: Path) -> None:
    """An off-system literal in run #2 is REJECTed at the API enrichment boundary."""

    async def _run() -> None:
        await persist_design_system(
            tenant_id=TENANT,
            tokens=SYSTEM_TOKENS,
            constitution=None,
            standards=[],
            run_id="run-1",
        )
        ctx = await source_resolver_agent(_tenant_ctx(), _brief())
        assert ctx.persisted_design_tokens is not None

        # Simulate run #2 producing an OFF-SYSTEM literal: a project context whose
        # design_tokens carry a colour the tenant never signed off (#ff0000), while
        # the persisted authorized set still pins primary_color to #1a73e8.
        off_ctx = ctx.model_copy(
            update={"design_tokens": {**SYSTEM_TOKENS, "primary_color": "#ff0000"}}
        )
        payload = {"project_context": off_ctx, "best_candidate": ""}
        enriched = _enrich_complete_payload(payload)

        # Fail-closed at the canonical site: the rejected surface is NOT emitted;
        # a governance rejection event is carried instead.
        assert enriched["a2ui_payload"] == []
        assert "a2ui_governance" in enriched
        gov = enriched["a2ui_governance"]
        assert gov, "expected a governance rejection event"
        errors = gov[0]["custom"]["payload"]["errors"]
        assert any("persisted design system" in e["message"] for e in errors)

    asyncio.run(_run())


@pytest.mark.integration
def test_in_system_surface_passes_at_canonical_gate_site(offline_dir: Path) -> None:
    """The in-system surface PASSes — enforcement is selective, not blanket-reject."""

    async def _run() -> None:
        await persist_design_system(
            tenant_id=TENANT,
            tokens=SYSTEM_TOKENS,
            constitution=None,
            standards=[],
            run_id="run-1",
        )
        ctx = await source_resolver_agent(_tenant_ctx(), _brief())
        payload = {"project_context": ctx, "best_candidate": ""}
        enriched = _enrich_complete_payload(payload)
        assert "a2ui_governance" not in enriched
        assert enriched["a2ui_payload"], "in-system surface should ship unchanged"

    asyncio.run(_run())


@pytest.mark.integration
def test_edit_propagates_to_enforcement(offline_dir: Path) -> None:
    """Editing the persisted system flips which literals are authorized (round-trip)."""

    async def _run() -> None:
        await persist_design_system(
            tenant_id=TENANT, tokens=SYSTEM_TOKENS, constitution=None, standards=[], run_id="run-1"
        )
        # User edits primary_color and re-signs (last-write-wins per tenant).
        edited = {**SYSTEM_TOKENS, "primary_color": "#0b57d0"}
        await persist_design_system(
            tenant_id=TENANT, tokens=edited, constitution=None, standards=[], run_id="run-2"
        )

        ctx = await source_resolver_agent(_tenant_ctx(), _brief())
        assert ctx.persisted_design_tokens is not None
        assert ctx.persisted_design_tokens["primary_color"] == "#0b57d0"

        # The NEW value now passes...
        ok_payload = {"project_context": ctx, "best_candidate": ""}
        ok = _enrich_complete_payload(ok_payload)
        assert "a2ui_governance" not in ok

        # ...and the OLD value is now off-system → rejected.
        old_ctx = ctx.model_copy(update={"design_tokens": dict(SYSTEM_TOKENS)})
        old = _enrich_complete_payload({"project_context": old_ctx, "best_candidate": ""})
        assert "a2ui_governance" in old

    asyncio.run(_run())
