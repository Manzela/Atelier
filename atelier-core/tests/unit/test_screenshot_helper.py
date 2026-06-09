import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from atelier.durability.screenshot_helper import capture_and_upload_screenshot


@patch("atelier.durability.screenshot_helper.upload_design_asset")
@patch("atelier.durability.screenshot_helper.sync_playwright")
def test_capture_and_upload_screenshot_success(mock_playwright, mock_upload):
    """Verify that screenshots are captured and uploaded successfully under mock conditions."""
    # Mock Playwright layout
    mock_p_instance = MagicMock()
    mock_playwright.return_value.__enter__.return_value = mock_p_instance

    mock_browser = MagicMock()
    mock_p_instance.chromium.launch.return_value = mock_browser

    # Untrusted HTML is rendered in a JS-disabled context with the network
    # blocked, so the helper goes through new_context(...).new_page() + route().
    mock_context = MagicMock()
    mock_browser.new_context.return_value = mock_context

    mock_page = MagicMock()
    mock_context.new_page.return_value = mock_page
    mock_page.screenshot.return_value = b"raw-screenshot-bytes"

    # Mock GCS upload
    mock_upload.return_value = "gs://my-bucket/tenants/tenant-123/candidates/cand-456.png"

    gcs_url = capture_and_upload_screenshot(
        tenant_id="tenant-123", candidate_id="cand-456", html="<html><body>Hello</body></html>"
    )

    assert gcs_url == "gs://my-bucket/tenants/tenant-123/candidates/cand-456.png"

    # Verify Playwright set_content and screenshot parameters
    mock_page.set_content.assert_called_once_with(
        "<html><body>Hello</body></html>", wait_until="domcontentloaded", timeout=15000
    )
    mock_page.screenshot.assert_called_once_with(type="png", full_page=True)
    mock_browser.close.assert_called_once()

    # The untrusted-HTML hardening must hold: JavaScript disabled on the context
    # and a request router installed to block non-data network access.
    mock_browser.new_context.assert_called_once_with(java_script_enabled=False)
    mock_page.route.assert_called_once()

    # Verify GCS upload was called
    mock_upload.assert_called_once()
    args, _ = mock_upload.call_args
    assert args[1] == "tenants/tenant-123/candidates/cand-456.png"
    assert isinstance(args[0], Path)


@patch("atelier.durability.screenshot_helper.sync_playwright")
def test_capture_and_upload_screenshot_fail_soft(mock_playwright):
    """Verify that failures during render or capture fail-soft and return None."""
    mock_playwright.side_effect = Exception("Playwright crash")

    gcs_url = capture_and_upload_screenshot(
        tenant_id="tenant-123", candidate_id="cand-456", html="<html></html>"
    )

    assert gcs_url is None
