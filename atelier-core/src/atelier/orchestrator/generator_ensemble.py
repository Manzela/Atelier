"""N3a Generator Ensemble — Parallel candidate generation.

Uses ADK ParallelAgent to run K=3 generators simultaneously.
Each generator attempts to use Stitch MCP first, falling back to gemini-3-pro direct generation.
"""

from google.adk.agents.llm_agent import LlmAgent
from google.adk.agents.parallel_agent import ParallelAgent

from atelier.integrations.stitch_mcp import get_stitch_mcp_toolset

# Standard K=3 ensemble for Phase 1
ENSEMBLE_SIZE = 3


def create_generator_ensemble() -> ParallelAgent:
    """Creates a ParallelAgent containing K=3 generators.

    Returns:
        ParallelAgent configured with LlmAgents that use Stitch MCP.
    """
    try:
        # Initialize the MCP toolset once to share across generators
        stitch_toolset = get_stitch_mcp_toolset()
        toolsets = [stitch_toolset]
    except Exception:  # noqa: BLE001
        # Fallback if Stitch is completely unconfigurable
        toolsets = []

    sub_agents = []
    for i in range(ENSEMBLE_SIZE):
        agent = LlmAgent(
            name=f"Generator_{i + 1}",
            model="gemini-3-pro",
            tools=toolsets,
            instruction=(
                "You are a UX/UI Generator for Atelier. "
                "Attempt to generate the requested screen using the `stitch_generate_screen_from_text` tool. "
                "If the tool is unavailable or fails, generate the raw HTML/CSS directly in your response."
            ),
        )
        sub_agents.append(agent)

    return ParallelAgent(
        name="GeneratorEnsemble",
        sub_agents=sub_agents,
    )
