"""AT-082 unit oracle — Agent Engine deploy helpers (no live deploy).

Exercises the pure helpers: the pinned requirement list, the google-adk
version-pin validation gate, and environment-driven config resolution. The live
``create()`` call is operator-gated and is not unit-tested.

PRD Reference: §12 E8 (AT-082)
"""

from __future__ import annotations

import pytest
from atelier.agent_engine_deploy import (
    AgentEngineDeployError,
    deployment_requirements,
    resolve_config,
    validate_adk_pin,
)


def test_deployment_requirements_match_at002_pins() -> None:
    reqs = deployment_requirements()
    assert "google-adk>=2.1.0,<3" in reqs
    assert any(r.startswith("google-genai") for r in reqs)
    assert any(r.startswith("google-cloud-aiplatform") for r in reqs)
    assert any(r.startswith("pydantic") for r in reqs)


def test_validate_adk_pin_accepts_installed_version() -> None:
    # The build venv pins google-adk==2.1.x (AT-002).
    assert validate_adk_pin().startswith("2.1")


def test_validate_adk_pin_rejects_version_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("importlib.metadata.version", lambda _name: "1.0.0")
    with pytest.raises(AgentEngineDeployError, match="drifts from the AT-002 pin"):
        validate_adk_pin()


def test_resolve_config_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-proj")
    monkeypatch.setenv("ATELIER_AGENT_NAME", "my-engine")
    config = resolve_config()
    assert config["project"] == "my-proj"
    assert config["display_name"] == "my-engine"


def test_resolve_config_defaults_to_serving_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("ATELIER_AGENT_NAME", raising=False)
    config = resolve_config()
    assert config["project"] == "atelier-build-2026"
    assert config["display_name"] == "atelier-planner-engine"
    assert config["location"] == "us-central1"
