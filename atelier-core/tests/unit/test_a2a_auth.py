"""Regression: the A2A JSON-RPC endpoint must be authenticated.

POST /v1/a2a previously had no ``Depends(require_auth)`` — an unauthenticated
caller could drive the full N1->N4 pipeline (paid Vertex spend, 20-30 min) with
no FirebaseUser, no TenantContext, and no binding to the per-user token-cap
governor (AT-095). This locks both methods behind the same Firebase gate every
other pipeline route uses, mirroring the 401 contract of /v1/generate.
"""

from __future__ import annotations

import pytest
from atelier.api.app import create_app
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.unit
@pytest.mark.anyio
@pytest.mark.parametrize("method", ["SendMessage", "GetTask"])
async def test_a2a_rejects_unauthenticated(client: AsyncClient, method: str) -> None:
    """No Authorization header -> 401 (the route never reaches the handler/pipeline)."""
    resp = await client.post(
        "/v1/a2a",
        json={"jsonrpc": "2.0", "method": method, "params": {}, "id": "probe"},
    )
    assert resp.status_code == 401, f"{method} must be 401 unauthenticated, got {resp.status_code}"


@pytest.mark.unit
@pytest.mark.anyio
async def test_a2a_rejects_garbage_bearer(client: AsyncClient) -> None:
    """A malformed Bearer token -> 401, never a 200 that runs the pipeline."""
    resp = await client.post(
        "/v1/a2a",
        json={"jsonrpc": "2.0", "method": "SendMessage", "params": {}, "id": "probe"},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401
