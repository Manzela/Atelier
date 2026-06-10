import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from atelier.durability.incident_memory import (
    IncidentMemoryBank,
    serialize_incident,
)
from atelier.memory.backends.vertex_semantic import VertexSemanticMemoryBackend
from atelier.models.data_contracts import GateOutcome
from atelier.models.enums import GateAxis, GateDecision
from atelier.nodes.consensus import ConsensusEvaluation


def _axe_failure() -> list[GateOutcome]:
    return [
        GateOutcome(
            candidate_id=uuid4(),
            axis=GateAxis.AXE,
            decision=GateDecision.REJECT,
            diagnostic="A11y fail",
        )
    ]


def test_serialize_incident_only_failures():
    """Verify that only failing gates or low consensus scores are serialized."""
    cand_id = uuid4()
    gate_outcomes = [
        GateOutcome(
            candidate_id=cand_id,
            axis=GateAxis.AXE,
            decision=GateDecision.REJECT,
            diagnostic="A11y fail",
        ),
        GateOutcome(
            candidate_id=cand_id,
            axis=GateAxis.SEMANTIC_HTML,
            decision=GateDecision.PASS,
            diagnostic="Clean HTML",
        ),
    ]

    mock_vote = MagicMock()
    mock_vote.score = 0.50
    mock_vote.reasoning = "Visual overlaps detected"

    consensus = MagicMock(spec=ConsensusEvaluation)
    consensus.votes = {GateAxis.VISUAL_DIFF: mock_vote}

    serialized = serialize_incident(
        tenant_id="tenant-123",
        incident_id="incident-456",
        gate_outcomes=gate_outcomes,
        consensus=consensus,
    )

    data = json.loads(serialized)
    assert data["incident_id"] == "incident-456"
    assert data["tenant_id"] == "tenant-123"
    assert "gate_fail:axe" in data["failures"]
    assert "low_score:visual-diff" in data["failures"]
    assert "Gate axe failed: A11y fail" in data["diagnostic_details"]
    assert (
        "Consensus Axis visual-diff low score 0.50: Visual overlaps detected"
        in data["diagnostic_details"]
    )


@pytest.mark.asyncio
async def test_learning_loop_records_and_queries(tmp_path):
    """End-to-end: record an incident + resolution, then retrieve it.

    Backed by an offline ``VertexSemanticMemoryBackend`` so the AT-080 loop is
    exercised with real persistence — proving it is no longer a silent no-op.
    """
    backend = VertexSemanticMemoryBackend(
        project_id="atelier-build-2026",
        persist_dir=str(tmp_path),
    )
    bank = IncidentMemoryBank(backend)
    gate_outcomes = _axe_failure()

    incident_id = "historical-inc-1"
    await bank.record_incident(
        tenant_id="tenant-123",
        incident_id=incident_id,
        gate_outcomes=gate_outcomes,
        consensus=None,
    )
    await bank.record_resolution(
        tenant_id="tenant-123",
        incident_id=incident_id,
        resolution_delta="Use an explicit aria-label.",
    )

    resolutions = await bank.query_similar_resolutions(
        tenant_id="tenant-123",
        gate_outcomes=gate_outcomes,
        consensus=None,
    )

    assert resolutions == ["Use an explicit aria-label."]


@pytest.mark.asyncio
async def test_passthrough_when_service_is_semantic(tmp_path):
    """A service that already speaks the semantic API is used directly."""
    backend = VertexSemanticMemoryBackend(
        project_id="atelier-build-2026",
        persist_dir=str(tmp_path),
    )
    bank = IncidentMemoryBank(backend)
    assert bank._backend is backend


@pytest.mark.asyncio
async def test_falls_back_for_adk_style_service(monkeypatch, tmp_path, caplog):
    """An ADK-style service (no write_semantic/query_semantic) triggers a logged fallback.

    This is the silent-no-op bug the fix removes: the resolved backend must be a
    real ``VertexSemanticMemoryBackend`` and a WARNING must explain the fallback.
    """
    monkeypatch.setenv("ATELIER_SEMANTIC_MEMORY_DIR", str(tmp_path))

    class _AdkStyleService:
        async def add_session_to_memory(self, session):  # pragma: no cover - shape only
            return None

        async def search_memory(self, *, app_name, user_id, query):  # pragma: no cover
            return None

    with caplog.at_level("WARNING"):
        bank = IncidentMemoryBank(_AdkStyleService())

    assert isinstance(bank._backend, VertexSemanticMemoryBackend)
    assert any("not a semantic backend" in rec.message for rec in caplog.records)

    # And the loop still works through the fallback backend.
    gate_outcomes = _axe_failure()
    await bank.record_incident(
        tenant_id="tenant-x",
        incident_id="inc-2",
        gate_outcomes=gate_outcomes,
        consensus=None,
    )
    await bank.record_resolution(
        tenant_id="tenant-x",
        incident_id="inc-2",
        resolution_delta="Add role=button.",
    )
    resolutions = await bank.query_similar_resolutions(
        tenant_id="tenant-x",
        gate_outcomes=gate_outcomes,
        consensus=None,
    )
    assert resolutions == ["Add role=button."]


@pytest.mark.asyncio
async def test_no_backend_degrades_to_logged_noop(monkeypatch, caplog):
    """If no semantic backend can be resolved, operations are explicit logged no-ops."""
    bank = IncidentMemoryBank(object())
    # Force the degraded path regardless of how resolution went.
    bank._backend = None

    gate_outcomes = _axe_failure()
    with caplog.at_level("WARNING"):
        await bank.record_incident(
            tenant_id="tenant-x",
            incident_id="inc-3",
            gate_outcomes=gate_outcomes,
            consensus=None,
        )
        resolutions = await bank.query_similar_resolutions(
            tenant_id="tenant-x",
            gate_outcomes=gate_outcomes,
            consensus=None,
        )

    assert resolutions == []
    assert any("no semantic backend" in rec.message for rec in caplog.records)
