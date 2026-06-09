"""Regression tests for the N3e FixerAgent prompt construction.

The fixer read ``consensus.per_axis_scores``, but the runner passes a
``ConsensusEvaluation`` (which exposes ``votes``); ``per_axis_scores`` lives on a
different model. The flow only reaches the fixer once generation completes
without converging, so the AttributeError was latent until the pipeline ran
end-to-end against real Vertex — it then 500'd every non-converging request.
"""

import json
from collections.abc import Sequence
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from atelier.gates.runner import run_gates
from atelier.memory.scope import MemoryScopeKey
from atelier.models.data_contracts import CandidateUI
from atelier.nodes.consensus import AxisWeights, evaluate_candidate
from atelier.nodes.fixer import FixerAgent, FixerDirective
from atelier.orchestrator.governor import GovernorState, MetacognitiveGovernor
from atelier.orchestrator.runner import _N3C_GATE_AXES

_HTML = (
    '<!DOCTYPE html><html lang="en"><head><title>T</title>'
    "<style>:root{--c:#1a73e8}body{color:var(--c)}</style></head>"
    "<body><header>h</header><main><h1>Hi</h1><p>x</p></main></body></html>"
)


@pytest.mark.anyio
async def test_fix_builds_prompt_from_consensus_votes() -> None:
    candidate = CandidateUI(
        candidate_id=uuid4(), surface_id=uuid4(), iteration=0, artifacts={"index.html": _HTML}
    )
    # A real ConsensusEvaluation (heuristic mode is deterministic, no LLM call) —
    # the exact object the runner hands the fixer.
    consensus = evaluate_candidate(candidate, AxisWeights())
    assert consensus.votes, "fixture must produce per-axis votes to exercise the loop"
    gate_outcomes = run_gates(candidate, _N3C_GATE_AXES).outcomes

    agent = FixerAgent(MetacognitiveGovernor(state=GovernorState()))
    # Stub the LLM so only the (previously crashing) prompt-build path runs.
    directive = FixerDirective(mutations=[], prompt_amendments=[], reasoning="ok")
    agent._call_llm = AsyncMock(return_value=directive)  # type: ignore[method-assign]

    result = await agent.fix(gate_outcomes=gate_outcomes, consensus=consensus)

    assert isinstance(result, FixerDirective)
    # The consensus scores were folded into the prompt the LLM received.
    prompt = agent._call_llm.call_args.args[0]
    assert "Consensus Scores:" in prompt
    for axis in consensus.votes:
        assert axis.value in prompt


@pytest.mark.anyio
async def test_fix_handles_missing_consensus() -> None:
    candidate = CandidateUI(
        candidate_id=uuid4(), surface_id=uuid4(), iteration=0, artifacts={"index.html": _HTML}
    )
    gate_outcomes = run_gates(candidate, _N3C_GATE_AXES).outcomes
    agent = FixerAgent(MetacognitiveGovernor(state=GovernorState()))
    directive = FixerDirective(mutations=[], prompt_amendments=[], reasoning="ok")
    agent._call_llm = AsyncMock(return_value=directive)  # type: ignore[method-assign]

    result = await agent.fix(gate_outcomes=gate_outcomes, consensus=None)
    assert isinstance(result, FixerDirective)


# ---------------------------------------------------------------------------
# Additional coverage: raw-JSON path, fail-soft path, memory_service branch
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_fix_parses_raw_json_string_from_llm() -> None:
    """_call_llm returning a JSON string goes through model_validate_json (fixer.py:150)."""
    candidate = CandidateUI(
        candidate_id=uuid4(), surface_id=uuid4(), iteration=0, artifacts={"index.html": _HTML}
    )
    consensus = evaluate_candidate(candidate, AxisWeights())
    gate_outcomes = run_gates(candidate, _N3C_GATE_AXES).outcomes

    raw_json = json.dumps(
        {
            "mutations": [],
            "prompt_amendments": ["Fix contrast ratio on body text."],
            "reasoning": "Accessibility gate failed — low contrast.",
        }
    )
    agent = FixerAgent(MetacognitiveGovernor(state=GovernorState()))
    agent._call_llm = AsyncMock(return_value=raw_json)  # type: ignore[method-assign]

    result = await agent.fix(gate_outcomes=gate_outcomes, consensus=consensus)

    assert isinstance(result, FixerDirective)
    assert result.prompt_amendments == ["Fix contrast ratio on body text."]


@pytest.mark.anyio
async def test_fix_extra_keys_in_json_route_to_fail_soft() -> None:
    """FixerDirective(extra='forbid') raises on extra keys; fix() must return fail-soft directive
    and call record_step('fixer_failed') (fixer.py:152-166)."""
    candidate = CandidateUI(
        candidate_id=uuid4(), surface_id=uuid4(), iteration=0, artifacts={"index.html": _HTML}
    )
    gate_outcomes = run_gates(candidate, _N3C_GATE_AXES).outcomes

    # JSON with an unexpected key triggers Pydantic extra='forbid' ValidationError.
    bad_json = json.dumps(
        {
            "mutations": [],
            "prompt_amendments": [],
            "reasoning": "ok",
            "unexpected_extra_field": "this should cause validation failure",
        }
    )
    state = GovernorState()
    agent = FixerAgent(MetacognitiveGovernor(state=state))
    agent._call_llm = AsyncMock(return_value=bad_json)  # type: ignore[method-assign]

    result = await agent.fix(gate_outcomes=gate_outcomes, consensus=None)

    assert isinstance(result, FixerDirective)
    # Fail-soft directive contains the recovery amendment, not the bad payload.
    assert any("failed validation" in a or "revise" in a.lower() for a in result.prompt_amendments)
    # Governor degradation accounting must fire.
    assert "fixer_failed" in list(state.step_history)


@pytest.mark.anyio
async def test_fix_llm_raises_routes_to_fail_soft_with_record_step() -> None:
    """When _call_llm raises, fix() returns a no-op directive and records the failure
    in governor state (fixer.py:152-166)."""
    candidate = CandidateUI(
        candidate_id=uuid4(), surface_id=uuid4(), iteration=0, artifacts={"index.html": _HTML}
    )
    gate_outcomes = run_gates(candidate, _N3C_GATE_AXES).outcomes

    state = GovernorState()
    agent = FixerAgent(MetacognitiveGovernor(state=state))
    agent._call_llm = AsyncMock(side_effect=RuntimeError("simulated LLM failure"))  # type: ignore[method-assign]

    result = await agent.fix(gate_outcomes=gate_outcomes, consensus=None)

    assert isinstance(result, FixerDirective)
    assert result.mutations == []
    assert "fixer_failed" in list(state.step_history)


class _FakeSemanticBackend:
    """Minimal in-memory semantic backend satisfying the _SemanticBackend protocol."""

    def __init__(self) -> None:
        self._written: list[tuple[MemoryScopeKey, str]] = []

    async def write_semantic(
        self,
        scope: MemoryScopeKey,
        content: str,
        *,
        embedding: Sequence[float] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> str:
        self._written.append((scope, content))
        return "fake-id"

    async def query_semantic(
        self,
        scope: MemoryScopeKey,
        query_text: str,
        *,
        top_k: int = 3,
        min_similarity: float = 0.0,
    ) -> list[object]:
        return []


@pytest.mark.anyio
async def test_fix_with_memory_service_records_incident_and_resolution() -> None:
    """When memory_service is provided, fix() records the incident and (on success)
    the resolution via IncidentMemoryBank (fixer.py:108-182)."""
    candidate = CandidateUI(
        candidate_id=uuid4(), surface_id=uuid4(), iteration=0, artifacts={"index.html": _HTML}
    )
    consensus = evaluate_candidate(candidate, AxisWeights())
    gate_outcomes = run_gates(candidate, _N3C_GATE_AXES).outcomes

    fake_bank = _FakeSemanticBackend()
    directive = FixerDirective(mutations=[], prompt_amendments=["improve a11y"], reasoning="ok")

    agent = FixerAgent(MetacognitiveGovernor(state=GovernorState()))
    agent._call_llm = AsyncMock(return_value=directive)  # type: ignore[method-assign]

    result = await agent.fix(
        gate_outcomes=gate_outcomes,
        consensus=consensus,
        memory_service=fake_bank,
        tenant_id="test-tenant",
    )

    assert isinstance(result, FixerDirective)
    # At least one write_semantic call must have occurred (incident record + resolution record).
    assert len(fake_bank._written) >= 2, (
        "Expected at least an incident write and a resolution write; "
        f"got {len(fake_bank._written)} write(s)"
    )
