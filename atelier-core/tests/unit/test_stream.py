"""Unit tests for POST /v1/generate/stream endpoint."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_HTML = """<!DOCTYPE html>
<html><head><title>Test</title></head>
<body><main><h1>Hello</h1><p>Content here</p></main></body>
</html>"""

_MINIMAL_EVALUATIONS = [
    {
        "composite_score": 0.75,
        "passed": True,
        "votes": {
            "brand": {"score": 0.8},
            "originality": {"score": 0.7},
            "relevance": {"score": 0.9},
            "accessibility": {"score": 0.6},
            "visual-clarity": {"score": 0.75},
        },
    }
]


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


# ---------------------------------------------------------------------------
# _enrich_complete_payload unit tests (pure function, no HTTP needed)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_enrich_complete_payload_adds_best_html() -> None:
    """complete payload must include best_html equal to the best_candidate string."""
    from atelier.api.generate import _enrich_complete_payload

    payload: dict[str, Any] = {
        "best_candidate": _MINIMAL_HTML,
        "converged": True,
        "composite_score": 0.75,
        "evaluations": _MINIMAL_EVALUATIONS,
    }
    result = _enrich_complete_payload(payload)

    assert "best_html" in result
    assert result["best_html"] == _MINIMAL_HTML


@pytest.mark.unit
def test_enrich_complete_payload_adds_dorav_with_all_axes() -> None:
    """complete payload must include dorav with per-axis scores + composite."""
    from atelier.api.generate import _enrich_complete_payload

    payload: dict[str, Any] = {
        "best_candidate": _MINIMAL_HTML,
        "converged": True,
        "composite_score": 0.75,
        "evaluations": _MINIMAL_EVALUATIONS,
    }
    result = _enrich_complete_payload(payload)

    assert "dorav" in result
    dorav = result["dorav"]
    # All five D-O-R-A-V axes must be present
    for axis in ("brand", "originality", "relevance", "accessibility", "visual-clarity"):
        assert axis in dorav, f"dorav missing axis: {axis}"
        assert isinstance(dorav[axis], float)
    # Composite must be present
    assert "composite" in dorav
    assert isinstance(dorav["composite"], float)
    assert dorav["composite"] == pytest.approx(0.75)


@pytest.mark.unit
def test_enrich_complete_payload_adds_nielsen_presence_list() -> None:
    """complete payload must include nielsen as a list of 10 heuristic verdicts."""
    from atelier.api.generate import _enrich_complete_payload

    payload: dict[str, Any] = {
        "best_candidate": _MINIMAL_HTML,
        "converged": True,
        "composite_score": 0.75,
        "evaluations": _MINIMAL_EVALUATIONS,
    }
    result = _enrich_complete_payload(payload)

    assert "nielsen" in result
    nielsen = result["nielsen"]
    assert isinstance(nielsen, list)
    # Nielsen-10 always produces exactly 10 verdicts
    assert len(nielsen) == 10
    for verdict in nielsen:
        assert "heuristic" in verdict
        assert "present" in verdict
        assert "votes" in verdict
        assert isinstance(verdict["heuristic"], str)
        assert isinstance(verdict["present"], bool)
        assert isinstance(verdict["votes"], int)


@pytest.mark.unit
def test_enrich_complete_payload_nielsen_no_severity_field() -> None:
    """Nielsen verdicts must NOT include a severity field (R6 — severity is human-only)."""
    from atelier.api.generate import _enrich_complete_payload

    payload: dict[str, Any] = {
        "best_candidate": _MINIMAL_HTML,
        "converged": True,
        "composite_score": 0.75,
        "evaluations": _MINIMAL_EVALUATIONS,
    }
    result = _enrich_complete_payload(payload)

    for verdict in result["nielsen"]:
        assert "severity" not in verdict, "Nielsen verdict must not expose severity (R6)"


@pytest.mark.unit
def test_enrich_complete_payload_empty_best_candidate_returns_empty_nielsen() -> None:
    """When best_candidate is None or empty, nielsen must degrade to an empty list."""
    from atelier.api.generate import _enrich_complete_payload

    for no_html in (None, "", "   "):
        payload: dict[str, Any] = {
            "best_candidate": no_html,
            "converged": False,
            "composite_score": 0.0,
            "evaluations": [],
        }
        result = _enrich_complete_payload(payload)
        assert result["nielsen"] == []
        assert result["best_html"] == (no_html if no_html else "")


@pytest.mark.unit
def test_enrich_complete_payload_dorav_fallback_on_empty_evaluations() -> None:
    """When evaluations list is empty, dorav composite falls back to top-level composite_score."""
    from atelier.api.generate import _enrich_complete_payload

    payload: dict[str, Any] = {
        "best_candidate": _MINIMAL_HTML,
        "converged": False,
        "composite_score": 0.55,
        "evaluations": [],
    }
    result = _enrich_complete_payload(payload)

    dorav = result["dorav"]
    assert dorav["composite"] == pytest.approx(0.55)
    # No axes (no evaluations), but composite must be present
    assert "composite" in dorav


@pytest.mark.unit
def test_enrich_complete_payload_does_not_mutate_original() -> None:
    """_enrich_complete_payload must return a new dict, not mutate the input."""
    from atelier.api.generate import _enrich_complete_payload

    original: dict[str, Any] = {
        "best_candidate": _MINIMAL_HTML,
        "converged": True,
        "composite_score": 0.75,
        "evaluations": _MINIMAL_EVALUATIONS,
    }
    original_keys = set(original.keys())
    _enrich_complete_payload(original)
    assert set(original.keys()) == original_keys, "Original payload dict was mutated"


@pytest.mark.unit
def test_stream_complete_event_contains_best_html_dorav_nielsen(client: TestClient) -> None:
    """The SSE complete event data must contain best_html, dorav, and nielsen fields."""
    mock_run = AsyncMock()

    async def side_effect(
        brief_text: str, tenant_ctx: Any, progress_callback: Any = None
    ) -> dict[str, Any]:
        if progress_callback:
            await progress_callback("plan", {"surfaces": ["home screen"]})
            await progress_callback(
                "complete",
                {
                    "best_candidate": _MINIMAL_HTML,
                    "converged": True,
                    "composite_score": 0.75,
                    "evaluations": _MINIMAL_EVALUATIONS,
                },
            )
        return {"session_id": "test-session", "best_candidate": _MINIMAL_HTML, "candidates": []}

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

        complete_payload: dict[str, Any] | None = None
        for line in resp.iter_lines():
            if line.startswith("data:") and "complete" in line:
                # The complete event: data line follows the event: complete line
                pass
            if line.startswith("data:"):
                try:
                    data = json.loads(line.removeprefix("data:").strip())
                    if "best_html" in data:
                        complete_payload = data
                except json.JSONDecodeError:
                    pass

        assert complete_payload is not None, "No complete event data found in SSE stream"
        assert "best_html" in complete_payload
        assert "dorav" in complete_payload
        assert "nielsen" in complete_payload
        # Nielsen must be a list (presence-only)
        assert isinstance(complete_payload["nielsen"], list)
