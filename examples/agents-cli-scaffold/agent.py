"""Minimal Atelier agent definition for agents-cli scaffold.

This file demonstrates how to wire an ADK 2.0 LlmAgent into the
agents-cli toolchain. For the full production agent, see
``atelier-core/src/atelier/agents/``.
"""

from google.adk.agents import LlmAgent
from google.genai import types as genai_types

# --- Safety settings (AG-04 compliance) ---
SAFETY_SETTINGS = [
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=genai_types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=genai_types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=genai_types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    genai_types.SafetySetting(
        category=genai_types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=genai_types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
]

# --- Agent Definition ---
AtelierRootAgent = LlmAgent(
    name="atelier-root",
    model="gemini-3-pro",
    description="Autonomous Design Agent — generates web UI from natural-language briefs.",
    instruction="""You are Atelier, an autonomous design agent.
Given a design brief, you generate high-quality web UI candidates,
evaluate them across 9 quality axes (brand, originality, relevance,
accessibility, visual clarity, copy, motion, token efficiency, coherence),
and select the best candidate through multi-judge Bayesian consensus.

Always respond with valid HTML/CSS/JS that can be rendered directly.""",
    generate_content_config=genai_types.GenerateContentConfig(
        safety_settings=SAFETY_SETTINGS,
        temperature=0.7,
        max_output_tokens=8192,
    ),
)
