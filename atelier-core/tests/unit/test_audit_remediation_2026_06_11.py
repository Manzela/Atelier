"""Regression tests for the 2026-06-11 code-only red-team audit remediation.

Each test pins a CONFIRMED finding from the audit ledger and fails on the
unremediated code (TDD red), then passes once the fix lands (green). Findings
covered here: L05 (model allow-list), L47 (sampling-param bounds), L06
(design_system_source path-traversal confinement), L49 (trace-summary cap).
"""

from __future__ import annotations

import asyncio
import os

import pytest
from atelier.api.generate import GenerateRequest
from atelier.intake.source_resolver import pull_design_tokens
from atelier.models.model_registry import get_model_catalog
from atelier.orchestrator.runner import _TRACE_SUMMARY_CHARS, _trace_summary
from pydantic import ValidationError

_VALID_BRIEF = "Build a SaaS analytics dashboard with a dark theme and KPI cards."


# --- L05: GenerateRequest.model must be allow-listed -----------------------------


def test_model_allows_a_catalogued_id() -> None:
    catalog_id = get_model_catalog()[0].model_id
    req = GenerateRequest(brief=_VALID_BRIEF, model=catalog_id)
    assert req.model == catalog_id


def test_model_none_is_allowed() -> None:
    assert GenerateRequest(brief=_VALID_BRIEF, model=None).model is None


def test_model_rejects_uncatalogued_id() -> None:
    # Forcing an arbitrary model bypasses operator-pin / tiered cost routing.
    with pytest.raises(ValidationError):
        GenerateRequest(brief=_VALID_BRIEF, model="gemini-9.9-ultra-unlimited")


# --- L47: sampling params bounded at the trust boundary --------------------------


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("temperature", 5.0),
        ("temperature", -0.1),
        ("top_k", 0),
        ("top_k", 99999),
        ("max_tokens", 0),
    ],
)
def test_sampling_params_reject_out_of_range(field: str, bad: float) -> None:
    with pytest.raises(ValidationError):
        GenerateRequest(brief=_VALID_BRIEF, **{field: bad})


def test_sampling_params_accept_in_range() -> None:
    req = GenerateRequest(brief=_VALID_BRIEF, temperature=0.7, top_k=40, max_tokens=4096)
    assert req.temperature == 0.7


# --- L06: design_system_source path traversal is confined ------------------------


def test_design_source_rejects_parent_traversal(tmp_path, monkeypatch) -> None:
    # A secret outside the working tree must never be read via `..` escape.
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-TOKEN", encoding="utf-8")
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    tokens = asyncio.run(pull_design_tokens("../secret.txt"))
    assert "TOP-SECRET-TOKEN" not in str(tokens)
    assert tokens.get("_source") == "defaults"


def test_design_source_rejects_absolute_path(tmp_path, monkeypatch) -> None:
    secret = tmp_path / "abs_secret.txt"
    secret.write_text("ABS-SECRET", encoding="utf-8")
    workdir = tmp_path / "work2"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    tokens = asyncio.run(pull_design_tokens(os.fspath(secret)))
    assert "ABS-SECRET" not in str(tokens)
    assert tokens.get("_source") == "defaults"


def test_design_source_allows_in_tree_file(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "DESIGN.md").write_text("--primary-color: #abcdef\n", encoding="utf-8")
    tokens = asyncio.run(pull_design_tokens("DESIGN.md"))
    assert tokens.get("primary_color") == "#abcdef"


# --- L49: specialist trace summary honors its declared cap -----------------------


def test_trace_summary_truncates_to_cap() -> None:
    big = ["x" * 5000]
    summary = _trace_summary(big)
    assert len(summary) <= _TRACE_SUMMARY_CHARS + 1  # +1 for the ellipsis char


def test_trace_summary_short_text_is_unchanged() -> None:
    assert _trace_summary(["hello"]) == "hello"


# --- L04: the cooperative Stop is namespaced per owner (cross-tenant IDOR) --------


def test_stop_key_is_namespaced_per_user() -> None:
    from atelier.orchestrator.stop_controller import stop_key

    assert stop_key("userA", "sess-1") != stop_key("userB", "sess-1")
    # An empty owner or session yields the empty (no-op) key.
    assert stop_key("", "sess-1") == ""
    assert stop_key("userA", "") == ""


def test_stop_by_one_user_cannot_halt_another_users_run() -> None:
    from atelier.orchestrator.stop_controller import (
        clear_stop,
        is_stop_requested,
        request_stop,
        stop_key,
    )

    owner_key = stop_key("owner-uid", "sess-shared")
    attacker_key = stop_key("attacker-uid", "sess-shared")
    request_stop(attacker_key)  # attacker tries to stop a session they do not own
    try:
        # The victim's run only ever polls ITS OWN owner key — which is not armed.
        assert is_stop_requested(owner_key) is False
        # The owner's own Stop is honored.
        request_stop(owner_key)
        assert is_stop_requested(owner_key) is True
    finally:
        clear_stop(owner_key)
        clear_stop(attacker_key)


# --- L10: top-level convergence must aggregate across ALL surfaces ---------------


def test_aggregate_convergence_requires_every_surface() -> None:
    from atelier.orchestrator.runner import _aggregate_convergence

    # surfaces[0] converged strongly, a later surface did NOT — the product must
    # report NOT converged, and the composite must be the weakest surface (not 0.9).
    screens = {
        "home": {"converged": True, "composite_score": 0.9},
        "settings": {"converged": False, "composite_score": 0.4},
    }
    converged, composite = _aggregate_convergence(screens)
    assert converged is False
    assert composite == 0.4


def test_aggregate_convergence_all_converged() -> None:
    from atelier.orchestrator.runner import _aggregate_convergence

    screens = {
        "a": {"converged": True, "composite_score": 0.8},
        "b": {"converged": True, "composite_score": 0.95},
    }
    converged, composite = _aggregate_convergence(screens)
    assert converged is True
    assert composite == 0.8


def test_aggregate_convergence_empty_is_not_converged() -> None:
    from atelier.orchestrator.runner import _aggregate_convergence

    assert _aggregate_convergence({}) == (False, 0.0)


# --- L14: evaluate trajectory row must match the DEPLOYED narrow BQ schema --------


def test_evaluate_trajectory_row_matches_deployed_narrow_schema() -> None:
    import json as _json
    from datetime import UTC, datetime

    from atelier.api.evaluate import _build_trajectory_row

    class _Fake:
        def model_dump(self) -> dict[str, object]:
            return {"k": "v"}

    now = datetime(2026, 6, 11, tzinfo=UTC)
    row = _build_trajectory_row(
        session_id="s1",
        tenant_id="t1",
        started_at=now,
        ended_at=now,
        results_count=10,
        matched_count=7,
        route=_Fake(),  # type: ignore[arg-type]
        artifact=_Fake(),  # type: ignore[arg-type]
    )
    # Exactly the deployed trajectory_records writable columns (embedding omitted).
    assert set(row.keys()) == {
        "session_id",
        "tenant_id",
        "node_name",
        "phase",
        "expert_id",
        "occurred_at",
        "payload",
    }
    # Every REQUIRED column is present and non-None (the old row omitted phase + occurred_at).
    for required in ("session_id", "tenant_id", "node_name", "phase", "occurred_at"):
        assert row[required] is not None
    # The optimize detail rides the JSON payload so GET /v1/replay can surface it.
    payload = _json.loads(row["payload"])
    assert payload["composite_score"] == 0.7
    assert payload["route_decisions"] == [{"k": "v"}]
