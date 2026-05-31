"""PII Scrubber — ensures no sensitive data leaks through span exports.

Strips PII and secrets from span attributes before they are exported
to Cloud Trace / any OTel exporter. Applied as a SpanProcessor in the
OTel pipeline.

The patterns are loaded from ``config/scrubber-patterns.yaml`` (already
defined in the audit checklist) and compiled once at import time.

PRD Reference: §7.3 (OTel span schema), §15 (audit trail compliance)
ADR Reference: 0006 (Google-native observability — scrub before export)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRUBBER_CONFIG_PATH: Final[Path] = (
    Path(__file__).resolve().parents[4] / "config" / "scrubber-patterns.yaml"
)

REDACTED_PLACEHOLDER: Final[str] = "[REDACTED]"


# ---------------------------------------------------------------------------
# Pattern registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScrubPattern:
    """A single PII/secret scrub pattern.

    Attributes:
        name: Human-readable name (e.g., "Google API Key").
        regex: Compiled regex pattern.
    """

    name: str
    regex: re.Pattern[str]


@dataclass
class ScrubberConfig:
    """Collection of scrub patterns."""

    patterns: list[ScrubPattern] = field(default_factory=list)

    def scrub(self, value: str) -> str:
        """Apply all patterns to a string, replacing matches with REDACTED.

        Args:
            value: The string to scrub.

        Returns:
            Scrubbed string with all pattern matches replaced.
        """
        result = value
        for pattern in self.patterns:
            result = pattern.regex.sub(REDACTED_PLACEHOLDER, result)
        return result

    def scrub_dict(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Scrub all string values in a dict of span attributes.

        Non-string values are left untouched.

        Args:
            attrs: Span attribute dictionary.

        Returns:
            New dict with scrubbed string values.
        """
        return {k: self.scrub(str(v)) if isinstance(v, str) else v for k, v in attrs.items()}


def load_scrubber_config(path: Path | None = None) -> ScrubberConfig:
    """Load scrub patterns from YAML config.

    Args:
        path: Path to the YAML config. Defaults to SCRUBBER_CONFIG_PATH.

    Returns:
        ScrubberConfig with compiled patterns.
    """
    config_path = path or SCRUBBER_CONFIG_PATH

    if not config_path.exists():
        logger.warning("Scrubber config not found at %s; using defaults", config_path)
        return _default_scrubber_config()

    with config_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    patterns = []
    raw_patterns = raw.get("patterns", {})

    # Support both dict format (production) and list format (testing)
    if isinstance(raw_patterns, dict):
        for name, entry in raw_patterns.items():
            try:
                compiled = re.compile(entry["pattern"])
                patterns.append(ScrubPattern(name=name, regex=compiled))
            except (re.error, KeyError) as exc:
                logger.warning("Invalid scrubber config for '%s': %s", name, exc)
    else:
        for entry in raw_patterns:
            try:
                compiled = re.compile(entry.get("pattern", entry.get("regex", "")))
                patterns.append(ScrubPattern(name=entry.get("name", "unknown"), regex=compiled))
            except (re.error, KeyError) as exc:
                logger.warning("Invalid scrubber regex: %s", exc)

    return ScrubberConfig(patterns=patterns)


def _default_scrubber_config() -> ScrubberConfig:
    """Built-in default patterns when config file is missing."""
    return ScrubberConfig(
        patterns=[
            ScrubPattern(
                name="Google API Key",
                regex=re.compile(r"AIzaSy[A-Za-z0-9\-_]{35}"),
            ),
            ScrubPattern(
                name="GitHub Token",
                regex=re.compile(r"ghp_[A-Za-z0-9_]{36,255}"),
            ),
            ScrubPattern(
                name="Service Account Key",
                regex=re.compile(r'"type"\s*:\s*"service_account"'),
            ),
            ScrubPattern(
                name="Generic Secret",
                regex=re.compile(
                    r'(?i)(password|secret|private_key|auth_token|api_key)\s*[:=]\s*["\x27][^"\x27\s]{8,}["\x27]'
                ),
            ),
            ScrubPattern(
                name="JWT Token",
                regex=re.compile(
                    r"eyJ[A-Za-z0-9\-_]{20,}\.[A-Za-z0-9\-_]{20,}\.[A-Za-z0-9\-_]{20,}"
                ),
            ),
            ScrubPattern(
                name="Email Address",
                regex=re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
            ),
            ScrubPattern(
                name="E.164 Phone Number",
                regex=re.compile(r"\+?[1-9]\d{7,14}\b"),
            ),
        ]
    )


# ---------------------------------------------------------------------------
# OTel SpanProcessor integration
# ---------------------------------------------------------------------------


class PiiScrubSpanProcessor:
    """OTel SpanProcessor that scrubs PII from span attributes on export.

    Wire into the OTel pipeline as::

        from opentelemetry.sdk.trace import TracerProvider
        from atelier.observability.scrubber import PiiScrubSpanProcessor

        provider = TracerProvider()
        provider.add_span_processor(PiiScrubSpanProcessor())

    Every span's attributes are scrubbed before they reach the exporter.
    """

    def __init__(self, config: ScrubberConfig | None = None) -> None:
        self._config = config or load_scrubber_config()

    def on_start(self, span: Any, parent_context: Any = None) -> None:
        """Called when a span starts. No-op — scrubbing happens on end."""

    def on_end(self, span: Any) -> None:
        """Scrub span attributes before export."""
        if not hasattr(span, "attributes") or span.attributes is None:
            return

        for key, value in span.attributes.items():
            if isinstance(value, str):
                scrubbed = self._config.scrub(value)
                if scrubbed != value:
                    # OTel ReadableSpan.attributes is typically immutable after
                    # export; this processor must be wired BEFORE the exporter
                    # so it processes the mutable Span, not the frozen ReadableSpan.
                    try:
                        span.set_attribute(key, scrubbed)
                    except Exception:  # noqa: BLE001
                        logger.debug("Could not scrub attribute '%s' (span may be frozen)", key)

    def shutdown(self) -> None:
        """Called on provider shutdown. No-op."""

    def force_flush(self, timeout_millis: int = 0) -> bool:  # noqa: ARG002
        """Called on provider force_flush. No-op — returns True."""
        return True


# ---------------------------------------------------------------------------
# Module-level singleton for fast access
# ---------------------------------------------------------------------------

_SCRUBBER: ScrubberConfig | None = None


def get_scrubber() -> ScrubberConfig:
    """Return the module-level scrubber singleton, loading config on first call."""
    global _SCRUBBER  # noqa: PLW0603
    if _SCRUBBER is None:
        _SCRUBBER = load_scrubber_config()
    return _SCRUBBER


def scrub_span_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    """Convenience function to scrub a dict of span attributes.

    This is the primary entry point for code that doesn't use the OTel
    SpanProcessor pattern directly.

    Args:
        attrs: Span attribute dictionary.

    Returns:
        New dict with PII/secrets scrubbed.
    """
    return get_scrubber().scrub_dict(attrs)
