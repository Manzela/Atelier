"""Board task-doc emitter — AT-020b (writer for PRD §7A.5; reader is AT-041).

Drives ONE Firestore document at
``tenants/{tenant_id}/projects/{project_id}/tasks/{task_id}`` through the EXACT
ordered 6-column Kanban set — :data:`BOARD_COLUMN_ORDER` ::

    [Brief, Decompose, Awaiting Sign-off, Generating, QA, Done]

— with **NO skips**. The runner calls :meth:`BoardEmitter.initialize_task_doc`
once (at the Brief column) and :meth:`BoardEmitter.transition` at each stage
boundary. Each write stamps the §7A.5 schema: ``columnId``, ``agentRole``, a
non-empty ``statusLine`` (carrying the active ``agentRole`` for the Generating
column, U6), a LexoRank ordering key, and ``updated_at``.

Backend selection mirrors the AT-095 usage counter and the AT-053 design-system
persister (the single durability pattern in this codebase):

* **in-memory** (offline / dev / hermetic test lane) — a process-wide dict, so
  ``make verify`` exercises the real state machine with **zero** GCP credentials
  and **no** Firestore emulator. Selected when ``FIREBASE_DISABLE_AUTH`` is set
  or ``ATELIER_ENV`` is ``development`` (or via an injected client double).
* **firestore** (production) — the Firebase Admin Firestore client (the same
  ``firebase_admin.firestore.client`` the AT-095 counter uses); writes go to
  ``tenants/{t}/projects/{p}/tasks/{task_id}`` (the path AT-084's rules pin to
  the owning tenant).

Failure trichotomy: the board is an **observability surface**, not a correctness
gate. A Firestore write failure therefore **fails soft** — it is logged with
structured context and returned as a :class:`BoardWriteAck` with
``degraded=True``; it MUST NOT raise, so a board outage never crashes the
generation run. (Contrast the AT-095 usage cap, which fails *closed* — it guards
a paid endpoint. The board guards nothing; a missing card is a cosmetic loss.)

A column-skip (or backward) transition is a **programming bug** in the runner's
wiring, not a runtime degradation, so it raises :class:`ColumnSkipError` loudly
— the invariant "the exact 6-set, in order, no skips" is enforced in code.

PRD Reference: §7A.5 (schema), §12 (AT-020b), §13.2 (durability pattern), U6.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from atelier.board.lexorank import lexorank_after
from atelier.models.data_contracts import TaskDocState, TenantContext
from atelier.models.enums import BoardColumnId

logger = logging.getLogger(__name__)

#: The exact ordered 6-column set. Single-sourced from the enum declaration
#: order so the legal forward transition order cannot drift from the schema.
BOARD_COLUMN_ORDER: Final[tuple[BoardColumnId, ...]] = tuple(BoardColumnId)

#: columnId -> its index in the ordered lane (the forward-only state machine).
_COLUMN_INDEX: Final[dict[BoardColumnId, int]] = {
    col: i for i, col in enumerate(BOARD_COLUMN_ORDER)
}

#: Firestore collection layout (production firestore backend); mirrors the path
#: AT-084's rules and AT-041's onSnapshot reader use.
_TENANTS_COLLECTION: Final[str] = "tenants"
_PROJECTS_COLLECTION: Final[str] = "projects"
_TASKS_COLLECTION: Final[str] = "tasks"


class ColumnSkipError(ValueError):
    """Raised when a transition would skip a column or move backward.

    The §7A.5 contract is "the exact ordered 6-set with no skips". A transition
    from column *i* is legal only to column *i+1* (or to *i*'s own re-stamp is
    NOT allowed — a transition must advance). Anything else is a wiring bug in
    the runner, surfaced loudly rather than silently corrupting the lane.
    """


@dataclass(frozen=True)
class BoardWriteAck:
    """Acknowledgement of a board write (fail-soft contract).

    ``degraded`` is ``True`` when the underlying store write failed; ``error``
    then carries the exception type name for the structured log. On success the
    ``state`` is the :class:`TaskDocState` that was persisted.
    """

    task_id: str
    column: BoardColumnId
    degraded: bool
    state: TaskDocState | None = None
    error: str | None = None


@dataclass
class _MemoryCard:
    """In-memory lane state for one task (dev / hermetic backend)."""

    state: TaskDocState
    last_rank: str


# Process-wide in-memory store keyed by the full doc path, so two BoardEmitter
# instances in one process (and the hermetic test lane) share lane state.
_MEMORY: dict[str, _MemoryCard] = {}
_MEMORY_LOCK = threading.Lock()


def _use_memory_backend() -> bool:
    """True when the offline in-memory backend should be used (dev / hermetic)."""
    explicit = os.getenv("ATELIER_BOARD_BACKEND", "").strip().lower()
    if explicit == "memory":
        return True
    if explicit == "firestore":
        return False
    bypass = os.getenv("FIREBASE_DISABLE_AUTH", "").lower() in ("1", "true", "yes")
    is_dev = os.getenv("ATELIER_ENV", "development") == "development"
    return bypass or is_dev


def _now() -> datetime:
    return datetime.now(UTC)


class BoardEmitter:
    """Writes the Board task-doc through the exact ordered 6-column lane (§7A.5).

    Construct cheaply per runner. Tests inject an in-memory Firestore double via
    ``client=...``; production lets the emitter lazily resolve the Firebase Admin
    Firestore client (only when the firestore backend is active).

    Args:
        client: An optional Firestore-client-shaped object. When provided, the
            emitter writes through it (bypassing backend auto-selection) — this
            is how the hermetic tests inject an in-memory double, and how a caller
            can pass a pre-built ``firebase_admin.firestore`` client. When
            ``None``, the backend is auto-selected (in-memory for dev/hermetic,
            Firestore otherwise) and the client is lazily resolved on first use.
    """

    def __init__(self, *, client: Any | None = None) -> None:
        self._injected_client = client
        self._fs_client: Any = None  # lazily resolved firestore client
        # Optional observers fired with the committed write payload (tests use
        # this to assert the transition history; production leaves it empty).
        self._write_observers: list[Callable[[dict[str, Any]], None]] = []

    # -- observers -----------------------------------------------------------

    def add_write_observer(self, observer: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback fired with each committed write's serialized payload."""
        self._write_observers.append(observer)

    def _notify(self, payload: dict[str, Any]) -> None:
        for observer in self._write_observers:
            observer(dict(payload))

    # -- backend resolution --------------------------------------------------

    @property
    def backend(self) -> str:
        if self._injected_client is not None:
            return "client"
        return "memory" if _use_memory_backend() else "firestore"

    def _client(self) -> Any:
        """Resolve the Firestore client (injected double, or lazy Firebase Admin)."""
        if self._injected_client is not None:
            return self._injected_client
        if self._fs_client is not None:
            return self._fs_client
        from atelier.auth.firebase import _init_firebase  # noqa: PLC0415

        app = _init_firebase()
        from firebase_admin import firestore as fb_firestore  # noqa: PLC0415

        self._fs_client = fb_firestore.client(app)
        return self._fs_client

    def _doc_path(self, tenant_ctx: TenantContext, task_id: str) -> str:
        return (
            f"{_TENANTS_COLLECTION}/{tenant_ctx.tenant_id}/"
            f"{_PROJECTS_COLLECTION}/{tenant_ctx.project_id}/"
            f"{_TASKS_COLLECTION}/{task_id}"
        )

    def _doc_ref(self, tenant_ctx: TenantContext, task_id: str) -> Any:
        client = self._client()
        return (
            client.collection(_TENANTS_COLLECTION)
            .document(tenant_ctx.tenant_id)
            .collection(_PROJECTS_COLLECTION)
            .document(tenant_ctx.project_id)
            .collection(_TASKS_COLLECTION)
            .document(task_id)
        )

    # -- public API ----------------------------------------------------------

    def initialize_task_doc(
        self,
        *,
        tenant_ctx: TenantContext,
        task_id: str,
        run_id: str,
        agent_role: str,
        status_line: str,
    ) -> BoardWriteAck:
        """Create the task doc at the FIRST column (Brief) with a seed LexoRank.

        Idempotent only in the sense that a re-init overwrites the card back to
        Brief; the runner calls this exactly once per task at run start.
        """
        seed_rank = lexorank_after(None)
        state = self._build_state(
            task_id=task_id,
            run_id=run_id,
            column=BoardColumnId.BRIEF,
            agent_role=agent_role,
            status_line=status_line,
            rank=seed_rank,
        )
        return self._commit(tenant_ctx=tenant_ctx, state=state, last_rank=seed_rank)

    def transition(
        self,
        *,
        tenant_ctx: TenantContext,
        task_id: str,
        column: BoardColumnId,
        agent_role: str,
        status_line: str,
    ) -> BoardWriteAck:
        """Advance the task doc to the next column (forward-only, no skips).

        Reads the card's current column, enforces that ``column`` is exactly the
        next one in :data:`BOARD_COLUMN_ORDER`, computes a fresh terminal
        LexoRank, and writes the §7A.5 doc. A skip or backward move raises
        :class:`ColumnSkipError` (a wiring bug, not a degradation).
        """
        current = self._read_card(tenant_ctx=tenant_ctx, task_id=task_id)
        if current is None:
            # No local lane state for this card. This is reachable in exactly two
            # ways: (1) a genuine wiring bug — a transition before initialize —
            # or (2) a PRIOR board write already degraded (so the card never made
            # it into the cache). We cannot distinguish them here, and the board
            # is an observability surface: crashing the run on case (2) would let
            # a Firestore outage take down generation, which violates the
            # trichotomy. So we degrade fail-soft (log + ack) rather than raise.
            # A real case-(1) wiring bug still surfaces — every subsequent write
            # degrades and the board stays empty, which is the visible symptom —
            # without ever crashing the run.
            logger.warning(
                "AT-020b: transition on an uninitialized/degraded board card "
                "(fail-soft; run continues)",
                extra={
                    "doc_path": self._doc_path(tenant_ctx, task_id),
                    "target_column": column.value,
                },
            )
            return BoardWriteAck(
                task_id=task_id,
                column=column,
                degraded=True,
                error="uninitialized_or_degraded_card",
            )
        self._assert_no_skip(current.state.columnId, column)

        next_rank = lexorank_after(current.last_rank)
        state = self._build_state(
            task_id=task_id,
            run_id=current.state.run_id,
            column=column,
            agent_role=agent_role,
            status_line=status_line,
            rank=next_rank,
        )
        return self._commit(tenant_ctx=tenant_ctx, state=state, last_rank=next_rank)

    def ensure_lane_at(
        self,
        *,
        tenant_ctx: TenantContext,
        task_id: str,
        run_id: str,
        column: BoardColumnId,
    ) -> None:
        """Seed the local lane cache to ``column`` IF it is cold (resume continuity).

        The forward-only skip-check reads from the in-process lane cache, which is
        warm within a single ``run()`` but COLD on the ``resume()`` path (a fresh
        runner/process after a sign-off halt). On resume the authoritative
        Firestore doc already sits at ``column`` (it was written before the halt),
        so we restore lane continuity here WITHOUT re-writing the earlier columns
        — re-walking Brief..column would emit spurious backward/duplicate cards.

        No-op when the lane is already warm (same-process inline path): a real
        card present in the cache is authoritative and must not be clobbered. This
        only ever seeds a MISSING entry, and never advances a card backward.
        """
        path = self._doc_path(tenant_ctx, task_id)
        with _MEMORY_LOCK:
            if path in _MEMORY:
                return  # warm cache — do not clobber the live lane
            seeded = TaskDocState(
                task_id=task_id,
                run_id=run_id,
                columnId=column,
                agentRole="resume",
                statusLine=f"resumed at {column.value}",
                rank=lexorank_after(None),
                updated_at=_now(),
            )
            _MEMORY[path] = _MemoryCard(state=seeded, last_rank=seeded.rank)

    # -- state machine -------------------------------------------------------

    @staticmethod
    def _assert_no_skip(current: BoardColumnId, target: BoardColumnId) -> None:
        """Enforce: a transition advances by EXACTLY one column (no skip/back)."""
        cur_i = _COLUMN_INDEX[current]
        tgt_i = _COLUMN_INDEX[target]
        if tgt_i != cur_i + 1:
            raise ColumnSkipError(
                f"illegal board transition {current.value!r} -> {target.value!r}: "
                f"the column set is exact and ordered with no skips "
                f"(legal next is index {cur_i + 1} of {len(BOARD_COLUMN_ORDER)})"
            )

    def _build_state(
        self,
        *,
        task_id: str,
        run_id: str,
        column: BoardColumnId,
        agent_role: str,
        status_line: str,
        rank: str,
    ) -> TaskDocState:
        # U6: the Generating statusLine must carry the active agentRole. We do
        # NOT silently mutate a caller's statusLine in general, but for the
        # Generating column we guarantee the invariant the §7A.5 reader asserts:
        # if the caller's line already names the role, keep it; else prefix it.
        effective_status = status_line
        if column is BoardColumnId.GENERATING and agent_role not in status_line:
            effective_status = f"{agent_role}: {status_line}"
        return TaskDocState(
            task_id=task_id,
            run_id=run_id,
            columnId=column,
            agentRole=agent_role,
            statusLine=effective_status,
            rank=rank,
            updated_at=_now(),
        )

    # -- write path (fail-soft) ---------------------------------------------

    def _commit(
        self, *, tenant_ctx: TenantContext, state: TaskDocState, last_rank: str
    ) -> BoardWriteAck:
        """Persist ``state`` to the backend; fail soft (log + ack), never raise.

        On a store error we degrade: the board is an observability surface, so a
        write failure is logged with structured context and returned as a
        degraded ack so the runner can acknowledge degradation and continue. The
        in-memory lane state is updated ONLY after a successful write so a failed
        write does not advance the card's tracked column out of sync with the
        store.
        """
        path = self._doc_path(tenant_ctx, state.task_id)
        try:
            if self.backend == "memory":
                with _MEMORY_LOCK:
                    _MEMORY[path] = _MemoryCard(state=state, last_rank=last_rank)
            else:
                self._doc_ref(tenant_ctx, state.task_id).set(state.to_firestore_dict(), merge=True)
                # For the firestore/client backend, track lane state in-process
                # too so the next transition's skip-check + rank do not require a
                # read round-trip on the hot path (the doc is authoritative; this
                # is a coherent local cache for the single-writer run).
                with _MEMORY_LOCK:
                    _MEMORY[path] = _MemoryCard(state=state, last_rank=last_rank)
        except Exception as exc:  # noqa: BLE001 — fail-soft: board must never crash the run
            logger.warning(
                "AT-020b: board task-doc write failed (fail-soft; run continues)",
                exc_info=True,
                extra={
                    "doc_path": path,
                    "columnId": state.columnId.value,
                    "backend": self.backend,
                    "error_type": type(exc).__name__,
                },
            )
            return BoardWriteAck(
                task_id=state.task_id,
                column=state.columnId,
                degraded=True,
                error=type(exc).__name__,
            )

        payload = state.to_firestore_dict()
        self._notify(payload)
        logger.info(
            "AT-020b: board task-doc -> %s",
            state.columnId.value,
            extra={
                "doc_path": path,
                "columnId": state.columnId.value,
                "agentRole": state.agentRole,
                "rank": state.rank,
            },
        )
        return BoardWriteAck(
            task_id=state.task_id,
            column=state.columnId,
            degraded=False,
            state=state,
        )

    def _read_card(self, *, tenant_ctx: TenantContext, task_id: str) -> _MemoryCard | None:
        """Return the current in-process lane state for the card (or None).

        For both backends the single-writer run keeps an authoritative local
        lane cache (updated on each successful commit), so the forward-only
        skip-check reads from there. A card not present locally means "not
        initialized yet" from this emitter's perspective.
        """
        path = self._doc_path(tenant_ctx, task_id)
        with _MEMORY_LOCK:
            return _MEMORY.get(path)


def reset_board_memory() -> None:
    """Clear the process-wide in-memory board lane state (test helper)."""
    with _MEMORY_LOCK:
        _MEMORY.clear()


__all__ = [
    "BOARD_COLUMN_ORDER",
    "BoardEmitter",
    "BoardWriteAck",
    "ColumnSkipError",
    "reset_board_memory",
]
