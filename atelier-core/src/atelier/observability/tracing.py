"""OpenTelemetry tracing configuration — Cloud Trace export.

Configures the OTel TracerProvider with:
    - CloudTraceSpanExporter (Cloud Trace v2 API, auto-batched)
    - GCPResourceDetector (auto-populates service.name, cloud.* attributes)
    - BatchSpanProcessor (async flush, no request-path blocking)

Usage in lifespan::

    from atelier.observability.tracing import init_tracing

    init_tracing()  # call once at startup

Usage in instrumented code::

    from atelier.observability.tracing import get_tracer

    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("my_operation") as span:
        span.set_attribute("key", "value")

PRD Reference: §6.6 (Observability pillar)
ADR Reference: 0006 (Google-native stack, Cloud Trace)
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_TRACER_INITIALIZED = False


def init_tracing() -> None:
    """Initialize OTel TracerProvider with Cloud Trace exporter.

    Idempotent — safe to call multiple times. Only initializes once.
    In ``ATELIER_ENV=test`` or when ``OTEL_DISABLED=true``, silently
    returns a no-op setup.

    Fail-soft: if OTel SDK or Cloud Trace exporter is unavailable,
    logs a warning and returns without crashing the application.
    """
    global _TRACER_INITIALIZED  # noqa: PLW0603

    if _TRACER_INITIALIZED:
        return

    env = os.getenv("ATELIER_ENV", "development")
    if os.getenv("OTEL_DISABLED", "").lower() == "true" or env == "test":
        logger.info("OTel tracing disabled (OTEL_DISABLED=true or ATELIER_ENV=test)")
        _TRACER_INITIALIZED = True
        return

    try:
        from opentelemetry import trace  # noqa: PLC0415
        from opentelemetry.exporter.cloud_trace import (  # noqa: PLC0415
            CloudTraceSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource  # noqa: PLC0415
        from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: PLC0415

        resource = Resource.create(
            {
                "service.name": "atelier-api",
                "service.version": _get_version(),
                "deployment.environment": env,
            }
        )

        provider = TracerProvider(resource=resource)

        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "atelier-build-2026")
        exporter = CloudTraceSpanExporter(project_id=project_id)
        provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        _TRACER_INITIALIZED = True

        logger.info(
            "OTel tracing initialized (Cloud Trace exporter, project=%s)",
            project_id,
        )

    except ImportError:
        logger.warning(
            "OTel tracing not available — opentelemetry-sdk or "
            "opentelemetry-exporter-gcp-trace not installed"
        )
        _TRACER_INITIALIZED = True
    except Exception:  # noqa: BLE001
        logger.warning("OTel tracing initialization failed (fail-soft)", exc_info=True)
        _TRACER_INITIALIZED = True


def get_tracer(name: str = "atelier") -> object:
    """Get an OTel tracer instance.

    Returns the real OTel tracer if initialized, otherwise returns a
    no-op tracer that silently discards spans.

    Args:
        name: Tracer instrumentation scope name.

    Returns:
        An OTel Tracer instance (real or no-op).
    """
    try:
        from opentelemetry import trace  # noqa: PLC0415

        return trace.get_tracer(name)
    except ImportError:
        from atelier.recorders.trajectory_recorder import NoOpTracer  # noqa: PLC0415

        return NoOpTracer()


def _get_version() -> str:
    """Get the Atelier version string."""
    try:
        from atelier.__version__ import __version__  # noqa: PLC0415
    except ImportError:
        return "unknown"
    else:
        return __version__
