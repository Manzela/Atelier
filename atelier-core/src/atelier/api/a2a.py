"""A2A v1.0 JSON-RPC endpoint — POST /v1/a2a.

Implements the Agent-to-Agent protocol v1.0 JSON-RPC interface for
inter-agent communication. Supports:
    - ``SendMessage``: delegates to the Atelier pipeline (same as /v1/generate),
      running it synchronously and returning a terminal ``COMPLETED`` result.

``GetTask`` is not implemented: SendMessage is synchronous, so there is no
asynchronous task to poll, and no task store exists yet to back ownership-scoped
status. The dispatcher therefore returns ``METHOD_NOT_FOUND`` for ``GetTask``
rather than a stub status that misrepresents a non-existent task store.

References:
    - A2A v1.0 spec: https://github.com/a2aproject/A2A/blob/main/docs/specification.md
    - A2A what's-new-v1: https://github.com/a2aproject/A2A/blob/main/docs/whats-new-v1.md
"""

from __future__ import annotations

import logging
import os
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from atelier.auth.firebase import FirebaseUser, require_auth_strict

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/a2a", tags=["a2a"])

# JSON-RPC 2.0 error codes
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603
# Server-defined codes (JSON-RPC reserves -32000..-32099 for implementation-defined
# errors). These let A2A clients distinguish a quota/rate-limit signal (retry later,
# back off) and a transient capacity fault from a true internal failure.
_QUOTA_EXCEEDED = -32001
_SERVICE_UNAVAILABLE = -32002


class JsonRpcRequest(BaseModel):
    """JSON-RPC 2.0 request envelope."""

    model_config = ConfigDict(frozen=True)

    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] = Field(default_factory=dict)
    id: str | int | None = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 response envelope."""

    model_config = ConfigDict(frozen=True)

    jsonrpc: str = "2.0"
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    id: str | int | None = None


def _error_response(
    code: int,
    message: str,
    request_id: str | int | None = None,
) -> JsonRpcResponse:
    """Build a JSON-RPC 2.0 error response."""
    return JsonRpcResponse(
        error={"code": code, "message": message},
        id=request_id,
    )


def _governor_error_response(
    exc: Exception,
    *,
    uid: str,
    task_id: str,
    request_id: str | int | None,
) -> JsonRpcResponse:
    """Map a Governor quota/rate-limit/breaker exception to a JSON-RPC error.

    Emits the SAME alert-level, abuse-monitoring log the ``app.py``/``/v1/generate``
    handlers do (with the structured ``uid``/``which_cap``/``reason`` context the
    breach-alerting relies on), then returns the correct JSON-RPC code so an A2A
    client can tell a quota/retry signal from a true internal error. Without this,
    these exceptions were swallowed into a generic ``-32603`` and the alert events
    never fired on the A2A surface.
    """
    from atelier.orchestrator.governor import (  # noqa: PLC0415
        GovernorCircuitBreakerOpen,
        GovernorRateLimitExceeded,
        GovernorTokenCapExceeded,
        GovernorUsageUnavailable,
    )
    from atelier.utils.log_sanitizer import sanitize  # noqa: PLC0415

    safe_uid = sanitize(uid)
    if isinstance(exc, GovernorTokenCapExceeded):
        logger.error(
            "atelier.token_cap_exceeded.a2a",
            extra={
                "uid": safe_uid,
                "task_id": task_id,
                "which_cap": exc.which_cap,
                "used_tokens": exc.used_tokens,
                "cap_tokens": exc.cap_tokens,
            },
        )
        return _error_response(_QUOTA_EXCEEDED, "Token cap reached.", request_id)
    if isinstance(exc, GovernorCircuitBreakerOpen):
        logger.error(
            "atelier.circuit_breaker_open.a2a",
            extra={
                "uid": safe_uid,
                "task_id": task_id,
                "reason": exc.reason,
                "retry_after_seconds": exc.retry_after_seconds,
            },
        )
        return _error_response(
            _SERVICE_UNAVAILABLE, "Service briefly busy; retry shortly.", request_id
        )
    if isinstance(exc, GovernorUsageUnavailable):
        logger.error(
            "atelier.usage_unavailable.a2a",
            extra={"uid": safe_uid, "task_id": task_id, "reason": exc.reason},
        )
        return _error_response(
            _SERVICE_UNAVAILABLE, "Usage guard unavailable; retry shortly.", request_id
        )
    if isinstance(exc, GovernorRateLimitExceeded):
        logger.warning(
            "atelier.rate_limit_exceeded.a2a",
            extra={"uid": safe_uid, "task_id": task_id},
        )
        return _error_response(
            _QUOTA_EXCEEDED, "Too many requests; please wait a moment.", request_id
        )
    # Unreachable: the caller only dispatches the four Governor types above.
    raise exc


async def _handle_send_message(
    params: dict[str, Any],
    request_id: str | int | None,
    user: FirebaseUser,
) -> JsonRpcResponse:
    """Handle the ``SendMessage`` A2A v1.0 RPC method.

    Delegates to the Atelier pipeline by extracting the message text
    from the A2A params and running it through the same path as
    ``POST /v1/generate``.

    Args:
        params: JSON-RPC params containing the message payload.
        request_id: JSON-RPC request ID for correlation.

    Returns:
        JSON-RPC response with task ID and status.
    """
    message = params.get("message", {})
    parts = message.get("parts", [])

    # Extract text from message parts
    text_parts = [p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p]
    brief_text = " ".join(text_parts).strip()

    if not brief_text:
        return _error_response(
            _INVALID_PARAMS,
            "SendMessage requires at least one text part in message.parts",
            request_id,
        )

    # Pre-gate the brief at the A2A layer, mirroring POST /v1/generate. A gate
    # rejection (injection attempt, empty/too-short/too-long brief) is a CLIENT
    # input error and must map to JSON-RPC _INVALID_PARAMS, not a generic
    # internal error. Without this, the gate runs deep inside runner._run_n1_n2
    # and surfaces as a ValueError caught by the broad handler below, mislabelling
    # a fixable client fault as a server failure.
    from atelier.intake.brief_parser import BriefParserGate  # noqa: PLC0415
    from atelier.models.enums import GateDecision  # noqa: PLC0415

    gate_outcome = BriefParserGate().check(brief_text)
    if gate_outcome.decision != GateDecision.PASS:
        return _error_response(
            _INVALID_PARAMS,
            f"Brief rejected: {gate_outcome.diagnostic}",
            request_id,
        )

    # Create a task ID for this A2A request
    task_id = str(uuid4())

    logger.info(
        "a2a.send_message",
        extra={
            "task_id": task_id,
            "brief_length": len(brief_text),
        },
    )

    # Run the pipeline synchronously for the hackathon (A2A is not the primary demo path)
    from atelier.models.data_contracts import TenantContext  # noqa: PLC0415
    from atelier.orchestrator.runner import AtelierRunner  # noqa: PLC0415

    runner = AtelierRunner()
    # Bind the authenticated identity so the governor's per-user token cap
    # (AT-095) and tenant isolation apply to A2A exactly as to /v1/generate —
    # otherwise this route would be an ungoverned, quota-bypassing entry point.
    tenant_ctx = TenantContext(
        tenant_id=user.tenant_id,
        user_id=user.uid,
        project_id=os.environ.get("GOOGLE_CLOUD_PROJECT", "atelier-build-2026"),
    )

    from atelier.models.model_armor_callbacks import ModelArmorInputBlocked  # noqa: PLC0415
    from atelier.orchestrator.governor import (  # noqa: PLC0415
        GovernorCircuitBreakerOpen,
        GovernorRateLimitExceeded,
        GovernorTokenCapExceeded,
        GovernorUsageUnavailable,
    )

    try:
        pipeline_result = await runner.run(brief_text, tenant_ctx)
        best_candidate = pipeline_result.get("best_candidate")
        composite_score = pipeline_result.get("composite_score", 0.0)
        converged = pipeline_result.get("converged", False)

        return JsonRpcResponse(
            result={
                "taskId": task_id,
                "status": "COMPLETED",
                "message": {
                    "role": "agent",
                    "parts": [
                        {
                            "text": (
                                f"Task {task_id} completed. "
                                f"Convergence: {converged} "
                                f"(Score: {composite_score:.2f})."
                            ),
                            "metadata": {
                                "best_candidate": best_candidate,
                            },
                        }
                    ],
                },
            },
            id=request_id,
        )
    except (
        GovernorTokenCapExceeded,
        GovernorCircuitBreakerOpen,
        GovernorUsageUnavailable,
        GovernorRateLimitExceeded,
    ) as exc:
        # Quota / rate-limit / circuit-breaker faults are NOT generic internal
        # errors. Map each to its proper JSON-RPC code and emit the same
        # alert-level, abuse-monitoring log the /v1/generate path does, so the
        # A2A surface is not an unmonitored quota-bypass entry point (the
        # AT-095/AT-097 controls bind here too).
        return _governor_error_response(exc, uid=user.uid, task_id=task_id, request_id=request_id)
    except ModelArmorInputBlocked as exc:
        # L15: a Model Armor safety block is a CLIENT input rejection (prompt
        # injection / unsafe content), NOT a server fault. Map it to _INVALID_PARAMS
        # with the branded user message, mirroring the POST /v1/generate 422 handler
        # — never the generic -32603 that would imply the server broke.
        return _error_response(_INVALID_PARAMS, exc.user_message, request_id)
    except Exception as exc:
        logger.exception("a2a.pipeline.error", extra={"task_id": task_id})
        return _error_response(
            _INTERNAL_ERROR,
            f"Pipeline execution failed: {type(exc).__name__}",
            request_id,
        )


# A2A v1.0 method dispatch (camelCase per spec).
#
# GetTask is intentionally NOT advertised: SendMessage runs the pipeline
# synchronously and returns a terminal COMPLETED result inline, so there is no
# asynchronous task to poll. A GetTask stub previously returned status "UNKNOWN"
# for every taskId, which lies to a spec-following client (it implies a task
# store that does not exist). Until a real, ownership-enforcing task store lands,
# GetTask returns METHOD_NOT_FOUND so clients do not build on a phantom status.
_METHOD_HANDLERS = {
    "SendMessage": _handle_send_message,
}


@router.post(
    "",
    response_model=JsonRpcResponse,
    summary="A2A v1.0 JSON-RPC endpoint",
    description=(
        "Agent-to-Agent protocol v1.0 JSON-RPC interface. Supports SendMessage and GetTask methods."
    ),
)
async def a2a_rpc(
    request: JsonRpcRequest,
    user: Annotated[FirebaseUser, Depends(require_auth_strict)],
) -> JsonRpcResponse:
    """Process an A2A v1.0 JSON-RPC request.

    Args:
        request: JSON-RPC 2.0 request with method and params.

    Returns:
        JSON-RPC 2.0 response with result or error.
    """
    if request.jsonrpc != "2.0":
        return _error_response(
            _INVALID_REQUEST,
            f"Unsupported JSON-RPC version: {request.jsonrpc}",
            request.id,
        )

    handler = _METHOD_HANDLERS.get(request.method)
    if handler is None:
        return _error_response(
            _METHOD_NOT_FOUND,
            f"Method not found: {request.method}",
            request.id,
        )

    try:
        return await handler(request.params, request.id, user)
    except Exception as exc:
        logger.exception(
            "a2a.rpc.error",
            extra={
                "method": request.method,
                "error": str(exc)[:200],
            },
        )
        return _error_response(
            _INTERNAL_ERROR,
            f"Internal error: {type(exc).__name__}",
            request.id,
        )
