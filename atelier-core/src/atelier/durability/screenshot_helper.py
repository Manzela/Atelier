"""Screenshot helper — renders HTML using Playwright and uploads to GCS (AT-080)."""

from __future__ import annotations

import concurrent.futures
import logging
import os
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

from atelier.durability.gcs_helper import upload_design_asset

logger = logging.getLogger(__name__)

_SET_CONTENT_TIMEOUT_MS = 15_000


def _launch_args() -> list[str]:
    return ["--no-sandbox"] if os.getenv("ATELIER_ENV") == "production" else []


def _capture_screenshot_sync(html: str) -> bytes:
    """Launch Chromium, render HTML, and capture page screenshot."""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=_launch_args())
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="domcontentloaded", timeout=_SET_CONTENT_TIMEOUT_MS)
            return page.screenshot(type="png", full_page=True)
        finally:
            browser.close()


def capture_and_upload_screenshot(tenant_id: str, candidate_id: str, html: str) -> str | None:
    """Render HTML, capture a screenshot, upload to GCS, and return the GCS URI."""
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            screenshot_bytes = executor.submit(_capture_screenshot_sync, html).result()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
            tmp_file.write(screenshot_bytes)

        try:
            blob_name = f"tenants/{tenant_id}/candidates/{candidate_id}.png"
            return upload_design_asset(tmp_path, blob_name)
        finally:
            tmp_path.unlink(missing_ok=True)

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to capture or upload screenshot for candidate %s: %s (fail-soft)",
            candidate_id,
            exc,
            exc_info=True,
        )
        return None
