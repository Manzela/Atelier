"""Unit tests for POST /v1/generate/stream endpoint."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    """TestClient with auth bypassed and dev mode environment variables set."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("FIREBASE_DISABLE_AUTH", "true")
        mp.setenv("ATELIER_ENV", "development")

        import importlib

        import atelier.auth.firebase as auth_mod

        importlib.reload(auth_mod)

        from atelier.api.app import create_app

        return TestClient(create_app(), raise_server_exceptions=False)


@pytest.mark.unit
def test_stream_validation_fails_for_short_brief(client: TestClient) -> None:
    """Validation must fail before running the pipeline if the brief is too short."""
    # "This is a brief." is > 10 chars (passes Pydantic) but < 10 words (fails BriefParserGate)
    resp = client.post(
        "/v1/generate/stream", json={"brief": "This is a brief.", "budget_usd": 10.0}
    )
    assert resp.status_code == 400
    assert "Brief too short" in resp.json()["detail"]


@pytest.mark.unit
def test_stream_returns_sse_events(client: TestClient) -> None:
    """The stream endpoint must yield a series of correctly formatted EventSource events."""
    mock_run = AsyncMock()

    async def side_effect(
        brief_text: str, tenant_ctx: Any, progress_callback: Any = None
    ) -> dict[str, Any]:
        if progress_callback:
            await progress_callback("plan", {"surfaces": ["home screen"]})
            await progress_callback("screen_start", {"screen": "home screen", "index": 0})
            await progress_callback("complete", {"status": "ok"})
        return {"session_id": "test-session", "best_candidate": "<html></html>", "candidates": []}

    mock_run.side_effect = side_effect

    with (
        patch("atelier.orchestrator.runner.AtelierRunner.run", mock_run),
        patch("atelier.api.generate._record_trajectory", AsyncMock()),
    ):
        resp = client.post(
            "/v1/generate/stream",
            json={
                "brief": "Generate a beautiful luxury brand landing page with pricing widgets.",
                "budget_usd": 10.0,
            },
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/event-stream; charset=utf-8"

        lines = [line for line in resp.iter_lines() if line]

        # Verify event sequence
        assert "event: plan" in lines
        assert "event: screen_start" in lines
        assert "event: complete" in lines
