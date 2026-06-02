"""Unit tests for POST /v1/generate/stream endpoint."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

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
def test_enrich_complete_payload_adds_a2ui_payload_from_project_context() -> None:
    """complete payload must carry a non-None A2UI surface built from design tokens.

    P0.4 (ADR-0011): the design-system panel is emitted as an A2UI v0.10/v0.9-wire
    surface threaded onto the ``complete`` event alongside ``best_html``.
    """
    from atelier.api.generate import _enrich_complete_payload
    from atelier.intake.brief_spec import (
        BriefSpec,
        ComplianceLevel,
        ConvergenceBar,
        StackChoice,
        VisualRegister,
    )
    from atelier.intake.source_resolver import ProjectContext

    project_ctx = ProjectContext(
        brief=BriefSpec(
            spec_id=uuid4(),
            tenant_id="tnt",
            project_id="prj",
            intent="Make booking easier with a clear hero and pricing widgets.",
            visual_register=VisualRegister.EDITORIAL,
            stack=StackChoice.VANILLA_HTML,
            compliance_level=ComplianceLevel.WCAG_AA,
            convergence_bar=ConvergenceBar.SHIP_IT,
            approved_at=datetime.now(UTC),
            approved_by_user_id="usr",
        ),
        design_tokens={"primary_color": "#1a73e8", "font": "Inter", "_source": "DESIGN.md"},
    )

    payload: dict[str, Any] = {
        "best_candidate": _MINIMAL_HTML,
        "converged": True,
        "composite_score": 0.75,
        "evaluations": _MINIMAL_EVALUATIONS,
        "project_context": project_ctx,
    }
    result = _enrich_complete_payload(payload)

    assert "a2ui_payload" in result
    a2ui = result["a2ui_payload"]
    assert a2ui is not None
    # The surface is an ordered A2UI message list (createSurface → updateComponents …).
    assert isinstance(a2ui, list)
    assert "createSurface" in a2ui[0]
    assert a2ui[0]["version"] == "v0.9"
    # The token rows reached the data model (meta keys excluded → 2 rows).
    rows = a2ui[2]["updateDataModel"]["value"]["tokens"]
    assert {row["path"] for row in rows} == {"primary_color", "font"}


@pytest.mark.unit
def test_enrich_complete_payload_a2ui_handles_serialized_project_context() -> None:
    """a2ui_payload must build even when project_context is a serialized dict.

    The runner stores ``project_ctx`` as a Pydantic object, but a re-serialized
    (``model_dump``) dict must also yield a surface — the extractor reads either.
    """
    from atelier.api.generate import _enrich_complete_payload

    payload: dict[str, Any] = {
        "best_candidate": _MINIMAL_HTML,
        "converged": True,
        "composite_score": 0.75,
        "evaluations": _MINIMAL_EVALUATIONS,
        "project_context": {"design_tokens": {"color_ink": "#0a0a0a"}},
    }
    result = _enrich_complete_payload(payload)

    a2ui = result["a2ui_payload"]
    assert a2ui is not None
    rows = a2ui[2]["updateDataModel"]["value"]["tokens"]
    assert {row["path"] for row in rows} == {"color_ink"}


@pytest.mark.unit
def test_enrich_complete_payload_a2ui_present_without_tokens() -> None:
    """Even with no project_context, a valid (empty-row) A2UI surface is emitted."""
    from atelier.api.generate import _enrich_complete_payload

    payload: dict[str, Any] = {
        "best_candidate": _MINIMAL_HTML,
        "converged": True,
        "composite_score": 0.75,
        "evaluations": _MINIMAL_EVALUATIONS,
    }
    result = _enrich_complete_payload(payload)

    a2ui = result["a2ui_payload"]
    assert a2ui is not None
    assert a2ui[2]["updateDataModel"]["value"]["tokens"] == []


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


# ---------------------------------------------------------------------------
# AT-093: _build_iteration_dorav helper tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_build_iteration_dorav_extracts_per_axis_and_composite() -> None:
    """_build_iteration_dorav must return per-axis scores + composite from evaluations."""
    from atelier.orchestrator.runner import _build_iteration_dorav

    evaluations_serialized = [
        {
            "composite_score": 0.72,
            "passed": True,
            "votes": {
                "brand": {"score": 0.80},
                "originality": {"score": 0.70},
                "relevance": {"score": 0.90},
                "accessibility": {"score": 0.55},  # lowest → failing axis
                "visual-clarity": {"score": 0.75},
            },
        }
    ]
    result = _build_iteration_dorav(evaluations_serialized, 0.72)

    assert result["brand"] == pytest.approx(0.80)
    assert result["originality"] == pytest.approx(0.70)
    assert result["relevance"] == pytest.approx(0.90)
    assert result["accessibility"] == pytest.approx(0.55)
    assert result["visual-clarity"] == pytest.approx(0.75)
    assert result["composite"] == pytest.approx(0.72)
    assert result["failing_axis"] == "accessibility"


@pytest.mark.unit
def test_build_iteration_dorav_empty_evaluations_falls_back_to_composite() -> None:
    """When evaluations list is empty, composite falls back to the passed value."""
    from atelier.orchestrator.runner import _build_iteration_dorav

    result = _build_iteration_dorav([], 0.45)

    assert result["composite"] == pytest.approx(0.45)
    assert result["failing_axis"] is None


@pytest.mark.unit
def test_build_iteration_dorav_does_not_mutate_input() -> None:
    """_build_iteration_dorav must not mutate the evaluations_serialized input."""
    from atelier.orchestrator.runner import _build_iteration_dorav

    original = [
        {
            "composite_score": 0.60,
            "passed": True,
            "votes": {"brand": {"score": 0.60}},
        }
    ]
    import copy

    before = copy.deepcopy(original)
    _build_iteration_dorav(original, 0.60)
    assert original == before


@pytest.mark.unit
def test_stream_emits_iteration_score_per_iteration(client: TestClient) -> None:
    """The SSE stream must emit one iteration_score event per convergence iteration.

    This test proves the backend REALLY emits the event — not a fixture-only illusion.
    The mock simulates two convergence iterations followed by a complete event, and
    asserts that two ``iteration_score`` events appear in the stream with well-formed
    per-axis D-O-R-A-V payloads and a non-null failing_axis.
    """
    mock_run = AsyncMock()

    async def side_effect(
        brief_text: str, tenant_ctx: Any, progress_callback: Any = None
    ) -> dict[str, Any]:
        if progress_callback:
            await progress_callback("plan", {"surfaces": ["home"]})
            # Iteration 0
            await progress_callback("iteration_start", {"screen": "home", "iteration": 0})
            await progress_callback(
                "iteration_score",
                {
                    "screen": "home",
                    "iteration": 0,
                    "dorav": {
                        "brand": 0.60,
                        "originality": 0.55,
                        "relevance": 0.65,
                        "accessibility": 0.45,
                        "visual-clarity": 0.50,
                        "composite": 0.55,
                    },
                    "composite": 0.55,
                    "failing_axis": "accessibility",
                },
            )
            # Iteration 1 — scores climb
            await progress_callback("iteration_start", {"screen": "home", "iteration": 1})
            await progress_callback(
                "iteration_score",
                {
                    "screen": "home",
                    "iteration": 1,
                    "dorav": {
                        "brand": 0.75,
                        "originality": 0.70,
                        "relevance": 0.80,
                        "accessibility": 0.60,
                        "visual-clarity": 0.65,
                        "composite": 0.70,
                    },
                    "composite": 0.70,
                    "failing_axis": "originality",
                },
            )
            await progress_callback(
                "complete",
                {
                    "best_candidate": _MINIMAL_HTML,
                    "converged": True,
                    "composite_score": 0.70,
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

        iteration_score_payloads: list[dict[str, Any]] = []
        current_event = ""
        for line in resp.iter_lines():
            if line.startswith("event:"):
                current_event = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                try:
                    data = json.loads(line.removeprefix("data:").strip())
                    if current_event == "iteration_score":
                        iteration_score_payloads.append(data)
                except json.JSONDecodeError:
                    pass

    # Two iterations → two iteration_score events
    assert len(iteration_score_payloads) == 2, (
        f"Expected 2 iteration_score events, got {len(iteration_score_payloads)}"
    )

    # Verify iteration 0 payload shape
    iter0 = iteration_score_payloads[0]
    assert iter0["iteration"] == 0
    assert iter0["screen"] == "home"
    assert isinstance(iter0["dorav"], dict)
    assert "composite" in iter0
    assert isinstance(iter0["failing_axis"], str)
    for axis in ("brand", "originality", "relevance", "accessibility", "visual-clarity"):
        assert axis in iter0["dorav"], f"dorav missing axis: {axis}"

    # Verify iteration 1: composite must be higher than iteration 0
    iter1 = iteration_score_payloads[1]
    assert iter1["iteration"] == 1
    assert iter1["composite"] > iter0["composite"], (
        "iteration 1 composite must be higher than iteration 0 (scores climb)"
    )
    # The failing axis must differ between the two iterations (test data is non-vacuous)
    assert iter1["failing_axis"] != iter0["failing_axis"], (
        "failing_axis must differ between iterations (non-vacuous fixture)"
    )
