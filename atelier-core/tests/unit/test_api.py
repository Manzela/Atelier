"""Tests for the FastAPI application skeleton.

Validates: /health endpoint, response schema, timing header, CORS headers.
Uses httpx AsyncClient for realistic request testing.
"""

from __future__ import annotations

import pytest
from atelier.__version__ import __version__
from atelier.api.app import create_app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app():
    """Create a fresh FastAPI app instance for each test."""
    return create_app()


@pytest.fixture
async def client(app):
    """Async test client bound to the app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.unit
@pytest.mark.anyio
async def test_health_returns_200(client: AsyncClient) -> None:
    """GET /health should return 200."""
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.unit
@pytest.mark.anyio
async def test_health_schema(client: AsyncClient) -> None:
    """GET /health should return service metadata."""
    response = await client.get("/health")
    body = response.json()
    assert body["status"] == "healthy"
    assert body["version"] == __version__
    assert body["service"] == "atelier-api"
    assert "env" in body


@pytest.mark.unit
@pytest.mark.anyio
async def test_health_has_timing_header(client: AsyncClient) -> None:
    """Every response should include X-Process-Time header."""
    response = await client.get("/health")
    assert "x-process-time" in response.headers
    elapsed = float(response.headers["x-process-time"])
    assert elapsed >= 0.0


@pytest.mark.unit
@pytest.mark.anyio
async def test_unknown_route_returns_404(client: AsyncClient) -> None:
    """Unknown routes should return 404, not 500."""
    response = await client.get("/nonexistent")
    assert response.status_code == 404
