"""Vertex AI Agent Engine deployment (AT-082, PRD v2.2 §12 E8).

Deploys the **Atelier root agent graph** to Vertex AI Agent Engine — a managed,
serverless runtime for the ADK agent — delegating scaling to the platform while
preserving control over the prompts and tools.

Root-graph deploy (the AT-082 generalisation)
----------------------------------------------
ADK + Agent Engine deploy the *root agent* and its ``sub_agents`` as **one**
Agent Engine application — the entire graph reachable from the root is packaged,
uploaded, and served as a single deployment (grounded on the google-adk docs,
``agent_engines.create(agent_engine=root_agent, ...)`` and
``AdkApp(agent=root_agent, enable_tracing=True)`` — see ``llms-full.txt``
"Create and deploy agent to Vertex AI Agent Engine" / "Add Sub-Agents to Root
Agent"). The earlier revision deployed only the bare ``PlannerAgent().llm`` leaf;
this module now assembles and deploys the full Atelier coordinator graph:

    atelier_root_coordinator (LlmAgent, root)
        ├─ brief_parser_llm           (LlmAgent — intake N1)
        ├─ DDLCSpecialistPipeline     (SequentialAgent of 6 specialists — N3a)
        ├─ QACritiquePanel            (ParallelAgent of 4 critics — N3d)
        └─ atelier_fixer              (LlmAgent — N3e)

The sub-graphs are built by the same first-class builders the live pipeline
uses (``create_specialist_pipeline`` / ``create_critique_panel``) so the deployed
graph can never drift from the in-repo agent definitions. The planner's own
``LlmAgent`` instruction (``_PLANNER_SYSTEM_PROMPT``) is reused for the root
coordinator, so the root carries the planner's routing brief.

The deploy itself runs against live GCP and is operator-gated: it requires
Application Default Credentials for the serving project and the Vertex AI Agent
Engine API enabled. The pure helpers — requirement pins, ADK-version validation,
configuration resolution, and the hermetic ``build_agent_engine_app()`` graph
builder — are exercised by the unit suite without any network or GCP call.

Symbols verified against google-adk==2.1.0 / google-cloud-aiplatform==1.153.1:
    vertexai.init(project, location, staging_bucket)
    vertexai.agent_engines.AdkApp(agent, enable_tracing)
    vertexai.agent_engines.create(agent_engine, *, requirements, display_name, ...)
ADK root-graph deploy semantics grounded via context7 (/google/adk-python).

PRD Reference: §12 E8 (AT-082), §22 D5 (AT-002 ADK pin)
"""

from __future__ import annotations

import importlib.metadata
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from google.adk.agents import BaseAgent

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
_DEFAULT_DISPLAY_NAME = "atelier-root-engine"
_DEFAULT_DESCRIPTION = "Atelier hybrid-runtime root agent graph (planner + DDLC + QA + fixer)"
# Staging bucket pre-created in the project (atelier-build-2026-agent-staging).
# Required by vertexai.agent_engines.create() to upload agent artifacts before
# the Agent Engine runtime downloads and serves them.
_DEFAULT_STAGING_BUCKET = "gs://atelier-build-2026-agent-staging"

# The ADK root coordinator's name. This is the single deployed root agent whose
# reachable sub_agents form the Agent Engine application.
_ROOT_AGENT_NAME = "atelier_root_coordinator"


class AgentEngineDeployError(RuntimeError):
    """Raised when the Agent Engine deploy cannot proceed (fail-loud)."""


@dataclass(frozen=True)
class AgentEngineApp:
    """Hermetically-built Agent Engine deployment spec (no ``create()`` call).

    A frozen value object describing exactly what ``deploy_agent_engine()`` will
    submit to ``vertexai.agent_engines.create()``. Separating construction from
    submission makes the whole deploy graph unit-testable offline: the unit
    suite asserts the root graph, sub-agent topology, and create-kwargs without
    ever touching Vertex / network.

    Attributes:
        app: The ``AdkApp`` wrapping the root agent with tracing enabled. Typed
            as ``Any`` because ``AdkApp`` is an optional (GCP-extra) import.
        root_agent: The root ``BaseAgent`` of the deployed graph (planner
            coordinator). Its reachable ``sub_agents`` are deployed with it.
        display_name: Agent Engine display name.
        description: Agent Engine description.
        requirements: The pinned requirement list for the deploy sandbox.
        extra_packages: Local packages uploaded alongside the agent.
    """

    app: Any
    root_agent: BaseAgent
    display_name: str
    description: str
    requirements: list[str]
    extra_packages: list[str]

    @property
    def sub_agent_names(self) -> list[str]:
        """Names of the root's direct sub_agents (the deployed graph members)."""
        return [child.name for child in self.root_agent.sub_agents]


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
        "staging_bucket": os.getenv("ATELIER_STAGING_BUCKET", _DEFAULT_STAGING_BUCKET),
    }


def build_root_agent() -> BaseAgent:
    """Assemble the Atelier root agent graph for Agent Engine deployment.

    Builds a fresh root coordinator ``LlmAgent`` whose ``sub_agents`` are the
    real, first-class Atelier sub-graphs — the brief parser, the DDLC specialist
    pipeline (``SequentialAgent`` of 6), the QA critique panel (``ParallelAgent``
    of 4), and the fixer. ADK deploys this whole reachable graph as one Agent
    Engine app, so wiring the live builders here guarantees the deployed topology
    matches the in-repo definitions (no drift).

    Fresh instances are constructed deliberately: ADK enforces a single parent
    per agent, so the deploy graph must own its own sub-agent objects rather than
    re-parenting the pipeline's live instances.

    Returns:
        The root ``BaseAgent`` (the coordinator), with its ``sub_agents`` wired.

    Raises:
        AgentEngineDeployError: If google-adk / atelier agent modules cannot be
            imported (the deploy requires the full ADK stack).
    """
    try:
        from google.adk.agents import LlmAgent  # noqa: PLC0415

        from atelier.intake.brief_parser import BriefParserAgent  # noqa: PLC0415
        from atelier.nodes.critique_panel import create_critique_panel  # noqa: PLC0415
        from atelier.nodes.fixer import FixerAgent  # noqa: PLC0415
        from atelier.orchestrator.governor import MetacognitiveGovernor  # noqa: PLC0415
        from atelier.orchestrator.planner import (  # noqa: PLC0415
            _PLANNER_SYSTEM_PROMPT,
            PlannerAgent,
        )
        from atelier.orchestrator.specialists import (  # noqa: PLC0415
            create_specialist_pipeline,
        )
    except ImportError as exc:
        raise AgentEngineDeployError(
            "Building the Agent Engine root graph requires google-adk and the "
            "atelier agent modules to be installed."
        ) from exc

    # Sub-graphs from the live builders (each owns freshly-constructed members).
    #
    # The intake parser and fixer are leaf ``LlmAgent``s configured with an
    # ``output_schema`` (BriefSpec / FixerDirective). ADK structured-output
    # agents are leaf-only — they cannot carry sub_agents or transfer — so they
    # are valid graph LEAVES under the coordinator, never the root. Their
    # underlying ``LlmAgent`` is the wrapper's ``_llm`` (the same instance the
    # live pipeline runs); the fixer wrapper takes a default ``Metacognitive
    # Governor`` (zero-arg) purely to construct the agent for the deploy graph.
    specialist_pipeline, _stitch_degradation = create_specialist_pipeline()
    critique_panel = create_critique_panel()
    brief_parser = BriefParserAgent()._llm
    fixer = FixerAgent(MetacognitiveGovernor())._llm

    # The planner's served model + routing brief drive the root coordinator. We
    # reuse the planner's resolved model so the root matches what the pipeline
    # routes the planner to (AT-024 pin), and the planner system prompt so the
    # coordinator carries the same DAG-routing instruction. The root itself sets
    # NO output_schema — a coordinator must be able to transfer to its
    # sub_agents, which output_schema would disable.
    planner_model = PlannerAgent().model

    root_agent: BaseAgent = LlmAgent(
        name=_ROOT_AGENT_NAME,
        model=planner_model,
        description=(
            "Atelier root coordinator: routes a design brief through the DDLC "
            "specialist pipeline, the QA critique panel, and the fixer "
            "(planner-driven dynamic DAG)."
        ),
        instruction=_PLANNER_SYSTEM_PROMPT,
        sub_agents=[brief_parser, specialist_pipeline, critique_panel, fixer],
    )
    return root_agent


def build_agent_engine_app(config: dict[str, str] | None = None) -> AgentEngineApp:
    """Construct the Agent Engine deployment spec **without** calling ``create()``.

    The hermetic core of the deploy: builds the root agent graph, wraps it in an
    ``AdkApp`` with tracing enabled, and packages the create-kwargs (display
    name, description, pinned requirements, extra packages) into a frozen
    :class:`AgentEngineApp`. No ``vertexai.init`` and no ``create()`` — so the
    whole deploy configuration is unit-testable offline. ``deploy_agent_engine()``
    calls this, then submits ``app.app`` to ``create()``.

    Args:
        config: Optional pre-resolved config dict (as from :func:`resolve_config`).
            Defaults to :func:`resolve_config`.

    Returns:
        A frozen :class:`AgentEngineApp` carrying the ``AdkApp`` and create-kwargs.

    Raises:
        AgentEngineDeployError: If ``AdkApp`` or the agent stack is unavailable.
    """
    resolved = config if config is not None else resolve_config()

    root_agent = build_root_agent()

    try:
        from vertexai.agent_engines import AdkApp  # noqa: PLC0415
    except ImportError as exc:
        raise AgentEngineDeployError(
            "Agent Engine deploy requires vertexai (google-cloud-aiplatform) "
            "with the agent_engines extra to be installed."
        ) from exc

    # enable_tracing=True is required for the deployed graph to emit traces to
    # Cloud Trace / the Agent Engine console (grounded: ADK "Wrap Agent with
    # AdkApp for Deployment").
    app = AdkApp(agent=root_agent, enable_tracing=True)

    return AgentEngineApp(
        app=app,
        root_agent=root_agent,
        display_name=resolved["display_name"],
        description=resolved["description"],
        requirements=deployment_requirements(),
        extra_packages=["."],
    )


def deploy_agent_engine() -> str:
    """Deploy the Atelier root agent graph to Vertex AI Agent Engine.

    Builds the deployment spec via :func:`build_agent_engine_app` (hermetic),
    initialises Vertex, and submits the root graph to
    ``vertexai.agent_engines.create()``. The entire graph reachable from the root
    (planner coordinator + brief parser + specialist pipeline + critique panel +
    fixer) is deployed as one Agent Engine application.

    Returns:
        The deployed Agent Engine resource name.

    Raises:
        AgentEngineDeployError: On any failure — missing dependencies, a
            google-adk version drift, or a failed create call. Deploy failures
            fail loud and are never swallowed.
    """
    adk_version = validate_adk_pin()
    config = resolve_config()
    spec = build_agent_engine_app(config)

    try:
        import vertexai  # noqa: PLC0415
        from vertexai.agent_engines import create  # noqa: PLC0415
    except ImportError as exc:
        raise AgentEngineDeployError(
            "Agent Engine deploy requires vertexai and google-adk to be installed."
        ) from exc

    logger.info(
        "Deploying Atelier root graph to Agent Engine: project=%s location=%s "
        "adk=%s root=%s sub_agents=%s",
        config["project"],
        config["location"],
        adk_version,
        spec.root_agent.name,
        spec.sub_agent_names,
    )
    vertexai.init(
        project=config["project"],
        location=config["location"],
        staging_bucket=config["staging_bucket"],
    )

    try:
        remote_app = create(
            agent_engine=spec.app,
            display_name=spec.display_name,
            description=spec.description,
            requirements=spec.requirements,
            extra_packages=spec.extra_packages,
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
