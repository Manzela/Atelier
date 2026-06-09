"""Unit tests for Firebase Authentication middleware (atelier.auth.firebase).

Covers: FirebaseUser dataclass, _user_from_token, require_auth, optional_auth.
Firebase SDK calls are mocked — tests run without a live Firebase project.
"""

from __future__ import annotations

import sys
import types
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


# ---------------------------------------------------------------------------
# require_auth_strict — revocation is enforced (check_revoked=True)
#
# The contract: the SAME token (already revoked at Firebase) must be REJECTED
# on a strict route and ACCEPTED on a non-strict route. The only difference
# between the two dependencies is the ``check_revoked`` flag, so we model the
# firebase-admin SDK exactly: ``verify_id_token(token, check_revoked=True)``
# raises ``RevokedIdTokenError`` for a revoked token, while the same call with
# ``check_revoked=False`` decodes successfully (revocation is not consulted).
# ---------------------------------------------------------------------------


class _RevokedIdTokenError(Exception):
    """Stand-in for firebase_admin.auth.RevokedIdTokenError.

    ``_decode_token`` classifies exceptions by name (``"Revoked" in
    type(exc).__name__``), so the class name — not its module — drives the
    ``token_revoked`` error code. This mirrors the real SDK's behaviour
    without importing firebase-admin.
    """


def _install_fake_firebase_admin_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject a fake ``firebase_admin.auth`` whose verify reacts to check_revoked.

    Models a token that is valid by signature/issuer/audience/expiry but has
    been REVOKED at Firebase (e.g. user signed out). The fake therefore:
      - raises ``RevokedIdTokenError`` when ``check_revoked=True``
      - returns a decoded payload when ``check_revoked=False``

    Also stubs ``_init_firebase`` so no real Admin SDK initialisation runs.
    """
    fake_auth = types.ModuleType("firebase_admin.auth")
    fake_auth.RevokedIdTokenError = _RevokedIdTokenError  # type: ignore[attr-defined]

    def _verify_id_token(token: str, *, check_revoked: bool = False) -> dict[str, Any]:
        # ``_decode_token`` calls verify_id_token(token, check_revoked=...) by
        # keyword, so a keyword-only param here matches the real call site.
        if check_revoked:
            raise _RevokedIdTokenError("The Firebase ID token has been revoked.")
        return {
            "uid": "revoked-user-uid",
            "email": "revoked@example.com",
            "email_verified": True,
        }

    fake_auth.verify_id_token = _verify_id_token  # type: ignore[attr-defined]

    fake_pkg = types.ModuleType("firebase_admin")
    fake_pkg.auth = fake_auth  # type: ignore[attr-defined]

    def _noop_init() -> object:
        return object()

    monkeypatch.setitem(sys.modules, "firebase_admin", fake_pkg)
    monkeypatch.setitem(sys.modules, "firebase_admin.auth", fake_auth)
    # Neutralise the lazy SDK init — the fake needs no real credentials/app.
    monkeypatch.setattr("atelier.auth.firebase._init_firebase", _noop_init)


def _app_with_strict_auth() -> FastAPI:
    from atelier.auth.firebase import FirebaseUser, require_auth_strict

    app = FastAPI()

    @app.get("/strict")
    async def strict(u: FirebaseUser = Depends(require_auth_strict)) -> dict[str, str]:  # type: ignore[arg-type]
        return {"uid": u.uid}

    return app


def test_strict_route_rejects_revoked_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """A revoked token is rejected with 401 token_revoked on a strict route."""
    monkeypatch.setattr("atelier.auth.firebase._BYPASS_AUTH", False)
    _install_fake_firebase_admin_auth(monkeypatch)

    client = TestClient(_app_with_strict_auth(), raise_server_exceptions=False)
    resp = client.get("/strict", headers={"Authorization": "Bearer revoked-but-unexpired-jwt"})

    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "token_revoked"


def test_non_strict_route_accepts_same_revoked_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """The SAME revoked token is accepted on a non-strict route.

    Proves the rejection above is caused solely by ``check_revoked=True`` —
    ``require_auth`` skips the revocation round-trip and admits the token.
    """
    monkeypatch.setattr("atelier.auth.firebase._BYPASS_AUTH", False)
    _install_fake_firebase_admin_auth(monkeypatch)

    client = TestClient(_app_with_require_auth(), raise_server_exceptions=False)
    resp = client.get("/p", headers={"Authorization": "Bearer revoked-but-unexpired-jwt"})

    assert resp.status_code == 200
    assert resp.json()["uid"] == "revoked-user-uid"
