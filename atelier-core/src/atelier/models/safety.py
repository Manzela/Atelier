"""SafetyDefaults -- canonical GEAP safety settings for every LlmAgent (CL-01, B5).

In ADK 2.0, safety settings are passed via ``generate_content_config`` using
``ModelArmorConfig`` for centralized enterprise policy enforcement.
Every LlmAgent call site MUST use::

    from google.genai import types as genai_types
    from atelier.models.safety import default_model_armor_config

    agent = LlmAgent(
        name="my_agent",
        model="gemini-2.5-flash",
        generate_content_config=genai_types.GenerateContentConfig(
            model_armor_config=default_model_armor_config(),
        ),
    )

Constants are Final; changes require an ADR amendment.
Verified against ADK 2.0.0 + google-genai 1.75.0 (requirements.lock pins).
"""

from __future__ import annotations

import os

from google.genai import types


def default_model_armor_config() -> types.ModelArmorConfig:
    """Return the canonical ModelArmorConfig for every LlmAgent.

    Uses centralized Model Armor templates instead of static thresholds.
    Template names can be overridden via ATELIER_MODEL_ARMOR_TEMPLATE env var.

    Operator step (AT-081): the referenced template must be provisioned once per
    project in the configured location via the Model Armor API / gcloud. Until it
    exists, Vertex applies no server-side Model Armor filtering, and the
    before_model_callback in ``atelier.models.model_armor_callbacks`` is the
    deterministic first-line injection guard (defense in depth).
    """
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "atelier-build-2026")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    template_id = os.getenv("ATELIER_MODEL_ARMOR_TEMPLATE", "atelier-default")

    template_name = f"projects/{project}/locations/{location}/templates/{template_id}"

    return types.ModelArmorConfig(
        prompt_template_name=template_name,
        response_template_name=template_name,
    )
