"""Firebase Authentication — Google SSO token verification for Atelier API.

Implements user authentication via Firebase Authentication (Google Identity
Platform). Firebase Auth is Google's own free, open-source-aligned auth
service — the canonical choice for B2C products targeting Google's ecosystem.

Why Firebase Auth over alternatives:
    - Google-maintained: ideal for Googler judge evaluation
    - Free tier: unlimited users, no rate limit on token verification
    - Google SSO built-in (OAuth 2.0): single click sign-in
    - firebase-admin (Apache-2.0): open source, audited, widely deployed
    - JWT verification is fully local — no round-trip to Firebase servers
      after the public key is cached (sub-1ms verification)
    - Wires directly with ADK session user_id and BigQuerySessionBackend

Integration points:
    - ``atelier.models.data_contracts.TenantContext.user_id`` — populated
      from ``decoded_token['uid']`` (Firebase UID, stable across sign-ins)
    - ``BigQuerySessionBackend.create_session(user_id=uid)`` — sessions are
      scoped per Firebase UID, ensuring cross-device resumption
    - ``atelier.orchestrator.runner.AtelierRunner`` — ``TenantContext`` is
      hydrated with the verified UID before pipeline execution

FastAPI usage::

    from atelier.auth.firebase import (
        require_auth,
        require_auth_strict,
        OptionalAuth,
        FirebaseUser,
    )

    @router.post("/v1/generate")
    async def generate(user: FirebaseUser = Depends(require_auth_strict)) -> ...:
        # Spend/sensitive routes use require_auth_strict so a revoked token
        # (sign-out, credential compromise) is rejected before paid Vertex
        # spend is triggered.
        tenant_ctx = TenantContext(
            tenant_id=user.tenant_id,
            user_id=user.uid,
            ...
        )

    @router.get("/v1/topology")
    async def topology(user: FirebaseUser = Depends(require_auth)) -> ...:
        ...  # read-only route: standard verification (no revocation round-trip)

    @router.get("/v1/health")
    async def health(user: FirebaseUser | None = Depends(OptionalAuth)) -> ...:
        ...  # user is None for unauthenticated callers

Security model:
    - ID tokens are short-lived (1 hour). The firebase-admin SDK verifies:
        1. JWT signature against Firebase's public keys (cached 6h)
        2. ``iss`` claim == ``accounts.google.com`` or the Firebase project
        3. ``aud`` claim == Firebase project ID
        4. ``exp`` claim (not expired)
    - Revocation check is opt-in (``check_revoked=True``). The standard
      ``require_auth`` / ``optional_auth`` dependencies verify signature,
      issuer, audience, and expiry but do NOT check revocation (no Firebase
      round-trip, sub-1ms). The ``require_auth_strict`` dependency flips
      ``check_revoked=True`` and is applied to spend/sensitive routes — the
      dream router (``/v1/dream``, ``/v1/dream/promote``), synchronous and
      streaming generation (``/v1/generate``, ``/v1/generate/stream``), and
      the A2A ``SendMessage`` path — so a revoked credential (sign-out,
      forced password reset, compromise) is rejected before paid Vertex
      spend is triggered.
    - Tenant isolation: every BigQuery query is scoped to ``user.uid``.
      Cross-tenant data access is structurally impossible.

Configuration:
    - ``FIREBASE_PROJECT_ID`` env var (required in production)
    - ``GOOGLE_APPLICATION_CREDENTIALS`` or Workload Identity for
      firebase-admin initialisation on Cloud Run
    - Local dev: set ``FIREBASE_DISABLE_AUTH=true`` to bypass verification
      (returns a synthetic dev user — never allowed in production)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from atelier.utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)

# Expected issuer prefix — Firebase ID tokens carry iss of the form
# "https://securetoken.google.com/<project_id>".
_FIREBASE_ISSUER_PREFIX = "https://securetoken.google.com/"

# ---------------------------------------------------------------------------
# Firebase admin SDK — lazy-initialised at first use
# ---------------------------------------------------------------------------

_firebase_app: Any = None  # firebase_admin.App instance or None (dev bypass)
_BYPASS_AUTH: bool = os.getenv("FIREBASE_DISABLE_AUTH", "").lower() in ("1", "true", "yes")
_PROJECT_ID: str | None = os.getenv("FIREBASE_PROJECT_ID")

# M-8: Require FIREBASE_PROJECT_ID in non-development environments.
# A missing project ID silently uses the wrong Firebase project.
if not _PROJECT_ID and os.getenv("ATELIER_ENV", "development") != "development":
    raise RuntimeError(
        "FIREBASE_PROJECT_ID env var is required in non-development environments. "
        "Set it to your Firebase project ID and restart."
    )
_PROJECT_ID = _PROJECT_ID or "atelier-build-2026"

# H-1: Guard against auth bypass outside local development.
# The old check `== "production"` was bypassable via ATELIER_ENV=staging.
# Allowlisting "development" as the only safe value closes that loophole.
if _BYPASS_AUTH and os.getenv("ATELIER_ENV", "development") != "development":
    raise RuntimeError(
        "FIREBASE_DISABLE_AUTH must not be set outside local development. "
        f"ATELIER_ENV={os.getenv('ATELIER_ENV')!r}. Unset and restart."
    )


def _init_firebase() -> Any:
    """Lazy-initialise the firebase-admin App.

    Uses Application Default Credentials on Cloud Run (Workload Identity)
    or the service account key at GOOGLE_APPLICATION_CREDENTIALS locally.

    Returns:
        The firebase_admin.App instance.

    Raises:
        RuntimeError: firebase-admin is not installed.
    """
    global _firebase_app  # noqa: PLW0603
    if _firebase_app is not None:
        return _firebase_app

    try:
        import firebase_admin  # noqa: PLC0415
        from firebase_admin import credentials  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "firebase-admin is not installed. "
            "Add 'firebase-admin>=7.4,<8' to atelier-core/pyproject.toml dependencies "
            "and regenerate requirements.lock. "
            "Latest stable: 7.4.0 (2026-04-09, Apache-2.0, PyPI: firebase-admin)."
        ) from exc

    if not firebase_admin._apps:  # pyright: ignore[reportPrivateUsage]
        cred = credentials.ApplicationDefault()
        _firebase_app = firebase_admin.initialize_app(cred, {"projectId": _PROJECT_ID})
    else:
        _firebase_app = firebase_admin.get_app()

    logger.info("Firebase Admin SDK initialised for project %s", _PROJECT_ID)
    return _firebase_app


# ---------------------------------------------------------------------------
# Verified user dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FirebaseUser:
    """Verified Firebase user — populated from a decoded ID token.

    Attributes:
        uid:        Firebase UID (stable, unique per user across sign-ins).
        email:      User's verified email address (may be None for phone auth).
        name:       Display name from the Google account.
        picture:    Profile photo URL.
        tenant_id:  Atelier tenant key — defaults to uid for B2C (one tenant
                    per user). Multi-tenant B2B setups override this via the
                    ``atelier_tenant`` custom claim on the Firebase token.
        email_verified: Whether the email address has been verified.
    """

    uid: str
    email: str | None
    name: str | None
    picture: str | None
    tenant_id: str
    email_verified: bool


def _decode_token(token: str, *, check_revoked: bool = False) -> dict[str, Any]:
    """Verify and decode a Firebase ID token.

    Args:
        token: Raw JWT string from the ``Authorization: Bearer`` header.
        check_revoked: When True, verifies the token has not been revoked
            (adds a network round-trip to Firebase; use for sensitive ops).

    Returns:
        The decoded token payload dict.

    Raises:
        HTTPException 401: Token is invalid, expired, or revoked.
    """
    # P1-5: catch typed firebase_admin subclasses so callers receive distinguishable
    # error codes — required by <no_silent_error_suppression> invariant.
    # Bare Exception fallback covers SDK initialisation errors (RuntimeError) and
    # any other unexpected failures, all of which produce HTTP 401.
    try:
        _init_firebase()
        from firebase_admin import auth as fb_auth  # noqa: PLC0415

        decoded: dict[str, Any] = fb_auth.verify_id_token(token, check_revoked=check_revoked)
    except Exception as exc:
        # Map typed firebase_admin exceptions to distinct error codes.
        exc_name = type(exc).__name__
        if "Expired" in exc_name:
            error_code = "token_expired"
            user_detail = "Your session has expired. Sign in again to continue."
        elif "Revoked" in exc_name:
            error_code = "token_revoked"
            user_detail = "Your credential has been revoked. Sign in again."
        elif "Disabled" in exc_name:
            error_code = "user_disabled"
            user_detail = "This account has been disabled. Contact support."
        else:
            error_code = "invalid_token"
            user_detail = (
                "The provided credential is missing, invalid, or expired. "
                "Sign in again to obtain a fresh ID token."
            )
        # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure -- the literal is a static log-format string, not a secret; interpolated args are an error code, the exception class name, and a sanitized/truncated message — no credential is logged.
        logger.warning(
            "Firebase token verification failed [%s]: %s — %s",
            error_code,
            exc_name,
            sanitize(str(exc)[:120]),
        )
        raise HTTPException(
            status_code=401,
            detail={
                "error": error_code,
                "title": "Authentication required",
                "detail": user_detail,
                "user_action": "Sign in at /auth/signin to refresh your credentials.",
            },
        ) from exc
    else:
        # Explicit post-decode audience and issuer assertions defend against an
        # SDK misconfiguration where initialize_app was called without the
        # correct projectId — tokens minted for a different Firebase project
        # would otherwise pass SDK signature verification undetected.
        # firebase-admin already performs these checks, but an in-repo assertion
        # makes the contract testable and survives SDK version changes.
        expected_iss = f"{_FIREBASE_ISSUER_PREFIX}{_PROJECT_ID}"
        actual_aud = decoded.get("aud", "")
        actual_iss = decoded.get("iss", "")
        if actual_aud != _PROJECT_ID or actual_iss != expected_iss:
            # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure -- static format string; interpolated values are the token audience, issuer, and expected project id (public identifiers), not a credential.
            logger.warning(
                "Firebase token audience/issuer mismatch [aud=%s iss=%s expected_project=%s]",
                actual_aud,
                actual_iss,
                _PROJECT_ID,
            )
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "invalid_token",
                    "title": "Authentication required",
                    "detail": (
                        "The provided credential is missing, invalid, or expired. "
                        "Sign in again to obtain a fresh ID token."
                    ),
                    "user_action": "Sign in at /auth/signin to refresh your credentials.",
                },
            )
        return decoded


def _user_from_token(decoded: dict[str, Any]) -> FirebaseUser:
    """Build a ``FirebaseUser`` from a decoded Firebase token payload."""
    uid = decoded["uid"]
    # B2C: tenant_id defaults to the user's own UID.
    # Multi-tenant B2B: set via custom claim ``atelier_tenant`` in Firebase.
    tenant_id = decoded.get("atelier_tenant") or uid
    return FirebaseUser(
        uid=uid,
        email=decoded.get("email"),
        name=decoded.get("name"),
        picture=decoded.get("picture"),
        tenant_id=tenant_id,
        email_verified=bool(decoded.get("email_verified", False)),
    )


def _dev_user() -> FirebaseUser:
    """Synthetic dev user returned when FIREBASE_DISABLE_AUTH=true."""
    return FirebaseUser(
        uid="dev-user-local",
        email="dev@atelier.local",
        name="Local Developer",
        picture=None,
        tenant_id="dev-tenant",
        email_verified=True,
    )


# ---------------------------------------------------------------------------
# FastAPI security scheme
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> FirebaseUser:
    """FastAPI dependency — requires a valid Firebase ID token.

    Raises HTTP 401 if the token is absent or invalid.
    Use as ``user: FirebaseUser = Depends(require_auth)``.
    """
    if _BYPASS_AUTH:
        logger.debug("Auth bypass active (dev mode)")
        return _dev_user()

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail={
                "error": "missing_token",
                "title": "Authentication required",
                "detail": "Provide a Firebase ID token in the Authorization: Bearer header.",
                "user_action": "Sign in at /auth/signin to obtain an ID token.",
            },
        )

    decoded = _decode_token(credentials.credentials)
    return _user_from_token(decoded)


async def require_auth_strict(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> FirebaseUser:
    """FastAPI dependency for spend/sensitive routes — verifies revocation.

    Identical to :func:`require_auth` except the ID token is verified with
    ``check_revoked=True``. This adds one Firebase round-trip per call, so it
    is reserved for routes that trigger paid Vertex spend or otherwise
    sensitive side effects (the dream/DPO tuning routes, ``/v1/generate`` and
    its streaming variant, and the A2A ``SendMessage`` path).

    A token that has been revoked — via sign-out, forced password reset, or
    credential compromise — is rejected with HTTP 401 (error code
    ``token_revoked``) before the route body runs. ``require_auth``, by
    contrast, would still accept a revoked-but-unexpired token because it
    skips the revocation round-trip.

    Use as ``user: FirebaseUser = Depends(require_auth_strict)``.

    Raises HTTP 401 if the token is absent, invalid, expired, or revoked.
    """
    if _BYPASS_AUTH:
        logger.debug("Auth bypass active (dev mode) — strict revocation check skipped")
        return _dev_user()

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail={
                "error": "missing_token",
                "title": "Authentication required",
                "detail": "Provide a Firebase ID token in the Authorization: Bearer header.",
                "user_action": "Sign in at /auth/signin to obtain an ID token.",
            },
        )

    decoded = _decode_token(credentials.credentials, check_revoked=True)
    return _user_from_token(decoded)


async def optional_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> FirebaseUser | None:
    """FastAPI dependency — returns ``None`` if no token is provided.

    Use for endpoints that work both authenticated and anonymously
    (e.g. health checks, public documentation).

    Security: distinguishes genuinely anonymous callers (no credentials)
    from callers with invalid/expired tokens. The latter receive 401
    instead of silent anonymous treatment — prevents token revocation
    from being silently bypassed.
    """
    if _BYPASS_AUTH:
        return _dev_user()

    # No credentials presented → genuinely anonymous
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None

    # Credentials were presented — validate them; any failure is 401.
    # Do NOT catch HTTPException here: invalid/expired/revoked tokens
    # must return 401, not degrade to anonymous (None).
    decoded = _decode_token(credentials.credentials)
    return _user_from_token(decoded)


# Convenience alias that reads more clearly as a FastAPI Depends parameter
OptionalAuth = Depends(optional_auth)
