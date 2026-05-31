"""Hybrid Runtime Deployment — Vertex AI Agent Engine integration.

Deploys the Atelier pipeline to Vertex AI Agent Engine. This provides
a managed, serverless hybrid runtime for the ADK agent components,
abstracting away infrastructure scaling while preserving control over
the prompt and tools.

Requires:
    - vertexai SDK >= 1.75.0
    - google-adk >= 1.34.1

Usage::

    python -m atelier.agent_engine_deploy

PRD Reference: §6.7 (Scale pillar)
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def deploy_agent_engine() -> None:
    """Deploy the Atelier PlannerAgent to Vertex AI Agent Engine."""
    try:
        import vertexai  # noqa: PLC0415
        from vertexai.agent_engines import AdkApp, create  # noqa: PLC0415

        from atelier.orchestrator.planner import PlannerAgent  # noqa: PLC0415

        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "atelier-build-2026")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

        logger.info("Initializing vertexai for project %s in %s", project_id, location)
        vertexai.init(project=project_id, location=location)

        # Retrieve the ADK BaseAgent
        agent = PlannerAgent().llm

        # Wrap it in an AdkApp
        app = AdkApp(agent=agent, enable_tracing=True)

        logger.info("Deploying to Vertex AI Agent Engine...")
        remote_app = create(
            agent_engine=app,
            display_name="atelier-planner-engine",
            description="Atelier Hybrid Runtime Planner",
            requirements=[
                "google-adk>=1.34.1",
                "google-genai>=1.75.0",
                "pydantic>=2.9.0",
            ],
            extra_packages=["."],  # Includes the atelier package
        )

        logger.info(
            "Deployment complete. Resource name: %s",
            remote_app.resource_name,
        )

    except ImportError:
        logger.exception(
            "Agent Engine deployment requires vertexai and google-adk. "
            "Please ensure they are installed."
        )
    except Exception:
        logger.exception("Deployment failed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    deploy_agent_engine()
