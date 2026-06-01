"""Per-user lifetime token-usage counter — AT-095 (PRD §13.2 / G14 / G16).

The sole V1 usage cap is a **per-Firebase-uid lifetime 5,000,000-token** hard
cap. Unlike the retired per-run USD governor (which reset every ``run()`` and
was therefore bypassable by starting a new run on our paid key — a token-burn
abuse hole), this counter is **cumulative and persisted across runs** in
Firestore at ``users/{uid}/usage/lifetime`` (the path AT-084's rules already
make owner-only).

Tokens counted = ``input + output + thoughts`` (thinking tokens, from Vertex
``usage_metadata.thoughts_token_count`` per G15). Writes are **atomic**
(``firestore.Increment``) so concurrent runs / device-sync cannot double-count
or lose updates.

Backend selection (mirrors the SessionService env-selection, PRD §11):

* **Firestore** — production / any environment with Application Default
  Credentials and ``firebase-admin`` available.
* **In-memory** — local development and the hermetic test lane
  (``FIREBASE_DISABLE_AUTH=true`` or ``ATELIER_ENV=development``). A
  **process-wide** dict keyed by uid, so the counter persists across
  ``AtelierRunner`` instances within a process — this is what makes the
  cross-run durability assertion (AT-095 acceptance (e)) and the byte-stable
  ``make verify`` token meter (§13.3) work without live Firestore.

A persistent-store read/write failure in a real environment is **not** a cap
breach (the breach itself is fail-loud and lives in the governor); it is a
transient infrastructure fault. Per the failure trichotomy this counter
**fails closed** on a hard persistence error (a usage cap is a security
control on a paid endpoint — availability must not be bought by dropping the
guard); the bounded retry / circuit-breaker policy around it is AT-097.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from atelier.orchestrator.governor import (
    GovernorRateLimitExceeded,
    GovernorTokenCapExceeded,
)

logger = logging.getLogger(__name__)

#: The single fixed V1 cap. Operator-open thresholds (global circuit-breaker,
#: request-rate limit) live in AT-097; only this per-user lifetime cap is fixed.
TOKEN_CAP_DEFAULT: Final[int] = 5_000_000

#: Firestore document path for a user's lifetime counter (AT-084 owner-only rules).
_USAGE_COLLECTION: Final[str] = "usage"
_USAGE_DOC: Final[str] = "lifetime"
_USERS_COLLECTION: Final[str] = "users"

#: Per-window request-rate limit defaults (operator-open, §22 D-cap-numbers;
#: AT-097 hardens these + adds the global circuit-breaker). Env-overridable so
#: the operator can tune without a code change.
_RATE_LIMIT_MAX_REQUESTS: Final[int] = int(os.getenv("ATELIER_RATE_LIMIT_MAX_REQUESTS", "30"))
_RATE_LIMIT_WINDOW_SECONDS: Final[float] = float(
    os.getenv("ATELIER_RATE_LIMIT_WINDOW_SECONDS", "60")
)


@dataclass(frozen=True)
class UsageSnapshot:
    """Immutable read of a user's cumulative token usage."""

    uid: str
    total_tokens: int
    input_tokens: int
    output_tokens: int
    thinking_tokens: int


class _Clock(Protocol):
    def __call__(self) -> float: ...


@dataclass
class _MemoryRecord:
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    request_times: list[float] = field(default_factory=list)


# Process-wide in-memory store. Persists across AtelierRunner instances within a
# process so the hermetic test lane and local dev get real cross-run durability.
_MEMORY: dict[str, _MemoryRecord] = {}
_MEMORY_LOCK = threading.Lock()


def _use_memory_backend() -> bool:
    """True when the offline in-memory backend should be used (dev / hermetic)."""
    if os.getenv("ATELIER_USAGE_BACKEND", "").lower() == "memory":
        return True
    if os.getenv("ATELIER_USAGE_BACKEND", "").lower() == "firestore":
        return False
    bypass = os.getenv("FIREBASE_DISABLE_AUTH", "").lower() in ("1", "true", "yes")
    is_dev = os.getenv("ATELIER_ENV", "development") == "development"
    return bypass or is_dev


class UsageCounterStore:
    """Cumulative per-uid token counter with atomic, persisted writes.

    One instance is cheap; the production singleton is :func:`get_usage_store`.
    Tests construct their own (``backend="memory"``) and call :meth:`reset`.
    """

    def __init__(
        self,
        *,
        backend: str | None = None,
        token_cap: int = TOKEN_CAP_DEFAULT,
        clock: _Clock | None = None,
        rate_limit_max_requests: int = _RATE_LIMIT_MAX_REQUESTS,
        rate_limit_window_seconds: float = _RATE_LIMIT_WINDOW_SECONDS,
    ) -> None:
        if backend is None:
            backend = "memory" if _use_memory_backend() else "firestore"
        if backend not in ("memory", "firestore"):
            raise ValueError(f"Unknown usage backend: {backend!r}")
        self._backend = backend
        self._token_cap = token_cap
        self._clock: _Clock = clock or time.monotonic
        self._rl_max = rate_limit_max_requests
        self._rl_window = rate_limit_window_seconds
        self._fs_client: Any = None  # lazily initialised google.cloud.firestore.Client

    @property
    def token_cap(self) -> int:
        return self._token_cap

    @property
    def backend(self) -> str:
        return self._backend

    # -- Firestore plumbing --------------------------------------------------

    def _client(self) -> Any:
        """Lazily obtain the Firestore client (Firestore backend only)."""
        if self._fs_client is not None:
            return self._fs_client
        from atelier.auth.firebase import _init_firebase  # noqa: PLC0415

        app = _init_firebase()
        from firebase_admin import firestore as fb_firestore  # noqa: PLC0415

        self._fs_client = fb_firestore.client(app)
        return self._fs_client

    def _doc_ref(self, uid: str) -> Any:
        client = self._client()
        return (
            client.collection(_USERS_COLLECTION)
            .document(uid)
            .collection(_USAGE_COLLECTION)
            .document(_USAGE_DOC)
        )

    # -- Public API ----------------------------------------------------------

    def get_total(self, uid: str) -> int:
        """Return the user's cumulative lifetime token count (0 if none yet)."""
        return self.snapshot(uid).total_tokens

    def snapshot(self, uid: str) -> UsageSnapshot:
        """Return the full cumulative breakdown for ``uid``."""
        if self._backend == "memory":
            with _MEMORY_LOCK:
                rec = _MEMORY.get(uid)
                if rec is None:
                    return UsageSnapshot(uid, 0, 0, 0, 0)
                return UsageSnapshot(
                    uid,
                    rec.total_tokens,
                    rec.input_tokens,
                    rec.output_tokens,
                    rec.thinking_tokens,
                )
        # Firestore: fail closed on a hard read error (security cap). A missing
        # document is a legitimate "new user" → zero, not an error.
        try:
            snap = self._doc_ref(uid).get()
        except Exception as exc:
            logger.error(  # noqa: TRY400 — structured fail-closed, not a stack dump
                "atelier.usage.read_failed",
                extra={"uid": uid, "error": type(exc).__name__},
            )
            raise GovernorTokenCapExceeded(
                uid=uid,
                used_tokens=self._token_cap,
                cap_tokens=self._token_cap,
                which_cap="persistence_unavailable_fail_closed",
            ) from exc
        if not snap.exists:
            return UsageSnapshot(uid, 0, 0, 0, 0)
        data = snap.to_dict() or {}
        return UsageSnapshot(
            uid,
            int(data.get("total_tokens", 0) or 0),
            int(data.get("input_tokens", 0) or 0),
            int(data.get("output_tokens", 0) or 0),
            int(data.get("thinking_tokens", 0) or 0),
        )

    def add(
        self,
        uid: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        thinking_tokens: int = 0,
    ) -> int:
        """Atomically add a token delta to ``uid``'s counter; return the new total.

        Negative deltas are rejected (a counter only grows) — defends against a
        bug or tampered delta silently lowering usage below the cap.
        """
        if input_tokens < 0 or output_tokens < 0 or thinking_tokens < 0:
            raise ValueError("token deltas must be non-negative")
        delta = input_tokens + output_tokens + thinking_tokens

        if self._backend == "memory":
            with _MEMORY_LOCK:
                rec = _MEMORY.setdefault(uid, _MemoryRecord())
                rec.input_tokens += input_tokens
                rec.output_tokens += output_tokens
                rec.thinking_tokens += thinking_tokens
                rec.total_tokens += delta
                return rec.total_tokens

        from google.cloud import firestore as gfs  # noqa: PLC0415

        try:
            self._doc_ref(uid).set(
                {
                    "total_tokens": gfs.Increment(delta),
                    "input_tokens": gfs.Increment(input_tokens),
                    "output_tokens": gfs.Increment(output_tokens),
                    "thinking_tokens": gfs.Increment(thinking_tokens),
                    "updated_at": gfs.SERVER_TIMESTAMP,
                },
                merge=True,
            )
        except Exception as exc:
            logger.error(  # noqa: TRY400
                "atelier.usage.write_failed",
                extra={"uid": uid, "delta": delta, "error": type(exc).__name__},
            )
            raise GovernorTokenCapExceeded(
                uid=uid,
                used_tokens=self._token_cap,
                cap_tokens=self._token_cap,
                which_cap="persistence_unavailable_fail_closed",
            ) from exc
        return self.get_total(uid)

    def check_rate_limit(self, uid: str) -> None:
        """Raise :class:`RateLimitExceededError` if ``uid`` is burning too fast.

        Sliding-window over request timestamps. In-process only (single Cloud
        Run instance); AT-097 makes it global + adds the circuit-breaker.
        """
        now = self._clock()
        cutoff = now - self._rl_window
        with _MEMORY_LOCK:
            rec = _MEMORY.setdefault(uid, _MemoryRecord())
            rec.request_times = [t for t in rec.request_times if t >= cutoff]
            if len(rec.request_times) >= self._rl_max:
                raise GovernorRateLimitExceeded(
                    uid=uid,
                    max_requests=self._rl_max,
                    window_seconds=self._rl_window,
                )
            rec.request_times.append(now)

    def reset(self, uid: str | None = None) -> None:
        """Clear usage (test helper; memory backend only)."""
        if self._backend != "memory":
            raise RuntimeError("reset() is only supported on the in-memory backend")
        with _MEMORY_LOCK:
            if uid is None:
                _MEMORY.clear()
            else:
                _MEMORY.pop(uid, None)


_STORE_SINGLETON: UsageCounterStore | None = None
_SINGLETON_LOCK = threading.Lock()


def get_usage_store() -> UsageCounterStore:
    """Return the process-wide usage store singleton (backend auto-selected)."""
    global _STORE_SINGLETON  # noqa: PLW0603
    if _STORE_SINGLETON is None:
        with _SINGLETON_LOCK:
            if _STORE_SINGLETON is None:
                _STORE_SINGLETON = UsageCounterStore()
    return _STORE_SINGLETON


def reset_usage_store_singleton() -> None:
    """Drop the cached singleton (test helper — re-reads env on next access)."""
    global _STORE_SINGLETON  # noqa: PLW0603
    with _SINGLETON_LOCK:
        _STORE_SINGLETON = None
