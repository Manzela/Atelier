"""Atelier Board — task-doc emitter (PRD §7A.5, writer AT-020b).

The board package owns the WRITE path for the Kanban board task documents at
``tenants/{tenant_id}/projects/{id}/tasks/{task_id}``. The dashboard reader
(AT-041) consumes the same Firestore path via ``onSnapshot``.
"""

from atelier.board.board_emitter import (
    BOARD_COLUMN_ORDER,
    BoardEmitter,
    BoardWriteAck,
    ColumnSkipError,
)

__all__ = [
    "BOARD_COLUMN_ORDER",
    "BoardEmitter",
    "BoardWriteAck",
    "ColumnSkipError",
]
