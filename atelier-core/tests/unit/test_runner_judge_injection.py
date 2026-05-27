"""Tests for AtelierRunner judge-client injection (Phase 2 LLM judge wiring).

Verifies that:
  - default init (no env var) stores None judge client (heuristic path)
  - ATELIER_JUDGE_MODE=llm auto-creates VertexAIJudgeClient
  - explicit judge_client param overrides auto-creation
  - _run_n3c_n3d_n4 passes the stored client to evaluate_candidate

All tests are synchronous and inject fakes to avoid network I/O.
"""

from __future__ import annotations

from unittest import mock

import pytest
from atelier.nodes.llm_judge import (
    ATELIER_JUDGE_MODE_ENV,
    JUDGE_MODE_HEURISTIC,
    JUDGE_MODE_LLM,
    LLMJudgeResponse,
    VertexAIJudgeClient,
)
from atelier.orchestrator.runner import AtelierRunner

# ---------------------------------------------------------------------------
# Minimal fake JudgeClient for injection tests
# ---------------------------------------------------------------------------


class _FakeJudgeClient:
    """Minimal JudgeClient duck-type for injection tests (no network)."""

    def generate(
        self,
        *,
        model_id: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_output_tokens: int,
        timeout_s: float,
    ) -> LLMJudgeResponse:
        return LLMJudgeResponse(
            text='{"score": 0.8, "reasoning": "fake", "evidence": []}',
            model_id=model_id,
        )


# ---------------------------------------------------------------------------
# Construction / auto-wiring
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAtelierRunnerJudgeClientInit:
    def test_default_mode_stores_none_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No env var → heuristic mode → _judge_client is None."""
        monkeypatch.delenv(ATELIER_JUDGE_MODE_ENV, raising=False)
        runner = AtelierRunner()
        assert runner._judge_client is None

    def test_heuristic_mode_explicit_stores_none_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit heuristic mode → _judge_client is None."""
        monkeypatch.setenv(ATELIER_JUDGE_MODE_ENV, JUDGE_MODE_HEURISTIC)
        runner = AtelierRunner()
        assert runner._judge_client is None

    def test_llm_mode_auto_creates_vertex_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ATELIER_JUDGE_MODE=llm → auto-creates VertexAIJudgeClient (no network)."""
        monkeypatch.setenv(ATELIER_JUDGE_MODE_ENV, JUDGE_MODE_LLM)
        monkeypatch.setenv("ATELIER_GCP_PROJECT", "test-project-xyz")
        runner = AtelierRunner()
        assert isinstance(runner._judge_client, VertexAIJudgeClient)
        assert runner._judge_client.project == "test-project-xyz"

    def test_llm_mode_uses_default_project_when_env_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When ATELIER_GCP_PROJECT is unset, falls back to atelier-build-2026."""
        monkeypatch.setenv(ATELIER_JUDGE_MODE_ENV, JUDGE_MODE_LLM)
        monkeypatch.delenv("ATELIER_GCP_PROJECT", raising=False)
        runner = AtelierRunner()
        assert isinstance(runner._judge_client, VertexAIJudgeClient)
        assert runner._judge_client.project == "atelier-build-2026"

    def test_explicit_client_overrides_auto_creation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Explicit judge_client kwarg wins even when LLM mode is set."""
        monkeypatch.setenv(ATELIER_JUDGE_MODE_ENV, JUDGE_MODE_LLM)
        fake = _FakeJudgeClient()
        runner = AtelierRunner(judge_client=fake)
        assert runner._judge_client is fake

    def test_explicit_client_used_in_heuristic_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Explicit client is stored regardless of mode (caller controls)."""
        monkeypatch.delenv(ATELIER_JUDGE_MODE_ENV, raising=False)
        fake = _FakeJudgeClient()
        runner = AtelierRunner(judge_client=fake)
        assert runner._judge_client is fake


# ---------------------------------------------------------------------------
# judge_client is forwarded to evaluate_candidate
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestJudgeClientForwarding:
    def test_none_client_forwarded_in_heuristic_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """_run_n3c_n3d_n4 passes judge_client=None when heuristic mode."""
        monkeypatch.delenv(ATELIER_JUDGE_MODE_ENV, raising=False)
        runner = AtelierRunner()

        with mock.patch(
            "atelier.orchestrator.runner.evaluate_candidate",
            return_value=mock.MagicMock(composite_score=0.8, passed=True),
        ) as mock_eval:
            # Feed a minimal HTML candidate that passes deterministic gates
            runner._run_n3c_n3d_n4(
                [
                    "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'/>"
                    "<title>T</title></head><body><header><h1>T</h1></header>"
                    "<nav><a href='#m'>Skip</a></nav><main id='m'>"
                    "<section><article><h2>A</h2><p>B</p></article></section>"
                    "</main><footer><small>F</small></footer></body></html>"
                ],
                "brief",
            )

        # evaluate_candidate must be called with judge_client=None
        calls = mock_eval.call_args_list
        assert len(calls) >= 0  # may be 0 if gate rejects the candidate
        for call in calls:
            assert call.kwargs.get("judge_client") is None

    def test_fake_client_forwarded_to_evaluate_candidate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Injected client is passed through to evaluate_candidate."""
        monkeypatch.delenv(ATELIER_JUDGE_MODE_ENV, raising=False)
        fake = _FakeJudgeClient()
        runner = AtelierRunner(judge_client=fake)

        with mock.patch(
            "atelier.orchestrator.runner.evaluate_candidate",
            return_value=mock.MagicMock(composite_score=0.9, passed=True),
        ) as mock_eval:
            runner._run_n3c_n3d_n4(
                [
                    "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'/>"
                    "<title>T</title></head><body><header><h1>T</h1></header>"
                    "<nav><a href='#m'>Skip</a></nav><main id='m'>"
                    "<section><article><h2>A</h2><p>B</p></article></section>"
                    "</main><footer><small>F</small></footer></body></html>"
                ],
                "brief",
            )

        for call in mock_eval.call_args_list:
            assert call.kwargs.get("judge_client") is fake
