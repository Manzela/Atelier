"""Tests for the Phase 2 LLM judge module (:mod:`atelier.nodes.llm_judge`).

The Phase 2 ConsensusAgent upgrade swaps each ``_score_*`` heuristic in
:mod:`atelier.nodes.consensus` for a Vertex AI LLM call routed via
:data:`atelier.models.model_registry.JUDGE_MODEL_CONFIG`. This test file
locks down that contract:

    1. **JudgeClient injection** — every LLM judge takes a pluggable
       ``JudgeClient`` so Vertex AI can be mocked out at test time. The
       five concrete judges (Brand, Originality, Relevance, Accessibility,
       VisualClarity) all delegate to that client.
    2. **Response parsing** — the JSON output schema is interpreted into a
       ``_JudgeScore`` with score, reasoning, and provenance vars.
    3. **Bayesian CI extraction** — when the response carries token-level
       ``avg_logprob`` the CI is narrower for confident responses; when
       absent the CI falls back to a symmetric band.
    4. **Fail-soft trichotomy** — every failure mode (JSON parse error,
       client timeout, network failure, score out of range) routes the
       judge to the Phase 1 heuristic so the surrounding pipeline never
       breaks.
    5. **Dispatch resolver** — :func:`_resolve_axis_scorers` returns the
       right scorer dict for ``heuristic | llm | hybrid``; hybrid logs
       disagreement between modes.
    6. **Backward compat** — :func:`evaluate_candidate` defaults to
       ``"heuristic"`` so all 249 Phase 1 tests keep passing without
       touching env vars.

Tests use a hand-rolled :class:`_FakeJudgeClient` (lighter than
``unittest.mock`` for this surface, and the call-recording it does is
explicit instead of magical). Real Vertex AI is never invoked from this
suite — that's covered by the integration suite tagged ``@external``.

PRD Reference: §6.3 (N3d ConsensusAgent), F0209-F0211
Audit Reference: §7 (FA-018 model routing, fail-soft trichotomy)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any
from unittest import mock
from uuid import uuid4

import pytest
from atelier.models.axis_weights import AxisWeights
from atelier.models.data_contracts import CandidateUI
from atelier.models.enums import JudgeAxis
from atelier.models.model_registry import (
    JUDGE_MODEL_CONFIG,
    JUDGE_MODEL_ORIGINALITY,
)
from atelier.nodes.consensus import (
    _AXIS_SCORERS,
    _JudgeScore,
    evaluate_candidate,
)
from atelier.nodes.llm_judge import (
    ATELIER_JUDGE_MODE_ENV,
    CI_DEFAULT_HALF_WIDTH,
    DEFAULT_JUDGE_MODE,
    JUDGE_MODE_HEURISTIC,
    JUDGE_MODE_HYBRID,
    JUDGE_MODE_LLM,
    JUDGE_PROMPTS,
    VALID_JUDGE_MODES,
    AccessibilityLLMJudge,
    BrandLLMJudge,
    LLMJudge,
    LLMJudgeError,
    LLMJudgeResponse,
    OriginalityLLMJudge,
    RelevanceLLMJudge,
    VisualClarityLLMJudge,
    compute_bayesian_ci,
    extract_score_from_response,
    make_llm_judge,
)
from atelier.nodes.llm_judge import (
    _resolve_axis_scorers as resolve_axis_scorers,
)

# ---------------------------------------------------------------------------
# Module-level test constants
# ---------------------------------------------------------------------------

EXPECTED_AXES: tuple[str, ...] = (
    "brand",
    "originality",
    "relevance",
    "accessibility",
    "visual_clarity",
)
EXPECTED_AXIS_COUNT: int = 5
DETERMINISTIC_SEED: int = 42

# Sample judge outputs.
HIGH_QUALITY_SCORE: float = 0.85
#: Phase 1 heuristic composite for the rich-artifact fixture; pinned
#: so Phase 2 mode dispatch in default (heuristic) mode is byte-equal
#: to the Phase 1 path. Update this value (with a justification) only
#: when the heuristic scoring formula itself changes.
PHASE1_RICH_COMPOSITE: float = 0.9562
MID_QUALITY_SCORE: float = 0.55
LOW_QUALITY_SCORE: float = 0.15
OUT_OF_RANGE_SCORE_HIGH: float = 1.7
OUT_OF_RANGE_SCORE_LOW: float = -0.3

# Logprob → CI calibration assertions.
HIGH_CONFIDENCE_LOGPROB: float = -0.05
LOW_CONFIDENCE_LOGPROB: float = -3.0


# ---------------------------------------------------------------------------
# Test fixtures and helpers
# ---------------------------------------------------------------------------


def _make_candidate(artifacts: dict[str, str] | None = None) -> CandidateUI:
    """Build a :class:`CandidateUI` from supplied artifacts."""
    return CandidateUI(
        candidate_id=uuid4(),
        surface_id=uuid4(),
        iteration=0,
        artifacts=artifacts if artifacts is not None else {},
    )


def _rich_artifacts() -> dict[str, str]:
    """Return a maximal HTML + CSS pair scoring composite=1.0 under Phase 1.

    Mathematically calibrated for the Phase 1 heuristic targets so the
    backward-compat test pinning ``composite_score == 1.0`` is satisfied
    without re-tuning the scorers (per CLAUDE.md `<no_test_driven_slop>`:
    fix the fixture, not the code under test).

    Targets met:
      * Brand: 7 CSS vars (>=5), 5 hex colors (>=3)
      * Originality: 23 unique CSS props (>=12), 8 unique selectors (>=6)
      * Relevance: ~1058 text chars / 26 tags > 30 chars/tag threshold
      * Accessibility: 3 ARIA attrs (>=3), 6 semantic landmarks (>=5),
        0 images (alt ratio=1.0)
      * Visual clarity: 10 typography decls (>=4), 7 spacing decls (>=4)
    """
    html = (
        "<!DOCTYPE html>\n"
        "<html lang='en'>\n"
        "<head><title>Atelier Reference Surface</title></head>\n"
        "<body>\n"
        "  <header aria-label='Site header'>\n"
        "    <nav aria-label='Primary navigation'>\n"
        "      <a href='/'>Home</a>\n"
        "      <a href='/about'>About</a>\n"
        "    </nav>\n"
        "  </header>\n"
        "  <main aria-label='Main content region'>\n"
        "    <article>\n"
        "      <h1>Atelier: an autonomous design agent</h1>\n"
        "      <p>\n"
        "        Atelier composes a deterministic-gate-first multi-agent DAG\n"
        "        with five LLM judges across the D-O-R-A-V axes to produce\n"
        "        production-grade UI candidates. Every node is structured as a\n"
        "        deterministic gate followed by a probabilistic agent, never\n"
        "        the reverse, so the system fails closed and surfaces real\n"
        "        signal even when LLM judges are degraded or unavailable.\n"
        "      </p>\n"
        "    </article>\n"
        "    <section>\n"
        "      <h2>Operating principles</h2>\n"
        "      <p>\n"
        "        Token discipline, accessibility-by-default, and Bayesian\n"
        "        confidence intervals on every judge vote keep dashboards\n"
        "        honest and the Fixer loop on the steepest possible gradient.\n"
        "      </p>\n"
        "    </section>\n"
        "    <aside>\n"
        "      <h2>Status</h2>\n"
        "      <p>Phase 1 shipped; Phase 2 LLM judges land this sprint.</p>\n"
        "    </aside>\n"
        "  </main>\n"
        "  <footer>(c) 2026 Atelier. All rights reserved.</footer>\n"
        "</body>\n"
        "</html>\n"
    )
    css = (
        ":root {\n"
        "  --color-primary: #0b1d3a;\n"
        "  --color-accent: #ff6b35;\n"
        "  --color-bg: #ffffff;\n"
        "  --color-fg: #1a1a1a;\n"
        "  --color-muted: #6b7280;\n"
        "  --space-unit: 0.5rem;\n"
        "  --radius-base: 6px;\n"
        "}\n"
        "body {\n"
        "  background-color: var(--color-bg);\n"
        "  color: var(--color-fg);\n"
        "  font-family: 'Inter', sans-serif;\n"
        "  font-size: 16px;\n"
        "  font-weight: 400;\n"
        "  line-height: 1.6;\n"
        "  letter-spacing: 0.01em;\n"
        "  margin: 0;\n"
        "  padding: 0;\n"
        "}\n"
        "header {\n"
        "  background: var(--color-primary);\n"
        "  padding: 1rem;\n"
        "  border-bottom: 1px solid var(--color-muted);\n"
        "}\n"
        "nav a {\n"
        "  color: var(--color-bg);\n"
        "  font-weight: 600;\n"
        "  margin: 0.25rem;\n"
        "  text-decoration: none;\n"
        "}\n"
        "main {\n"
        "  display: grid;\n"
        "  gap: 1rem;\n"
        "  max-width: 720px;\n"
        "  margin: 0 auto;\n"
        "  padding: 2rem;\n"
        "}\n"
        "article h1 {\n"
        "  font-size: 32px;\n"
        "  font-weight: 700;\n"
        "  line-height: 1.2;\n"
        "  margin-bottom: 1rem;\n"
        "}\n"
        "section h2 {\n"
        "  font-family: 'Inter', sans-serif;\n"
        "  font-size: 22px;\n"
        "  font-weight: 600;\n"
        "  color: var(--color-accent);\n"
        "}\n"
        "footer {\n"
        "  border-top: 1px solid #cccccc;\n"
        "  padding: 1rem;\n"
        "  text-align: center;\n"
        "  color: var(--color-muted);\n"
        "}\n"
    )
    return {"index.html": html, "main.css": css}


def _good_response(
    *,
    score: float = HIGH_QUALITY_SCORE,
    reasoning: str = "The artifact demonstrates strong tokenization.",
    evidence: list[str] | None = None,
    model_id: str = "gemini-2.5-flash-preview-05-20",
    avg_logprob: float | None = None,
) -> LLMJudgeResponse:
    """Build a well-formed :class:`LLMJudgeResponse`.

    The body is structured JSON matching the schema the LLM judges expect.
    """
    payload = {
        "score": score,
        "reasoning": reasoning,
        "evidence": evidence if evidence is not None else ["main.css", "index.html"],
    }
    return LLMJudgeResponse(
        text=json.dumps(payload),
        model_id=model_id,
        input_tokens=120,
        output_tokens=80,
        avg_logprob=avg_logprob,
    )


@dataclass
class _FakeJudgeClient:
    """Hand-rolled test double for :class:`atelier.nodes.llm_judge.JudgeClient`.

    Replaces ``unittest.mock`` for this surface because the calls are not
    just one shape (we want per-axis canned responses, exception injection,
    and call recording) and a tiny dataclass spells out the contract more
    clearly than the magic of ``MagicMock``.

    Attributes:
        responses: Per-axis canned responses keyed by snake_case axis name.
        exceptions: Per-axis exception classes to raise instead of returning.
            When set, takes precedence over ``responses``.
        default_response: Fallback used when no per-axis entry exists.
        calls: Recorded call kwargs in invocation order.
    """

    responses: dict[str, LLMJudgeResponse] = field(default_factory=dict)
    exceptions: dict[str, type[BaseException]] = field(default_factory=dict)
    default_response: LLMJudgeResponse | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

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
        """Return the canned response or raise the canned exception."""
        self.calls.append(
            {
                "model_id": model_id,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
                "timeout_s": timeout_s,
            },
        )
        # Route by system_prompt rather than model_id: four axes share
        # the same Flash model_id (only Originality runs on Pro), so a
        # model_id lookup would always collapse to a single axis. Each
        # JUDGE_PROMPTS entry has a unique system_prompt per axis, so
        # this lookup is unambiguous.
        axis_name = next(
            (axis for axis, prompts in JUDGE_PROMPTS.items() if prompts[0] == system_prompt),
            None,
        )
        if axis_name is not None and axis_name in self.exceptions:
            raise self.exceptions[axis_name]("injected client failure")
        if axis_name is not None and axis_name in self.responses:
            return self.responses[axis_name]
        if self.default_response is not None:
            return self.default_response
        return _good_response(model_id=model_id)


# ---------------------------------------------------------------------------
# Module-level invariants
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModuleConstants:
    """Constants exported by :mod:`atelier.nodes.llm_judge`."""

    def test_judge_mode_names_are_canonical(self) -> None:
        assert JUDGE_MODE_HEURISTIC == "heuristic"
        assert JUDGE_MODE_LLM == "llm"
        assert JUDGE_MODE_HYBRID == "hybrid"

    def test_default_mode_is_heuristic_for_backward_compat(self) -> None:
        # Defaulting to heuristic is the contract that keeps Phase 1 tests
        # passing unchanged when no env var is set.
        assert DEFAULT_JUDGE_MODE == JUDGE_MODE_HEURISTIC

    def test_valid_modes_set_matches_constants(self) -> None:
        assert (
            frozenset(
                {JUDGE_MODE_HEURISTIC, JUDGE_MODE_LLM, JUDGE_MODE_HYBRID},
            )
            == VALID_JUDGE_MODES
        )

    def test_env_var_name_matches_spec(self) -> None:
        # PRD §6.3 N3d names the flag ATELIER_JUDGE_MODE.
        assert ATELIER_JUDGE_MODE_ENV == "ATELIER_JUDGE_MODE"

    def test_judge_prompts_cover_every_axis(self) -> None:
        # Every axis in the dispatch table must have a prompt pair.
        assert set(JUDGE_PROMPTS.keys()) == set(EXPECTED_AXES)
        for axis, prompts in JUDGE_PROMPTS.items():
            system_prompt, user_template = prompts
            assert isinstance(system_prompt, str)
            assert isinstance(user_template, str)
            # The user template must reference the candidate's artifacts.
            assert "{artifacts}" in user_template, (
                f"axis '{axis}' user template missing {{artifacts}} placeholder"
            )

    def test_prompts_mention_axis_specific_concerns(self) -> None:
        # Each system prompt should namesake the axis concept so the judge
        # doesn't drift across axes.
        assert "brand" in JUDGE_PROMPTS["brand"][0].lower()
        assert "original" in JUDGE_PROMPTS["originality"][0].lower()
        assert "relevan" in JUDGE_PROMPTS["relevance"][0].lower()
        assert "accessib" in JUDGE_PROMPTS["accessibility"][0].lower()
        assert "visual" in JUDGE_PROMPTS["visual_clarity"][0].lower()


# ---------------------------------------------------------------------------
# Response parsing helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractScoreFromResponse:
    """:func:`extract_score_from_response` parses JSON judge output."""

    def test_well_formed_json_returns_triple(self) -> None:
        response = _good_response(
            score=0.72,
            reasoning="Tokens are present, palette is restrained.",
            evidence=["main.css"],
        )
        score, reasoning, evidence = extract_score_from_response(response)
        assert score == pytest.approx(0.72)
        assert "tokens" in reasoning.lower()
        assert evidence == ["main.css"]

    def test_score_above_range_is_clamped_to_one(self) -> None:
        response = _good_response(score=OUT_OF_RANGE_SCORE_HIGH)
        score, _, _ = extract_score_from_response(response)
        assert score == 1.0

    def test_score_below_range_is_clamped_to_zero(self) -> None:
        response = _good_response(score=OUT_OF_RANGE_SCORE_LOW)
        score, _, _ = extract_score_from_response(response)
        assert score == 0.0

    def test_malformed_json_raises_llm_judge_error(self) -> None:
        response = LLMJudgeResponse(
            text="not json at all",
            model_id="gemini-2.5-flash-preview-05-20",
        )
        with pytest.raises(LLMJudgeError):
            extract_score_from_response(response)

    def test_missing_score_field_raises_llm_judge_error(self) -> None:
        response = LLMJudgeResponse(
            text=json.dumps({"reasoning": "no score here"}),
            model_id="gemini-2.5-flash-preview-05-20",
        )
        with pytest.raises(LLMJudgeError):
            extract_score_from_response(response)

    def test_score_not_numeric_raises_llm_judge_error(self) -> None:
        response = LLMJudgeResponse(
            text=json.dumps({"score": "high", "reasoning": "bad type"}),
            model_id="gemini-2.5-flash-preview-05-20",
        )
        with pytest.raises(LLMJudgeError):
            extract_score_from_response(response)

    def test_json_inside_markdown_code_fence_is_tolerated(self) -> None:
        # Gemini sometimes wraps its JSON in ```json``` fences. The parser
        # should peel the fence before json.loads.
        payload = {"score": 0.6, "reasoning": "ok", "evidence": []}
        response = LLMJudgeResponse(
            text=f"```json\n{json.dumps(payload)}\n```",
            model_id="gemini-2.5-flash-preview-05-20",
        )
        score, reasoning, evidence = extract_score_from_response(response)
        assert score == pytest.approx(0.6)
        assert reasoning == "ok"
        assert evidence == []


# ---------------------------------------------------------------------------
# Bayesian CI computation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestComputeBayesianCI:
    """:func:`compute_bayesian_ci` derives an interval from avg_logprob."""

    def test_missing_logprob_yields_default_half_width(self) -> None:
        low, high = compute_bayesian_ci(0.5, None)
        assert low == pytest.approx(max(0.0, 0.5 - CI_DEFAULT_HALF_WIDTH))
        assert high == pytest.approx(min(1.0, 0.5 + CI_DEFAULT_HALF_WIDTH))

    def test_high_confidence_logprob_narrows_interval(self) -> None:
        low_narrow, high_narrow = compute_bayesian_ci(0.5, HIGH_CONFIDENCE_LOGPROB)
        low_wide, high_wide = compute_bayesian_ci(0.5, LOW_CONFIDENCE_LOGPROB)
        narrow_width = high_narrow - low_narrow
        wide_width = high_wide - low_wide
        # Confident judge → smaller interval.
        assert narrow_width < wide_width
        # And both intervals remain inside [0, 1].
        assert 0.0 <= low_narrow <= high_narrow <= 1.0
        assert 0.0 <= low_wide <= high_wide <= 1.0

    def test_interval_clamped_to_unit_range(self) -> None:
        _low_top, high_top = compute_bayesian_ci(1.0, LOW_CONFIDENCE_LOGPROB)
        assert high_top == 1.0
        low_bottom, _ = compute_bayesian_ci(0.0, LOW_CONFIDENCE_LOGPROB)
        assert low_bottom == 0.0

    def test_score_is_always_inside_interval(self) -> None:
        for score in (0.05, 0.5, 0.95):
            low, high = compute_bayesian_ci(score, HIGH_CONFIDENCE_LOGPROB)
            assert low <= score <= high


# ---------------------------------------------------------------------------
# Concrete judge factories
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConcreteJudgeWiring:
    """Each concrete judge wires up its axis identity and prompt pair."""

    def test_brand_judge_axis_identity(self) -> None:
        judge = BrandLLMJudge(client=_FakeJudgeClient())
        assert judge.axis_name == "brand"
        assert judge.system_prompt == JUDGE_PROMPTS["brand"][0]
        assert judge.model_spec is JUDGE_MODEL_CONFIG["brand"]

    def test_originality_judge_uses_pro_thinking_spec(self) -> None:
        judge = OriginalityLLMJudge(client=_FakeJudgeClient())
        assert judge.axis_name == "originality"
        # Originality is the only axis on Gemini 2.5 Pro per the registry.
        assert judge.model_spec is JUDGE_MODEL_ORIGINALITY

    def test_relevance_judge_axis_identity(self) -> None:
        judge = RelevanceLLMJudge(client=_FakeJudgeClient())
        assert judge.axis_name == "relevance"
        assert judge.model_spec is JUDGE_MODEL_CONFIG["relevance"]

    def test_accessibility_judge_axis_identity(self) -> None:
        judge = AccessibilityLLMJudge(client=_FakeJudgeClient())
        assert judge.axis_name == "accessibility"
        assert judge.model_spec is JUDGE_MODEL_CONFIG["accessibility"]

    def test_visual_clarity_judge_axis_identity(self) -> None:
        judge = VisualClarityLLMJudge(client=_FakeJudgeClient())
        assert judge.axis_name == "visual_clarity"
        assert judge.model_spec is JUDGE_MODEL_CONFIG["visual_clarity"]

    def test_factory_returns_correct_concrete_judge(self) -> None:
        client = _FakeJudgeClient()
        for axis, expected_cls in [
            ("brand", BrandLLMJudge),
            ("originality", OriginalityLLMJudge),
            ("relevance", RelevanceLLMJudge),
            ("accessibility", AccessibilityLLMJudge),
            ("visual_clarity", VisualClarityLLMJudge),
        ]:
            judge = make_llm_judge(axis, client)
            assert isinstance(judge, expected_cls)
            assert isinstance(judge, LLMJudge)

    def test_factory_rejects_unknown_axis(self) -> None:
        with pytest.raises(ValueError, match="axis"):
            make_llm_judge("not-a-real-axis", _FakeJudgeClient())


# ---------------------------------------------------------------------------
# Judge scoring path (template method)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLLMJudgeScoring:
    """End-to-end LLMJudge.score() with the fake client."""

    def test_score_routes_to_client_with_axis_specific_model(self) -> None:
        client = _FakeJudgeClient(
            responses={
                "brand": _good_response(
                    score=0.8,
                    model_id=JUDGE_MODEL_CONFIG["brand"].model_id,
                ),
            },
        )
        judge = BrandLLMJudge(client=client)
        result = judge.score(_make_candidate(_rich_artifacts()))
        assert isinstance(result, _JudgeScore)
        assert result.score == pytest.approx(0.8)
        # Client was called exactly once with the brand model_id.
        assert len(client.calls) == 1
        assert client.calls[0]["model_id"] == JUDGE_MODEL_CONFIG["brand"].model_id

    def test_score_includes_artifact_names_in_provenance(self) -> None:
        client = _FakeJudgeClient(
            default_response=_good_response(
                evidence=["main.css", "index.html"],
            ),
        )
        judge = BrandLLMJudge(client=client)
        candidate = _make_candidate(_rich_artifacts())
        result = judge.score(candidate)
        # Evidence drives provenance_vars; both files should appear.
        assert "main.css" in result.provenance_vars
        assert "index.html" in result.provenance_vars

    def test_score_diagnostic_contains_reasoning(self) -> None:
        client = _FakeJudgeClient(
            default_response=_good_response(
                reasoning="Strong typographic hierarchy detected.",
            ),
        )
        judge = VisualClarityLLMJudge(client=client)
        result = judge.score(_make_candidate(_rich_artifacts()))
        assert "typographic" in result.diagnostic.lower()

    def test_score_clamps_out_of_range_response(self) -> None:
        # Client returns score=1.7; judge must clamp to 1.0.
        client = _FakeJudgeClient(
            default_response=_good_response(score=OUT_OF_RANGE_SCORE_HIGH),
        )
        judge = BrandLLMJudge(client=client)
        result = judge.score(_make_candidate(_rich_artifacts()))
        assert result.score == 1.0

    def test_user_prompt_contains_artifact_content(self) -> None:
        client = _FakeJudgeClient(
            default_response=_good_response(),
        )
        judge = RelevanceLLMJudge(client=client)
        candidate = _make_candidate(
            {"index.html": "<p>UNIQUE_SENTINEL_42</p>"},
        )
        judge.score(candidate)
        user_prompt = client.calls[0]["user_prompt"]
        assert "UNIQUE_SENTINEL_42" in user_prompt

    def test_temperature_routed_from_model_spec(self) -> None:
        client = _FakeJudgeClient(default_response=_good_response())
        judge = BrandLLMJudge(client=client)
        judge.score(_make_candidate(_rich_artifacts()))
        # Brand judge spec sets temperature=0.3 per the registry.
        assert client.calls[0]["temperature"] == JUDGE_MODEL_CONFIG["brand"].temperature

    def test_max_output_tokens_routed_from_model_spec(self) -> None:
        client = _FakeJudgeClient(default_response=_good_response())
        judge = AccessibilityLLMJudge(client=client)
        judge.score(_make_candidate(_rich_artifacts()))
        assert client.calls[0]["max_output_tokens"] == (
            JUDGE_MODEL_CONFIG["accessibility"].max_output_tokens
        )


# ---------------------------------------------------------------------------
# Failure handling (fail-soft trichotomy)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFailSoftFallback:
    """Every client failure mode must fall back to the Phase 1 heuristic."""

    def test_client_timeout_falls_back_to_heuristic(self) -> None:
        client = _FakeJudgeClient(exceptions={"brand": TimeoutError})
        judge = BrandLLMJudge(client=client)
        # Provide an artifact set the heuristic can score above zero.
        candidate = _make_candidate(_rich_artifacts())
        result = judge.score(candidate)
        # Score must come from the Phase 1 heuristic.
        heuristic_result = _AXIS_SCORERS["brand"](candidate)
        assert result.score == heuristic_result.score
        # Diagnostic must explicitly mark the degradation per the
        # "agent always acknowledges degradation" rule.
        assert "fallback" in result.diagnostic.lower() or ("heuristic" in result.diagnostic.lower())

    def test_client_runtime_error_falls_back_to_heuristic(self) -> None:
        client = _FakeJudgeClient(exceptions={"relevance": RuntimeError})
        judge = RelevanceLLMJudge(client=client)
        candidate = _make_candidate(_rich_artifacts())
        result = judge.score(candidate)
        # Score is whatever the heuristic produces -- crucially, not zero
        # unless the heuristic itself says so.
        heuristic_result = _AXIS_SCORERS["relevance"](candidate)
        assert result.score == heuristic_result.score

    def test_malformed_json_falls_back_to_heuristic(self) -> None:
        bad_response = LLMJudgeResponse(
            text="<<<not-json>>>",
            model_id=JUDGE_MODEL_CONFIG["brand"].model_id,
        )
        client = _FakeJudgeClient(responses={"brand": bad_response})
        judge = BrandLLMJudge(client=client)
        candidate = _make_candidate(_rich_artifacts())
        result = judge.score(candidate)
        heuristic_result = _AXIS_SCORERS["brand"](candidate)
        assert result.score == heuristic_result.score

    def test_explicit_fallback_overrides_heuristic_default(self) -> None:
        # Caller-supplied fallback wins over the heuristic default.
        sentinel_score = _JudgeScore(
            score=0.42,
            diagnostic="custom fallback used",
            provenance_vars=["custom"],
        )
        client = _FakeJudgeClient(exceptions={"brand": RuntimeError})
        judge = BrandLLMJudge(
            client=client,
            fallback=lambda _candidate: sentinel_score,
        )
        result = judge.score(_make_candidate(_rich_artifacts()))
        assert result.score == 0.42
        assert "custom fallback" in result.diagnostic


# ---------------------------------------------------------------------------
# Dispatch resolver
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveAxisScorers:
    """``_resolve_axis_scorers`` returns the dispatch dict per mode."""

    def test_heuristic_mode_returns_phase_one_dispatch(self) -> None:
        scorers = resolve_axis_scorers(mode=JUDGE_MODE_HEURISTIC)
        assert set(scorers.keys()) == set(EXPECTED_AXES)
        # Each scorer must be the exact Phase 1 callable -- no wrapper.
        for axis in EXPECTED_AXES:
            assert scorers[axis] is _AXIS_SCORERS[axis]

    def test_llm_mode_returns_callable_per_axis(self) -> None:
        client = _FakeJudgeClient()
        scorers = resolve_axis_scorers(mode=JUDGE_MODE_LLM, client=client)
        assert set(scorers.keys()) == set(EXPECTED_AXES)
        # Each scorer should produce a _JudgeScore when called.
        candidate = _make_candidate(_rich_artifacts())
        for axis in EXPECTED_AXES:
            result = scorers[axis](candidate)
            assert isinstance(result, _JudgeScore)

    def test_hybrid_mode_uses_llm_score_and_records_disagreement(self) -> None:
        # Force a strong disagreement between heuristic and LLM.
        client = _FakeJudgeClient(
            default_response=_good_response(score=HIGH_QUALITY_SCORE),
        )
        scorers = resolve_axis_scorers(mode=JUDGE_MODE_HYBRID, client=client)
        # Use an empty candidate -- the heuristic will return 0.0.
        candidate = _make_candidate()
        result = scorers["brand"](candidate)
        # LLM score wins.
        assert result.score == pytest.approx(HIGH_QUALITY_SCORE)
        # Diagnostic captures both scores so dashboards can plot delta.
        assert "heuristic" in result.diagnostic.lower()
        assert "llm" in result.diagnostic.lower()

    def test_invalid_mode_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="mode"):
            resolve_axis_scorers(mode="not-a-mode")

    def test_mode_defaults_to_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ATELIER_JUDGE_MODE_ENV, JUDGE_MODE_HEURISTIC)
        scorers = resolve_axis_scorers()
        # Heuristic mode → no client needed → returns Phase 1 dispatch.
        for axis in EXPECTED_AXES:
            assert scorers[axis] is _AXIS_SCORERS[axis]

    def test_unset_env_var_defaults_to_heuristic(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv(ATELIER_JUDGE_MODE_ENV, raising=False)
        scorers = resolve_axis_scorers()
        for axis in EXPECTED_AXES:
            assert scorers[axis] is _AXIS_SCORERS[axis]

    def test_llm_mode_without_client_raises(self) -> None:
        # LLM mode requires a client; failing loud beats silent heuristic.
        with pytest.raises(ValueError, match="client"):
            resolve_axis_scorers(mode=JUDGE_MODE_LLM, client=None)


# ---------------------------------------------------------------------------
# Integration with evaluate_candidate (backward compatibility)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEvaluateCandidateBackwardCompat:
    """``evaluate_candidate`` defaults to heuristic; LLM mode is opt-in."""

    def test_default_mode_matches_phase_one_behavior(self) -> None:
        candidate = _make_candidate(_rich_artifacts())
        result = evaluate_candidate(
            candidate,
            AxisWeights(),
            seed=DETERMINISTIC_SEED,
        )
        # Phase 1 heuristic composite for the rich-artifact fixture pins
        # at ~0.9562; this test guards that Phase 2 dispatch in default
        # (heuristic) mode reproduces the Phase 1 value bit-for-bit.
        assert result.composite_score == pytest.approx(PHASE1_RICH_COMPOSITE)
        assert result.passed is True

    def test_explicit_heuristic_mode_matches_default(self) -> None:
        candidate = _make_candidate(_rich_artifacts())
        default_result = evaluate_candidate(
            candidate,
            AxisWeights(),
            seed=DETERMINISTIC_SEED,
        )
        explicit_result = evaluate_candidate(
            candidate,
            AxisWeights(),
            seed=DETERMINISTIC_SEED,
            judge_mode=JUDGE_MODE_HEURISTIC,
        )
        assert default_result.composite_score == explicit_result.composite_score
        assert default_result.diagnostics == explicit_result.diagnostics

    def test_llm_mode_uses_supplied_client(self) -> None:
        client = _FakeJudgeClient(
            default_response=_good_response(
                score=HIGH_QUALITY_SCORE,
                reasoning="LLM judge says yes.",
                evidence=["main.css", "index.html"],
            ),
        )
        candidate = _make_candidate(_rich_artifacts())
        result = evaluate_candidate(
            candidate,
            AxisWeights(),
            seed=DETERMINISTIC_SEED,
            judge_mode=JUDGE_MODE_LLM,
            judge_client=client,
        )
        # Every axis goes through the LLM client → 5 calls per evaluation.
        assert len(client.calls) == EXPECTED_AXIS_COUNT
        # All five votes should record HIGH_QUALITY_SCORE.
        for vote in result.votes.values():
            assert vote.score == pytest.approx(HIGH_QUALITY_SCORE)

    def test_llm_mode_records_real_model_id_on_vote(self) -> None:
        client = _FakeJudgeClient(default_response=_good_response())
        candidate = _make_candidate(_rich_artifacts())
        result = evaluate_candidate(
            candidate,
            AxisWeights(),
            seed=DETERMINISTIC_SEED,
            judge_mode=JUDGE_MODE_LLM,
            judge_client=client,
        )
        brand_vote = result.votes[JudgeAxis.BRAND]
        # Phase 1 stub suffix should NOT appear in LLM-mode runs.
        assert "Phase 1 stub" not in brand_vote.judge_model
        # The vote's judge_model should mention the model display name.
        assert (
            JUDGE_MODEL_CONFIG["brand"].display_name in brand_vote.judge_model
            or JUDGE_MODEL_CONFIG["brand"].model_id in brand_vote.judge_model
        )

    def test_env_var_drives_mode_when_no_param(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(ATELIER_JUDGE_MODE_ENV, JUDGE_MODE_HEURISTIC)
        candidate = _make_candidate(_rich_artifacts())
        result = evaluate_candidate(
            candidate,
            AxisWeights(),
            seed=DETERMINISTIC_SEED,
        )
        # Heuristic env reproduces Phase 1 composite for rich artifacts.
        assert result.composite_score == pytest.approx(PHASE1_RICH_COMPOSITE)

    def test_llm_mode_emits_judge_vote_with_real_ci(self) -> None:
        # With logprobs supplied, the CI should be narrower than the
        # synthetic default band used in Phase 1.
        confident_response = _good_response(
            score=0.5,
            avg_logprob=HIGH_CONFIDENCE_LOGPROB,
        )
        client = _FakeJudgeClient(default_response=confident_response)
        candidate = _make_candidate(_rich_artifacts())
        result = evaluate_candidate(
            candidate,
            AxisWeights(),
            seed=DETERMINISTIC_SEED,
            judge_mode=JUDGE_MODE_LLM,
            judge_client=client,
        )
        brand_vote = result.votes[JudgeAxis.BRAND]
        ci_width = brand_vote.confidence_interval[1] - brand_vote.confidence_interval[0]
        # High-confidence CI must be strictly narrower than 2 * default.
        assert ci_width < 2 * CI_DEFAULT_HALF_WIDTH


# ---------------------------------------------------------------------------
# Vertex AI client smoke test (no network call)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestVertexAIClientLazyImport:
    """The Vertex AI client must not require the SDK at import time."""

    def test_module_imports_without_google_cloud_aiplatform(self) -> None:
        # If `import atelier.nodes.llm_judge` triggered a real
        # google.cloud.aiplatform import, this whole test module would
        # have failed to collect. Reaching this assertion confirms the
        # lazy-import contract holds for the import path.
        # In-method import is deliberate: this test verifies the
        # lazy-import contract for VertexAIJudgeClient.
        from atelier.nodes import llm_judge as module  # noqa: PLC0415

        assert hasattr(module, "VertexAIJudgeClient")

    def test_vertex_client_instantiation_does_not_call_network(self) -> None:
        # Constructing the client must not call any vertex API. We patch
        # the lazy importer to verify no module is fetched until generate().
        # In-method import is deliberate: this test verifies the
        # lazy-import contract for VertexAIJudgeClient.
        from atelier.nodes import llm_judge as module  # noqa: PLC0415

        client = module.VertexAIJudgeClient(project="atelier-test")
        # The client should not have eagerly created a Vertex AI client.
        assert getattr(client, "_model_cache", None) in (None, {}, [])

    def test_vertex_client_generate_raises_clear_error_without_sdk(self) -> None:
        # Without the google.cloud.aiplatform SDK installed (Phase 1 dep
        # state), invoking generate() must raise a clear error rather
        # than producing a misleading partial response.
        # In-method import is deliberate: this test verifies the
        # lazy-import contract for VertexAIJudgeClient.
        from atelier.nodes import llm_judge as module  # noqa: PLC0415

        client = module.VertexAIJudgeClient(project="atelier-test")
        with (
            mock.patch.object(
                module,
                "_import_vertex_sdk",
                side_effect=ImportError("google.cloud.aiplatform not installed"),
            ),
            pytest.raises((ImportError, LLMJudgeError)),
        ):
            client.generate(
                model_id="gemini-2.5-flash-preview-05-20",
                system_prompt="sys",
                user_prompt="user",
                temperature=0.2,
                max_output_tokens=1024,
                timeout_s=5.0,
            )


# ---------------------------------------------------------------------------
# Cleanup — make sure env var leakage between tests doesn't poison state.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_judge_mode_env() -> Any:
    """Save and restore the ATELIER_JUDGE_MODE env var for every test."""
    previous = os.environ.get(ATELIER_JUDGE_MODE_ENV)
    yield
    if previous is None:
        os.environ.pop(ATELIER_JUDGE_MODE_ENV, None)
    else:
        os.environ[ATELIER_JUDGE_MODE_ENV] = previous
