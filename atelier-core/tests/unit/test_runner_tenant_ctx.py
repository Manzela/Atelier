"""Fail-loud guard on the runner's ``tenant_ctx=None`` placeholder default.

The 2026-06-09 code-health audit flagged that ``AtelierRunner.run()`` /
``resume()`` silently substituted a hardcoded placeholder context
(``tenant_id="t1"``, ``user_id="u1"``, ``project_id="p1"``) when no tenant
context was supplied. In production that would bill usage, write board task
docs, and persist design systems under a tenant/project path no verified
caller owns — dead data the dashboard can never read back.

The remediated contract (mirrors the codebase's single env-gating convention —
``os.getenv("ATELIER_ENV", "development") == "development"``, the same gate the
usage counter / board emitter / design-system persister use):

* ``ATELIER_ENV=development`` (and the unset default) — the placeholder is a
  legitimate local-dev / hermetic-test convenience and keeps working.
* Any other environment (production, staging, test) — ``tenant_ctx=None`` is a
  caller wiring bug and raises ``ValueError`` BEFORE any model call, usage
  accounting, or session creation.

Hermetic: the guard fires at the top of ``run()``/``resume()``, so no model
surface, Firestore client, or session backend is ever touched.
"""

from __future__ import annotations

import pytest
from atelier.durability.usage_counter import UsageCounterStore
from atelier.orchestrator.runner import AtelierRunner, _dev_placeholder_tenant_ctx
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools.tool_confirmation import ToolConfirmation

#: Long enough to clear the deterministic BriefParserGate — though the guard
#: under test must fire before the brief is ever parsed.
_BRIEF = "Build a calm editorial landing page and a pricing page for a co-working studio."


def _hermetic_runner() -> AtelierRunner:
    """An AtelierRunner wired entirely to in-memory backends (no GCP)."""
    return AtelierRunner(
        session_service=InMemorySessionService(),
        usage_store=UsageCounterStore(backend="memory"),
    )


@pytest.mark.anyio
@pytest.mark.parametrize("env", ["production", "staging", "test"])
async def test_run_rejects_none_tenant_ctx_outside_dev(
    monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    """``run(tenant_ctx=None)`` fails loud outside development — never tenant 't1'."""
    monkeypatch.setenv("ATELIER_ENV", env)
    runner = _hermetic_runner()
    with pytest.raises(ValueError, match="tenant_ctx is required"):
        await runner.run(_BRIEF)


@pytest.mark.anyio
async def test_resume_rejects_none_tenant_ctx_outside_dev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``resume(tenant_ctx=None)`` fails loud outside development too."""
    monkeypatch.setenv("ATELIER_ENV", "production")
    runner = _hermetic_runner()
    with pytest.raises(ValueError, match="tenant_ctx is required"):
        await runner.resume("session-under-test", ToolConfirmation(confirmed=True))


def test_placeholder_allowed_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    """In ATELIER_ENV=development the placeholder keeps the hermetic lane working."""
    monkeypatch.setenv("ATELIER_ENV", "development")
    ctx = _dev_placeholder_tenant_ctx()
    assert (ctx.tenant_id, ctx.user_id, ctx.project_id) == ("t1", "u1", "p1")


def test_placeholder_allowed_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset ATELIER_ENV defaults to development (the codebase-wide convention)."""
    monkeypatch.delenv("ATELIER_ENV", raising=False)
    ctx = _dev_placeholder_tenant_ctx()
    assert ctx.tenant_id == "t1"


def test_placeholder_raises_outside_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    """The helper itself is the single enforcement point — raises outside dev."""
    monkeypatch.setenv("ATELIER_ENV", "production")
    with pytest.raises(ValueError, match="placeholder tenant 't1'"):
        _dev_placeholder_tenant_ctx()
