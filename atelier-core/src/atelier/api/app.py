"""Atelier FastAPI application — API skeleton + health endpoint.

Design Principles:
    - **Health endpoint**: ``GET /health`` — unauthenticated, returns service metadata
    - **Structured logging**: ``structlog`` JSON output for Cloud Logging integration
    - **OpenTelemetry**: Middleware wired to OTLP exporter (configured via env vars)
    - **CORS**: Disabled by default; enabled per-route for dashboard origin only
    - **Lifespan**: async context manager for startup/shutdown hooks (DB pool, etc.)

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

from atelier.__version__ import __version__

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

    # --- CORS (restrictive) ---
    dashboard_origin = os.getenv("ATELIER_DASHBOARD_ORIGIN", "http://localhost:5173")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[dashboard_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
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

    # --- Health endpoint ---
    @application.get(
        "/health",
        tags=["infrastructure"],
        summary="Health check for Cloud Run readiness/liveness probes",
        response_model=None,
    )
    async def health() -> dict[str, str]:
        """Return service health status and metadata.

        This endpoint is unauthenticated and used by:
            - Cloud Run readiness probe
            - Cloud Run liveness probe
            - Monitoring systems (uptime checks)

        Returns:
            JSON with status, version, and environment.
        """
        return {
            "status": "healthy",
            "version": __version__,
            "service": "atelier-api",
            "env": os.getenv("ATELIER_ENV", "development"),
        }

    return application


# ---------------------------------------------------------------------------
# Module-level app instance (for uvicorn)
# ---------------------------------------------------------------------------

app = create_app()
