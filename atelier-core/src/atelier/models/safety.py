"""SafetyDefaults — canonical GEAP safety settings for every LlmAgent (CL-01, B5).

In ADK 2.0, safety settings are passed via ``generate_content_config``, not as a
direct ``safety_settings`` parameter. Every LlmAgent call site MUST use::

    from google.genai import types as genai_types
    from atelier.models.safety import default_safety_settings

    agent = LlmAgent(
        name="my_agent",
        model="gemini-2.5-flash",
        generate_content_config=genai_types.GenerateContentConfig(
            safety_settings=default_safety_settings(),
        ),
    )

Constants are Final; changes require an ADR amendment.
Verified against ADK 2.0.0 + google-genai 1.75.0 (requirements.lock pins).
"""

from __future__ import annotations

from typing import Final

from google.genai import types

# ---------------------------------------------------------------------------
# Locked constants — ADR amendment required to change
# ---------------------------------------------------------------------------

_HARM_THRESHOLD: Final[types.HarmBlockThreshold] = types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE

_SAFETY_CATEGORIES: Final[tuple[types.HarmCategory, ...]] = (
    types.HarmCategory.HARM_CATEGORY_HARASSMENT,
    types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
    types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
    types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
)


def default_safety_settings() -> list[types.SafetySetting]:
    """Return the canonical safety settings list for every LlmAgent.

    All four harm categories are blocked at BLOCK_MEDIUM_AND_ABOVE. Returns a
    fresh list each call — callers must not mutate. Conforms to the type expected
    by ``google.genai.types.GenerateContentConfig.safety_settings``.
    """
    return [
        types.SafetySetting(category=cat, threshold=_HARM_THRESHOLD) for cat in _SAFETY_CATEGORIES
    ]
