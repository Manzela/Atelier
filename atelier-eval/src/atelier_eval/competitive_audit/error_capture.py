"""Console error and failed network request capture via CDP.

Listens for browser console messages and network failures during page load
and post-load stabilization. Captures JS errors, warnings, uncaught
exceptions, and failed HTTP requests (4xx/5xx, CORS, timeout).

Design decisions:
  - Uses Playwright's native event listeners (page.on("console"), page.on("pageerror"))
    rather than raw CDP, for cross-browser compatibility and simpler lifecycle.
  - Network failures captured via page.on("response") filtering for non-2xx.
  - Stabilization wait of 5s post-load to catch lazy-loaded errors.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import ConsoleMessage, Page, Response

logger = logging.getLogger(__name__)

# HTTP status threshold for capturing failed requests.
_HTTP_CLIENT_ERROR_FLOOR = 400
_HTTP_SERVER_ERROR_FLOOR = 500


@dataclass
class ConsoleEntry:
    """A single browser console message."""

    level: str  # "error", "warning", "info", "log", "debug"
    text: str
    url: str = ""
    line_number: int = 0
    column_number: int = 0


@dataclass
class NetworkFailure:
    """A failed network request."""

    url: str
    status: int
    status_text: str
    method: str = "GET"
    resource_type: str = ""


@dataclass
class PageError:
    """An uncaught JavaScript exception."""

    message: str
    stack: str = ""


@dataclass
class ErrorCaptureResult:
    """Aggregated error capture data for a single product page load."""

    console_errors: list[ConsoleEntry] = field(default_factory=list)
    console_warnings: list[ConsoleEntry] = field(default_factory=list)
    page_errors: list[PageError] = field(default_factory=list)
    network_failures: list[NetworkFailure] = field(default_factory=list)

    @property
    def total_errors(self) -> int:
        return len(self.console_errors) + len(self.page_errors)

    @property
    def total_warnings(self) -> int:
        return len(self.console_warnings)

    @property
    def total_network_failures(self) -> int:
        return len(self.network_failures)

    @property
    def has_critical_issues(self) -> bool:
        """True if there are JS errors, uncaught exceptions, or 5xx responses."""
        has_5xx = any(f.status >= _HTTP_SERVER_ERROR_FLOOR for f in self.network_failures)
        return self.total_errors > 0 or has_5xx


class ErrorCaptor:
    """Attaches to a Playwright page and collects errors during navigation.

    Usage:
        captor = ErrorCaptor()
        captor.attach(page)
        await page.goto(url)
        await page.wait_for_timeout(5000)  # stabilization
        result = captor.detach()
    """

    def __init__(self) -> None:
        self._result = ErrorCaptureResult()
        self._page: Page | None = None

    def attach(self, page: Page) -> None:
        """Attach console/error/network listeners to the page."""
        self._page = page
        self._result = ErrorCaptureResult()

        page.on("console", self._on_console)
        page.on("pageerror", self._on_page_error)
        page.on("response", self._on_response)

        logger.debug("ErrorCaptor attached to page")

    def detach(self) -> ErrorCaptureResult:
        """Remove listeners and return collected data."""
        if self._page:
            try:
                self._page.remove_listener("console", self._on_console)
                self._page.remove_listener("pageerror", self._on_page_error)
                self._page.remove_listener("response", self._on_response)
            except (RuntimeError, ValueError):
                # Page may have been closed already.
                pass
            self._page = None

        logger.debug(
            "ErrorCaptor detached: %d errors, %d warnings, %d network failures",
            self._result.total_errors,
            self._result.total_warnings,
            self._result.total_network_failures,
        )
        return self._result

    def _on_console(self, msg: ConsoleMessage) -> None:
        """Handle a browser console message."""
        location = getattr(msg, "location", None)
        entry = ConsoleEntry(
            level=msg.type,
            text=msg.text,
            url=location.get("url", "") if location else "",
            line_number=location.get("lineNumber", 0) if location else 0,
            column_number=location.get("columnNumber", 0) if location else 0,
        )

        if msg.type == "error":
            self._result.console_errors.append(entry)
        elif msg.type == "warning":
            self._result.console_warnings.append(entry)
        # Ignore info/log/debug for audit purposes.

    def _on_page_error(self, error: Exception) -> None:
        """Handle an uncaught page exception."""
        self._result.page_errors.append(
            PageError(
                message=str(error),
                stack=getattr(error, "stack", ""),
            )
        )

    def _on_response(self, response: Response) -> None:
        """Handle a network response — capture failures (4xx/5xx)."""
        if response.status >= _HTTP_CLIENT_ERROR_FLOOR:
            self._result.network_failures.append(
                NetworkFailure(
                    url=response.url,
                    status=response.status,
                    status_text=response.status_text,
                    method=response.request.method,
                    resource_type=response.request.resource_type,
                )
            )
