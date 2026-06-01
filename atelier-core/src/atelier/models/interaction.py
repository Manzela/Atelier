r"""Interaction-spec schema and parser — AT-023.

Defines the structured output contract for the ``InteractionDesigner`` DDLC
specialist (``output_key="interaction_spec"``).  The parser accepts raw LLM
text (with or without a ``\`\`\`json … \`\`\`` fence) and returns a validated
:class:`InteractionSpec`.

Import hierarchy: this module imports from ``atelier.models.enums`` only
(no circular deps), consistent with the models-package invariant.
"""

from __future__ import annotations

import json
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from atelier.models.enums import InteractionTrigger

__all__ = [
    "DeclaredInteraction",
    "InteractionSpec",
    "parse_interaction_spec",
]

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)


class DeclaredInteraction(BaseModel):
    """One element/trigger/effect triple in the interaction spec.

    Attributes:
        element: CSS selector or component name (e.g. ``".btn-primary"``).
        trigger: The interaction trigger (hover, focus, active, disabled, keyboard).
        effect: What changes when the trigger fires (e.g. ``"opacity 0.2s ease"``).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    element: str = Field(min_length=1, description="CSS selector or component name")
    trigger: InteractionTrigger
    effect: str = Field(min_length=1, description="Visual/behavioural change on trigger")


class InteractionSpec(BaseModel):
    """Structured interaction specification produced by the InteractionDesigner.

    Invariants (validated at model construction):
        - At least one :class:`DeclaredInteraction` entry.
        - At least one entry whose trigger is ``FOCUS`` or ``KEYBOARD``
          (the "every interactive element has a focus-visible state" rule,
          derived from WCAG 2.4.7 / PRD §4 R-accessibility).

    Attributes:
        interactions: All declared element/trigger/effect triples.
        schema_version: Forward-compat version marker (never decreases).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    interactions: list[DeclaredInteraction] = Field(
        min_length=1,
        description="All declared interaction triples (non-empty)",
    )
    schema_version: int = 1

    @model_validator(mode="after")
    def _require_focus_coverage(self) -> InteractionSpec:
        """Fail loudly if no focus or keyboard interaction is declared.

        WCAG 2.4.7 / PRD R-accessibility: every interactive element must have
        a focus-visible state.  An ``InteractionSpec`` without at least one
        FOCUS or KEYBOARD trigger is structurally invalid.
        """
        if not self.focus_covered:
            raise ValueError(
                "InteractionSpec must include at least one interaction with trigger "
                "'focus' or 'keyboard' (WCAG 2.4.7 / PRD R-accessibility). "
                f"Got triggers: {[i.trigger for i in self.interactions]}"
            )
        return self

    @property
    def focus_covered(self) -> bool:
        """``True`` iff at least one interaction uses FOCUS or KEYBOARD trigger."""
        return any(
            i.trigger in (InteractionTrigger.FOCUS, InteractionTrigger.KEYBOARD)
            for i in self.interactions
        )


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_interaction_spec(raw: str) -> InteractionSpec:
    """Parse raw LLM output into a validated :class:`InteractionSpec`.

    Handles two input shapes:
        1. A bare JSON object: ``{"interactions": [...]}``
        2. A fenced code block: ``\\`\\`\\`json\\n{...}\\n\\`\\`\\`\\`` (or ``\\`\\`\\`{...}\\`\\`\\``).

    Surrounding prose outside the fence is ignored.  If no fence is present the
    entire stripped string is treated as JSON.

    Args:
        raw: The raw string returned by the LLM (may include markdown fencing
            or surrounding prose).

    Returns:
        A validated :class:`InteractionSpec`.

    Raises:
        ValueError: If the input is empty, not valid JSON, or fails Pydantic
            validation (missing fields, constraint violations, or missing
            focus/keyboard coverage).  The error message is structured and
            includes the original validation failure.
    """
    stripped = raw.strip()
    if not stripped:
        raise ValueError("parse_interaction_spec received an empty string")

    # Prefer the fenced block when present; fall back to the full string.
    fence_match = _JSON_FENCE_RE.search(stripped)
    json_text = fence_match.group(1).strip() if fence_match else stripped

    try:
        payload = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"parse_interaction_spec: invalid JSON — {exc.msg} "
            f"(at line {exc.lineno}, col {exc.colno}). "
            f"Input (first 200 chars): {json_text[:200]!r}"
        ) from exc

    try:
        return InteractionSpec.model_validate(payload)
    except Exception as exc:  # pydantic.ValidationError is not re-exported cleanly
        raise ValueError(f"parse_interaction_spec: schema validation failed — {exc}") from exc
