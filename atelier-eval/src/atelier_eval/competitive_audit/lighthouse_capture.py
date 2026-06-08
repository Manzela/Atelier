"""Lighthouse + Core Web Vitals capture via Chrome DevTools Protocol.

Runs Lighthouse audits programmatically (via subprocess to the `lighthouse`
CLI) and captures Core Web Vitals from the Performance Observer API.

Design decisions:
  - Uses subprocess to `npx lighthouse` rather than a Python binding because
    the Node.js Lighthouse CLI is the canonical implementation and avoids
    stale Python wrapper issues.
  - Runs N iterations (default 3) and takes the median for stability,
    per Google's own Lighthouse best practices.
  - CWV are captured separately via Playwright's CDP session for real-user
    timing data, not just Lighthouse's simulated throttling estimates.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from statistics import median
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.async_api import Page

from atelier_eval.competitive_audit.config import (
    CWV_THRESHOLDS,
    LIGHTHOUSE_THRESHOLDS,
    AuditConfig,
    Product,
)

logger = logging.getLogger(__name__)


@dataclass
class LighthouseResult:
    """Parsed result from a single Lighthouse run."""

    performance: float = 0.0
    accessibility: float = 0.0
    best_practices: float = 0.0
    seo: float = 0.0
    lcp_ms: float = 0.0
    cls: float = 0.0
    inp_ms: float = 0.0  # May be 0 if no interaction was simulated.
    raw_json_path: Path | None = None


@dataclass
class CWVResult:
    """Core Web Vitals captured via Performance Observer."""

    lcp_ms: float = 0.0
    cls: float = 0.0
    inp_ms: float = 0.0
    ttfb_ms: float = 0.0
    fcp_ms: float = 0.0


@dataclass
class LighthouseCapture:
    """Aggregated Lighthouse + CWV data for a single product."""

    product: Product
    lighthouse_median: LighthouseResult = field(default_factory=LighthouseResult)
    lighthouse_runs: list[LighthouseResult] = field(default_factory=list)
    cwv: CWVResult = field(default_factory=CWVResult)
    passed_thresholds: bool = False
    threshold_details: dict[str, bool] = field(default_factory=dict)


async def run_lighthouse_cli(
    url: str,
    output_dir: Path,
    run_index: int,
    config: AuditConfig,
) -> LighthouseResult:
    """Run a single Lighthouse audit via the CLI and parse the JSON report.

    Args:
        url: The URL to audit.
        output_dir: Directory to write the raw JSON report.
        run_index: Index of this run (for file naming).
        config: Audit configuration.

    Returns:
        Parsed LighthouseResult.
    """
    output_path = output_dir / f"lighthouse-run-{run_index}.json"

    cmd = [
        "npx",
        "-y",
        "lighthouse",
        url,
        "--output=json",
        f"--output-path={output_path}",
        "--chrome-flags=--headless=new --no-sandbox --disable-gpu",
        f"--throttling-method={config.lighthouse_throttling}",
        "--quiet",
    ]

    logger.info("Lighthouse run %d for %s", run_index, url)

    try:
        proc = subprocess.run(  # noqa: S603 — cmd is built from trusted config, not user input
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if proc.returncode != 0:
            logger.warning(
                "Lighthouse run %d returned code %d: %s",
                run_index,
                proc.returncode,
                proc.stderr[:500],
            )
    except subprocess.TimeoutExpired:
        logger.exception("Lighthouse run %d timed out for %s", run_index, url)
        return LighthouseResult()

    return _parse_lighthouse_json(output_path)


def _parse_lighthouse_json(path: Path) -> LighthouseResult:
    """Parse a Lighthouse JSON report into a LighthouseResult."""
    if not path.exists():
        logger.error("Lighthouse report not found: %s", path)
        return LighthouseResult()

    try:
        with path.open() as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        logger.exception("Failed to parse Lighthouse report %s", path)
        return LighthouseResult()

    categories = data.get("categories", {})
    audits = data.get("audits", {})

    return LighthouseResult(
        performance=_score(categories, "performance"),
        accessibility=_score(categories, "accessibility"),
        best_practices=_score(categories, "best-practices"),
        seo=_score(categories, "seo"),
        lcp_ms=_audit_numeric(audits, "largest-contentful-paint", "numericValue"),
        cls=_audit_numeric(audits, "cumulative-layout-shift", "numericValue"),
        inp_ms=_audit_numeric(audits, "interaction-to-next-paint", "numericValue"),
        raw_json_path=path,
    )


def _score(categories: dict[str, Any], key: str) -> float:
    """Extract a 0-100 score from Lighthouse categories."""
    cat = categories.get(key, {})
    raw = cat.get("score")
    if raw is None:
        return 0.0
    return round(raw * 100, 1)


def _audit_numeric(audits: dict[str, Any], audit_id: str, field_name: str) -> float:
    """Extract a numeric value from a specific Lighthouse audit."""
    audit = audits.get(audit_id, {})
    return float(audit.get(field_name, 0.0))


def compute_median_lighthouse(runs: list[LighthouseResult]) -> LighthouseResult:
    """Compute the median across N Lighthouse runs for stability."""
    if not runs:
        return LighthouseResult()

    return LighthouseResult(
        performance=median(r.performance for r in runs),
        accessibility=median(r.accessibility for r in runs),
        best_practices=median(r.best_practices for r in runs),
        seo=median(r.seo for r in runs),
        lcp_ms=median(r.lcp_ms for r in runs),
        cls=median(r.cls for r in runs),
        inp_ms=median(r.inp_ms for r in runs),
    )


async def capture_cwv_via_cdp(page: Page) -> CWVResult:
    """Capture Core Web Vitals using the Performance Observer API via CDP.

    This captures real-browser timing data, complementing Lighthouse's
    simulated throttling estimates.

    Args:
        page: Playwright page object (must already be navigated).

    Returns:
        CWVResult with real-user-timing data.
    """
    cwv_script = """
    () => {
        return new Promise((resolve) => {
            const result = {
                lcp_ms: 0,
                cls: 0,
                inp_ms: 0,
                ttfb_ms: 0,
                fcp_ms: 0,
            };

            // TTFB + FCP from Navigation / Paint timing.
            const navEntry = performance.getEntriesByType('navigation')[0];
            if (navEntry) {
                result.ttfb_ms = navEntry.responseStart;
            }
            const paintEntries = performance.getEntriesByType('paint');
            for (const entry of paintEntries) {
                if (entry.name === 'first-contentful-paint') {
                    result.fcp_ms = entry.startTime;
                }
            }

            // LCP.
            const lcpObs = new PerformanceObserver((list) => {
                const entries = list.getEntries();
                if (entries.length > 0) {
                    result.lcp_ms = entries[entries.length - 1].startTime;
                }
            });
            lcpObs.observe({ type: 'largest-contentful-paint', buffered: true });

            // CLS.
            let clsValue = 0;
            const clsObs = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (!entry.hadRecentInput) {
                        clsValue += entry.value;
                    }
                }
                result.cls = clsValue;
            });
            clsObs.observe({ type: 'layout-shift', buffered: true });

            // Resolve after 5s to capture post-load shifts.
            setTimeout(() => {
                lcpObs.disconnect();
                clsObs.disconnect();
                resolve(result);
            }, 5000);
        });
    }
    """

    try:
        data = await page.evaluate(cwv_script)
    except (TimeoutError, RuntimeError):
        logger.exception("CWV capture failed")
        return CWVResult()

    return CWVResult(
        lcp_ms=data.get("lcp_ms", 0.0),
        cls=data.get("cls", 0.0),
        inp_ms=data.get("inp_ms", 0.0),
        ttfb_ms=data.get("ttfb_ms", 0.0),
        fcp_ms=data.get("fcp_ms", 0.0),
    )


def evaluate_thresholds(result: LighthouseResult) -> dict[str, bool]:
    """Check Lighthouse results against methodology.md L1 thresholds."""
    return {
        "performance": result.performance >= LIGHTHOUSE_THRESHOLDS.performance,
        "accessibility": result.accessibility >= LIGHTHOUSE_THRESHOLDS.accessibility,
        "best_practices": result.best_practices >= LIGHTHOUSE_THRESHOLDS.best_practices,
        "seo": result.seo >= LIGHTHOUSE_THRESHOLDS.seo,
    }


def evaluate_cwv(cwv: CWVResult) -> dict[str, str]:
    """Rate CWV metrics as 'good', 'needs-improvement', or 'poor'."""

    def _rate(value: float, good: float, poor: float) -> str:
        if value <= good:
            return "good"
        if value <= poor:
            return "needs-improvement"
        return "poor"

    return {
        "lcp": _rate(cwv.lcp_ms, CWV_THRESHOLDS.lcp_good_ms, CWV_THRESHOLDS.lcp_poor_ms),
        "cls": _rate(cwv.cls, CWV_THRESHOLDS.cls_good, CWV_THRESHOLDS.cls_poor),
        "inp": _rate(cwv.inp_ms, CWV_THRESHOLDS.inp_good_ms, CWV_THRESHOLDS.inp_poor_ms),
    }
