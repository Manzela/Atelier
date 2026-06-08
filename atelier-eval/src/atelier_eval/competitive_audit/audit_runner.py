"""Main orchestrator for the competitive browser UI/UX audit.

Coordinates all capture modules (Lighthouse, error capture, screenshots)
across all products under test and generates the final markdown report.

Usage:
    python -m atelier_eval.competitive_audit.audit_runner --products all
    python -m atelier_eval.competitive_audit.audit_runner --products atelier,stitch --lighthouse-only
    python -m atelier_eval.competitive_audit.audit_runner --products lovable --output audit/2026-06-02-competitive

Design decisions:
  - Async-first with Playwright async API for concurrent captures.
  - Products are audited sequentially (not concurrently) to avoid
    resource contention skewing Lighthouse results.
  - Each product gets its own browser context to ensure isolation.
  - Auth-required products are skipped by default (--include-auth to enable).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from atelier_eval.competitive_audit.config import (
    PRODUCTS,
    AuditConfig,
    Product,
)
from atelier_eval.competitive_audit.error_capture import ErrorCaptor
from atelier_eval.competitive_audit.lighthouse_capture import (
    LighthouseCapture,
    LighthouseResult,
    capture_cwv_via_cdp,
    compute_median_lighthouse,
    evaluate_thresholds,
    run_lighthouse_cli,
)
from atelier_eval.competitive_audit.report_generator import (
    ProductAuditResult,
    generate_report,
)
from atelier_eval.competitive_audit.screenshot_capture import (
    capture_responsive_screenshots,
    capture_visual_baseline,
)

logger = logging.getLogger(__name__)

# Post-navigation stabilization time (ms).
_STABILIZATION_MS = 5000


async def audit_single_product(
    product: Product,
    config: AuditConfig,
) -> ProductAuditResult:
    """Run the full audit pipeline for a single product.

    Args:
        product: The product to audit.
        config: Audit configuration.

    Returns:
        Complete audit result for this product.
    """
    logger.info("=" * 60)
    logger.info("Auditing: %s (%s)", product.name, product.url)
    logger.info("=" * 60)

    product_dir = config.output_dir / product.name.lower().replace(" ", "-")
    product_dir.mkdir(parents=True, exist_ok=True)

    result = ProductAuditResult(product=product)

    # -- Lighthouse (runs in its own Chrome instance) ---------------------
    if config.run_lighthouse:
        lighthouse_dir = product_dir / "lighthouse"
        lighthouse_dir.mkdir(parents=True, exist_ok=True)

        runs: list[LighthouseResult] = []
        for i in range(config.lighthouse_runs):
            lh_result = await run_lighthouse_cli(
                url=product.url,
                output_dir=lighthouse_dir,
                run_index=i,
                config=config,
            )
            runs.append(lh_result)

        median_result = compute_median_lighthouse(runs)
        thresholds = evaluate_thresholds(median_result)

        result.lighthouse = LighthouseCapture(
            product=product,
            lighthouse_median=median_result,
            lighthouse_runs=runs,
            passed_thresholds=all(thresholds.values()),
            threshold_details=thresholds,
        )
        logger.info(
            "%s Lighthouse: perf=%s a11y=%s bp=%s seo=%s",
            product.name,
            median_result.performance,
            median_result.accessibility,
            median_result.best_practices,
            median_result.seo,
        )

    # -- Browser-based captures (errors, screenshots, CWV) ----------------
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=config.headless,
            args=["--no-sandbox", "--disable-gpu"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
        )
        page = await context.new_page()

        # Attach error captor.
        error_captor = ErrorCaptor()
        if config.run_error_capture:
            error_captor.attach(page)

        # Navigate.
        try:
            await page.goto(
                product.url,
                wait_until=config.navigation_wait_until,
                timeout=config.timeout_ms,
            )
        except (TimeoutError, RuntimeError):
            logger.exception("Navigation failed for %s", product.name)
            if config.run_error_capture:
                result.errors = error_captor.detach()
            await browser.close()
            return result

        # Post-load stabilization.
        await page.wait_for_timeout(_STABILIZATION_MS)

        # CWV capture.
        if config.run_lighthouse and result.lighthouse:
            cwv = await capture_cwv_via_cdp(page)
            result.lighthouse.cwv = cwv
            logger.info(
                "%s CWV: LCP=%sms CLS=%s TTFB=%sms FCP=%sms",
                product.name,
                cwv.lcp_ms,
                cwv.cls,
                cwv.ttfb_ms,
                cwv.fcp_ms,
            )

        # Error capture.
        if config.run_error_capture:
            result.errors = error_captor.detach()
            logger.info(
                "%s Errors: %d JS errors, %d warnings, %d network failures",
                product.name,
                result.errors.total_errors,
                result.errors.total_warnings,
                result.errors.total_network_failures,
            )

        # Screenshots.
        if config.run_screenshots:
            screenshots_dir = product_dir / "screenshots"
            result.screenshots = await capture_responsive_screenshots(
                page=page,
                product=product,
                output_dir=screenshots_dir,
                full_page=config.screenshot_full_page,
            )
            # Visual baseline.
            await capture_visual_baseline(
                page=page,
                product=product,
                output_dir=screenshots_dir,
            )

        await browser.close()

    return result


async def run_audit(config: AuditConfig) -> Path:
    """Run the complete competitive audit across all configured products.

    Args:
        config: Audit configuration.

    Returns:
        Path to the generated report.
    """
    config.output_dir.mkdir(parents=True, exist_ok=True)

    products = config.resolved_products
    logger.info("Starting competitive audit for %d products", len(products))

    results: list[ProductAuditResult] = []
    for product in products:
        if product.requires_auth:
            logger.warning(
                "Skipping %s (requires auth). Use --include-auth to enable.",
                product.name,
            )
            continue

        result = await audit_single_product(product, config)
        results.append(result)

    # Generate report.
    report_path = config.output_dir / "report.md"
    generate_report(results, report_path)

    logger.info("Audit complete. Report: %s", report_path)
    return report_path


def parse_args(argv: list[str] | None = None) -> AuditConfig:
    """Parse CLI arguments into an AuditConfig."""
    parser = argparse.ArgumentParser(
        description="Competitive browser UI/UX audit for Atelier vs. Tier 1 products",
    )
    parser.add_argument(
        "--products",
        default="all",
        help="Comma-separated product keys or 'all' (default: all)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory (default: audit/YYYY-MM-DD-competitive)",
    )
    parser.add_argument(
        "--lighthouse-only",
        action="store_true",
        help="Run only Lighthouse audits (skip errors/screenshots)",
    )
    parser.add_argument(
        "--screenshots-only",
        action="store_true",
        help="Run only responsive screenshots",
    )
    parser.add_argument(
        "--include-auth",
        action="store_true",
        help="Include products that require authentication",
    )
    parser.add_argument(
        "--lighthouse-runs",
        type=int,
        default=3,
        help="Number of Lighthouse runs for median (default: 3)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode (visible)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args(argv)

    # Resolve products.
    if args.products == "all":
        product_keys = list(PRODUCTS.keys())
    else:
        product_keys = [k.strip() for k in args.products.split(",")]

    # Resolve output dir (DTZ011: use tz-aware datetime).
    if args.output:
        output_dir = Path(args.output)
    else:
        today = datetime.datetime.now(datetime.UTC).date().isoformat()
        output_dir = Path("audit") / f"{today}-competitive"

    config = AuditConfig(
        product_keys=product_keys,
        output_dir=output_dir,
        run_lighthouse=not args.screenshots_only,
        run_error_capture=not args.lighthouse_only and not args.screenshots_only,
        run_screenshots=not args.lighthouse_only,
        headless=not args.headed,
        lighthouse_runs=args.lighthouse_runs,
    )

    # Handle auth-required products.
    if not args.include_auth:
        config.product_keys = [
            k for k in config.product_keys if k not in PRODUCTS or not PRODUCTS[k].requires_auth
        ]

    return config


def main() -> None:
    """CLI entry point."""
    config = parse_args()

    log_level = logging.DEBUG if "--verbose" in sys.argv or "-v" in sys.argv else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    asyncio.run(run_audit(config))


if __name__ == "__main__":
    main()
