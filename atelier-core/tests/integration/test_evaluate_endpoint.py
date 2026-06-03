"""Integration tests for the Optimize-surfacing eval lane — AT-027.

POST /v1/evaluate is the endpoint that finally wires the previously-dead
``run_simulation()`` into a request path, AND surfaces — read-only — the two
optimize assets the product never exposed before:

    1. The MoE routing decision (real ``RouteDecision`` from
       ``EpsilonGreedyBandit.route()`` — the v1_bandit router).
    2. A dreaming / DPO artifact (real ``ExtractedPair`` from the dreaming
       module's mid-flight pair extraction, with the anti-sycophancy reward
       rule applied).

The trace these produce is then visible via GET /v1/replay/{session_id}:
the evaluate endpoint persists ONE ``TrajectoryRecord`` whose payload carries
``route_decisions`` and ``dreaming_artifacts``, and the replay assembler
hydrates both arrays back out.

This is a READ-ONLY surfacing feature (PRD §6.5 Simulation, §9.3 DPO flywheel).
No new training infrastructure is built — existing optimize code is wired and
displayed. The only external dependency (BigQuery) is injected so the
simulation / routing / pair-extraction all run for real.

PRD Reference: §6.5 (Simulation), §9.3 (DPO flywheel), §3.6 (anti-sycophancy),
    §7.1 (API surface), §18.4 (MoE router).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from atelier.api.evaluate import router as evaluate_router
from atelier.api.replay import router as replay_router
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.fixture
def app_client() -> Any:
    """TestClient with auth bypass and both evaluate + replay routers mounted.

    The evaluate endpoint persists its TrajectoryRecord to an in-memory fake
    BQ sink; the replay endpoint reads back from the same sink. This keeps the
    full RED→GREEN trace deterministic without touching real BigQuery, while
    the simulation, routing, and pair-extraction all execute for real.
    """
    sink: dict[str, list[dict[str, Any]]] = {"rows": []}

    fake_bq = MagicMock()

    def _insert(table: str, rows: list[dict[str, Any]]) -> list[Any]:
        sink["rows"].extend(rows)
        return []

    fake_bq.insert_rows_json.side_effect = _insert

    def _query(sql: str, *_a: Any, **_k: Any) -> Any:
        job = MagicMock()
        job.result.return_value = list(sink["rows"])
        return job

    fake_bq.query.side_effect = _query

    with patch("atelier.auth.firebase._BYPASS_AUTH", True):
        app = FastAPI()
        app.include_router(evaluate_router)
        app.include_router(replay_router)
        client = TestClient(app, raise_server_exceptions=False)
        client.__dict__["_atelier_bq"] = fake_bq  # carry the fake for patches
        yield client


def test_evaluate_surfaces_artifacts(app_client: TestClient) -> None:
    """POST /v1/evaluate returns simulation results + the MoE RouteDecision + a
    dreaming/DPO artifact, and the same trace is replayable via /v1/replay.

    Acceptance bar (AT-027):
      - run_simulation() is actually invoked (results non-empty, >=1 matched).
      - >=1 dreaming/DPO artifact is surfaced read-only.
      - the MoE RouteDecision is surfaced read-only.
      - the trace is visible via /v1/replay with both arrays non-empty.
    """
    fake_bq = app_client.__dict__["_atelier_bq"]

    # Two adversarial briefs (both deterministically rejected by the gate) so
    # the simulation has a non-trivial matched_expected outcome to assert on.
    body = {
        "brief_ids": ["adv-001", "adv-002"],
    }

    with (
        patch("atelier.api.evaluate._make_bq_client", return_value=fake_bq),
        patch("atelier.api.replay._make_bq_client", return_value=fake_bq),
    ):
        resp = app_client.post("/v1/evaluate", json=body)

    assert resp.status_code == 200, resp.text
    data = resp.json()

    # --- Clause 1: run_simulation() actually invoked -----------------------
    results = data["results"]
    assert len(results) == 2, "run_simulation must return one result per brief"
    matched = [r for r in results if r["matched_expected"]]
    assert len(matched) >= 1, "at least one brief's outcome must match expected"
    # adversarial briefs must be rejected by the deterministic gate
    assert any(r["actual_outcome"] == "reject" for r in results)

    # --- Clause 2: MoE RouteDecision surfaced ------------------------------
    route = data["route_decision"]
    assert route is not None
    assert route["expert"], "RouteDecision.expert must be present"
    assert route["routing_mode"] == "v1_bandit", "must be the real bandit router"
    assert "fallback_chain" in route

    # --- Clause 3: dreaming / DPO artifact surfaced ------------------------
    artifact = data["dreaming_artifact"]
    assert artifact is not None
    assert artifact["chosen_score"] >= artifact["rejected_score"]
    assert artifact["margin"] >= 0.0

    # --- Clause 4: trace visible via /v1/replay ----------------------------
    session_id = data["session_id"]
    assert session_id

    with patch("atelier.api.replay._make_bq_client", return_value=fake_bq):
        replay = app_client.get(f"/v1/replay/{session_id}")

    assert replay.status_code == 200, replay.text
    replay_data = replay.json()
    assert replay_data["route_decisions"], "replay must surface route_decisions"
    assert replay_data["dreaming_artifacts"], "replay must surface dreaming_artifacts"
    assert replay_data["route_decisions"][0]["routing_mode"] == "v1_bandit"


def test_evaluate_anti_sycophancy_reward_penalises_unjustified_praise(
    app_client: TestClient,
) -> None:
    """The DPO reward applied during /v1/evaluate must encode the §3.6
    anti-sycophancy rule: a 'chosen' response that praises ('looks good')
    without a justification ('because' / 'reason' / 'standard' / a WCAG cite)
    is penalised, so personalization cannot drift sycophantic.
    """
    from atelier.optimize.dreaming_module import apply_anti_sycophancy_reward

    baseline = 0.90

    # Unjustified praise → penalised.
    penalised = apply_anti_sycophancy_reward(
        chosen_response="This looks good! Great work, excellent.",
        chosen_score=baseline,
    )
    assert penalised < baseline, "unjustified praise must be penalised"
    assert penalised == pytest.approx(baseline * 0.5)

    # Justified praise (carries a reason / standard) → NOT penalised.
    justified = apply_anti_sycophancy_reward(
        chosen_response="This looks good because it meets the WCAG AA contrast standard.",
        chosen_score=baseline,
    )
    assert justified == pytest.approx(baseline), "justified praise must not be penalised"
