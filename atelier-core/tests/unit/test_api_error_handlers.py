"""Unit tests for API-level error handlers and account endpoints (app.py).

Covers: GovernorTokenCapExceeded → HTTP 402 (AT-095), GovernorRateLimitExceeded
        → HTTP 429, /health, /auth/signin.
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
# GovernorTokenCapExceeded → HTTP 402 (AT-095)
# ---------------------------------------------------------------------------


def test_token_cap_exceeded_handler_returns_402(client: TestClient) -> None:
    """GovernorTokenCapExceeded must be caught and returned as the branded HTTP 402."""
    from atelier.orchestrator.governor import (
        TOKEN_CAP_MESSAGE,
        GovernorTokenCapExceeded,
    )
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/test/token-cap-exceeded")
    async def trigger_token_cap_exceeded() -> None:
        raise GovernorTokenCapExceeded(
            uid="u1", used_tokens=5_000_000, cap_tokens=5_000_000, session_id="s1"
        )

    app = client.app  # type: ignore[attr-defined]
    app.include_router(router)

    import structlog

    # AT-095 acceptance (d): the breach is logged fail-loud with uid/session/IP.
    with structlog.testing.capture_logs() as logs:
        resp = client.get("/test/token-cap-exceeded")
    assert resp.status_code == 402
    body = resp.json()
    assert body["error"] == "token_cap_exhausted"
    assert body["code"] == 402
    # The single branded, non-error message (acceptance (b)).
    assert body["detail"] == TOKEN_CAP_MESSAGE
    assert "Contact administrator" in body["detail"]
    assert "user_action" in body
    assert "autonomous-agent.dev" in body["docs_url"]

    # (d) the alertable breach log carries uid + session + (sanitized) IP at error level.
    breach = next((e for e in logs if e.get("event") == "atelier.token_cap_exceeded"), None)
    assert breach is not None, "the token-cap breach must be logged"
    assert breach["log_level"] == "error"
    assert breach["uid"] == "u1"
    assert breach["session_id"] == "s1"
    assert "client_ip" in breach


def test_usage_unavailable_handler_returns_503_not_402(client: TestClient) -> None:
    """A persistence/corruption fail-closed must surface as a transient, retryable
    503 — NEVER the permanent 402 'you reached your cap / contact admin' message."""
    from atelier.orchestrator.governor import (
        TOKEN_CAP_MESSAGE,
        USAGE_UNAVAILABLE_MESSAGE,
        GovernorUsageUnavailable,
    )
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/test/usage-unavailable")
    async def trigger_usage_unavailable() -> None:
        raise GovernorUsageUnavailable(uid="u1", reason="read_failed")

    app = client.app  # type: ignore[attr-defined]
    app.include_router(router)

    resp = client.get("/test/usage-unavailable")
    assert resp.status_code == 503
    assert resp.headers.get("Retry-After") == "30"
    body = resp.json()
    assert body["error"] == "usage_unavailable"
    assert body["code"] == 503
    assert body["detail"] == USAGE_UNAVAILABLE_MESSAGE
    # Honesty: it must NOT tell the user they hit their cap.
    assert body["detail"] != TOKEN_CAP_MESSAGE
    assert "Contact administrator" not in body["detail"]


def test_rate_limit_exceeded_handler_returns_429(client: TestClient) -> None:
    """GovernorRateLimitExceeded must be caught and returned as HTTP 429 + Retry-After."""
    from atelier.orchestrator.governor import GovernorRateLimitExceeded
    from fastapi import APIRouter

    router = APIRouter()

    @router.get("/test/rate-limited")
    async def trigger_rate_limited() -> None:
        raise GovernorRateLimitExceeded(uid="u1", max_requests=30, window_seconds=60)

    app = client.app  # type: ignore[attr-defined]
    app.include_router(router)

    resp = client.get("/test/rate-limited")
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "60"
    body = resp.json()
    assert body["error"] == "rate_limited"
    assert body["code"] == 429


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


# The legacy USD /v1/account/usage tests were removed with the endpoint
# (PRD v2.2 AT-095 deletes the per-RUN USD path). Token-based usage coverage
# is added by AT-095/AT-096 in Phase C.
