"""AT-024 model-pin: registry/planner/web_research return the pinned served id.

The served Gemini model is pinned to ``GEMINI_MODEL_ID`` (env) or the GA default
``gemini-2.5-pro`` (PRD §22 D5 / G13). Verifies the single source of truth
(`resolve_model_id`) and that every consumer resolves to it, with env override.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from atelier.intake import web_research
from atelier.intake.brief_parser import BriefParserAgent
from atelier.models import model_registry
from atelier.models.model_registry import (
    ALL_MODEL_IDS,
    DEFAULT_GEMINI_MODEL_ID,
    resolve_model_id,
)
from atelier.orchestrator.planner import PlannerAgent


@pytest.mark.unit
def test_default_pinned_to_ga_gemini_2_5_pro() -> None:
    assert DEFAULT_GEMINI_MODEL_ID == "gemini-2.5-pro"
    assert resolve_model_id() == "gemini-2.5-pro"


@pytest.mark.unit
def test_env_override_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_MODEL_ID", "gemini-2.5-flash")
    assert resolve_model_id() == "gemini-2.5-flash"


@pytest.mark.unit
def test_registry_specs_all_pinned() -> None:
    """Every ModelSpec model_id collapses to the single served id (acceptance)."""
    assert frozenset({resolve_model_id()}) == ALL_MODEL_IDS


@pytest.mark.unit
def test_planner_default_model_is_pinned() -> None:
    assert PlannerAgent().model == resolve_model_id()


@pytest.mark.unit
def test_planner_explicit_model_override() -> None:
    assert PlannerAgent(model="gemini-2.5-flash").model == "gemini-2.5-flash"


@pytest.mark.unit
def test_brief_parser_default_model_is_pinned() -> None:
    agent = BriefParserAgent()
    assert agent.model == resolve_model_id()
    assert agent.project == "atelier-build-2026"


@pytest.mark.unit
def test_grounding_model_is_pinned() -> None:
    # Module-level Final resolved at import (no GEMINI_MODEL_ID set in the test env).
    assert web_research._GROUNDING_MODEL == DEFAULT_GEMINI_MODEL_ID


@pytest.mark.unit
def test_no_preview_model_ids_remain_in_registry() -> None:
    """Guard: no stale preview/non-GA Gemini id is hardcoded in the registry."""
    src = Path(model_registry.__file__).read_text(encoding="utf-8")
    assert not re.search(r"gemini-[\d.]+-(?:flash|pro)[\w-]*-preview", src)
    assert not re.search(r'model_id\s*=\s*"gemini-', src)  # ids come from resolve_model_id()
