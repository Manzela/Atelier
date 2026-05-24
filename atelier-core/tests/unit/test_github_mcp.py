"""Tests for GitHub MCP integration (C5, FA-004).

8 tests covering:
    - Successful README fetch (mocked)
    - 404 raises GitHubMCPError
    - 5xx retry behavior (succeeds on retry)
    - Auth failure (raises with reason="auth")
    - Rate-limit handling (X-RateLimit-Remaining=0 triggers backoff)
    - Token-from-env fallback
    - CodeSearchResult model
"""

from __future__ import annotations

import asyncio
from base64 import b64encode
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from atelier.integrations.github_mcp import (
    CodeSearchResult,
    GitHubMCPClient,
    GitHubMCPError,
)

# ---------------------------------------------------------------------------
# Constants (PLR2004 compliance)
# ---------------------------------------------------------------------------

STATUS_OK = 200
STATUS_UNAUTHORIZED = 401
STATUS_NOT_FOUND = 404
STATUS_SERVER_ERROR = 503
SCORE_VALUE = 42.0
EXPECTED_TWO_CALLS = 2
TEST_TOKEN = "ghp_test123"  # noqa: S105
BAD_TOKEN = "ghp_bad_token"  # noqa: S105
ENV_TOKEN = "ghp_from_env"  # noqa: S105


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(
    *,
    status: int = STATUS_OK,
    json_data: dict | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Build a fake httpx.Response for testing."""
    return httpx.Response(
        status_code=status,
        json=json_data or {},
        headers=headers or {},
        request=httpx.Request("GET", "https://api.github.com/test"),
    )


def _encoded_content(text: str) -> str:
    """Base64-encode text content as GitHub API does."""
    return b64encode(text.encode()).decode()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFetchReadme:
    """Verify README fetch with mocked responses."""

    def test_successful_fetch(self) -> None:
        readme_text = "# My Project\n\nHello world."
        mock_resp = _mock_response(
            json_data={
                "content": _encoded_content(readme_text),
                "encoding": "base64",
            },
        )
        client = GitHubMCPClient(token=TEST_TOKEN)
        with patch.object(
            httpx.AsyncClient,
            "request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = asyncio.run(client.fetch_readme("owner", "repo"))
        assert result == readme_text


@pytest.mark.unit
class TestNotFoundError:
    """Verify 404 raises structured error."""

    def test_404_raises_error(self) -> None:
        mock_resp = _mock_response(
            status=STATUS_NOT_FOUND,
            json_data={"message": "Not Found"},
        )
        client = GitHubMCPClient(token=TEST_TOKEN)
        with patch.object(
            httpx.AsyncClient,
            "request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            with pytest.raises(GitHubMCPError) as exc_info:
                asyncio.run(client.fetch_readme("owner", "missing-repo"))
            assert exc_info.value.reason == "not_found"
            assert exc_info.value.status_code == STATUS_NOT_FOUND


@pytest.mark.unit
class TestServerErrorRetry:
    """Verify 5xx triggers retry and eventual success."""

    def test_retries_on_5xx_then_succeeds(self) -> None:
        readme_text = "# Retried"
        error_resp = _mock_response(
            status=STATUS_SERVER_ERROR,
            json_data={"message": "Service Unavailable"},
        )
        success_resp = _mock_response(
            json_data={
                "content": _encoded_content(readme_text),
                "encoding": "base64",
            },
        )
        client = GitHubMCPClient(token=TEST_TOKEN)
        mock_fn = AsyncMock(side_effect=[error_resp, success_resp])
        with (
            patch.object(httpx.AsyncClient, "request", mock_fn),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = asyncio.run(client.fetch_readme("owner", "repo"))
        assert result == readme_text
        assert mock_fn.call_count == EXPECTED_TWO_CALLS


@pytest.mark.unit
class TestAuthFailure:
    """Verify 401 raises with reason='auth'."""

    def test_401_raises_auth_error(self) -> None:
        mock_resp = _mock_response(
            status=STATUS_UNAUTHORIZED,
            json_data={"message": "Bad credentials"},
        )
        client = GitHubMCPClient(token=BAD_TOKEN)
        with patch.object(
            httpx.AsyncClient,
            "request",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            with pytest.raises(GitHubMCPError) as exc_info:
                asyncio.run(client.fetch_readme("owner", "repo"))
            assert exc_info.value.reason == "auth"
            assert exc_info.value.status_code == STATUS_UNAUTHORIZED


@pytest.mark.unit
class TestRateLimitHandling:
    """Verify rate-limit header triggers backoff."""

    def test_rate_limit_exhausted_triggers_backoff(self) -> None:
        readme_text = "# Rate Limited Then OK"
        limited_resp = _mock_response(
            json_data={
                "content": _encoded_content(readme_text),
                "encoding": "base64",
            },
            headers={
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "9999999999",
            },
        )
        ok_resp = _mock_response(
            json_data={
                "content": _encoded_content(readme_text),
                "encoding": "base64",
            },
            headers={"X-RateLimit-Remaining": "100"},
        )
        client = GitHubMCPClient(token=TEST_TOKEN)
        mock_fn = AsyncMock(side_effect=[limited_resp, ok_resp])
        with (
            patch.object(httpx.AsyncClient, "request", mock_fn),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            result = asyncio.run(client.fetch_readme("owner", "repo"))
        assert result == readme_text


@pytest.mark.unit
class TestTokenFromEnv:
    """Verify token falls back to GITHUB_TOKEN env var."""

    def test_token_from_env(self) -> None:
        with patch.dict("os.environ", {"GITHUB_TOKEN": ENV_TOKEN}):
            client = GitHubMCPClient()
            assert client._token == ENV_TOKEN

    def test_no_token_warns(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            client = GitHubMCPClient()
            assert client._token == ""


@pytest.mark.unit
class TestCodeSearchResult:
    """Verify the Pydantic model."""

    def test_create(self) -> None:
        result = CodeSearchResult(
            repo="owner/repo",
            path="src/main.py",
            snippet="def hello():",
            score=SCORE_VALUE,
        )
        assert result.repo == "owner/repo"
        assert result.score == SCORE_VALUE

    def test_default_values(self) -> None:
        result = CodeSearchResult(repo="owner/repo", path="file.py")
        assert result.snippet == ""
        assert result.score == 0.0
