"""Shared internal types for the nodes package.

Extracted here to break the module-level circular import between
``atelier.nodes.consensus`` and ``atelier.nodes.llm_judge``:

- ``consensus`` defines heuristic scorers that return ``_JudgeScore`` and
  assembles ``_AXIS_SCORERS``. It lazily imports ``_resolve_axis_scorers``
  from ``llm_judge`` at call-time (not import-time).
- ``llm_judge`` defines the LLM-backed judge that falls back to the
  heuristic scorers when Vertex AI is unavailable. It needs ``_JudgeScore``
  to construct return values and ``_AXIS_SCORERS`` to wire fallbacks.

If ``_JudgeScore`` lived in ``consensus`` and was imported from there by
``llm_judge`` at module level, any import ordering where ``llm_judge``
loads before ``consensus`` has finished would result in a
``ImportError: cannot import name '_JudgeScore'``. Moving ``_JudgeScore``
to this neutral module eliminates that ordering constraint.

Nothing else should be added here. If more shared state is needed between
``consensus`` and ``llm_judge``, consider whether it belongs in
``atelier.models.*`` instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class _JudgeScore:
    """Internal per-axis result produced by a ``_score_*`` helper.

    Not exported beyond the nodes package: callers see :class:`JudgeVote`
    instances built from this via :func:`consensus._build_judge_vote`. Kept
    as a separate type so the scoring helpers stay pure (no Pydantic, no
    UUID) and can be unit-tested in isolation from the consensus aggregation.

    Attributes:
        score: Normalized score in ``[0.0, 1.0]``.
        diagnostic: Human-readable explanation of what was counted and why
            the score landed where it did. Embedded into
            :attr:`JudgeVote.reasoning` downstream.
        provenance_vars: DEMAS-D variable names the scorer "consulted."
            v1.0 implementation scorers report artifact filenames actually opened; Phase
            2 LLM judges report richer provenance.
        judge_model: Optional LLM judge identifier set by
            LLMJudge.score(). Defaults to ``None`` so v1.0 implementation heuristic
            scorers construct with the original 3-argument signature;
            ``_build_judge_vote`` falls back to the v1.0 implementation stub suffix when
            this is None.
        confidence_interval: Optional Bayesian confidence interval set by
            LLMJudge.score(). Defaults to ``None`` so
            ``_build_judge_vote`` can derive the synthetic v1.0 implementation band via
            :func:`_confidence_interval` when absent.
        input_tokens: Vertex prompt tokens this axis's LLM judge consumed
            (``0`` for heuristic scorers, which make no LLM call). Threaded into
            the per-user lifetime cap so N3d judge spend is counted, not just N3a
            (AT-097 — closes the AT-095 under-count carry-forward).
        output_tokens: Vertex completion tokens this axis's LLM judge consumed.
        thinking_tokens: Vertex ``thoughts_token_count`` this axis's LLM judge
            consumed (G15).
    """

    score: float
    diagnostic: str
    provenance_vars: list[str] = field(default_factory=list)
    judge_model: str | None = None
    confidence_interval: tuple[float, float] | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
