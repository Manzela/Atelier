"""Atelier FastAPI application.

Design Principles:
    - ``GET /health`` — unauthenticated readiness/liveness probe
    - ``GET /v1/account/usage`` — authenticated budget + session usage summary
    - Structured logging (structlog) for Cloud Logging
    - GovernorBudgetExceeded -> HTTP 402 with user-readable body (Explainable AI)
    - CORS restrictive — dashboard origin only
    - All error responses follow the ``ErrorResponse`` schema for UI consumption

Cloud Run Contract:
    - Listens on ``$PORT`` (default 8080)
    - ``/health`` returns 200 for readiness/liveness probes
    - ``X-Cloud-Trace-Context`` header propagated for distributed tracing

See Also:
    - PRD §7.1 (API surface)
    - ADR 0006 (Google-native observability stack)
"""

from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Annotated, Any

import structlog
from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from atelier.__version__ import __version__
from atelier.auth.firebase import FirebaseUser, require_auth
from atelier.orchestrator.governor import GovernorBudgetExceeded

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

logger: Any = structlog.get_logger("atelier.api")


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown hooks
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: runs once at startup and once at shutdown.

    Startup:
        - Initialize structlog with JSON rendering
        - Log service metadata
        - (Future) Initialize DB connection pool, OTel provider, etc.

    Shutdown:
        - (Future) Flush telemetry, close DB connections, etc.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if os.getenv("ATELIER_ENV", "development") == "development"
            else structlog.processors.JSONRenderer(),
        ],
    )
    await logger.ainfo(
        "atelier.startup",
        version=__version__,
        env=os.getenv("ATELIER_ENV", "development"),
        port=os.getenv("PORT", "8080"),
    )
    yield
    await logger.ainfo("atelier.shutdown")


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Factory function for the FastAPI application.

    Returns a fully configured FastAPI instance with:
        - Health endpoint (unauthenticated)
        - Request timing middleware
        - CORS middleware (restrictive — dashboard origin only)
        - Structured logging via structlog
    """
    application = FastAPI(
        title="Atelier",
        description="Autonomous Design Agent — API",
        version=__version__,
        docs_url="/docs" if os.getenv("ATELIER_ENV", "development") == "development" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # --- CORS (restrictive, multi-origin) ---
    # Supports comma-separated origins for staging + production domains.
    # Default: localhost for development.
    raw_origins = os.getenv("ATELIER_DASHBOARD_ORIGIN", "http://localhost:5173")
    allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    )

    # --- Request timing middleware ---
    @application.middleware("http")
    async def add_timing_header(
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        """Add X-Process-Time header to every response."""
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed = time.perf_counter() - start
        response.headers["X-Process-Time"] = f"{elapsed:.4f}"
        return response

    # --- Global exception handler: GovernorBudgetExceeded → HTTP 402 ─────────
    # Surfaces budget-cap exhaustion as a structured, user-readable response
    # rather than a raw 500. Implements Explainable AI + Self-Serve SaaS principle:
    # the user is told exactly what happened, how much budget was consumed, and
    # what action they can take — without needing to read logs.
    @application.exception_handler(GovernorBudgetExceeded)
    async def budget_exceeded_handler(
        request: Request,
        exc: GovernorBudgetExceeded,
    ) -> JSONResponse:
        await logger.awarning(
            "atelier.budget_exceeded",
            path=str(request.url.path),
            detail=str(exc),
        )
        return JSONResponse(
            status_code=402,
            content={
                "error": "budget_cap_exceeded",
                "code": 402,
                "title": "Generation budget cap reached",
                "detail": (
                    "This request would exceed your account's generation budget cap "
                    "of $5,000. No charge was applied for this request. To continue, "
                    "review your usage in the account dashboard and contact support "
                    "to raise your cap."
                ),
                "user_action": "Review usage at /v1/account/usage or contact support.",
                "docs_url": "https://atelier.autonomous-agent.dev/docs/limits",
            },
        )

    # --- Health endpoint ──────────────────────────────────────────────────────
    @application.get(
        "/health",
        tags=["infrastructure"],
        summary="Health check for Cloud Run readiness/liveness probes",
        response_model=None,
    )
    async def health() -> dict[str, str]:
        """Return service health status and metadata.

        Unauthenticated. Used by Cloud Run readiness/liveness probes.
        """
        return {
            "status": "healthy",
            "version": __version__,
            "service": "atelier-api",
            "env": os.getenv("ATELIER_ENV", "development"),
        }

    # --- Account usage endpoint ───────────────────────────────────────────────
    # Self-serve SaaS principle: users can inspect their own budget consumption
    # without contacting support. Explainable AI: surfaces exactly what the
    # governor has spent and what the cap is.
    @application.get(
        "/v1/account/usage",
        tags=["account"],
        summary="Current generation budget usage for the authenticated user",
        response_model=None,
    )
    async def account_usage(
        user: Annotated[FirebaseUser, Depends(require_auth)],
    ) -> dict[str, Any]:
        """Return budget consumption and session summary for the authenticated account.

        Args:
            user: Verified Firebase user (from Authorization: Bearer header).

        Returns:
            budget_cap_usd: The hard per-account budget cap (PRD §7.2).
            budget_used_usd: Cumulative spend in the current runner session.
            budget_remaining_usd: Remaining before GovernorBudgetExceeded fires.
            budget_pct_used: 0.0-1.0 fraction consumed.
            warning: Human-readable alert when above 80% consumed.
        """
        # Runner is not held as app state yet (Phase 1 stateless design).
        # Phase 2 will inject a runner singleton; for now return the cap constant.
        from atelier.orchestrator.runner import BUDGET_CAP_USD  # noqa: PLC0415

        budget_cap = float(os.getenv("ATELIER_BUDGET_CAP_USD", str(BUDGET_CAP_USD)))
        # Phase-2 deferral: Runner is ephemeral; query BigQuery for real-time usage.
        budget_used = 0.0
        remaining = budget_cap - budget_used
        pct_used = budget_used / budget_cap if budget_cap > 0 else 0.0

        warning: str | None = None
        budget_warn_critical = 0.90
        budget_warn_high = 0.80
        if pct_used >= budget_warn_critical:
            warning = (
                f"You have used {pct_used * 100:.1f}% of your generation budget. "
                "Further requests may be blocked. Contact support to raise your cap."
            )
        elif pct_used >= budget_warn_high:
            warning = (
                f"You have used {pct_used * 100:.1f}% of your generation budget. "
                "Consider reviewing your usage to avoid interruptions."
            )

        return {
            "user_id": user.uid,
            "tenant_id": user.tenant_id,
            "budget_cap_usd": budget_cap,
            "budget_used_usd": round(budget_used, 4),
            "budget_remaining_usd": round(remaining, 4),
            "budget_pct_used": round(pct_used, 4),
            "warning": warning,
            "info": (
                "Budget is enforced per-runner session. The $5,000 cap prevents "
                "runaway generation costs per PRD §7.2. Unused budget does not roll over."
            ),
        }

    # --- Register API routers ─────────────────────────────────────────────────
    from atelier.api.dream import router as dream_router  # noqa: PLC0415
    from atelier.api.generate import router as generate_router  # noqa: PLC0415
    from atelier.api.replay import router as replay_router  # noqa: PLC0415

    application.include_router(generate_router)
    application.include_router(replay_router)
    application.include_router(dream_router)

    # --- Auth info endpoint (documents the Firebase sign-in flow) ─────────────
    # Self-serve SaaS principle: the API itself tells clients how to authenticate.
    @application.get(
        "/auth/signin",
        tags=["auth"],
        summary="Firebase Authentication — sign-in instructions",
        response_model=None,
    )
    async def auth_signin_info() -> dict[str, Any]:
        """Return Firebase sign-in configuration for the frontend.

        Clients use the Firebase JS SDK (https://firebase.google.com/docs/auth/web)
        to obtain an ID token, then pass it as ``Authorization: Bearer <token>``
        to all authenticated API endpoints.

        This endpoint is unauthenticated — it provides the project configuration
        and sign-in instructions needed to start the auth flow.
        """
        return {
            "auth_provider": "Firebase Authentication (Google Identity Platform)",
            "project_id": os.getenv("FIREBASE_PROJECT_ID", "atelier-build-2026"),
            "sign_in_methods": ["google.com"],
            "sdk_url": "https://www.gstatic.com/firebasejs/10/firebase-auth.js",
            "flow": [
                "1. Initialize Firebase JS SDK with the project config below.",
                "2. Call signInWithPopup(provider) or signInWithRedirect(provider).",
                "3. After sign-in, call user.getIdToken() to get a short-lived JWT.",
                "4. Pass the JWT as 'Authorization: Bearer <token>' on every API request.",
                "5. Tokens expire after 1 hour. Call user.getIdToken(true) to refresh.",
            ],
            "firebase_config": {
                "projectId": os.getenv("FIREBASE_PROJECT_ID", "atelier-build-2026"),
                "authDomain": f"{os.getenv('FIREBASE_PROJECT_ID', 'atelier-build-2026')}.firebaseapp.com",
                "note": "Full config (apiKey, storageBucket, etc.) is served by the dashboard at /auth/config.js",
            },
        }

    return application


# ---------------------------------------------------------------------------
# Module-level app instance (for uvicorn)
# ---------------------------------------------------------------------------

app = create_app()
