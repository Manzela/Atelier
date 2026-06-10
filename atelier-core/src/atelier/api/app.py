"""Atelier FastAPI application.

Design Principles:
    - ``GET /health`` — unauthenticated readiness/liveness probe
    - Structured logging (structlog) for Cloud Logging
    - GovernorTokenCapExceeded -> HTTP 402 with the branded usage-limit body (AT-095)
    - GovernorRateLimitExceeded -> HTTP 429 (AT-095/097 quota-DoS guard)
    - GovernorCircuitBreakerOpen -> HTTP 503 + Retry-After (AT-097 fleet breaker)
    - GovernorUsageUnavailable -> HTTP 503 + Retry-After (AT-095 fail-closed)
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
from atelier.models.model_armor_callbacks import ModelArmorInputBlocked
from atelier.orchestrator.governor import (
    CIRCUIT_BREAKER_MESSAGE,
    TOKEN_CAP_MESSAGE,
    USAGE_UNAVAILABLE_MESSAGE,
    GovernorCircuitBreakerOpen,
    GovernorRateLimitExceeded,
    GovernorTokenCapExceeded,
    GovernorUsageUnavailable,
)
from atelier.utils.log_sanitizer import sanitize

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
    # S7 hardening: validate the operator-set ATELIER_JUDGE_MODE here, at
    # startup, so a non-canonical value fails LOUD and EARLY (a clear boot-time
    # error the verify-before-shift health check catches) instead of latently
    # 500-ing every generation request in production. A normalized whitespace/
    # case typo passes; genuine garbage raises and the revision never takes
    # traffic.
    from atelier.nodes.llm_judge import validate_judge_mode_env  # noqa: PLC0415

    judge_mode = validate_judge_mode_env()

    await logger.ainfo(
        "atelier.startup",
        version=__version__,
        env=os.getenv("ATELIER_ENV", "development"),
        port=os.getenv("PORT", "8080"),
        judge_mode=judge_mode,
    )

    # Initialize OpenTelemetry tracing (Cloud Trace export)
    from atelier.observability.tracing import init_tracing  # noqa: PLC0415

    init_tracing()

    # Warm the Firebase Remote Config model-routing cache once, here. The
    # hot-path calibrate_model() then reads it synchronously — no per-lookup
    # network call. Fully fail-soft: a Remote Config outage leaves the pinned
    # TASK_MODEL_ROUTING table in effect and never blocks startup.
    from atelier.models.model_registry import warm_remote_config_routes  # noqa: PLC0415

    await warm_remote_config_routes()

    yield
    await logger.ainfo("atelier.shutdown")


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:  # noqa: C901, PLR0915 — handler-registration factory: statement/branch count grows one per exception handler (inherent, not accidental complexity)
    """Factory function for the FastAPI application.

    Returns a fully configured FastAPI instance with:
        - Health endpoint (unauthenticated)
        - Request timing middleware
        - CORS middleware (restrictive — dashboard origin only)
        - Structured logging via structlog
    """
    _is_dev = os.getenv("ATELIER_ENV", "development") == "development"
    application = FastAPI(
        title="Atelier",
        description="Autonomous Design Agent — API",
        version=__version__,
        # S9 hardening: the interactive docs AND the raw OpenAPI schema are
        # development-only. FastAPI serves /openapi.json by default even when
        # docs_url is None, which would publish the full route/parameter surface
        # of a paid, authenticated production API — so openapi_url is gated too.
        docs_url="/docs" if _is_dev else None,
        redoc_url=None,
        openapi_url="/openapi.json" if _is_dev else None,
        lifespan=lifespan,
    )

    # --- CORS (restrictive, multi-origin) ---
    # Supports comma-separated origins for staging + production domains.
    # Default: localhost for development.
    # F-06 hardening: reject wildcard and non-URL origins outside development.
    raw_origins = os.getenv(
        "ATELIER_DASHBOARD_ORIGIN", "http://localhost:5173,http://localhost:3000"
    )
    allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    if not _is_dev:
        for origin in allowed_origins:
            if origin == "*":
                raise RuntimeError(
                    "ATELIER_DASHBOARD_ORIGIN='*' is forbidden outside development. "
                    "Set explicit dashboard origin(s) and restart."
                )
            if not origin.startswith(("http://", "https://")):
                raise RuntimeError(
                    f"ATELIER_DASHBOARD_ORIGIN contains non-URL origin: {origin!r}. "
                    "Origins must start with http:// or https://."
                )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    )

    # --- Response headers middleware (timing + transport security) ---
    @application.middleware("http")
    async def add_response_headers(
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        """Stamp timing + baseline security headers on every response.

        S4 hardening: the API is reachable both through Cloudflare
        (api.atelier.autonomous-agent.dev) and directly on its *.run.app host.
        Setting HSTS at the origin guarantees the directive is present on the
        direct host too, not only at the edge. ``nosniff`` blocks content-type
        sniffing on the JSON error/agent-card bodies. These are added
        unconditionally — the service is TLS-only in every deployed environment.
        """
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed = time.perf_counter() - start
        response.headers["X-Process-Time"] = f"{elapsed:.4f}"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    # --- Global exception handler: GovernorTokenCapExceeded → HTTP 402 ────────
    # AT-095 (§13.2): the per-user lifetime 5M-token cap is a FAIL-LOUD security
    # control on a public, paid endpoint. The breach is logged at error level with
    # the alertable context (uid / session / client IP / which cap) AND surfaced to
    # the user as the single branded message — never a raw quota error or 500.
    @application.exception_handler(GovernorTokenCapExceeded)
    async def token_cap_exceeded_handler(
        request: Request,
        exc: GovernorTokenCapExceeded,
    ) -> JSONResponse:
        client_ip = exc.client_ip or (request.client.host if request.client else None)
        await logger.aerror(
            "atelier.token_cap_exceeded",
            path=str(request.url.path),
            uid=sanitize(str(exc.uid)),
            session_id=sanitize(str(exc.session_id)) if exc.session_id else None,
            client_ip=sanitize(str(client_ip)) if client_ip else None,
            which_cap=exc.which_cap,
            used_tokens=exc.used_tokens,
            cap_tokens=exc.cap_tokens,
        )
        return JSONResponse(
            status_code=402,
            content={
                "error": "token_cap_exhausted",
                "code": 402,
                "title": "Account usage limit reached",
                "detail": TOKEN_CAP_MESSAGE,
                "user_action": "Contact administrator to continue.",
                "docs_url": "https://atelier.autonomous-agent.dev/docs/limits",
            },
        )

    # --- Global exception handler: ModelArmorInputBlocked → HTTP 422 ──────────
    # A prompt-injection brief that Model Armor blocked at the N1 parse boundary.
    # The non-streaming /v1/generate path would otherwise 500 on the downstream
    # JSON "Parse failure"; fail LOUD but HONESTLY with the branded safety message
    # (the streaming path emits the same message as a degraded+complete event).
    # 422 Unprocessable Content: the input was well-formed HTTP but semantically
    # rejected by the safety guard.
    @application.exception_handler(ModelArmorInputBlocked)
    async def model_armor_input_blocked_handler(
        request: Request,
        exc: ModelArmorInputBlocked,
    ) -> JSONResponse:
        await logger.awarning(
            "atelier.input_blocked",
            path=str(request.url.path),
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": "input_blocked",
                "code": 422,
                "title": "Request blocked by safety guard",
                "detail": exc.user_message,
                "user_action": "Revise the brief to describe the design you want, then resubmit.",
            },
        )

    # --- Global exception handler: GovernorUsageUnavailable → HTTP 503 ───────
    # AT-095: the usage store could not be read/written (transient outage or a
    # corrupt counter). We fail CLOSED (deny — a paid endpoint must not run
    # without a working cap guard) but acknowledge HONESTLY: a transient,
    # retryable fault, NOT a cap breach (PRD §21). RFC 9110 §15.6.4 — 503 +
    # Retry-After is the correct status for a dependency-unavailable deny.
    @application.exception_handler(GovernorUsageUnavailable)
    async def usage_unavailable_handler(
        request: Request,
        exc: GovernorUsageUnavailable,
    ) -> JSONResponse:
        client_ip = exc.client_ip or (request.client.host if request.client else None)
        await logger.aerror(
            "atelier.usage_unavailable",
            path=str(request.url.path),
            uid=sanitize(str(exc.uid)),
            client_ip=sanitize(str(client_ip)) if client_ip else None,
            reason=exc.reason,
        )
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": "30"},
            content={
                "error": "usage_unavailable",
                "code": 503,
                "title": "Service temporarily unavailable",
                "detail": USAGE_UNAVAILABLE_MESSAGE,
                "user_action": "Please retry shortly.",
            },
        )

    # --- Global exception handler: GovernorRateLimitExceeded → HTTP 429 ───────
    # AT-095/097: guards against burning the lifetime cap in seconds. The client
    # may retry after the window; the rejection is logged for abuse monitoring.
    @application.exception_handler(GovernorRateLimitExceeded)
    async def rate_limit_exceeded_handler(
        request: Request,
        exc: GovernorRateLimitExceeded,
    ) -> JSONResponse:
        client_ip = exc.client_ip or (request.client.host if request.client else None)
        await logger.awarning(
            "atelier.rate_limit_exceeded",
            path=str(request.url.path),
            uid=sanitize(str(exc.uid)),
            client_ip=sanitize(str(client_ip)) if client_ip else None,
            max_requests=exc.max_requests,
            window_seconds=exc.window_seconds,
        )
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(int(exc.window_seconds))},
            content={
                "error": "rate_limited",
                "code": 429,
                "title": "Too many requests",
                "detail": (
                    "Too many generation requests in a short window. "
                    "Please wait a moment and try again."
                ),
                "user_action": "Retry after a short pause.",
            },
        )

    # --- Global exception handler: GovernorCircuitBreakerOpen → HTTP 503 ──────
    # AT-097: the fleet-wide (per-total) token circuit-breaker tripped — aggregate
    # consumption across ALL users crossed the operator-set budget, so new work is
    # paused for a cooldown to protect the shared paid key. This is a SYSTEM
    # protection, NOT a per-user fault, so it is surfaced as a retryable 503 +
    # Retry-After with its own message — never the per-user "you reached your
    # limit" (402) body. Logged at error level for fleet-protection alerting.
    @application.exception_handler(GovernorCircuitBreakerOpen)
    async def circuit_breaker_open_handler(
        request: Request,
        exc: GovernorCircuitBreakerOpen,
    ) -> JSONResponse:
        client_ip = exc.client_ip or (request.client.host if request.client else None)
        await logger.aerror(
            "atelier.circuit_breaker_open",
            path=str(request.url.path),
            client_ip=sanitize(str(client_ip)) if client_ip else None,
            reason=exc.reason,
            window_tokens=exc.window_tokens,
            budget=exc.budget,
            retry_after_seconds=exc.retry_after_seconds,
        )
        return JSONResponse(
            status_code=503,
            headers={"Retry-After": str(int(exc.retry_after_seconds))},
            content={
                "error": "circuit_breaker_open",
                "code": 503,
                "title": "Service temporarily unavailable",
                "detail": CIRCUIT_BREAKER_MESSAGE,
                "user_action": "Please retry shortly.",
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
    from atelier.api.evaluate import router as evaluate_router  # noqa: PLC0415
    from atelier.api.generate import router as generate_router  # noqa: PLC0415
    from atelier.api.generate import stop_router  # noqa: PLC0415
    from atelier.api.platform import router as platform_router  # noqa: PLC0415
    from atelier.api.replay import router as replay_router  # noqa: PLC0415

    application.include_router(generate_router)
    application.include_router(stop_router)  # AT-026 (R13): POST /v1/stop/{session_id}
    application.include_router(replay_router)
    application.include_router(dream_router)
    application.include_router(evaluate_router)  # AT-027: POST /v1/evaluate
    application.include_router(a2a_router)
    application.include_router(platform_router)  # Phase B: GET /v1/platform/* (read-only)

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

    # --- Per-agent A2A 0.3.0 AgentCard well-known endpoints ──────────────────
    # Serves GET /.well-known/agents/{agent_id}/agent-card.json for every agent
    # in the registry.  Cards are generated from the same live registry that
    # drives /v1/platform/agents — single source, zero drift.
    #
    # Fail-soft: an unknown agent_id returns {"available": false, ...} with
    # HTTP 200 (mirrors the platform.py pattern).  An unexpected card-build
    # error also returns a soft 200 body (never a 500 or raw exception string).
    #
    # GET-only, unauthenticated (A2A discovery is a public well-known surface).
    # Cache-Control: public, max-age=3600 — same as the top-level card.
    @application.get(
        "/.well-known/agents/{agent_id}/agent-card.json",
        tags=["a2a"],
        summary="Per-agent A2A 0.3.0 AgentCard",
        response_model=None,
    )
    async def per_agent_card(agent_id: str) -> Response:
        """Serve the A2A 0.3.0 AgentCard for one specific Atelier agent.

        Cards are generated from the live agent registry (single source of
        truth — the committed artifacts under agent_cards/ are the drift guard).
        Unknown agent_id values return a fail-soft ``{"available": false}``
        body with HTTP 200 rather than a 404, consistent with the platform
        surface convention.
        """
        from atelier.orchestrator.agent_cards import build_agent_cards  # noqa: PLC0415
        from atelier.orchestrator.agent_registry import get_agent_registry  # noqa: PLC0415

        try:
            registry = get_agent_registry()
            cards = build_agent_cards(registry)
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                content={
                    "available": False,
                    "reason": type(exc).__name__,
                },
                headers={"Cache-Control": "no-store"},
            )

        card = cards.get(agent_id)
        if card is None:
            return JSONResponse(
                content={
                    "available": False,
                    "reason": "agent_not_found",
                    "requested_id": agent_id,
                },
                headers={"Cache-Control": "no-store"},
            )

        return JSONResponse(
            content=card,
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
