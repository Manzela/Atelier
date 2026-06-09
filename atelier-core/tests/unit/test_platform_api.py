"""Unit tests for the read-only platform API — api/platform.py.

Hermetic by construction: runs with ``FIREBASE_DISABLE_AUTH=1`` (dev auth bypass
returns a synthetic user) and ``ATELIER_USAGE_BACKEND=memory`` (no Firestore).
No live GCP / network. Asserts the audit-derived invariants:

    * /agents lists the full 18-agent roster (planner + intake + 6 specialists
      + 5 judges + 4 critics + fixer).
    * /agents/{id} returns the full descriptor incl. prompt; unknown id is
      fail-soft (available:false), not a 500.
    * /topology edges exactly match the specialists' specialist-to-specialist
      hand-offs (upstream_keys filtered to specialist outputs).
    * /govern usage math is internally consistent: used + remaining == cap for
      every tier, and the caps equal TIER_TOKEN_CAPS.
    * BigQuery-backed surfaces (/optimize) report available:false offline with
      HTTP 200 — never a 500, never a raw exception string.
    * Every platform route requires auth (no anonymous access when the bypass
      is off).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Hermetic env MUST be set before importing the auth module (it reads the
# bypass flag at import time).
os.environ.setdefault("FIREBASE_DISABLE_AUTH", "1")
os.environ.setdefault("ATELIER_USAGE_BACKEND", "memory")
os.environ.setdefault("ATELIER_ENV", "development")

from atelier.api.platform import router
from atelier.models.model_registry import TIER_TOKEN_CAPS
from atelier.orchestrator.specialists import (
    SPECIALIST_OUTPUT_KEYS,
    get_specialist_specs,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

_EXPECTED_AGENT_IDS = {
    "planner",
    "intake_brief_parser",
    "specialist_uxresearcher",
    "specialist_iaflowdesigner",
    "specialist_wireframer",
    "specialist_uidesigner",
    "specialist_interactiondesigner",
    "specialist_tokengenerator",
    "judge_brand",
    "judge_originality",
    "judge_relevance",
    "judge_accessibility",
    "judge_visual_clarity",
    "critic_accessibilitycritic",
    "critic_nielsenheuristiccritic",
    "critic_visualqacritic",
    "critic_brandcoherencecritic",
    "fixer",
}

# Every GET route the platform router exposes (path templates).
_PLATFORM_ROUTES = [
    "/v1/platform/agents",
    "/v1/platform/agents/planner",
    "/v1/platform/build",
    "/v1/platform/topology",
    "/v1/platform/scale",
    "/v1/platform/govern",
    "/v1/platform/optimize",
]


@pytest.fixture
def client() -> Iterator[TestClient]:
    """TestClient with the dev auth bypass active (FIREBASE_DISABLE_AUTH)."""
    from unittest.mock import patch

    with patch("atelier.auth.firebase._BYPASS_AUTH", True):
        app = FastAPI()
        app.include_router(router)
        yield TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def no_auth_client() -> Iterator[TestClient]:
    """TestClient with auth ENFORCED (bypass off) to assert 401 on every route."""
    from unittest.mock import patch

    with patch("atelier.auth.firebase._BYPASS_AUTH", False):
        app = FastAPI()
        app.include_router(router)
        yield TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# /agents — full roster
# ---------------------------------------------------------------------------


def test_agents_lists_full_roster(client: TestClient) -> None:
    resp = client.get("/v1/platform/agents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    ids = {a["id"] for a in body["agents"]}
    assert ids == _EXPECTED_AGENT_IDS
    assert body["count"] == len(_EXPECTED_AGENT_IDS)
    # Roster composition is single-sourced from the registry.
    assert body["counts_by_kind"] == {
        "planner": 1,
        "intake": 1,
        "specialist": 6,
        "judge": 5,
        "critic": 4,
        "fixer": 1,
    }


def test_agents_summary_omits_prompt_body(client: TestClient) -> None:
    body = client.get("/v1/platform/agents").json()
    # Summary rows must not carry the (large) prompt body.
    assert all("prompt" not in a for a in body["agents"])


def test_agent_detail_includes_prompt_and_config(client: TestClient) -> None:
    resp = client.get("/v1/platform/agents/specialist_uidesigner")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    agent = body["agent"]
    assert agent["id"] == "specialist_uidesigner"
    assert agent["prompt"]  # non-empty role brief
    # The UI Designer is the only Stitch-MCP-carrying specialist.
    assert agent["tools"] == ["stitch_mcp"]
    assert agent["output_key"] == "ui_design"


def test_agent_detail_unknown_id_is_fail_soft(client: TestClient) -> None:
    resp = client.get("/v1/platform/agents/does_not_exist")
    # Fail-soft, not a 404 / 500.
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["reason"] == "agent_not_found"


# ---------------------------------------------------------------------------
# /topology — DAG edges match the hand-off contract
# ---------------------------------------------------------------------------


def test_topology_nodes_are_the_specialists(client: TestClient) -> None:
    body = client.get("/v1/platform/topology").json()
    assert body["available"] is True
    node_ids = {n["id"] for n in body["nodes"]}
    assert node_ids == set(SPECIALIST_OUTPUT_KEYS)
    assert body["kind"] == "static_pipeline_dag"


def test_topology_edges_match_upstream_keys(client: TestClient) -> None:
    body = client.get("/v1/platform/topology").json()
    output_keys = set(SPECIALIST_OUTPUT_KEYS)

    # Reconstruct the expected edge set directly from the live specs: an edge
    # for every upstream_key that is itself a specialist output (external inputs
    # like WRAI research_findings are NOT nodes, so they produce no edge).
    expected = {
        (upstream, spec.output_key)
        for spec in get_specialist_specs()
        for upstream in spec.upstream_keys
        if upstream in output_keys
    }
    actual = {(e["from"], e["to"]) for e in body["edges"]}
    assert actual == expected
    # Sanity: every edge endpoint is a real node.
    for frm, to in actual:
        assert frm in output_keys
        assert to in output_keys


# ---------------------------------------------------------------------------
# /govern — usage math (used + remaining == cap)
# ---------------------------------------------------------------------------


def test_govern_usage_math_is_consistent(client: TestClient) -> None:
    body = client.get("/v1/platform/govern").json()
    assert body["available"] is True

    usage = body["usage"]
    assert usage["available"] is True
    tiers = usage["tiers"]
    # Every tier in TIER_TOKEN_CAPS is reported, with used + remaining == cap.
    assert set(tiers) == set(TIER_TOKEN_CAPS)
    for tier, cap in TIER_TOKEN_CAPS.items():
        row = tiers[tier]
        assert row["cap"] == cap
        assert row["used"] + row["remaining"] == cap

    # Identity is the verified (dev-bypass) user; tenant comes from the token.
    assert body["identity"]["tenant_id"] == "dev-tenant"
    # Thresholds + safety categories are present and fail-soft-shaped.
    assert body["model_armor"]["available"] is True
    assert body["model_armor"]["deterministic_injection_guard"]["marker_count"] > 0
    assert body["thresholds"]["available"] is True


def test_govern_usage_backend_is_memory(client: TestClient) -> None:
    body = client.get("/v1/platform/govern").json()
    assert body["usage_backend"] == "memory"


# ---------------------------------------------------------------------------
# /scale — model catalog + backend modes (hermetic, no live GCP)
# ---------------------------------------------------------------------------


def test_scale_reports_model_catalog_and_backends(client: TestClient) -> None:
    body = client.get("/v1/platform/scale").json()
    assert body["available"] is True
    catalog = body["model_catalog"]
    assert catalog["available"] is True
    # The full routing table inverts to exactly 3 model ids.
    by_tier = {m["tier"]: m for m in catalog["models"]}
    assert set(by_tier) == {"pro", "flash", "flash_lite"}
    assert len(by_tier["pro"]["task_types"]) == 3
    assert len(by_tier["flash"]["task_types"]) == 10
    assert len(by_tier["flash_lite"]["task_types"]) == 4
    # deploy_config.resolve_config() is pure (env + defaults) — available offline.
    assert body["deploy_config"]["available"] is True
    assert body["session_backend"] == "memory"


# ---------------------------------------------------------------------------
# /build — agent card skills + MCP toolsets
# ---------------------------------------------------------------------------


def test_build_surfaces_skills_and_mcp_toolsets(client: TestClient) -> None:
    body = client.get("/v1/platform/build").json()
    assert body["available"] is True
    # The single Stitch MCP toolset is wired to the UI Designer.
    toolsets = {t["toolset"]: t for t in body["mcp_toolsets"]}
    assert "stitch_mcp" in toolsets
    assert toolsets["stitch_mcp"]["agents"] == ["specialist_uidesigner"]
    # Agent card skills are surfaced when the repo-root card is present.
    assert body["agent_card"]["available"] is True
    assert body["counts"]["agents_total"] == len(_EXPECTED_AGENT_IDS)


# ---------------------------------------------------------------------------
# /optimize — BigQuery-backed, fail-soft offline (no 500)
# ---------------------------------------------------------------------------


def test_optimize_is_fail_soft_offline(client: TestClient) -> None:
    # No BigQuery client is constructible in the hermetic lane, so list_recent_runs
    # returns None -> the handler reports available:false with HTTP 200 (never 500).
    from unittest.mock import patch

    with patch("atelier.api.replay._make_bq_client", return_value=None):
        resp = client.get("/v1/platform/optimize")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    # RR-05 honesty: never claims spend caps are enforced.
    assert body["spend_caps_enforced"] is False


def test_optimize_does_not_claim_enforced_caps_when_available(client: TestClient) -> None:
    # Mock list_recent_runs to a concrete (empty) list to exercise the available
    # path without BigQuery; the handler must still disclaim enforced caps.
    from unittest.mock import AsyncMock, patch

    with patch("atelier.api.replay.list_recent_runs", new=AsyncMock(return_value=[])):
        resp = client.get("/v1/platform/optimize")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["spend_caps_enforced"] is False
    assert body["count"] == 0


# ---------------------------------------------------------------------------
# Auth — every route requires a verified token
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route", _PLATFORM_ROUTES)
def test_routes_require_auth(no_auth_client: TestClient, route: str) -> None:
    resp = no_auth_client.get(route)
    assert resp.status_code == 401
