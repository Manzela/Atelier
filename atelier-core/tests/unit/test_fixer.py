"""Regression tests for the N3e FixerAgent prompt construction.

The fixer read ``consensus.per_axis_scores``, but the runner passes a
``ConsensusEvaluation`` (which exposes ``votes``); ``per_axis_scores`` lives on a
different model. The flow only reaches the fixer once generation completes
without converging, so the AttributeError was latent until the pipeline ran
end-to-end against real Vertex — it then 500'd every non-converging request.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from atelier.gates.runner import run_gates
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
