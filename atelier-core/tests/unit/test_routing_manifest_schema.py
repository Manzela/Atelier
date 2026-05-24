"""Schema validation tests for the routing manifest (§13.1 gate g10).

Validates that infra/routing/manifest.yaml conforms to the JSON Schema
at infra/routing/routing_manifest.schema.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]  # atelier-core/tests/unit -> worktree root
_MANIFEST_PATH = _REPO_ROOT / "infra" / "routing" / "manifest.yaml"
_SCHEMA_PATH = _REPO_ROOT / "infra" / "routing" / "routing_manifest.schema.json"


@pytest.fixture
def manifest() -> dict:
    """Load the routing manifest YAML."""
    return yaml.safe_load(_MANIFEST_PATH.read_text())


@pytest.fixture
def schema() -> dict:
    """Load the JSON Schema."""
    return json.loads(_SCHEMA_PATH.read_text())


def test_manifest_validates_against_schema(manifest: dict, schema: dict) -> None:
    """The manifest must pass schema validation — §13.1 gate g10."""
    jsonschema.validate(instance=manifest, schema=schema)


def test_schema_is_well_formed_json() -> None:
    """The schema file must be parseable JSON."""
    data = json.loads(_SCHEMA_PATH.read_text())
    assert "$schema" in data
    assert "properties" in data


def test_manifest_has_all_eight_phases(manifest: dict) -> None:
    """All 8 DAG phases must be present in the manifest."""
    expected_phases = {
        "brief_parse",
        "intent_schema",
        "surface_plan",
        "generate_candidates",
        "judge_candidates",
        "select_winner",
        "polish",
        "emit",
    }
    actual_phases = set(manifest["phases"].keys())
    assert actual_phases == expected_phases


def test_manifest_expert_ids_match_cost_map(manifest: dict) -> None:
    """Every expert used in phases must appear in the experts registry."""
    expert_ids = {e["id"] for e in manifest["experts"]}
    for phase_name, phase_cfg in manifest["phases"].items():
        assert phase_cfg["primary_expert"] in expert_ids, (
            f"Phase {phase_name} references unknown expert {phase_cfg['primary_expert']}"
        )
        if phase_cfg.get("low_budget_expert"):
            assert phase_cfg["low_budget_expert"] in expert_ids, (
                f"Phase {phase_name} low_budget_expert references unknown expert"
            )


def test_fallback_chains_reference_valid_experts(manifest: dict) -> None:
    """Every expert in a fallback chain must exist in the registry."""
    expert_ids = {e["id"] for e in manifest["experts"]}
    for primary, chain in manifest["fallback_chains"].items():
        assert primary in expert_ids, f"Fallback primary {primary} not in experts"
        for fallback in chain:
            assert fallback in expert_ids, f"Fallback {fallback} for {primary} not in experts"


def test_budget_sensitive_phases_have_required_fields(manifest: dict) -> None:
    """Phases with budget_sensitive=true must have budget_floor_usd + low_budget_expert."""
    for phase_name, phase_cfg in manifest["phases"].items():
        if phase_cfg.get("budget_sensitive"):
            assert "budget_floor_usd" in phase_cfg, (
                f"Phase {phase_name} is budget_sensitive but missing budget_floor_usd"
            )
            assert "low_budget_expert" in phase_cfg, (
                f"Phase {phase_name} is budget_sensitive but missing low_budget_expert"
            )


def test_invalid_manifest_fails_schema(schema: dict) -> None:
    """A manifest missing required fields must fail validation."""
    bad_manifest = {"version": "1.0"}  # Missing most required fields
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad_manifest, schema=schema)
