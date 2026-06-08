"""Responsive breakpoint screenshots and visual baseline capture.

Captures full-page screenshots at the 4 methodology-defined breakpoints
(375/768/1280/1920) for each product under test. Screenshots are saved
as PNG files with deterministic naming for reproducible comparison.

Design decisions:
  - Uses Playwright's set_viewport_size + screenshot rather than device
    emulation, because we want pure viewport width testing (no UA spoofing).
  - Full-page screenshots are default to capture below-the-fold content.
  - File naming convention: {product}_{breakpoint}_{timestamp}.png
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from playwright.async_api import Page

from atelier_eval.competitive_audit.config import RESPONSIVE_BREAKPOINTS, Product

logger = logging.getLogger(__name__)

# Layout settle times (ms) after viewport change.
_VIEWPORT_SETTLE_MS = 1000
_BASELINE_SETTLE_MS = 2000


@dataclass
class ScreenshotResult:
    """Result of a screenshot capture at a single breakpoint."""

    product_name: str
    breakpoint_label: str
    width: int
    height: int
    file_path: Path
    file_size_bytes: int = 0


@dataclass
class ScreenshotCaptureResult:
    """All screenshots for a single product."""

    product: Product
    screenshots: list[ScreenshotResult] = field(default_factory=list)

    @property
    def all_captured(self) -> bool:
        return len(self.screenshots) == len(RESPONSIVE_BREAKPOINTS)


async def capture_responsive_screenshots(
    page: Page,
    product: Product,
    output_dir: Path,
    *,
    full_page: bool = True,
    breakpoints: Sequence[dict[str, str | int]] | None = None,
    timestamp_suffix: str = "",
) -> ScreenshotCaptureResult:
    """Capture screenshots at each responsive breakpoint.

    Args:
        page: Playwright page (must already be navigated to the product URL).
        product: The product being audited.
        output_dir: Directory to save screenshot PNGs.
        full_page: Whether to capture the full scrollable page.
        breakpoints: Override breakpoints (default: RESPONSIVE_BREAKPOINTS).
        timestamp_suffix: Optional suffix for file naming.

    Returns:
        ScreenshotCaptureResult with paths to all captured screenshots.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    bp_list = breakpoints or RESPONSIVE_BREAKPOINTS
    result = ScreenshotCaptureResult(product=product)

    for bp in bp_list:
        width = int(bp["width"])
        height = int(bp["height"])
        label = str(bp.get("label_suffix", f"{width}px"))
        sanitized_name = product.name.lower().replace(" ", "-")

        filename = f"{sanitized_name}_{label}"
        if timestamp_suffix:
            filename += f"_{timestamp_suffix}"
        filename += ".png"

        file_path = output_dir / filename

        logger.info(
            "Capturing %s at %dx%d -> %s",
            product.name,
            width,
            height,
            file_path,
        )

        try:
            await page.set_viewport_size({"width": width, "height": height})
            # Wait for layout to settle after viewport change.
            await page.wait_for_timeout(_VIEWPORT_SETTLE_MS)

            await page.screenshot(
                path=str(file_path),
                full_page=full_page,
                type="png",
            )
        except (TimeoutError, RuntimeError):
            logger.exception(
                "Screenshot failed for %s at %dx%d",
                product.name,
                width,
                height,
            )
        else:
            file_size = file_path.stat().st_size if file_path.exists() else 0
            result.screenshots.append(
                ScreenshotResult(
                    product_name=product.name,
                    breakpoint_label=label,
                    width=width,
                    height=height,
                    file_path=file_path,
                    file_size_bytes=file_size,
                )
            )

    return result


async def capture_visual_baseline(
    page: Page,
    product: Product,
    output_dir: Path,
) -> Path | None:
    """Capture a single 1280x800 baseline screenshot for visual regression.

    This is the reference image used for cross-product visual comparison.

    Args:
        page: Playwright page (must already be navigated).
        product: The product being audited.
        output_dir: Directory to save the baseline PNG.

    Returns:
        Path to the baseline screenshot, or None on failure.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    sanitized_name = product.name.lower().replace(" ", "-")
    baseline_path = output_dir / f"{sanitized_name}_baseline.png"

    try:
        await page.set_viewport_size({"width": 1280, "height": 800})
        await page.wait_for_timeout(_BASELINE_SETTLE_MS)
        await page.screenshot(
            path=str(baseline_path),
            full_page=False,  # Above-the-fold only for baseline.
            type="png",
        )
    except (TimeoutError, RuntimeError):
        logger.exception("Baseline capture failed for %s", product.name)
        return None
    else:
        logger.info("Baseline captured: %s", baseline_path)
        return baseline_path
