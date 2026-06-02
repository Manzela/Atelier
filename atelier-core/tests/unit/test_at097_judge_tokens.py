"""AT-097 — N3d judge-token threading oracle (closes the AT-095 under-count).

Before AT-097, N3d (D-O-R-A-V consensus) judge LLM calls had their Vertex
``usage_metadata`` tokens extracted into :class:`LLMJudgeResponse` but DROPPED at
the ``_JudgeScore`` boundary, so judge spend never reached the per-user lifetime
cap — only N3a was counted (a conservative under-count, flagged in the AT-095
review). These tests prove the tokens now flow end-to-end:

    LLMJudgeResponse → _JudgeScore → ConsensusEvaluation → runner → add_user_tokens

Hermetic: a hand-rolled ``JudgeClient`` double — no Vertex / network. Assertions
are structural (token sums, fallback accounting), never specific generated text.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from atelier.models.axis_weights import AxisWeights
from atelier.models.data_contracts import CandidateUI
from atelier.nodes.consensus import evaluate_candidate
from atelier.nodes.llm_judge import BrandLLMJudge, LLMJudgeResponse
from atelier.orchestrator.runner import AtelierRunner

pytestmark = pytest.mark.unit

# A valid-JSON judge body so the LLM score() success path is taken.
_VALID_JUDGE_JSON = '{"score": 0.85, "reasoning": "ok", "evidence": ["index.html"]}'
_DORAV_AXES = 5  # D-O-R-A-V: brand / originality / relevance / accessibility / visual


class _StubJudgeClient:
    """Returns one fixed response for every axis (known token counts)."""

    def __init__(self, response: LLMJudgeResponse) -> None:
        self._response = response
        self.calls = 0

    def generate(self, **_kwargs: Any) -> LLMJudgeResponse:
        self.calls += 1
        return self._response


class _RaisingJudgeClient:
    """generate() itself fails — nothing was spent, so 0 tokens must be counted."""

    def generate(self, **_kwargs: Any) -> LLMJudgeResponse:
        raise RuntimeError("vertex unavailable")


def _response(*, input_tokens: int, output_tokens: int, thinking_tokens: int) -> LLMJudgeResponse:
    return LLMJudgeResponse(
        text=_VALID_JUDGE_JSON,
        model_id="stub-model",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        thinking_tokens=thinking_tokens,
    )


def _candidate() -> CandidateUI:
    return CandidateUI(
        candidate_id=uuid4(),
        surface_id=uuid4(),
        iteration=0,
        artifacts={
            "index.html": "<!doctype html><html lang='en'><body><h1>Hi</h1></body></html>",
            "main.css": ":root{--brand:#0a0a0a}",
        },
    )


# --- 1. LLMJudge.score() carries the response tokens into _JudgeScore ----------


def test_llm_judge_score_populates_tokens_on_success() -> None:
    judge = BrandLLMJudge(
        client=_StubJudgeClient(_response(input_tokens=120, output_tokens=80, thinking_tokens=10))
    )
    result = judge.score(_candidate())
    assert (result.input_tokens, result.output_tokens, result.thinking_tokens) == (120, 80, 10)


def test_llm_judge_counts_real_spend_even_when_parse_fails_after_generate() -> None:
    # generate() SUCCEEDED (tokens were spent on Vertex) but the body is unparseable
    # → the judge falls back to the heuristic SCORE, but the real token spend MUST
    # still be counted (no silent under-count of money already spent).
    bad = LLMJudgeResponse(
        text="THIS IS NOT JSON",
        model_id="m",
        input_tokens=120,
        output_tokens=80,
        thinking_tokens=10,
    )
    judge = BrandLLMJudge(client=_StubJudgeClient(bad))
    result = judge.score(_candidate())
    assert "fallback" in result.diagnostic.lower()  # heuristic score path taken
    assert (result.input_tokens, result.output_tokens, result.thinking_tokens) == (120, 80, 10)


def test_llm_judge_counts_zero_tokens_when_generate_itself_fails() -> None:
    # The Vertex call never returned → nothing was spent → 0 tokens (not phantom).
    judge = BrandLLMJudge(client=_RaisingJudgeClient())
    result = judge.score(_candidate())
    assert "fallback" in result.diagnostic.lower()
    assert (result.input_tokens, result.output_tokens, result.thinking_tokens) == (0, 0, 0)


# --- 2. evaluate_candidate() accumulates judge tokens across all 5 axes --------


def test_evaluate_candidate_sums_judge_tokens_across_axes() -> None:
    client = _StubJudgeClient(_response(input_tokens=120, output_tokens=80, thinking_tokens=10))
    result = evaluate_candidate(
        _candidate(), AxisWeights(), judge_mode="llm", judge_client=client, seed=0
    )
    assert client.calls == _DORAV_AXES  # one LLM call per axis
    assert result.total_input_tokens == _DORAV_AXES * 120
    assert result.total_output_tokens == _DORAV_AXES * 80
    assert result.total_thinking_tokens == _DORAV_AXES * 10


def test_evaluate_candidate_hybrid_mode_threads_llm_judge_tokens() -> None:
    # Hybrid mode runs BOTH the heuristic AND the LLM judge (real Vertex spend),
    # then returns the LLM score. The LLM tokens MUST be counted — otherwise
    # hybrid silently re-opens the N3a-only under-count that `llm` mode closed.
    client = _StubJudgeClient(_response(input_tokens=120, output_tokens=80, thinking_tokens=10))
    result = evaluate_candidate(
        _candidate(), AxisWeights(), judge_mode="hybrid", judge_client=client, seed=0
    )
    assert client.calls == _DORAV_AXES
    assert result.total_input_tokens == _DORAV_AXES * 120
    assert result.total_output_tokens == _DORAV_AXES * 80
    assert result.total_thinking_tokens == _DORAV_AXES * 10


def test_evaluate_candidate_heuristic_mode_attributes_zero_judge_tokens() -> None:
    # Non-vacuity guard: heuristic scorers make no LLM call, so they must NOT
    # fabricate token spend. If the threading double-counted or defaulted wrong,
    # this would be non-zero.
    result = evaluate_candidate(_candidate(), AxisWeights(), judge_mode="heuristic", seed=0)
    assert result.total_input_tokens == 0
    assert result.total_output_tokens == 0
    assert result.total_thinking_tokens == 0


# --- 3. The runner sums per-candidate judge tokens into the convergence result -


def test_run_n3c_n3d_n4_returns_summed_judge_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATELIER_JUDGE_MODE", "llm")
    runner = AtelierRunner(
        judge_client=_StubJudgeClient(
            _response(input_tokens=120, output_tokens=80, thinking_tokens=10)
        )
    )
    # Force the deterministic N3c gate to pass so the lone candidate reaches N3d
    # (gates are tested exhaustively elsewhere; here we isolate token threading).
    monkeypatch.setattr(
        "atelier.orchestrator.runner.run_gates",
        lambda *_a, **_k: SimpleNamespace(all_passed=True, outcomes=[]),
    )
    result = runner._run_n3c_n3d_n4(
        ["<!doctype html><html lang='en'><body><h1>Hi</h1></body></html>"], "brief"
    )
    assert result["judge_input_tokens"] == _DORAV_AXES * 120
    assert result["judge_output_tokens"] == _DORAV_AXES * 80
    assert result["judge_thinking_tokens"] == _DORAV_AXES * 10
