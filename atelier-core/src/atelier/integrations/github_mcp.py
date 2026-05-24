"""GitHub MCP Integration — Repository content retrieval for WRAI.

Wraps GitHub's REST API v3 into a typed async Python interface for
the Web-Research-Augmented Intake (N14) node. Enables the WRAI agent
to fetch READMEs, search code, and retrieve file contents from
reference repositories during the PIP intake phase.

Uses ``httpx`` (already in deps) for HTTP. Does NOT use ``PyGithub``
or ``gidgethub`` — per ``<lockfile_only_installs>``, no new deps
without ADR + lockfile regen + Snyk scan.

Auth: ``GITHUB_TOKEN`` env var or constructor ``token`` param.

PRD Reference: section 6.3 (N14 WRAI), section 15 (research flow)
Audit Reference: C5 (FA-004 GitHub MCP wrapper)
ADR Reference: 0011 (Web-Research-Augmented Intake)
"""

from __future__ import annotations

import asyncio
import logging
import os
from base64 import b64decode
from typing import Any

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (PLR2004 compliance)
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://api.github.com"
MAX_RETRY_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_MULTIPLIER = 2.0
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_RATE_LIMITED = 429
HTTP_SERVER_ERROR_START = 500
DEFAULT_SEARCH_LIMIT = 10
RATE_LIMIT_REMAINING_HEADER = "X-RateLimit-Remaining"
RATE_LIMIT_RESET_HEADER = "X-RateLimit-Reset"


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class GitHubMCPError(Exception):
    """Structured error from the GitHub MCP integration.

    Attributes:
        reason: Error classification for programmatic handling.
        status_code: HTTP status code (if applicable).
        detail: Human-readable detail message.
    """

    def __init__(
        self,
        message: str,
        *,
        reason: str = "unknown",
        status_code: int | None = None,
        detail: str = "",
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.status_code = status_code
        self.detail = detail


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class CodeSearchResult(BaseModel):
    """A single code search result from GitHub.

    Attributes:
        repo: Full repository name (``owner/repo``).
        path: File path within the repository.
        snippet: Matched text fragment.
        score: GitHub's relevance score for this result.
    """

    repo: str
    path: str
    snippet: str = ""
    score: float = Field(default=0.0, ge=0.0)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class GitHubMCPClient:
    """Async client for GitHub REST API v3.

    Mirrors the ``StitchMCPClient`` architecture from ``stitch_mcp.py``:
    typed methods, structured errors, and Pydantic response models.

    Args:
        token: GitHub personal access token. Falls back to
            ``GITHUB_TOKEN`` env var if not provided.
        base_url: API base URL. Defaults to ``https://api.github.com``.
    """

    def __init__(
        self,
        token: str = "",
        *,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        resolved_token = token or os.environ.get("GITHUB_TOKEN", "")
        if not resolved_token:
            logger.warning(
                "GitHubMCPClient initialized without a token. "
                "Authenticated requests will fail with 401."
            )
        self._token = resolved_token
        self._base_url = base_url.rstrip("/")
        self._headers: dict[str, str] = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            self._headers["Authorization"] = f"Bearer {self._token}"

    async def fetch_readme(self, owner: str, repo: str) -> str:
        """Fetch the README content for a repository.

        Args:
            owner: Repository owner (user or org).
            repo: Repository name.

        Returns:
            Decoded README content as a string.

        Raises:
            GitHubMCPError: On HTTP error or missing README.
        """
        url = f"{self._base_url}/repos/{owner}/{repo}/readme"
        data = await self._request("GET", url)
        content = data.get("content", "")
        encoding = data.get("encoding", "base64")
        if encoding == "base64" and content:
            return b64decode(content).decode("utf-8")
        return str(content)

    async def search_code(
        self,
        query: str,
        *,
        language: str | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> list[CodeSearchResult]:
        """Search for code across GitHub repositories.

        Args:
            query: Search query string.
            language: Optional language filter (e.g., ``"python"``).
            limit: Maximum number of results to return.

        Returns:
            List of code search results.

        Raises:
            GitHubMCPError: On HTTP error.
        """
        q = query
        if language:
            q += f" language:{language}"
        url = f"{self._base_url}/search/code"
        params: dict[str, Any] = {"q": q, "per_page": min(limit, 100)}
        data = await self._request("GET", url, params=params)
        results: list[CodeSearchResult] = []
        for item in data.get("items", [])[:limit]:
            results.append(
                CodeSearchResult(
                    repo=item.get("repository", {}).get("full_name", ""),
                    path=item.get("path", ""),
                    snippet=item.get("text_matches", [{}])[0].get("fragment", "")
                    if item.get("text_matches")
                    else "",
                    score=item.get("score", 0.0),
                )
            )
        return results

    async def fetch_file(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str = "HEAD",
    ) -> str:
        """Fetch a single file's content from a repository.

        Args:
            owner: Repository owner.
            repo: Repository name.
            path: File path within the repository.
            ref: Git reference (branch, tag, or SHA). Defaults to ``HEAD``.

        Returns:
            Decoded file content as a string.

        Raises:
            GitHubMCPError: On HTTP error or missing file.
        """
        url = f"{self._base_url}/repos/{owner}/{repo}/contents/{path}"
        params: dict[str, Any] = {"ref": ref}
        data = await self._request("GET", url, params=params)
        content = data.get("content", "")
        encoding = data.get("encoding", "base64")
        if encoding == "base64" and content:
            return b64decode(content).decode("utf-8")
        return str(content)

    # -------------------------------------------------------------------
    # Internal HTTP with retry + error classification
    # -------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request with retry and error classification.

        Implements failure-trichotomy:
            - fail-loud for auth errors (401/403)
            - self-heal for 5xx/429 with bounded exponential backoff
            - fail-loud for 404 and other client errors

        Args:
            method: HTTP method.
            url: Request URL.
            params: Optional query parameters.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            GitHubMCPError: On unrecoverable HTTP error.
        """
        last_error: httpx.HTTPError | None = None

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                async with httpx.AsyncClient(
                    headers=self._headers,
                    timeout=30.0,
                ) as client:
                    response = await client.request(
                        method,
                        url,
                        params=params,
                    )

                    # Check rate limiting
                    remaining = response.headers.get(RATE_LIMIT_REMAINING_HEADER)
                    if remaining is not None and int(remaining) == 0:
                        reset_at = response.headers.get(RATE_LIMIT_RESET_HEADER, "0")
                        logger.warning(
                            "GitHub rate limit exhausted, reset at %s",
                            reset_at,
                        )
                        if attempt < MAX_RETRY_ATTEMPTS - 1:
                            backoff = BACKOFF_BASE_SECONDS * BACKOFF_MULTIPLIER**attempt
                            await asyncio.sleep(backoff)
                            continue
                        raise GitHubMCPError(
                            f"Rate limit exhausted (reset at {reset_at})",
                            reason="rate_limit",
                            status_code=HTTP_RATE_LIMITED,
                        )

                    # Auth errors — fail-loud, no retry
                    if response.status_code in (
                        HTTP_UNAUTHORIZED,
                        HTTP_FORBIDDEN,
                    ):
                        raise GitHubMCPError(
                            f"Authentication failed: HTTP {response.status_code}",
                            reason="auth",
                            status_code=response.status_code,
                            detail=response.text,
                        )

                    # Not found — fail-loud, no retry
                    if response.status_code == HTTP_NOT_FOUND:
                        raise GitHubMCPError(
                            f"Resource not found: {url}",
                            reason="not_found",
                            status_code=HTTP_NOT_FOUND,
                            detail=response.text,
                        )

                    # Server errors — self-heal with retry
                    if response.status_code >= HTTP_SERVER_ERROR_START:
                        logger.warning(
                            "GitHub 5xx error (attempt %d/%d): %d",
                            attempt + 1,
                            MAX_RETRY_ATTEMPTS,
                            response.status_code,
                        )
                        if attempt < MAX_RETRY_ATTEMPTS - 1:
                            backoff = BACKOFF_BASE_SECONDS * BACKOFF_MULTIPLIER**attempt
                            await asyncio.sleep(backoff)
                            continue
                        raise GitHubMCPError(
                            f"Server error after {MAX_RETRY_ATTEMPTS} attempts",
                            reason="server_error",
                            status_code=response.status_code,
                        )

                    # Other client errors
                    response.raise_for_status()
                    return response.json()  # type: ignore[no-any-return]

            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "HTTP error on attempt %d/%d: %s",
                    attempt + 1,
                    MAX_RETRY_ATTEMPTS,
                    exc,
                )
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    backoff = BACKOFF_BASE_SECONDS * BACKOFF_MULTIPLIER**attempt
                    await asyncio.sleep(backoff)
                    continue
                raise GitHubMCPError(
                    f"HTTP error after {MAX_RETRY_ATTEMPTS} attempts: {exc}",
                    reason="transport",
                    detail=str(exc),
                ) from exc

        # Should not reach here, but satisfy the type checker
        raise GitHubMCPError(
            f"Request failed after {MAX_RETRY_ATTEMPTS} attempts",
            reason="exhausted",
            detail=str(last_error),
        )
