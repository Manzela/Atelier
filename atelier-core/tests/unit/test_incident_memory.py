import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from atelier.durability.incident_memory import (
    IncidentMemoryBank,
    serialize_incident,
)
from atelier.models.data_contracts import GateOutcome
from atelier.models.enums import GateAxis, GateDecision
from atelier.nodes.consensus import ConsensusEvaluation


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
async def test_record_incident_semantic():
    """Verify that record_incident successfully calls write_semantic on memory service."""
    mock_memory = AsyncMock()
    mock_memory.write_semantic = AsyncMock(return_value="resource-name")

    bank = IncidentMemoryBank(mock_memory)
    gate_outcomes = [
        GateOutcome(
            candidate_id=uuid4(),
            axis=GateAxis.AXE,
            decision=GateDecision.REJECT,
            diagnostic="A11y fail",
        )
    ]

    await bank.record_incident(
        tenant_id="tenant-123",
        incident_id="incident-456",
        gate_outcomes=gate_outcomes,
        consensus=None,
    )

    mock_memory.write_semantic.assert_called_once()
    _, kwargs = mock_memory.write_semantic.call_args
    assert kwargs["metadata"]["incident_id"] == "incident-456"
    assert kwargs["metadata"]["type"] == "incident"
    assert kwargs["scope"].project_id == "tenant-123"
    assert kwargs["scope"].phase == "incident"
    assert kwargs["scope"].actor_id == "fixer"


@pytest.mark.asyncio
async def test_record_incident_episodic_fallback():
    """Verify fallback to write_episodic if write_semantic is missing on memory service."""
    mock_memory = AsyncMock(spec=["write_episodic"])

    bank = IncidentMemoryBank(mock_memory)
    gate_outcomes = [
        GateOutcome(
            candidate_id=uuid4(),
            axis=GateAxis.AXE,
            decision=GateDecision.REJECT,
            diagnostic="A11y fail",
        )
    ]

    await bank.record_incident(
        tenant_id="tenant-123",
        incident_id="incident-456",
        gate_outcomes=gate_outcomes,
        consensus=None,
    )

    mock_memory.write_episodic.assert_called_once()
    event = mock_memory.write_episodic.call_args[0][0]
    assert event.event_id == "incident-456"
    assert event.node_name == "FixerIncident"


@pytest.mark.asyncio
async def test_record_resolution():
    """Verify resolution is recorded properly using write_semantic."""
    mock_memory = AsyncMock()
    mock_memory.write_semantic = AsyncMock(return_value="resource-name")

    bank = IncidentMemoryBank(mock_memory)
    await bank.record_resolution(
        tenant_id="tenant-123",
        incident_id="incident-456",
        resolution_delta="my-delta-instructions",
    )

    mock_memory.write_semantic.assert_called_once()
    _, kwargs = mock_memory.write_semantic.call_args
    assert kwargs["metadata"]["incident_id"] == "incident-456"
    assert kwargs["metadata"]["type"] == "resolution"
    assert "my-delta-instructions" in kwargs["content"]


@pytest.mark.asyncio
async def test_query_similar_resolutions():
    """Verify that query retrieves incidents first and then fetches their resolutions."""
    mock_memory = AsyncMock()

    # Mock similar incident result
    mock_incident_hit = MagicMock()
    mock_incident_hit.passage = json.dumps(
        {
            "incident_id": "historical-inc-1",
            "failures": ["gate_fail:axe"],
        }
    )

    # Mock resolution result
    mock_resolution_hit = MagicMock()
    mock_resolution_hit.passage = json.dumps(
        {
            "incident_id": "historical-inc-1",
            "resolution": "Use an explicit aria-label.",
        }
    )

    # Side effect for query_semantic calls
    async def mock_query_semantic(*args, **kwargs):
        if "query" in kwargs["query_text"]:  # First call (searching for similar incidents)
            return (mock_incident_hit,)
        if "historical-inc-1" in kwargs["query_text"]:  # Second call (searching for resolution)
            return (mock_resolution_hit,)
        return ()

    mock_memory.query_semantic.side_effect = mock_query_semantic

    bank = IncidentMemoryBank(mock_memory)
    gate_outcomes = [
        GateOutcome(
            candidate_id=uuid4(),
            axis=GateAxis.AXE,
            decision=GateDecision.REJECT,
            diagnostic="A11y fail",
        )
    ]

    resolutions = await bank.query_similar_resolutions(
        tenant_id="tenant-123",
        gate_outcomes=gate_outcomes,
        consensus=None,
    )

    assert resolutions == ["Use an explicit aria-label."]
    assert mock_memory.query_semantic.call_count == 2
