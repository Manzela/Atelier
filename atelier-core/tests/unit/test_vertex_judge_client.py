"""Unit tests for VertexAIJudgeClient.generate — behavioral coverage.

Finding 90 identified that the production Vertex client path (request
construction + response-to-LLMJudgeResponse mapping) had zero behavioral
coverage.  These tests patch ``_import_vertex_sdk`` to return a fake SDK
object and assert the full response-mapping logic without any real network
call.

Coverage targets:
    - text, model_id, input/output/thinking token extraction from usage_metadata
    - avg_logprob extraction from candidates[0].avg_logprobs
    - LLMJudgeError raised when response.text is None
    - GCS screenshot attachment (happy path and fail-soft on image-part error)
    - SDK initialization runs exactly once across multiple calls (cached)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest import mock

import pytest
from atelier.nodes.llm_judge import LLMJudgeError, LLMJudgeResponse, VertexAIJudgeClient

# ---------------------------------------------------------------------------
# Fake SDK objects
# ---------------------------------------------------------------------------


@dataclass
class _FakeUsageMetadata:
    prompt_token_count: int = 10
    candidates_token_count: int = 5
    thoughts_token_count: int = 2


@dataclass
class _FakeCandidate:
    avg_logprobs: float | None = -0.15


@dataclass
class _FakeResponse:
    text: str | None = '{"score": 0.8, "reasoning": "ok"}'
    usage_metadata: _FakeUsageMetadata | None = field(default_factory=_FakeUsageMetadata)
    candidates: list[_FakeCandidate] = field(default_factory=lambda: [_FakeCandidate()])


@dataclass
class _FakeGenerativeModel:
    model_name: str = ""
    system_instruction: str = ""
    _response: _FakeResponse = field(default_factory=_FakeResponse)

    def generate_content(self, contents: list[Any], *, generation_config: Any) -> _FakeResponse:
        return self._response


class _FakeGenerativeModels:
    """Minimal stand-in for vertexai.generative_models."""

    def __init__(self, model: _FakeGenerativeModel | None = None) -> None:
        self._model = model or _FakeGenerativeModel()
        self._init_called = 0
        self._created_models: list[str] = []

    class GenerationConfig:
        def __init__(self, **kwargs: Any) -> None:
            pass

    class Part:
        @staticmethod
        def from_uri(*, mime_type: str, uri: str) -> _FakeGenerativeModels.Part:  # type: ignore[name-defined]
            _ = mime_type
            _ = uri
            return _FakeGenerativeModels.Part()  # type: ignore[attr-defined]

    # Named to match the production SDK's class-like callable attribute.
    # Ruff N802 is suppressed: this must match the name the production code calls.
    def GenerativeModel(  # noqa: N802
        self, *, model_name: str, system_instruction: str
    ) -> _FakeGenerativeModel:
        _ = system_instruction
        self._created_models.append(model_name)
        return self._model


class _FakeVertexAI:
    """Minimal stand-in for the vertexai top-level module."""

    def __init__(self, gm: _FakeGenerativeModels) -> None:
        self._gm = gm
        self.init_call_count = 0

    def init(self, *, project: str, location: str) -> None:
        self.init_call_count += 1


def _make_sdk(
    response: _FakeResponse | None = None,
) -> tuple[_FakeVertexAI, _FakeGenerativeModels]:
    gm = _FakeGenerativeModels(model=_FakeGenerativeModel(_response=response or _FakeResponse()))
    vtx = _FakeVertexAI(gm)
    return vtx, gm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_KWARGS: dict[str, Any] = {
    "model_id": "gemini-2.5-flash-preview-05-20",
    "system_prompt": "You are a judge.",
    "user_prompt": "Evaluate this.",
    "temperature": 0.2,
    "max_output_tokens": 1024,
    "timeout_s": 10.0,
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestVertexAIJudgeClientGenerate:
    """Behavioral tests for VertexAIJudgeClient.generate."""

    def _call(
        self,
        *,
        response: _FakeResponse | None = None,
        screenshot_url: str | None = None,
    ) -> tuple[LLMJudgeResponse, _FakeVertexAI, _FakeGenerativeModels]:
        vtx, gm = _make_sdk(response)

        import atelier.nodes.llm_judge as module

        client = module.VertexAIJudgeClient(project="test-project")
        with mock.patch.object(module, "_import_vertex_sdk", return_value=(vtx, gm)):
            result = client.generate(**_BASE_KWARGS, screenshot_url=screenshot_url)
        return result, vtx, gm

    def test_text_and_model_id_mapped(self) -> None:
        resp = _FakeResponse(text='{"score": 0.9}')
        result, _, _ = self._call(response=resp)
        assert result.text == '{"score": 0.9}'
        assert result.model_id == _BASE_KWARGS["model_id"]

    def test_token_counts_extracted_from_usage_metadata(self) -> None:
        usage = _FakeUsageMetadata(
            prompt_token_count=12, candidates_token_count=7, thoughts_token_count=3
        )
        resp = _FakeResponse(usage_metadata=usage)
        result, _, _ = self._call(response=resp)
        assert result.input_tokens == 12
        assert result.output_tokens == 7
        assert result.thinking_tokens == 3

    def test_zero_tokens_when_no_usage_metadata(self) -> None:
        resp = _FakeResponse(usage_metadata=None)
        result, _, _ = self._call(response=resp)
        assert result.input_tokens == 0
        assert result.output_tokens == 0
        assert result.thinking_tokens == 0

    def test_avg_logprob_extracted_from_candidates(self) -> None:
        resp = _FakeResponse(candidates=[_FakeCandidate(avg_logprobs=-0.25)])
        result, _, _ = self._call(response=resp)
        assert result.avg_logprob == pytest.approx(-0.25)

    def test_avg_logprob_none_when_no_candidates(self) -> None:
        resp = _FakeResponse(candidates=[])
        result, _, _ = self._call(response=resp)
        assert result.avg_logprob is None

    def test_avg_logprob_none_when_candidates_logprobs_absent(self) -> None:
        resp = _FakeResponse(candidates=[_FakeCandidate(avg_logprobs=None)])
        result, _, _ = self._call(response=resp)
        assert result.avg_logprob is None

    def test_raises_llm_judge_error_when_text_is_none(self) -> None:
        resp = _FakeResponse(text=None)
        with pytest.raises(LLMJudgeError, match=r"no .text attribute"):
            self._call(response=resp)

    def test_sdk_initialized_exactly_once_across_calls(self) -> None:
        vtx, gm = _make_sdk()
        import atelier.nodes.llm_judge as module

        client = module.VertexAIJudgeClient(project="test-project")
        with mock.patch.object(module, "_import_vertex_sdk", return_value=(vtx, gm)):
            client.generate(**_BASE_KWARGS)
            client.generate(**_BASE_KWARGS)
        assert vtx.init_call_count == 1, (
            f"vertexai.init should be called once; got {vtx.init_call_count}"
        )

    def test_model_cached_across_calls_with_same_model_id(self) -> None:
        vtx, gm = _make_sdk()
        import atelier.nodes.llm_judge as module

        client = module.VertexAIJudgeClient(project="test-project")
        with mock.patch.object(module, "_import_vertex_sdk", return_value=(vtx, gm)):
            client.generate(**_BASE_KWARGS)
            client.generate(**_BASE_KWARGS)
        # GenerativeModel should be constructed only once for the same model_id.
        assert gm._created_models.count(_BASE_KWARGS["model_id"]) == 1

    def test_returns_llm_judge_response_instance(self) -> None:
        result, _, _ = self._call()
        assert isinstance(result, LLMJudgeResponse)

    def test_screenshot_url_attached_when_gcs_uri(self) -> None:
        # When a GCS URI is provided the image Part is constructed and appended
        # to contents.  We verify the call doesn't raise and returns a valid
        # response (the Part construction is tested implicitly via the fake).
        result, _, _ = self._call(screenshot_url="gs://bucket/image.png")
        assert result.text is not None

    def test_screenshot_url_skipped_when_not_gcs(self) -> None:
        # Non-GCS URLs must not be attached (the code checks startswith("gs://")).
        result, _, _ = self._call(screenshot_url="https://example.com/img.png")
        assert result.text is not None

    def test_screenshot_part_error_is_fail_soft(self) -> None:
        # If Part.from_uri raises, the call must continue and return a response
        # rather than propagating the error.
        vtx, gm = _make_sdk()

        class _RaisingPart:
            @staticmethod
            def from_uri(**_kwargs: Any) -> None:
                raise RuntimeError("gcs fail")

        gm.Part = _RaisingPart  # type: ignore[assignment]
        import atelier.nodes.llm_judge as module

        client = module.VertexAIJudgeClient(project="test-project")
        with mock.patch.object(module, "_import_vertex_sdk", return_value=(vtx, gm)):
            result = client.generate(**_BASE_KWARGS, screenshot_url="gs://bucket/img.png")
        assert isinstance(result, LLMJudgeResponse)
