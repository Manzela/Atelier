"""In-process cooperative Stop registry — AT-026 (PRD §1 interruption / R13).

A user-initiated **Stop** must halt an in-flight generation WITHIN ONE ITERATION
and — the trust-critical guarantee (R13) — issue **no model call after the Stop**.
This module is the seam that decouples the request that sets the stop (the
``POST /v1/stop/{session_id}`` API handler) from the convergence loop that honors
it (``AtelierRunner._run_surfaces_and_assemble``).

Design:

* The flag is keyed on ``session_id`` and lives in a process-local set guarded by a
  lock — set/cleared in O(1), read with zero I/O so the loop can poll it cheaply at
  the TOP of every iteration BEFORE any model call. Because the check precedes the
  model invocation, a Stop that is set at iteration boundary N halts before
  iteration N's model call ever runs: that is what makes "no model call after Stop"
  a structural property, provable by the AT-003 ``LiveCallGuard`` model-call
  counter reading 0 after the Stop.

* Scope is **single instance**. A multi-instance deployment routes the Stop to the
  instance running the session (sticky session / the session-service backend); the
  in-process registry is the per-instance honoring mechanism, not a distributed
  lock. This matches the AT-031 sign-off halt, which is likewise per-instance with
  the durable checkpoint as the cross-instance recovery surface.

* No silent failure: the registry never swallows — it is pure in-memory state with
  no error surface. A Stop on an unknown session is a harmless no-op (the loop
  simply never observes it), never an exception.
"""

from __future__ import annotations

import threading

_LOCK = threading.Lock()
#: session_ids with a pending Stop. Membership == "halt at the next iteration top".
_STOP_REQUESTED: set[str] = set()


def request_stop(session_id: str) -> None:
    """Arm a Stop for ``session_id`` (idempotent). The loop halts within one iteration.

    A no-op for an empty ``session_id`` so an un-started run cannot pollute the
    registry (the convergence loop only ever reads a real, created session id).
    """
    if not session_id:
        return
    with _LOCK:
        _STOP_REQUESTED.add(session_id)


def is_stop_requested(session_id: str) -> bool:
    """Return whether a Stop is pending for ``session_id`` (zero-I/O, lock-guarded)."""
    if not session_id:
        return False
    with _LOCK:
        return session_id in _STOP_REQUESTED


def clear_stop(session_id: str) -> None:
    """Clear a pending Stop for ``session_id`` (idempotent).

    Called once the loop has honored the Stop (so a subsequent resume of the same
    session is not immediately re-halted) and defensively in tests' ``finally``
    blocks. Clearing an absent key is a harmless no-op.
    """
    if not session_id:
        return
    with _LOCK:
        _STOP_REQUESTED.discard(session_id)
