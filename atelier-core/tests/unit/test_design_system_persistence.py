"""AT-053 — persistent per-tenant design-system memory (enforced, not applied).

The USP vs Claude Design: a tenant's design system is *persisted* at sign-off,
*auto-applied* on the next run with no re-specification, and *enforced* by the
AT-012 zero-tolerance token-fidelity gate — an off-system literal is REJECTed,
never silently merged.

V1 scope (PRD §12 / AT-053): persist + auto-apply + enforce ONLY. There is
exactly ONE design system per tenant; the codebase-onboarding learner and
multi-system-per-tenant are V2 and are deliberately NOT exercised here.

These tests run fully offline (``backend="memory"`` / file fallback) — no GCP
credentials, no live Vertex Memory Bank, no Firestore. The offline persister
writes a real JSON file so the system survives across two distinct persister
*instances* within one test (the cross-run durability assertion), exactly the
way the AT-095 usage counter persists across ``AtelierRunner`` instances.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from atelier.a2ui.gate import gate_a2ui_surface
from atelier.a2ui.surface import build_design_system_surface
from atelier.durability.design_system_persister import (
    DesignSystemPersister,
    load_persisted_design_system,
    persist_design_system,
)
from atelier.intake.source_resolver import pull_memory_bank_priors
from atelier.models.design_system import DesignSystemRecord


@pytest.fixture
def offline_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the offline persister at an isolated, real on-disk directory."""
    monkeypatch.setenv("ATELIER_DESIGN_SYSTEM_BACKEND", "file")
    monkeypatch.setenv("ATELIER_DESIGN_SYSTEM_DIR", str(tmp_path))
    return tmp_path


TENANT = "tnt_acme"
RUN1_TOKENS = {
    "primary_color": "#1a73e8",
    "surface_background": "#ffffff",
    "surface_foreground": "#202124",
    "font": "Inter",
}


@pytest.mark.unit
def test_persist_and_load_roundtrip(offline_dir: Path) -> None:
    """persist_design_system writes a record; load returns it with tokens intact."""

    async def _run() -> None:
        record_id = await persist_design_system(
            tenant_id=TENANT,
            tokens=RUN1_TOKENS,
            constitution="Never ship below AA contrast.",
            standards=[{"id": "WCAG-2.2", "level": "AA"}],
            run_id="run-1",
        )
        assert record_id

        loaded = await load_persisted_design_system(TENANT)
        assert loaded is not None
        assert isinstance(loaded, DesignSystemRecord)
        assert loaded.tokens == RUN1_TOKENS
        assert loaded.constitution == "Never ship below AA contrast."
        assert loaded.applicable_standards == [{"id": "WCAG-2.2", "level": "AA"}]

    asyncio.run(_run())


@pytest.mark.unit
def test_load_returns_none_when_not_found(offline_dir: Path) -> None:
    """Loading an unknown tenant returns None (degrade, never raise)."""
    assert asyncio.run(load_persisted_design_system("tnt_unknown")) is None


@pytest.mark.unit
def test_persistence_survives_across_persister_instances(offline_dir: Path) -> None:
    """The system persists across two distinct persister instances (cross-run).

    This is the durability core: run #1 uses one persister, the process tears it
    down, and run #2 (a *fresh* persister) still loads the persisted system. A
    pure in-memory store that lost data on instance teardown would fail here.
    """

    async def _run() -> None:
        writer = DesignSystemPersister()
        await writer.persist(
            tenant_id=TENANT, tokens=RUN1_TOKENS, constitution=None, standards=[], run_id="run-1"
        )

        # Fresh instance — no shared in-instance state with `writer`.
        reader = DesignSystemPersister()
        loaded = await reader.load(TENANT)
        assert loaded is not None
        assert loaded.tokens == RUN1_TOKENS

    asyncio.run(_run())


@pytest.mark.unit
def test_design_system_persists_at_signoff_and_loads_on_next_run(offline_dir: Path) -> None:
    """The canonical AT-053 acceptance chain (first_failing_test).

    (a) sign-off persists run #1's tokens;
    (b) run #2 inherits them via pull_memory_bank_priors with NO re-specification;
    (c) an off-system literal in run #2 is REJECTed by the AT-012 gate (enforced);
    (d) editing the persisted system propagates immediately (round-trip).
    """

    async def _run() -> None:
        # (a) Run #1 signs off → persist the tenant design system.
        await persist_design_system(
            tenant_id=TENANT,
            tokens=RUN1_TOKENS,
            constitution="Brand fidelity is non-negotiable.",
            standards=[{"id": "WCAG-2.2", "level": "AA"}],
            run_id="run-1",
        )

        # (b) Run #2: the source resolver auto-applies the persisted system as
        # memory-bank priors — the tenant did NOT re-specify any token.
        priors = await pull_memory_bank_priors(TENANT)
        joined = "\n".join(priors)
        assert "#1a73e8" in joined  # primary_color inherited
        assert "Inter" in joined  # font inherited
        assert "Brand fidelity is non-negotiable." in joined  # constitution inherited

        # (c) Enforcement: build run #2's surface from an OFF-SYSTEM literal
        # (primary_color flipped to #ff0000, never signed off for this tenant).
        # With the persisted system threaded in, the AT-012 gate must REJECT.
        off_system = dict(RUN1_TOKENS)
        off_system["primary_color"] = "#ff0000"
        surface = build_design_system_surface(off_system, surface_id="atelier-design-system")
        persisted = await load_persisted_design_system(TENANT)
        assert persisted is not None
        result = gate_a2ui_surface(
            surface,
            design_tokens=off_system,
            surface_id="atelier-design-system",
            persisted_design_tokens=persisted.tokens,
        )
        assert result.passed is False
        assert any(r.validator == "token_fidelity" for r in result.reasons)
        assert any("persisted design system" in r.message for r in result.reasons)

        # The in-system surface (exactly the persisted tokens) PASSES — the gate
        # enforces, it does not just reject everything.
        in_system_surface = build_design_system_surface(
            RUN1_TOKENS, surface_id="atelier-design-system"
        )
        ok = gate_a2ui_surface(
            in_system_surface,
            design_tokens=RUN1_TOKENS,
            surface_id="atelier-design-system",
            persisted_design_tokens=persisted.tokens,
        )
        assert ok.passed is True, [r.message for r in ok.reasons]

        # (d) Edit propagates: the user edits primary_color → #0b57d0 and re-signs.
        # The new literal is now IN-system; the OLD one is now off-system.
        edited = dict(RUN1_TOKENS)
        edited["primary_color"] = "#0b57d0"
        await persist_design_system(
            tenant_id=TENANT,
            tokens=edited,
            constitution="Brand fidelity is non-negotiable.",
            standards=[{"id": "WCAG-2.2", "level": "AA"}],
            run_id="run-3",
        )
        re_loaded = await load_persisted_design_system(TENANT)
        assert re_loaded is not None
        assert re_loaded.tokens["primary_color"] == "#0b57d0"  # edit propagated

        edited_surface = build_design_system_surface(edited, surface_id="atelier-design-system")
        after_edit = gate_a2ui_surface(
            edited_surface,
            design_tokens=edited,
            surface_id="atelier-design-system",
            persisted_design_tokens=re_loaded.tokens,
        )
        assert after_edit.passed is True, [r.message for r in after_edit.reasons]

        # And the OLD value is now rejected (the edit truly replaced the system).
        old_surface = build_design_system_surface(RUN1_TOKENS, surface_id="atelier-design-system")
        after_old = gate_a2ui_surface(
            old_surface,
            design_tokens=RUN1_TOKENS,
            surface_id="atelier-design-system",
            persisted_design_tokens=re_loaded.tokens,
        )
        assert after_old.passed is False

    asyncio.run(_run())


@pytest.mark.unit
def test_multi_tenant_isolation(offline_dir: Path) -> None:
    """One system per tenant; tenant A's system never leaks into tenant B."""

    async def _run() -> None:
        tokens_a = {"primary_color": "#1a73e8", "font": "Inter"}
        tokens_b = {"primary_color": "#34a853", "font": "Roboto"}
        await persist_design_system(
            tenant_id="tnt_a", tokens=tokens_a, constitution=None, standards=[], run_id="a1"
        )
        await persist_design_system(
            tenant_id="tnt_b", tokens=tokens_b, constitution=None, standards=[], run_id="b1"
        )

        a = await load_persisted_design_system("tnt_a")
        b = await load_persisted_design_system("tnt_b")
        assert a is not None
        assert b is not None
        assert a.tokens == tokens_a
        assert b.tokens == tokens_b
        assert a.tokens != b.tokens

    asyncio.run(_run())


@pytest.mark.unit
def test_gate_without_persisted_system_is_unchanged(offline_dir: Path) -> None:
    """No persisted system → the gate behaves exactly as before (no enforcement).

    Run #1 for a brand-new tenant has nothing to enforce against; the
    token-fidelity validator must be a no-op so first runs are never blocked.
    """
    surface = build_design_system_surface(RUN1_TOKENS, surface_id="atelier-design-system")
    result = gate_a2ui_surface(
        surface,
        design_tokens=RUN1_TOKENS,
        surface_id="atelier-design-system",
        persisted_design_tokens=None,
    )
    assert result.passed is True, [r.message for r in result.reasons]
