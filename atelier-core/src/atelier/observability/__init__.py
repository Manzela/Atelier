"""Atelier observability package — OTel spans, traces, and metrics.

Environment Configuration:
    ATELIER_OBSERVABILITY_MODE: Controls observability routing.
        - "dev"  → Phoenix (Arize) local collector for trace inspection
        - "prod" → Google Cloud Trace + Cloud Monitoring via OTel Collector

    See ADR 0006 for rationale: Phoenix is dev-only because production
    uses Cloud Trace for persistence and BigQuery for calibration dashboard
    ingestion. Running Phoenix in production would create a parallel trace
    sink that diverges from the production pipeline.

Usage:
    from atelier.observability import get_observability_mode, is_dev_mode

    mode = get_observability_mode()  # "dev" or "prod"
    if is_dev_mode():
        # configure Phoenix exporter
        ...
"""

from __future__ import annotations

import os
import warnings
from typing import Literal

ObservabilityMode = Literal["dev", "prod"]

_DEFAULT_MODE: ObservabilityMode = "dev"


def get_observability_mode() -> ObservabilityMode:
    """Return the current observability mode from environment.

    Reads ``ATELIER_OBSERVABILITY_MODE`` env var. Defaults to ``"dev"``
    if unset or set to an unrecognized value (logged as warning).

    Returns:
        ``"dev"`` or ``"prod"``.
    """
    raw = os.environ.get("ATELIER_OBSERVABILITY_MODE", _DEFAULT_MODE).lower().strip()
    if raw in ("dev", "prod"):
        return raw  # type: ignore[return-value]
    # Unrecognized value — fall back to dev with a warning.
    warnings.warn(
        f"ATELIER_OBSERVABILITY_MODE={raw!r} is not recognized. "
        f"Expected 'dev' or 'prod'. Falling back to '{_DEFAULT_MODE}'.",
        UserWarning,
        stacklevel=2,
    )
    return _DEFAULT_MODE


def is_dev_mode() -> bool:
    """Return True if observability is in development (Phoenix) mode.

    Convenience wrapper around :func:`get_observability_mode`.
    """
    return get_observability_mode() == "dev"


def is_prod_mode() -> bool:
    """Return True if observability is in production (Cloud Trace) mode.

    Convenience wrapper around :func:`get_observability_mode`.
    """
    return get_observability_mode() == "prod"
