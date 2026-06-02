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
guard). The fleet-wide token circuit-breaker that bounds aggregate burn across
all users — the third orthogonal limit of PRD §13.2 — is
:meth:`UsageCounterStore.check_circuit_breaker` (AT-097).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from atelier.orchestrator.governor import (
    GovernorCircuitBreakerOpen,
    GovernorRateLimitExceeded,
    GovernorUsageUnavailable,
)

logger = logging.getLogger(__name__)

#: The single fixed V1 cap. Operator-open thresholds (global circuit-breaker,
#: request-rate limit) live in AT-097; only this per-user lifetime cap is fixed.
TOKEN_CAP_DEFAULT: Final[int] = 5_000_000

#: Firestore document path for a user's lifetime counter (AT-084 owner-only rules).
_USAGE_COLLECTION: Final[str] = "usage"
_USAGE_DOC: Final[str] = "lifetime"
_USERS_COLLECTION: Final[str] = "users"

#: Per-window request-rate limit defaults (operator-open, §22 D-cap-numbers).
#: Env-overridable so the operator can tune without a code change.
_RATE_LIMIT_MAX_REQUESTS: Final[int] = int(os.getenv("ATELIER_RATE_LIMIT_MAX_REQUESTS", "30"))
_RATE_LIMIT_WINDOW_SECONDS: Final[float] = float(
    os.getenv("ATELIER_RATE_LIMIT_WINDOW_SECONDS", "60")
)

#: AT-097 — the global (per-total) token circuit-breaker. The third orthogonal
#: limit (PRD §13.2): trips when aggregate token consumption across ALL users in
#: a rolling window crosses the operator-set budget, pausing new work for a
#: cooldown so a coordinated multi-account burst cannot drain the shared paid key
#: in seconds. Thresholds are operator-open (§22 D-cap-numbers — only the
#: per-user 5M cap is fixed); env-overridable. The default budget is a generous
#: fleet-protection ceiling (10x the per-user lifetime cap **per minute**): it
#: never trips on a normal single-user demo but caps a runaway / sybil burst.
#: Set the budget to 0 (or negative) to DISABLE the breaker. NOTE: this is an
#: in-process breaker (one Cloud Run instance); the distributed fleet-edge limit
#: is Cloud Armor at the ALB (PRD §22) — see check_circuit_breaker for why both
#: layers exist.
_GLOBAL_TOKEN_BUDGET_PER_WINDOW: Final[int] = int(
    os.getenv("ATELIER_GLOBAL_TOKEN_BUDGET_PER_WINDOW", str(50_000_000))
)
_GLOBAL_WINDOW_SECONDS: Final[float] = float(os.getenv("ATELIER_GLOBAL_WINDOW_SECONDS", "60"))
_CIRCUIT_BREAKER_COOLDOWN_SECONDS: Final[float] = float(
    os.getenv("ATELIER_CIRCUIT_BREAKER_COOLDOWN_SECONDS", "60")
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


@dataclass
class _GlobalRecord:
    """Process-wide aggregate token window for the AT-097 circuit-breaker.

    ``token_events`` is a sliding window of ``(timestamp, tokens)`` across ALL
    users; ``window_token_sum`` is the running sum (kept in lock-step with the
    deque so the check is O(1) amortized). ``breaker_open_until`` is the
    monotonic deadline before which the breaker is OPEN (fast-reject) after a
    trip — the cooldown that stops the breaker from flapping.
    """

    token_events: deque[tuple[float, int]] = field(default_factory=deque)
    window_token_sum: int = 0
    breaker_open_until: float = 0.0


# The global breaker is shared across every UsageCounterStore in the process
# (the fleet aggregate is a process-level concept, not a per-store one), mirroring
# how ``_MEMORY`` is shared. Guarded by its own lock to avoid contending with the
# per-uid counter lock.
_GLOBAL = _GlobalRecord()
_GLOBAL_LOCK = threading.Lock()


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
        global_token_budget_per_window: int = _GLOBAL_TOKEN_BUDGET_PER_WINDOW,
        global_window_seconds: float = _GLOBAL_WINDOW_SECONDS,
        circuit_breaker_cooldown_seconds: float = _CIRCUIT_BREAKER_COOLDOWN_SECONDS,
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
        # AT-097 global circuit-breaker thresholds (operator-open). A budget <= 0
        # disables the breaker entirely (the window is then never recorded either).
        self._global_budget = global_token_budget_per_window
        self._global_window = global_window_seconds
        self._breaker_cooldown = circuit_breaker_cooldown_seconds
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
        # Firestore: fail CLOSED on a hard read error OR a corrupt (non-coercible)
        # counter value — but as GovernorUsageUnavailable (a transient/retryable
        # 503 deny), NEVER as a cap breach. A missing document is a legitimate
        # "new user" -> zero, not an error.
        try:
            snap = self._doc_ref(uid).get()
        except Exception as exc:
            logger.error(  # noqa: TRY400 — structured fail-closed, not a stack dump
                "atelier.usage.read_failed",
                extra={"uid": uid, "error": type(exc).__name__},
            )
            raise GovernorUsageUnavailable(uid=uid, reason="read_failed") from exc
        if not snap.exists:
            return UsageSnapshot(uid, 0, 0, 0, 0)
        data = snap.to_dict() or {}
        # Guard the parse: a non-int stored value (a server bug, a console edit, a
        # pre-rules migrated doc) is a data-integrity fault -> fail CLOSED, never a
        # raw 500 and never a silent coerce-to-zero (which would under-count).
        try:
            return UsageSnapshot(
                uid,
                int(data.get("total_tokens", 0) or 0),
                int(data.get("input_tokens", 0) or 0),
                int(data.get("output_tokens", 0) or 0),
                int(data.get("thinking_tokens", 0) or 0),
            )
        except (ValueError, TypeError) as exc:
            logger.error(  # noqa: TRY400
                "atelier.usage.corrupt_counter",
                extra={"uid": uid, "error": type(exc).__name__},
            )
            raise GovernorUsageUnavailable(uid=uid, reason="corrupt_counter") from exc

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
                new_total = rec.total_tokens
            # AT-097: feed the fleet-wide breaker window AFTER the per-uid commit
            # (outside _MEMORY_LOCK — _record_global_tokens takes _GLOBAL_LOCK only,
            # so the two locks never nest and cannot deadlock).
            self._record_global_tokens(delta)
            return new_total

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
            raise GovernorUsageUnavailable(uid=uid, reason="write_failed") from exc
        # AT-097: record toward the fleet-wide breaker only after the charge
        # COMMITTED above (a failed write raised; we never record phantom tokens).
        self._record_global_tokens(delta)
        # The increment COMMITTED above (the charge is persisted). A post-write
        # read is only to return the fresh total; if it fails we must NOT
        # manufacture a deny for an already-successful charge — return a
        # best-effort value and log degraded. (The runner ignores this return and
        # reads the authoritative cumulative from governor state.)
        try:
            return self.get_total(uid)
        except GovernorUsageUnavailable:
            logger.warning(
                "atelier.usage.postwrite_read_degraded",
                extra={"uid": uid, "delta": delta},
            )
            return delta

    def check_rate_limit(self, uid: str) -> None:
        """Raise :class:`GovernorRateLimitExceeded` if ``uid`` is burning too fast.

        Per-user sliding window over request timestamps — the per-window limit of
        the three orthogonal limits (PRD §13.2). In-process (single Cloud Run
        instance); the distributed fleet edge is Cloud Armor at the ALB (PRD §22).
        This app-layer check is the authoritative pre-flight gate exercised by the
        hermetic oracle and runs before any Vertex spend. The fleet-wide breaker
        is :meth:`check_circuit_breaker`.
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

    # -- AT-097 global (per-total) circuit-breaker ---------------------------

    def _prune_global_window(self, now: float) -> None:
        """Drop token events older than the window; keep the running sum exact.

        Caller MUST hold ``_GLOBAL_LOCK``.
        """
        cutoff = now - self._global_window
        events = _GLOBAL.token_events
        while events and events[0][0] < cutoff:
            _, tokens = events.popleft()
            _GLOBAL.window_token_sum -= tokens
        # defensive: never let arithmetic drift push the running sum negative
        _GLOBAL.window_token_sum = max(_GLOBAL.window_token_sum, 0)

    def _record_global_tokens(self, delta: int) -> None:
        """Add ``delta`` tokens to the fleet-wide breaker window (no-op if disabled).

        Fed by every :meth:`add` call — i.e. the same N3a + N3d spend that feeds
        the per-user lifetime cap. The fixed-cost N1/N2 planning stages record via
        the governor's ``record_stage_call`` accumulator and never reach ``add``,
        so (consistent with the per-user cap) they do not count toward the breaker.
        This is a bounded under-count: N3a/N3d dominate spend, and the breaker is an
        operator-open fleet guard backed by Cloud Armor at the edge, not exact
        fleet-spend accounting.
        """
        if self._global_budget <= 0 or delta <= 0:
            return
        now = self._clock()
        with _GLOBAL_LOCK:
            _GLOBAL.token_events.append((now, delta))
            _GLOBAL.window_token_sum += delta
            self._prune_global_window(now)

    def check_circuit_breaker(self) -> None:
        """Raise :class:`GovernorCircuitBreakerOpen` if the fleet breaker is open.

        The third orthogonal limit (PRD §13.2): per-total/global. Called
        pre-flight, before any Vertex spend, alongside :meth:`check_rate_limit`
        and the per-user cap. It raises in two cases:

        1. **Cooldown active** — the breaker tripped recently and its cooldown has
           not elapsed → fast-reject (the breaker stays OPEN so it can't flap).
        2. **Budget reached** — aggregate token consumption across ALL users in
           the rolling window has reached the operator-set budget → TRIP (arm the
           cooldown) and reject.

        In-process (one Cloud Run instance); the distributed fleet edge is Cloud
        Armor at the ALB (PRD §22 — "Cloud Armor (rate-limit)"). This app-layer
        breaker is defense-in-depth: it works in the hermetic lane and on a single
        instance, and is never weaker than the edge. Disabled when the operator
        sets the budget to <= 0.
        """
        if self._global_budget <= 0:
            return
        now = self._clock()
        with _GLOBAL_LOCK:
            self._prune_global_window(now)
            if now < _GLOBAL.breaker_open_until:
                raise GovernorCircuitBreakerOpen(
                    reason="global_token_budget",
                    retry_after_seconds=max(1, int(_GLOBAL.breaker_open_until - now)),
                    window_tokens=_GLOBAL.window_token_sum,
                    budget=self._global_budget,
                )
            if _GLOBAL.window_token_sum >= self._global_budget:
                _GLOBAL.breaker_open_until = now + self._breaker_cooldown
                logger.error(  # structured fleet-protection alert, not a stack dump
                    "atelier.usage.circuit_breaker_tripped",
                    extra={
                        "window_tokens": _GLOBAL.window_token_sum,
                        "budget": self._global_budget,
                        "cooldown_s": self._breaker_cooldown,
                    },
                )
                raise GovernorCircuitBreakerOpen(
                    reason="global_token_budget",
                    retry_after_seconds=max(1, int(self._breaker_cooldown)),
                    window_tokens=_GLOBAL.window_token_sum,
                    budget=self._global_budget,
                )

    def reset(self, uid: str | None = None) -> None:
        """Clear usage (test helper; memory backend only).

        Clearing all users (``uid is None``) also resets the process-wide global
        breaker window so each test starts from a clean fleet aggregate.
        """
        if self._backend != "memory":
            raise RuntimeError("reset() is only supported on the in-memory backend")
        with _MEMORY_LOCK:
            if uid is None:
                _MEMORY.clear()
            else:
                _MEMORY.pop(uid, None)
        if uid is None:
            reset_global_breaker()


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


def reset_global_breaker() -> None:
    """Clear the process-wide global circuit-breaker window + cooldown.

    The breaker state in :data:`_GLOBAL` is module-level (shared across every
    store in the process — the fleet aggregate is process-scoped). Tests that
    TRIP the breaker must call this in teardown so a tripped ``breaker_open_until``
    never leaks into an unrelated test (which would see spurious 503s). Also the
    natural reset point for a process-level ops intervention.
    """
    with _GLOBAL_LOCK:
        _GLOBAL.token_events.clear()
        _GLOBAL.window_token_sum = 0
        _GLOBAL.breaker_open_until = 0.0
