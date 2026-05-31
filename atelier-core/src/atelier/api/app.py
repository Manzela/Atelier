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
from typing import TYPE_CHECKING, Any

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from atelier.__version__ import __version__
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

    # Initialize OpenTelemetry tracing (Cloud Trace export)
    from atelier.observability.tracing import init_tracing  # noqa: PLC0415

    init_tracing()

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
        In production, strips ``env`` and ``version`` to reduce information
        exposure (M-4).
        """
        resp: dict[str, str] = {"status": "healthy", "service": "atelier-api"}
        if os.getenv("ATELIER_ENV", "development") == "development":
            resp["version"] = __version__
            resp["env"] = os.getenv("ATELIER_ENV", "development")
        return resp

    # Legacy USD /v1/account/usage endpoint removed here (matching phase/2): the
    # per-RUN USD budget surface is the legacy path PRD v2.2 AT-095 deletes. The
    # token-based usage surface is rebuilt by AT-095/AT-096 (token meter) in Phase C.

    # --- Register API routers ─────────────────────────────────────────────────
    from atelier.api.a2a import router as a2a_router  # noqa: PLC0415
    from atelier.api.dream import router as dream_router  # noqa: PLC0415
    from atelier.api.generate import router as generate_router  # noqa: PLC0415
    from atelier.api.replay import router as replay_router  # noqa: PLC0415

    application.include_router(generate_router)
    application.include_router(replay_router)
    application.include_router(dream_router)
    application.include_router(a2a_router)

    # --- A2A v1.0 agent card discovery ────────────────────────────────────────
    # Serves the agent card at the canonical well-known path for A2A discovery.
    # Cache-Control allows CDN caching (1 hour) per A2A v1.0 best practices.
    import json  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    @application.get(
        "/.well-known/agent-card.json",
        tags=["a2a"],
        summary="A2A v1.0 agent card for discovery",
        response_model=None,
    )
    async def agent_card() -> Response:
        """Serve the A2A v1.0 agent card for agent-to-agent discovery.

        The agent card describes Atelier's capabilities, supported interfaces,
        authentication schemes, and skills per the A2A v1.0 specification.
        """
        # Resolve agent_card.json relative to the repo root
        card_path = Path(__file__).resolve().parents[3] / "agent_card.json"
        if not card_path.exists():
            # Fallback: serve a minimal card
            card_data = {
                "name": "Atelier",
                "version": __version__,
                "description": "Autonomous UI/UX design agent",
                "supportedInterfaces": [],
            }
        else:
            card_data = json.loads(card_path.read_text(encoding="utf-8"))

        return JSONResponse(
            content=card_data,
            headers={"Cache-Control": "public, max-age=3600"},
        )

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
