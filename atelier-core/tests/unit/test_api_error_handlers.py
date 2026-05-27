"""Unit tests for API-level error handlers and account endpoints (app.py).

Covers: GovernorBudgetExceeded → HTTP 402, /health, /auth/signin,
        /v1/account/usage (auth required).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    """TestClient with FIREBASE_DISABLE_AUTH=true so auth is bypassed."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("FIREBASE_DISABLE_AUTH", "true")
        mp.setenv("ATELIER_ENV", "development")

        import importlib

        import atelier.auth.firebase as auth_mod

        importlib.reload(auth_mod)

        from atelier.api.app import create_app

        app = create_app()
        return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Health endpoint (unauthenticated, readiness probe)
# ---------------------------------------------------------------------------


def test_health_returns_200(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert "version" in body
    assert "service" in body


def test_health_is_unauthenticated(client: TestClient) -> None:
    """Health endpoint must NOT require auth (Cloud Run readiness probe)."""
    resp = client.get("/health")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GovernorBudgetExceeded → HTTP 402
# ---------------------------------------------------------------------------


def test_budget_exceeded_handler_returns_402(client: TestClient) -> None:
    """GovernorBudgetExceeded exception must be caught and returned as HTTP 402."""
    from atelier.orchestrator.governor import GovernorBudgetExceeded

    # Mount a test route that raises GovernorBudgetExceeded
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/test/budget-exceeded")
    async def trigger_budget_exceeded() -> None:
        raise GovernorBudgetExceeded("Test: cap exceeded")

    app = client.app  # type: ignore[attr-defined]
    app.include_router(router)

    resp = client.get("/test/budget-exceeded")
    assert resp.status_code == 402
    body = resp.json()
    assert body["error"] == "budget_cap_exceeded"
    assert body["code"] == 402
    assert "title" in body
    assert "detail" in body
    assert "user_action" in body
    assert "docs_url" in body
    assert "autonomous-agent.dev" in body["docs_url"]


# ---------------------------------------------------------------------------
# /auth/signin — sign-in flow documentation (unauthenticated)
# ---------------------------------------------------------------------------


def test_auth_signin_info_returns_200(client: TestClient) -> None:
    resp = client.get("/auth/signin")
    assert resp.status_code == 200
    body = resp.json()
    assert "auth_provider" in body
    assert "Firebase" in body["auth_provider"]
    assert "sign_in_methods" in body
    assert "google.com" in body["sign_in_methods"]
    assert "flow" in body
    assert len(body["flow"]) >= 4


# ---------------------------------------------------------------------------
# /v1/account/usage — authenticated endpoint
# ---------------------------------------------------------------------------


def test_account_usage_returns_budget_info(client: TestClient) -> None:
    """With FIREBASE_DISABLE_AUTH=true, dev user is injected — should return 200."""
    resp = client.get("/v1/account/usage")
    assert resp.status_code == 200
    body = resp.json()
    assert "budget_cap_usd" in body
    assert "budget_used_usd" in body
    assert "budget_remaining_usd" in body
    assert "budget_pct_used" in body
    assert body["budget_cap_usd"] > 0
    assert body["budget_remaining_usd"] <= body["budget_cap_usd"]
    # Dev user wired
    assert "user_id" in body
    assert body["user_id"] == "dev-user-local"


def test_account_usage_requires_auth_without_bypass() -> None:
    """Without FIREBASE_DISABLE_AUTH, missing token returns 401."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("FIREBASE_DISABLE_AUTH", "false")
        mp.setenv("ATELIER_ENV", "development")
        import importlib

        import atelier.auth.firebase as auth_mod

        importlib.reload(auth_mod)

        from atelier.api.app import create_app

        app = create_app()
        c = TestClient(app, raise_server_exceptions=False)
        resp = c.get("/v1/account/usage")
        assert resp.status_code == 401

    import importlib

    import atelier.auth.firebase as auth_mod

    importlib.reload(auth_mod)
