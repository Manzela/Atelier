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

* Bounded + self-healing: each Stop carries the monotonic time it was armed, and
  entries are evicted on every access once older than ``_STOP_TTL_SECONDS``. The
  honoring path clears its own entry, but a Stop armed for a run that never
  reaches (or never completes) the convergence loop — a failed N1/N2, a run that
  raised before the loop, or a wrong session id — would otherwise leak forever in
  a long-lived instance and could re-halt a much-later resume that reuses the id.
  The TTL bounds the registry size and guarantees a stale flag self-expires rather
  than silently halting a future run at iteration 0.
"""

from __future__ import annotations

import threading
import time

_LOCK = threading.Lock()
#: session_id -> monotonic time the Stop was armed. Presence (within TTL) ==
#: "halt at the next iteration top".
_STOP_REQUESTED: dict[str, float] = {}
#: A Stop older than this (seconds) is treated as expired and evicted. Sized well
#: above any single run's wall-clock so a legitimate in-flight Stop is always
#: honored, while a Stop on a run that never reaches/finishes the loop cannot leak
#: or re-halt a far-later resume.
_STOP_TTL_SECONDS = 3600.0


def _evict_expired_locked(now: float) -> None:
    """Drop Stops older than the TTL. Caller MUST hold ``_LOCK``."""
    expired = [
        sid for sid, armed_at in _STOP_REQUESTED.items() if now - armed_at >= _STOP_TTL_SECONDS
    ]
    for sid in expired:
        del _STOP_REQUESTED[sid]


def stop_key(user_id: str, session_id: str) -> str:
    """Compose the per-OWNER stop-registry key (L04 — cross-tenant IDOR fix).

    The registry is keyed on (owner uid, session_id), NOT a bare ``session_id``, so
    a Stop armed by one user can never halt another user's in-flight run: the
    convergence loop only ever polls the key built from ITS OWN owner uid, and the
    ``POST /v1/stop`` handler arms the key built from the REQUESTER's uid. A cross-
    user stop therefore arms a key the victim's run never reads (and leaks no
    existence oracle — the handler still returns the same 200 regardless).

    An empty uid or session yields the empty key, preserving the existing
    "empty session is a harmless no-op" contract of :func:`request_stop`.
    """
    if not user_id or not session_id:
        return ""
    return f"{user_id}\x1f{session_id}"


def request_stop(session_id: str) -> None:
    """Arm a Stop for ``session_id`` (idempotent). The loop halts within one iteration.

    A no-op for an empty ``session_id`` so an un-started run cannot pollute the
    registry (the convergence loop only ever reads a real, created session id).
    """
    if not session_id:
        return
    now = time.monotonic()
    with _LOCK:
        _evict_expired_locked(now)
        _STOP_REQUESTED[session_id] = now


def is_stop_requested(session_id: str) -> bool:
    """Return whether a non-expired Stop is pending for ``session_id`` (zero-I/O, lock-guarded).

    An entry past ``_STOP_TTL_SECONDS`` is treated as absent and evicted, so a
    Stop armed for a run that never honored it cannot re-halt a later resume on a
    reused session id.
    """
    if not session_id:
        return False
    now = time.monotonic()
    with _LOCK:
        _evict_expired_locked(now)
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
        _STOP_REQUESTED.pop(session_id, None)
