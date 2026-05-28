"""N3a Generator Ensemble — Parallel candidate generation.

Uses ADK ParallelAgent to run K=3 generators simultaneously.
Each generator attempts to use Stitch MCP first, falling back to direct
generation via the model pinned in ``model_registry.GENERATOR_MODEL``.

.. deprecated:: ADK 2.1.0
    ParallelAgent is deprecated. Migrate to ``Workflow`` when ADK ships it.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.parallel_agent import (
    ParallelAgent,  # Deprecation(adk-3.0): migrate -> Workflow
)
from google.genai import types as genai_types

from atelier.integrations.stitch_mcp import (
    StitchDegradationInfo,
    try_get_stitch_mcp_toolset,
)
from atelier.models.model_registry import GENERATOR_MODEL
from atelier.models.safety import default_safety_settings

if TYPE_CHECKING:
    from google.adk.agents import BaseAgent
    from google.adk.tools.base_toolset import BaseToolset

# Standard K=3 ensemble for Phase 1
ENSEMBLE_SIZE = 3


def create_generator_ensemble() -> tuple[ParallelAgent, StitchDegradationInfo]:  # type: ignore[no-any-unimported]
    """Creates a ParallelAgent containing K=3 generators.

    Returns:
        Tuple of (ParallelAgent, StitchDegradationInfo) so the caller can
        propagate degradation state to session metadata (AG-06 / FIX-3).
    """
    stitch_toolset, degradation = try_get_stitch_mcp_toolset()
    toolsets: Sequence[BaseToolset] = [stitch_toolset] if stitch_toolset is not None else []

    sub_agents: list[BaseAgent] = []
    for i in range(ENSEMBLE_SIZE):
        agent = LlmAgent(
            name=f"Generator_{i + 1}",
            model=GENERATOR_MODEL.model_id,
            tools=toolsets,
            instruction=(
                "You are a UX/UI Generator for Atelier. "
                "Attempt to generate the requested screen using the `stitch_generate_screen_from_text` tool. "
                "If the tool is unavailable or fails, generate the raw HTML/CSS directly in your response."
            ),
            generate_content_config=genai_types.GenerateContentConfig(
                safety_settings=default_safety_settings(),
            ),
        )
        sub_agents.append(agent)

    return ParallelAgent(
        name="GeneratorEnsemble",
        sub_agents=sub_agents,
    ), degradation
