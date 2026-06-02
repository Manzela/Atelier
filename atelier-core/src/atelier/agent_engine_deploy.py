"""Vertex AI Agent Engine deployment (AT-082, PRD v2.2 §12 E8).

Deploys the Atelier planner agent to Vertex AI Agent Engine — a managed,
serverless runtime for the ADK agent — delegating scaling to the platform while
preserving control over the prompt and tools.

The deploy itself runs against live GCP and is operator-gated: it requires
Application Default Credentials for the serving project and the Vertex AI Agent
Engine API enabled. The pure helpers (requirement pins, ADK-version validation,
configuration resolution) are exercised by the unit suite.

Symbols verified against google-adk==2.1.0 / google-cloud-aiplatform==1.153.1:
    vertexai.init(project, location)
    vertexai.agent_engines.AdkApp(agent, enable_tracing)
    vertexai.agent_engines.create(agent_engine, *, requirements, display_name, ...)

PRD Reference: §12 E8 (AT-082), §22 D5 (AT-002 ADK pin)
"""

from __future__ import annotations

import importlib.metadata
import logging
import os

logger = logging.getLogger(__name__)

# Agent Engine sandbox requirements — kept in lockstep with the AT-002 pins in
# pyproject.toml. The deployed runtime must resolve the same major versions as
# the verified build so the served agent matches what was tested.
_DEPLOY_REQUIREMENTS: tuple[str, ...] = (
    "google-adk>=2.1.0,<3",
    "google-genai>=1.0,<3",
    "google-cloud-aiplatform>=1.71,<2",
    "pydantic>=2.6,<3",
)

# The deployed google-adk major.minor must match the AT-002 pin (acceptance:
# "version == pin"). A mismatch means the build venv has drifted from the pin
# and the deploy would serve an unverified ADK version — fail loud.
_REQUIRED_ADK_PREFIX = "2.1"

_DEFAULT_PROJECT = "atelier-build-2026"
_DEFAULT_LOCATION = "us-central1"
_DEFAULT_DISPLAY_NAME = "atelier-planner-engine"
_DEFAULT_DESCRIPTION = "Atelier hybrid-runtime planner agent"


class AgentEngineDeployError(RuntimeError):
    """Raised when the Agent Engine deploy cannot proceed (fail-loud)."""


def deployment_requirements() -> list[str]:
    """Return the pinned requirement list for the Agent Engine sandbox."""
    return list(_DEPLOY_REQUIREMENTS)


def validate_adk_pin() -> str:
    """Return the installed google-adk version, or raise if it drifts from the pin.

    Acceptance gate for "version == pin": the deploy must not ship a google-adk
    version other than the AT-002 pin (2.1.x).

    Returns:
        The installed google-adk version string.

    Raises:
        AgentEngineDeployError: If google-adk is absent or off the pinned line.
    """
    try:
        installed = importlib.metadata.version("google-adk")
    except importlib.metadata.PackageNotFoundError as exc:
        raise AgentEngineDeployError(
            "google-adk is not installed; cannot deploy the Agent Engine."
        ) from exc
    if not installed.startswith(_REQUIRED_ADK_PREFIX):
        raise AgentEngineDeployError(
            f"google-adk=={installed} drifts from the AT-002 pin "
            f"({_REQUIRED_ADK_PREFIX}.x); refusing to deploy an unverified version."
        )
    return installed


def resolve_config() -> dict[str, str]:
    """Resolve deploy configuration from the environment, with defaults."""
    return {
        "project": os.getenv("GOOGLE_CLOUD_PROJECT", _DEFAULT_PROJECT),
        "location": os.getenv("GOOGLE_CLOUD_LOCATION", _DEFAULT_LOCATION),
        "display_name": os.getenv("ATELIER_AGENT_NAME", _DEFAULT_DISPLAY_NAME),
        "description": os.getenv("ATELIER_AGENT_DESCRIPTION", _DEFAULT_DESCRIPTION),
    }


def deploy_agent_engine() -> str:
    """Deploy the Atelier planner agent to Vertex AI Agent Engine.

    Returns:
        The deployed Agent Engine resource name.

    Raises:
        AgentEngineDeployError: On any failure — missing dependencies, a
            google-adk version drift, or a failed create call. Deploy failures
            fail loud and are never swallowed.
    """
    adk_version = validate_adk_pin()
    config = resolve_config()

    try:
        import vertexai  # noqa: PLC0415
        from vertexai.agent_engines import AdkApp, create  # noqa: PLC0415

        from atelier.orchestrator.planner import PlannerAgent  # noqa: PLC0415
    except ImportError as exc:
        raise AgentEngineDeployError(
            "Agent Engine deploy requires vertexai and google-adk to be installed."
        ) from exc

    logger.info(
        "Deploying Atelier planner to Agent Engine: project=%s location=%s adk=%s",
        config["project"],
        config["location"],
        adk_version,
    )
    vertexai.init(project=config["project"], location=config["location"])

    app = AdkApp(agent=PlannerAgent().llm, enable_tracing=True)

    try:
        remote_app = create(
            agent_engine=app,
            display_name=config["display_name"],
            description=config["description"],
            requirements=deployment_requirements(),
            extra_packages=["."],
        )
    except Exception as exc:
        raise AgentEngineDeployError(f"Agent Engine deploy failed: {exc}") from exc

    resource_name = str(remote_app.resource_name)
    logger.info("Agent Engine deploy complete. Resource name: %s", resource_name)
    return resource_name


def main() -> None:
    """CLI entrypoint: deploy, then print the resource name for the shell wrapper."""
    logging.basicConfig(level=logging.INFO)
    resource_name = deploy_agent_engine()
    print(resource_name)  # noqa: T201 — the shell wrapper captures this on stdout


if __name__ == "__main__":
    main()
