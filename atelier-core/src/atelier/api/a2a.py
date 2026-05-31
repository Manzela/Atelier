"""A2A v1.0 JSON-RPC endpoint — POST /v1/a2a.

Implements the Agent-to-Agent protocol v1.0 JSON-RPC interface for
inter-agent communication. Supports:
    - ``SendMessage``: delegates to the Atelier pipeline (same as /v1/generate)
    - ``GetTask``: returns task status (stub; wire to task store when available)

References:
    - A2A v1.0 spec: https://github.com/a2aproject/A2A/blob/main/docs/specification.md
    - A2A what's-new-v1: https://github.com/a2aproject/A2A/blob/main/docs/whats-new-v1.md
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/a2a", tags=["a2a"])

# JSON-RPC 2.0 error codes
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603


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


async def _handle_send_message(
    params: dict[str, Any],
    request_id: str | int | None,
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
    from atelier.orchestrator.runner import AtelierRunner  # noqa: PLC0415

    runner = AtelierRunner()

    try:
        pipeline_result = await runner.run(brief_text)
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
    except Exception as exc:
        logger.exception("a2a.pipeline.error", extra={"task_id": task_id})
        return _error_response(
            _INTERNAL_ERROR,
            f"Pipeline execution failed: {type(exc).__name__}",
            request_id,
        )


async def _handle_get_task(
    params: dict[str, Any],
    request_id: str | int | None,
) -> JsonRpcResponse:
    """Handle the ``GetTask`` A2A v1.0 RPC method.

    Returns a stub response. Wire to persistent task store when available.

    Args:
        params: JSON-RPC params containing the task ID.
        request_id: JSON-RPC request ID.

    Returns:
        JSON-RPC response with task status.
    """
    task_id = params.get("taskId", params.get("task_id"))
    if not task_id:
        return _error_response(
            _INVALID_PARAMS,
            "GetTask requires a taskId parameter",
            request_id,
        )

    return JsonRpcResponse(
        result={
            "taskId": task_id,
            "status": "UNKNOWN",
            "message": {
                "role": "agent",
                "parts": [
                    {
                        "text": (
                            "Task store not yet implemented. "
                            "Use POST /v1/generate for synchronous execution."
                        ),
                    }
                ],
            },
        },
        id=request_id,
    )


# A2A v1.0 method dispatch (camelCase per spec)
_METHOD_HANDLERS = {
    "SendMessage": _handle_send_message,
    "GetTask": _handle_get_task,
}


@router.post(
    "",
    response_model=JsonRpcResponse,
    summary="A2A v1.0 JSON-RPC endpoint",
    description=(
        "Agent-to-Agent protocol v1.0 JSON-RPC interface. Supports SendMessage and GetTask methods."
    ),
)
async def a2a_rpc(request: JsonRpcRequest) -> JsonRpcResponse:
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
        return await handler(request.params, request.id)
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
