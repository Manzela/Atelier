"""Record/replay determinism: the golden offline pipeline is byte-stable (AT-003).

PRD v2.2 AT-003 acceptance: with the network disabled, repeated offline runs of
the same pipeline produce a BYTE-IDENTICAL canonical trajectory (sha256 equal)
AND make ZERO live model/tool calls. Canonicalization
(:mod:`atelier.testing.record_replay`) normalizes the inherently-varying ids and
timestamps so the determinism is checkable; the :class:`LiveCallGuard` proves no
network call slipped through. This is hermetic CI/test infrastructure only --
the live product remains the sole generation path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from atelier.intake.brief_parser import BriefParserAgent
from atelier.intake.web_research import WebResearchReport
from atelier.orchestrator.runner import AtelierRunner
from atelier.testing.record_replay import (
    canonicalize_trajectory,
    hermetic,
    trajectory_sha256,
)

_BRIEF_SPEC_JSON = """
{
    "spec_id": "123e4567-e89b-12d3-a456-426614174000",
    "tenant_id": "t1",
    "project_id": "p1",
    "intent": "build a landing page",
    "visual_register": "editorial",
    "stack": "vanilla-html",
    "design_system_source": "infer",
    "compliance_level": "wcag-aa",
    "convergence_bar": "ship-it",
    "reference_artifacts": [],
    "campaign_scope": null,
    "intake_transcript": [],
    "schema_version": 1,
    "approved_at": "2026-05-25T12:00:00Z",
    "approved_by_user_id": "user1"
}
"""
_BRIEF_TEXT = (
    "This is a brief text that needs to have more than ten words to pass the "
    "deterministic gate check."
)


async def _run_golden_offline() -> dict[str, Any]:
    """Run N1 -> N2 -> N3a fully offline (mocked surfaces, heuristic judges)."""
    mock_session_service = MagicMock()
    mock_session = MagicMock()
    mock_session.id = "test-session-id"
    mock_session_service.create_session = AsyncMock(return_value=mock_session)

    runner = AtelierRunner(session_service=mock_session_service)

    with (
        patch.object(BriefParserAgent, "_call_llm", new_callable=AsyncMock) as mock_n1,
        patch("atelier.orchestrator.runner.source_resolver_gate", return_value=True),
        patch(
            "atelier.intake.source_resolver.pull_design_tokens", new_callable=AsyncMock
        ) as mock_tokens,
        patch(
            "atelier.intake.source_resolver.pull_memory_bank_priors", new_callable=AsyncMock
        ) as mock_priors,
        # WRAI (N14) is on by default; mock it to a deterministic empty report so
        # the run never reaches the grounded-search genai client (hermetic).
        patch(
            "atelier.orchestrator.runner.research_brief",
            new_callable=AsyncMock,
            return_value=WebResearchReport(results=[]),
        ),
        patch("atelier.orchestrator.runner.Runner") as mock_runner_cls,
    ):
        mock_n1.return_value = _BRIEF_SPEC_JSON
        mock_tokens.return_value = {"primary_color": "#ffffff"}
        mock_priors.return_value = ["fake-prior"]

        async def mock_events(*_args: Any, **_kwargs: Any) -> Any:
            yield {"type": "message", "data": "candidate1"}
            yield {"type": "message", "data": "candidate2"}
            yield {"type": "message", "data": "candidate3"}

        mock_runner_cls.return_value.run_async.side_effect = mock_events

        result: dict[str, Any] = await runner.run(_BRIEF_TEXT)
        return result


@pytest.mark.anyio
async def test_golden_trajectory_is_byte_identical_across_runs(tmp_path: Path) -> None:
    """3x offline runs -> identical canonical trajectory; zero live model/tool calls."""
    shas: list[str] = []
    canon = ""
    with hermetic() as guard:
        for _ in range(3):
            result = await _run_golden_offline()
            canon = canonicalize_trajectory(result)
            shas.append(trajectory_sha256(result))

    # AT-003 acceptance, part 2: no live model/tool call slipped through.
    assert guard.live_calls == 0, "hermetic run attempted a live model/tool call"
    # AT-003 acceptance, part 1: byte-identical canonical trajectory across runs.
    assert len(set(shas)) == 1, f"non-deterministic canonical trajectory: {shas}"
    # The trajectory must be non-trivial (a real run, not an empty skeleton).
    assert canon, "canonical trajectory is empty"
    assert canon not in ("{}", "null"), "canonical trajectory is a skeleton"
    assert json.loads(canon), "canonical trajectory does not parse"

    # Emit the canonical out/trajectory.jsonl artifact (what `make replay` views).
    out = tmp_path / "trajectory.jsonl"
    out.write_text(canon + "\n", encoding="utf-8")
    assert out.read_text(encoding="utf-8").strip() == canon


def test_canonicalize_normalizes_uuids_timestamps_and_sorts_keys() -> None:
    """Unit guard on the canonicalizer: varying ids/timestamps collapse to sentinels."""
    a = {
        "session_id": "abc12345-0000-0000-0000-000000000001",
        "run_id": "run-7f3a",
        "started_at": "2026-05-31T10:00:00Z",
        "converged": True,
        "candidates": [{"candidate_id": "ffffffff-1111-2222-3333-444444444444"}],
    }
    b = {
        "candidates": [{"candidate_id": "00000000-9999-8888-7777-666666666666"}],
        "converged": True,
        "run_id": "run-9c2b",
        "started_at": "2026-05-31T23:59:59Z",
        "session_id": "99998888-0000-0000-0000-000000000002",
    }
    assert canonicalize_trajectory(a) == canonicalize_trajectory(b)
    # And a genuine content difference must NOT collapse.
    c = dict(a)
    c["converged"] = False
    assert canonicalize_trajectory(a) != canonicalize_trajectory(c)
