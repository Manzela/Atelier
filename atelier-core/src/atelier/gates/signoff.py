"""AT-031 — fail-closed human-in-the-loop sign-off gate (PRD v2.2 §1, §12 E3, §16, R5).

The "pause for a human" win-condition. After the plan and scope are locked (N0/N1/N2),
the runner halts on an explicit human sign-off before any screen generation (N3a) runs.
The gate is durable: the halt persists an idempotent ``AWAITING_SIGNOFF`` checkpoint into
the ADK session state, so a crashed-and-restarted runner resumes from the same point with
zero re-execution of completed stages and zero model calls while it waits.

The halt is built on the native ADK tool-confirmation primitive (verified against
google-adk==2.1.0):

    - ``google.adk.tools.long_running_tool.LongRunningFunctionTool`` wraps
      :func:`await_signoff`. A long-running tool's first response is "not yet complete":
      the runner emits an ``adk_request_confirmation`` ``FunctionCall`` (with the call id
      registered in ``Event.long_running_tool_ids``) and the driver stops issuing model
      calls until a ``FunctionResponse`` carrying ``ToolConfirmation(confirmed=True)``
      resumes it.
    - ``ToolContext.request_confirmation(*, hint, payload)`` (verified signature:
      ``(self, *, hint: str | None = None, payload: Any | None = None) -> None``) records a
      :class:`~google.adk.tools.tool_confirmation.ToolConfirmation` into
      ``EventActions.requested_tool_confirmations[function_call_id]``.
    - ``google.adk.flows.llm_flows.functions.generate_request_confirmation_event`` is the
      runner-side function that turns that request into the ``adk_request_confirmation``
      long-running event (constant
      ``functions.REQUEST_CONFIRMATION_FUNCTION_CALL_NAME == "adk_request_confirmation"``).

``ToolConfirmation`` is ``@experimental`` in 2.1.0; instantiating it emits a one-time
``UserWarning`` (FeatureName.TOOL_CONFIRMATION). That is expected ADK behaviour and is not
suppressed globally per ``<no_silent_error_suppression>``.

PRD Reference: §1 (win-condition), §12 E3 line 358, §16 (golden path), R5 (durability).
"""

from __future__ import annotations

from typing import Any

# Verified against google-adk==2.1.0 wheel: LongRunningFunctionTool, ToolContext (with
# request_confirmation), and the experimental ToolConfirmation. These are runtime imports
# (not gated by TYPE_CHECKING) because ADK introspects the await_signoff signature to build
# the tool function declaration and must resolve the ToolContext annotation at runtime.
from google.adk.tools.long_running_tool import LongRunningFunctionTool
from google.adk.tools.tool_confirmation import (
    ToolConfirmation,  # noqa: TC002 — runtime annotation resolution
)
from google.adk.tools.tool_context import ToolContext  # noqa: TC002 — ADK signature introspection

#: Stable stage id recorded against the sign-off boundary. Used by the runner's
#: per-stage accumulators and by the checkpoint payload so resume is idempotent.
SIGNOFF_STAGE_ID: str = "pre_orchestrate"

#: Durable session-state keys (persisted via an ADK ``state_delta`` so a fresh
#: runner reading the same session service can resume after a crash).
SIGNOFF_STATUS_KEY: str = "signoff_status"
CHECKPOINT_KEY: str = "atelier_checkpoint"

#: ``signoff_status`` lifecycle values.
#:   AWAITING_SIGNOFF -> APPROVED -> COMPLETED
#: ``APPROVED`` is set the moment a confirmed sign-off begins running surfaces;
#: ``COMPLETED`` is the terminal state recorded after the surface loop returns.
#: Either of the two latter states is treated as terminal by ``resume()``'s
#: re-entry guard (fail-closed: no surface re-run on redelivery/double-click).
STATUS_AWAITING: str = "AWAITING_SIGNOFF"
STATUS_APPROVED: str = "APPROVED"
STATUS_COMPLETED: str = "COMPLETED"


def _default_hint(scope_summary: str) -> str:
    """Compose the human-facing confirmation hint from the scope summary."""
    summary = scope_summary.strip() or "the planned scope"
    return (
        "Atelier has locked the plan and scope and is paused for your sign-off. "
        f"Approve to begin generating: {summary}. "
        "Generation will not start until you confirm."
    )


def await_signoff(
    tool_context: ToolContext,
    scope_summary: str = "",
) -> dict[str, Any]:
    """Long-running sign-off tool body — requests human confirmation, then yields.

    Calls :meth:`ToolContext.request_confirmation` (verified ADK 2.1.0 symbol) to register
    a :class:`ToolConfirmation` request. Because this function is wrapped in
    :data:`AWAIT_SIGNOFF_TOOL` (a ``LongRunningFunctionTool``), the returned dict is treated
    as a "not yet complete" response: the runner emits the native ``adk_request_confirmation``
    long-running event and halts further model calls until a confirmed ``ToolConfirmation``
    resumes the call.

    Args:
        tool_context: ADK tool context (must carry a ``function_call_id``; the runner
            populates it when dispatching a tool call).
        scope_summary: Short human-readable description of the locked scope, surfaced in
            the confirmation hint.

    Returns:
        A "pending" response dict: ``{"status": "AWAITING_SIGNOFF", "stage": ...}``.
    """
    tool_context.request_confirmation(
        hint=_default_hint(scope_summary),
        payload={"stage": SIGNOFF_STAGE_ID, "scope_summary": scope_summary},
    )
    return {"status": STATUS_AWAITING, "stage": SIGNOFF_STAGE_ID}


#: The production tool: ``await_signoff`` wrapped as a native ADK long-running tool so the
#: runner emits the ``adk_request_confirmation`` halt and waits for a confirmed response.
AWAIT_SIGNOFF_TOOL: LongRunningFunctionTool = LongRunningFunctionTool(func=await_signoff)


def is_signoff_confirmed(confirmation: ToolConfirmation | None) -> bool:
    """Return ``True`` only when an explicit, confirmed sign-off is present.

    Fail-closed: ``None`` (no confirmation supplied) and ``confirmed is False`` both deny.
    Only an explicit ``ToolConfirmation(confirmed=True)`` advances the pipeline.

    Args:
        confirmation: The confirmation supplied on resume, or ``None``.

    Returns:
        ``True`` iff ``confirmation is not None and confirmation.confirmed is True``.
    """
    return confirmation is not None and confirmation.confirmed is True
