"""Model Armor request/response callbacks — defense-in-depth injection guard (AT-081).

Atelier applies Google Cloud Model Armor as the managed safety layer on every
``LlmAgent`` through ``GenerateContentConfig.model_armor_config``
(:mod:`atelier.models.safety`). This module adds the ADK
``before_model_callback`` / ``after_model_callback`` hooks at the model boundary
itself, so injection carried in content the intake gate never sees — tool
returns, web-research findings (R8), multi-turn state — is blocked before it
reaches the model.

Division of responsibility:
    Managed Model Armor template (prompt + response) — the primary, server-side
        filter in production, provisioned in ``us-central1`` (AT-081 operator step).
    ``before_model_callback`` (this module) — a deterministic, fail-closed input
        guard for a high-confidence set of natural-language injection markers,
        exercised hermetically by the unit suite. Structural code markers
        (script tags, template macros, ``__import__``) are intentionally NOT
        scanned here: they are handled on the raw brief by
        :data:`atelier.intake.brief_parser.INJECTION_PATTERNS`, and legitimate
        design prompts routinely discuss web code, so scanning every model
        request for them would reject real work.
    ``after_model_callback`` (this module) — a structured audit hook that does
        not mutate the response; output filtering is performed by the managed
        response template, because generated design code legitimately contains
        template and macro syntax that a client-side scan must not reject.

Callback contract verified against google-adk==2.1.0 (AT-002 pin):
    before_model_callback(callback_context, llm_request) -> LlmResponse | None
    after_model_callback(callback_context, llm_response) -> LlmResponse | None
    Returning an ``LlmResponse`` from the before-callback short-circuits the
    model call; returning ``None`` lets the call proceed unchanged.

PRD Reference: §12 E8 (AT-081), §6 R8 (Model-Armor-sanitized grounded research),
R11 (managed over custom).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

from google.adk.models.llm_response import LlmResponse
from google.genai import types

if TYPE_CHECKING:
    from google.adk.agents.callback_context import CallbackContext
    from google.adk.models.llm_request import LlmRequest

logger = logging.getLogger(__name__)

# High-confidence natural-language prompt-injection markers. Each is an
# imperative override that does not occur in legitimate design-system content,
# so the guard does not false-positive on real briefs, prompts, or generated
# output. Structural code-injection markers are deliberately excluded (see the
# module docstring).
_INJECTION_PATTERNS: tuple[str, ...] = (
    r"ignore\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above|earlier)\s+instructions",
    r"disregard\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above|earlier)\s+instructions",
    r"reveal\s+(?:your\s+)?system\s+prompt",
    r"override\s+(?:your\s+)?system\s+prompt",
)

_COMPILED: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE) for pattern in _INJECTION_PATTERNS
)

_BLOCK_MESSAGE = (
    "This request was blocked by the Model Armor input guard because it "
    "contained a prompt-injection pattern."
)

#: User-facing acknowledgment surfaced by the runner when generation was
#: short-circuited at the safety boundary. The internal ``_BLOCK_MESSAGE`` above
#: is the model-boundary sentinel; this is the calm, branded explanation the end
#: user sees (PRD failure-handling trichotomy: a security block fails LOUD — the
#: agent states plainly what happened and that nothing was generated).
MODEL_ARMOR_BLOCK_USER_MESSAGE = (
    "Atelier's Model Armor safety guard blocked this request: the brief "
    "contained a prompt-injection pattern (an instruction to override the "
    "system's own directives). Nothing was generated and no design was "
    "produced. Revise the brief to describe the design you want, then resubmit."
)


def was_model_armor_blocked(candidates: Iterable[object]) -> bool:
    """True when Model Armor short-circuited generation for these candidates.

    The before-callback replaces a blocked model call's output with the exact
    :data:`_BLOCK_MESSAGE` sentinel, which then surfaces downstream as a
    "candidate". No legitimate design candidate contains that sentence, so an
    exact-substring match is a precise, false-positive-free signal that the run
    was stopped at the safety boundary. The runner uses it to raise a clean
    user-facing acknowledgment (:data:`MODEL_ARMOR_BLOCK_USER_MESSAGE`) instead
    of feeding refusal text through the N3c gates as if it were a design.

    Args:
        candidates: The raw generator candidates for one iteration.

    Returns:
        ``True`` if any candidate is the Model Armor block sentinel.
    """
    return any(isinstance(c, str) and _BLOCK_MESSAGE in c for c in candidates)


def _request_text(llm_request: LlmRequest) -> str:
    """Concatenate the text of every part in the request for scanning."""
    chunks: list[str] = []
    for content in llm_request.contents or []:
        for part in content.parts or []:
            text = getattr(part, "text", None)
            if text:
                chunks.append(text)
    return "\n".join(chunks)


def _first_injection_hit(text: str) -> str | None:
    """Return the first matching injection pattern, or ``None`` if the text is clean."""
    for pattern in _COMPILED:
        if pattern.search(text):
            return pattern.pattern
    return None


def model_armor_before_callback(
    callback_context: CallbackContext,
    llm_request: LlmRequest,
) -> LlmResponse | None:
    """Block prompt-injection inputs at the model boundary (fail-closed).

    Scans the outgoing request for a high-confidence set of injection markers.
    On a hit the model call is short-circuited with a refusal response and a
    structured warning is logged (the block is acknowledged, never swallowed).
    A clean request returns ``None`` so the model call proceeds unchanged.

    Args:
        callback_context: The ADK callback context for the current agent.
        llm_request: The request about to be sent to the model.

    Returns:
        A refusal ``LlmResponse`` to block the call, or ``None`` to proceed.
    """
    hit = _first_injection_hit(_request_text(llm_request))
    if hit is None:
        return None

    logger.warning(
        "model_armor before-callback blocked an injection attempt: agent=%s pattern=%s",
        getattr(callback_context, "agent_name", "unknown"),
        hit,
    )
    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text=_BLOCK_MESSAGE)]),
    )


def model_armor_after_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    """Audit hook for model responses; output filtering is the managed template's job.

    Returns ``None`` so the response passes through unchanged: legitimate
    generated design code contains template and macro syntax that must not be
    rejected by a client-side scan. The managed Model Armor response template
    performs server-side output filtering in production. This hook only records
    that the response passed through the guard, for the audit trail.

    Args:
        callback_context: The ADK callback context for the current agent.
        llm_response: The response returned by the model.

    Returns:
        ``None`` — the response is not mutated.
    """
    logger.debug(
        "model_armor after-callback: response observed for agent=%s (has_content=%s)",
        getattr(callback_context, "agent_name", "unknown"),
        llm_response.content is not None,
    )
    return None
