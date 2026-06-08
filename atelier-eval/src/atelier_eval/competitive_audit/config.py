"""Product registry, thresholds, and audit configuration.

Centralises every configurable parameter for the competitive audit.
Products are defined as frozen dataclasses to prevent runtime mutation.
Thresholds are sourced from Atelier's L1 deterministic gate (methodology.md).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True)
class Product:
    """A product to be audited."""

    name: str
    url: str
    category: str
    reason: str
    requires_auth: bool = False
    auth_note: str = ""


# -- Product registry ------------------------------------------------------
# Maps to methodology.md Competitive comparative audit -> Products under test.

PRODUCTS: dict[str, Product] = {
    "atelier": Product(
        name="Atelier",
        url="https://atelier.autonomous-agent.dev",
        category="Self",
        reason="Baseline",
    ),
    "stitch": Product(
        name="Stitch",
        url="https://stitch.withgoogle.com",
        category="Google Labs",
        reason="Direct competitor (AI design canvas)",
    ),
    "lovable": Product(
        name="Lovable",
        url="https://lovable.dev",
        category="Independent",
        reason="Market leader (full-stack AI builder)",
    ),
    "v0": Product(
        name="v0",
        url="https://v0.dev",
        category="Vercel",
        reason="Production frontend standard",
    ),
    "claude_artifacts": Product(
        name="Claude Artifacts",
        url="https://claude.ai",
        category="Anthropic",
        reason="Rapid prototyping benchmark",
        requires_auth=True,
        auth_note="Requires Anthropic account login",
    ),
}


# -- Responsive breakpoints ------------------------------------------------
# From methodology.md L1 Responsive snapshot grader: 375 / 768 / 1280 / 1920 px.

RESPONSIVE_BREAKPOINTS: list[dict[str, str | int]] = [
    {"width": 375, "height": 812, "label_suffix": "mobile"},
    {"width": 768, "height": 1024, "label_suffix": "tablet"},
    {"width": 1280, "height": 800, "label_suffix": "desktop"},
    {"width": 1920, "height": 1080, "label_suffix": "desktop-hd"},
]


# -- Lighthouse thresholds -------------------------------------------------
# From methodology.md L1: Lighthouse a11y/perf/best-practices >= 90.


@dataclass(frozen=True)
class LighthouseThresholds:
    """Pass/fail thresholds for Lighthouse categories."""

    performance: int = 90
    accessibility: int = 90
    best_practices: int = 90
    seo: int = 80  # Less strict for competitor comparison


LIGHTHOUSE_THRESHOLDS = LighthouseThresholds()


# -- Core Web Vitals thresholds --------------------------------------------
# Per web.dev "good" thresholds (June 2026).


@dataclass(frozen=True)
class CWVThresholds:
    """Good / Needs Improvement boundaries for CWV metrics."""

    lcp_good_ms: int = 2500
    lcp_poor_ms: int = 4000
    cls_good: float = 0.1
    cls_poor: float = 0.25
    inp_good_ms: int = 200
    inp_poor_ms: int = 500


CWV_THRESHOLDS = CWVThresholds()


# -- Report constants ------------------------------------------------------
# Extracted from magic values per PLR2004.

MAX_ERRORS_IN_REPORT: int = 10
MAX_ERROR_TEXT_LENGTH: int = 200
MAX_URL_LENGTH_IN_REPORT: int = 100


# -- Audit configuration --------------------------------------------------


@dataclass
class AuditConfig:
    """Top-level configuration for a competitive audit run."""

    # Products to audit (keys from PRODUCTS dict, or "all").
    product_keys: Sequence[str] = field(default_factory=lambda: list(PRODUCTS.keys()))

    # Output directory for reports, screenshots, and raw data.
    output_dir: Path = field(
        default_factory=lambda: (
            Path("audit") / f"{datetime.datetime.now(datetime.UTC).date().isoformat()}-competitive"
        )
    )

    # Feature flags for selective auditing.
    run_lighthouse: bool = True
    run_error_capture: bool = True
    run_screenshots: bool = True
    run_network_profile: bool = True
    run_motion_analysis: bool = True

    # Playwright settings.
    headless: bool = True
    slow_mo_ms: int = 0
    timeout_ms: int = 30_000
    navigation_wait_until: str = "networkidle"

    # Lighthouse settings.
    lighthouse_runs: int = 3  # Median of N runs for stability.
    lighthouse_throttling: str = "simulated"  # or "devtools" or "provided"

    # Screenshot settings.
    screenshot_full_page: bool = True

    # Report settings.
    report_format: str = "markdown"  # or "json"
    include_raw_data: bool = True

    @property
    def resolved_products(self) -> list[Product]:
        """Resolve product keys to Product objects, skipping unknown keys."""
        return [PRODUCTS[key] for key in self.product_keys if key in PRODUCTS]

    def __post_init__(self) -> None:
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
