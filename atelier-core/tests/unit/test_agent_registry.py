"""Unit tests for the agent registry (read-only descriptor projection).

Asserts the registry single-sources every Atelier agent from its live
definition: every expected agent appears, each carries a non-empty prompt and a
routed Vertex model id, and only the UI Designer specialist holds the Stitch MCP
toolset. Fully hermetic — the registry constructs no agents and touches no
network / credentials.
"""

from __future__ import annotations

import pytest
from atelier.models.model_registry import (
    ALL_MODEL_IDS,
    TASK_MODEL_ROUTING,
    TaskType,
    get_model_catalog,
)
from atelier.orchestrator.agent_registry import (
    AgentDescriptor,
    get_agent_registry,
)

# The model ids the routing table can resolve to (static targets). The registry
# may also surface resolve_model_id()'s operator-pinned default, so the union of
# routed values is the authoritative "is this a real model id" check.
_ROUTED_MODEL_IDS = frozenset(TASK_MODEL_ROUTING.values()) | ALL_MODEL_IDS

# Every agent id we expect the registry to expose.
_EXPECTED_IDS = {
    "planner",
    "intake_brief_parser",
    # 6 DDLC specialists
    "specialist_uxresearcher",
    "specialist_iaflowdesigner",
    "specialist_wireframer",
    "specialist_uidesigner",
    "specialist_interactiondesigner",
    "specialist_tokengenerator",
    # 5 D-O-R-A-V judges
    "judge_brand",
    "judge_originality",
    "judge_relevance",
    "judge_accessibility",
    "judge_visual_clarity",
    # 4 QA critics
    "critic_accessibilitycritic",
    "critic_nielsenheuristiccritic",
    "critic_visualqacritic",
    "critic_brandcoherencecritic",
    # fixer
    "fixer",
}


@pytest.fixture
def registry() -> list[AgentDescriptor]:
    return get_agent_registry()


def test_all_expected_agents_present(registry: list[AgentDescriptor]) -> None:
    ids = {d.id for d in registry}
    assert ids == _EXPECTED_IDS


def test_ids_are_unique(registry: list[AgentDescriptor]) -> None:
    ids = [d.id for d in registry]
    assert len(ids) == len(set(ids))


def test_expected_counts_per_kind(registry: list[AgentDescriptor]) -> None:
    by_kind: dict[str, int] = {}
    for d in registry:
        by_kind[d.kind] = by_kind.get(d.kind, 0) + 1
    assert by_kind == {
        "planner": 1,
        "intake": 1,
        "specialist": 6,
        "judge": 5,
        "critic": 4,
        "fixer": 1,
    }


def test_every_agent_has_nonempty_prompt(registry: list[AgentDescriptor]) -> None:
    for d in registry:
        assert d.prompt.strip(), f"{d.id} has an empty prompt"


def test_every_agent_has_routed_model_id(registry: list[AgentDescriptor]) -> None:
    for d in registry:
        assert d.model_id, f"{d.id} has no model_id"
        assert d.model_id in _ROUTED_MODEL_IDS, (
            f"{d.id} routes to an unknown model id {d.model_id!r}"
        )


def test_only_ui_specialist_has_stitch_tool(registry: list[AgentDescriptor]) -> None:
    with_stitch = {d.id for d in registry if "stitch_mcp" in d.tools}
    assert with_stitch == {"specialist_uidesigner"}


def test_no_other_tools_exposed(registry: list[AgentDescriptor]) -> None:
    # The only external tool any agent should carry in V1 is the Stitch MCP
    # toolset on the UI Designer. Guard against an accidental tool leak.
    all_tools = {tool for d in registry for tool in d.tools}
    assert all_tools <= {"stitch_mcp"}


def test_prompt_source_is_recorded(registry: list[AgentDescriptor]) -> None:
    valid_sources = {"static", "vertex_agent_registry"}
    for d in registry:
        assert d.prompt_source in valid_sources, (
            f"{d.id} has invalid prompt_source {d.prompt_source!r}"
        )
    # Specialists honor the ATELIER_AGENT_REGISTRY_ENABLED override hook; by
    # default (hook disabled) they resolve to the in-repo static role.
    specialists = [d for d in registry if d.kind == "specialist"]
    assert specialists
    assert all(d.prompt_source == "static" for d in specialists)


def test_specialist_prompt_source_reflects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATELIER_AGENT_REGISTRY_ENABLED", "true")
    enabled_registry = get_agent_registry()
    specialists = [d for d in enabled_registry if d.kind == "specialist"]
    assert specialists
    assert all(d.prompt_source == "vertex_agent_registry" for d in specialists)
    # Non-specialist agents are always static regardless of the env gate.
    judges = [d for d in enabled_registry if d.kind == "judge"]
    assert all(d.prompt_source == "static" for d in judges)


def test_specialist_handoff_contract(registry: list[AgentDescriptor]) -> None:
    # Every specialist writes a unique output_key and belongs to the DDLC pipeline.
    specialists = [d for d in registry if d.kind == "specialist"]
    output_keys = [d.output_key for d in specialists]
    assert output_keys == [
        "ux_research",
        "ia_flows",
        "wireframe",
        "ui_design",
        "interaction_spec",
        "tokens",
    ]
    assert all(d.subagent_of == "DDLCSpecialistPipeline" for d in specialists)


def test_judges_route_to_calibrated_models(registry: list[AgentDescriptor]) -> None:
    judges = {d.id: d for d in registry if d.kind == "judge"}
    # The originality judge must route to Pro (deep novelty reasoning).
    assert judges["judge_originality"].model_id == TASK_MODEL_ROUTING[TaskType.JUDGE_ORIGINALITY]
    # The accessibility judge routes to the cheap Flash-Lite fallback tier.
    assert (
        judges["judge_accessibility"].model_id == TASK_MODEL_ROUTING[TaskType.JUDGE_ACCESSIBILITY]
    )


def test_descriptors_are_frozen(registry: list[AgentDescriptor]) -> None:
    d = registry[0]
    with pytest.raises((AttributeError, TypeError)):
        d.model_id = "tampered"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# get_model_catalog — model-id-centric view of the routing table
# ---------------------------------------------------------------------------


def test_model_catalog_covers_all_routed_models() -> None:
    catalog = get_model_catalog()
    catalog_ids = {e.model_id for e in catalog}
    assert catalog_ids == set(TASK_MODEL_ROUTING.values())


def test_model_catalog_task_grouping_is_complete() -> None:
    catalog = get_model_catalog()
    # Every routed task appears under exactly one catalog entry.
    grouped: set[TaskType] = set()
    for entry in catalog:
        for task in entry.task_types:
            assert task not in grouped, f"{task} grouped twice"
            grouped.add(task)
    assert grouped == set(TASK_MODEL_ROUTING.keys())


def test_model_catalog_attaches_tier_and_cap() -> None:
    catalog = get_model_catalog()
    for entry in catalog:
        assert entry.tier in {"pro", "flash", "flash_lite"}
        assert entry.token_cap > 0
        assert entry.display_name
