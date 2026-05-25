"""Unit tests for Firebase Authentication middleware (atelier.auth.firebase).

Covers: FirebaseUser dataclass, _user_from_token, require_auth, optional_auth.
Firebase SDK calls are mocked — tests run without a live Firebase project.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# FirebaseUser dataclass
# ---------------------------------------------------------------------------


def test_firebase_user_is_frozen() -> None:
    from atelier.auth.firebase import FirebaseUser

    user = FirebaseUser(
        uid="uid-001",
        email="test@example.com",
        name="Test User",
        picture=None,
        tenant_id="uid-001",
        email_verified=True,
    )
    assert user.uid == "uid-001"
    with pytest.raises(AttributeError):
        user.uid = "other"  # type: ignore[misc]


def test_firebase_user_all_fields_accessible() -> None:
    from atelier.auth.firebase import FirebaseUser

    user = FirebaseUser(
        uid="u1",
        email="a@b.com",
        name="Alice",
        picture="https://example.com/pic.jpg",
        tenant_id="t1",
        email_verified=True,
    )
    assert user.email_verified is True
    assert user.picture is not None


# ---------------------------------------------------------------------------
# _user_from_token
# ---------------------------------------------------------------------------


def test_user_from_token_b2c_tenant_defaults_to_uid() -> None:
    from atelier.auth.firebase import _user_from_token

    decoded: dict[str, Any] = {
        "uid": "firebase-uid-abc",
        "email": "user@example.com",
        "name": "Alice",
        "email_verified": True,
    }
    user = _user_from_token(decoded)
    assert user.tenant_id == "firebase-uid-abc"
    assert user.uid == "firebase-uid-abc"


def test_user_from_token_multitenant_custom_claim() -> None:
    from atelier.auth.firebase import _user_from_token

    decoded: dict[str, Any] = {
        "uid": "firebase-uid-abc",
        "atelier_tenant": "enterprise-corp",
        "email": "admin@corp.com",
        "email_verified": True,
    }
    user = _user_from_token(decoded)
    assert user.tenant_id == "enterprise-corp"


def test_user_from_token_optional_fields_are_none() -> None:
    from atelier.auth.firebase import _user_from_token

    decoded: dict[str, Any] = {"uid": "x", "email_verified": False}
    user = _user_from_token(decoded)
    assert user.email is None
    assert user.name is None
    assert user.picture is None


# ---------------------------------------------------------------------------
# _dev_user
# ---------------------------------------------------------------------------


def test_dev_user_has_expected_fields() -> None:
    from atelier.auth.firebase import _dev_user

    dev = _dev_user()
    assert dev.uid == "dev-user-local"
    assert dev.email_verified is True
    assert dev.tenant_id == "dev-tenant"


# ---------------------------------------------------------------------------
# require_auth — integration via FastAPI TestClient
# ---------------------------------------------------------------------------


def _app_with_require_auth() -> FastAPI:
    from atelier.auth.firebase import FirebaseUser, require_auth

    app = FastAPI()

    @app.get("/p")
    async def p(u: FirebaseUser = Depends(require_auth)) -> dict[str, str]:  # type: ignore[arg-type]
        return {"uid": u.uid}

    return app


def test_require_auth_with_bypass_returns_dev_user() -> None:
    """Bypass mode → dev user injected without token validation."""
    with patch("atelier.auth.firebase._BYPASS_AUTH", True):
        client = TestClient(_app_with_require_auth(), raise_server_exceptions=True)
        resp = client.get("/p")
    assert resp.status_code == 200
    assert resp.json()["uid"] == "dev-user-local"


def test_require_auth_missing_bearer_returns_401() -> None:
    """No Authorization header + bypass off → HTTP 401."""
    with patch("atelier.auth.firebase._BYPASS_AUTH", False):
        client = TestClient(_app_with_require_auth(), raise_server_exceptions=False)
        resp = client.get("/p")
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "missing_token"


def test_require_auth_decode_raises_http_401() -> None:
    """When _decode_token raises HTTPException(401), endpoint propagates 401."""
    from fastapi import HTTPException

    def _bad_decode(*a: Any, **kw: Any) -> None:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_token", "user_action": "Sign in again."},
        )

    with (
        patch("atelier.auth.firebase._BYPASS_AUTH", False),
        patch("atelier.auth.firebase._decode_token", side_effect=_bad_decode),
    ):
        client = TestClient(_app_with_require_auth(), raise_server_exceptions=False)
        resp = client.get("/p", headers={"Authorization": "Bearer bad-jwt"})

    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "invalid_token"


# ---------------------------------------------------------------------------
# optional_auth — returns None when no token, dev user when bypass
# ---------------------------------------------------------------------------


def _app_with_optional_auth() -> FastAPI:
    from atelier.auth.firebase import FirebaseUser, optional_auth

    app = FastAPI()

    @app.get("/o")
    async def o(u: FirebaseUser | None = Depends(optional_auth)) -> dict[str, str]:  # type: ignore[arg-type]
        return {"uid": u.uid if u else "anonymous"}

    return app


def test_optional_auth_returns_none_when_unauthenticated() -> None:
    """No token + bypass off → optional_auth yields None."""
    with patch("atelier.auth.firebase._BYPASS_AUTH", False):
        client = TestClient(_app_with_optional_auth(), raise_server_exceptions=False)
        resp = client.get("/o")
    assert resp.status_code == 200
    assert resp.json()["uid"] == "anonymous"


def test_optional_auth_with_bypass_returns_dev_user() -> None:
    """Bypass mode → dev user via optional_auth."""
    with patch("atelier.auth.firebase._BYPASS_AUTH", True):
        client = TestClient(_app_with_optional_auth(), raise_server_exceptions=True)
        resp = client.get("/o")
    assert resp.status_code == 200
    assert resp.json()["uid"] == "dev-user-local"
