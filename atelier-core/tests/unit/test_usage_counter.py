"""AT-095 — UsageCounterStore oracle (per-user lifetime token counter).

Hermetic (in-memory backend); no Firestore / network. Covers the store contract
the cap enforcement rides on: cumulative accumulation, atomic-style growth,
the input/output/thinking breakdown (G15), the per-window rate limit (acceptance
(f)), backend selection, and the process-wide singleton.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from atelier.durability.usage_counter import (
    TOKEN_CAP_DEFAULT,
    UsageCounterStore,
    get_usage_store,
    reset_global_breaker,
    reset_usage_store_singleton,
)
from atelier.orchestrator.governor import (
    GovernorCircuitBreakerOpen,
    GovernorRateLimitExceeded,
    GovernorUsageUnavailable,
)


@pytest.fixture(autouse=True)
def _reset_global_breaker_after() -> Iterator[None]:
    # The global circuit-breaker lives in process-wide module state; a test that
    # trips it must not leak a tripped cooldown into the next test (which would
    # see spurious 503s). Reset after every test in this module.
    yield
    reset_global_breaker()


@pytest.fixture
def store() -> UsageCounterStore:
    s = UsageCounterStore(backend="memory")
    s.reset()  # clear the process-wide _MEMORY so each test starts clean
    return s


def test_new_user_starts_at_zero(store: UsageCounterStore) -> None:
    assert store.get_total("new-uid") == 0
    snap = store.snapshot("new-uid")
    assert (snap.total_tokens, snap.input_tokens, snap.output_tokens, snap.thinking_tokens) == (
        0,
        0,
        0,
        0,
    )


def test_add_accumulates_and_returns_new_total(store: UsageCounterStore) -> None:
    assert store.add("u", input_tokens=10, output_tokens=20, thinking_tokens=5) == 35
    # Cumulative across calls (this is the cross-run durability primitive).
    assert store.add("u", input_tokens=1, output_tokens=2, thinking_tokens=3) == 41
    snap = store.snapshot("u")
    assert snap.total_tokens == 41
    assert snap.input_tokens == 11
    assert snap.output_tokens == 22
    assert snap.thinking_tokens == 8  # AT-095 (g): thinking tokens counted


def test_counters_are_isolated_per_uid(store: UsageCounterStore) -> None:
    store.add("a", input_tokens=100)
    store.add("b", input_tokens=7)
    assert store.get_total("a") == 100
    assert store.get_total("b") == 7


def test_add_rejects_negative_delta(store: UsageCounterStore) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        store.add("u", input_tokens=-5)


def test_default_cap_is_five_million(store: UsageCounterStore) -> None:
    assert store.token_cap == TOKEN_CAP_DEFAULT == 5_000_000


def test_rate_limit_blocks_rapid_burn(store: UsageCounterStore) -> None:
    # AT-095 acceptance (f): a per-window request-rate limit stops a rapid burn.
    clock_time = [1000.0]
    s = UsageCounterStore(
        backend="memory",
        rate_limit_max_requests=2,
        rate_limit_window_seconds=60.0,
        clock=lambda: clock_time[0],
    )
    s.reset()
    s.check_rate_limit("u")  # 1st — ok
    s.check_rate_limit("u")  # 2nd — ok
    with pytest.raises(GovernorRateLimitExceeded):
        s.check_rate_limit("u")  # 3rd within the window — blocked


def test_rate_limit_window_slides(store: UsageCounterStore) -> None:
    clock_time = [1000.0]
    s = UsageCounterStore(
        backend="memory",
        rate_limit_max_requests=2,
        rate_limit_window_seconds=60.0,
        clock=lambda: clock_time[0],
    )
    s.reset()
    s.check_rate_limit("u")
    s.check_rate_limit("u")
    clock_time[0] = 1000.0 + 61.0  # advance past the window — old requests age out
    s.check_rate_limit("u")  # must NOT raise


def test_reset_clears_usage(store: UsageCounterStore) -> None:
    store.add("u", input_tokens=500)
    store.reset("u")
    assert store.get_total("u") == 0


def test_backend_selection_respects_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from atelier.durability import usage_counter as uc

    monkeypatch.setenv("ATELIER_USAGE_BACKEND", "memory")
    assert uc._use_memory_backend() is True
    monkeypatch.setenv("ATELIER_USAGE_BACKEND", "firestore")
    assert uc._use_memory_backend() is False
    # Unset → falls back to FIREBASE_DISABLE_AUTH / ATELIER_ENV heuristic.
    monkeypatch.delenv("ATELIER_USAGE_BACKEND", raising=False)
    monkeypatch.setenv("FIREBASE_DISABLE_AUTH", "true")
    assert uc._use_memory_backend() is True


def test_singleton_is_stable_and_resettable() -> None:
    reset_usage_store_singleton()
    s1 = get_usage_store()
    s2 = get_usage_store()
    assert s1 is s2
    reset_usage_store_singleton()
    s3 = get_usage_store()
    assert s3 is not s1


# --- Fail-closed on persistence failure / corruption (Firestore backend) ------
# A read/write error or a corrupt counter value must fail CLOSED as a distinct,
# retryable GovernorUsageUnavailable (HTTP 503) — NOT a GovernorTokenCapExceeded
# (which would dishonestly tell the user they hit their cap), and NOT a raw 500.


class _RaisingDoc:
    def get(self) -> object:
        raise RuntimeError("firestore unavailable")

    def set(self, *_a: object, **_k: object) -> None:
        raise RuntimeError("firestore unavailable")


class _WriteOkReadFailsDoc:
    """set() commits, but the post-write get() fails — the add() best-effort path."""

    def set(self, *_a: object, **_k: object) -> None:
        return None

    def get(self) -> object:
        raise RuntimeError("firestore read blip after a committed write")


class _CorruptDoc:
    def get(self) -> object:
        class _Snap:
            exists = True

            @staticmethod
            def to_dict() -> dict[str, object]:
                return {"total_tokens": "not-a-number"}  # poisoned / non-coercible

        return _Snap()


def _firestore_store_with(doc: object) -> UsageCounterStore:
    s = UsageCounterStore(backend="firestore")
    s._doc_ref = lambda _uid: doc  # type: ignore[method-assign]  # inject a fake doc ref
    return s


def test_read_failure_fails_closed_as_usage_unavailable() -> None:
    s = _firestore_store_with(_RaisingDoc())
    with pytest.raises(GovernorUsageUnavailable) as exc:
        s.get_total("u")
    assert exc.value.reason == "read_failed"


def test_write_failure_fails_closed_as_usage_unavailable() -> None:
    s = _firestore_store_with(_RaisingDoc())
    with pytest.raises(GovernorUsageUnavailable) as exc:
        s.add("u", input_tokens=10)
    assert exc.value.reason == "write_failed"


def test_corrupt_counter_value_fails_closed_not_500_or_zero() -> None:
    s = _firestore_store_with(_CorruptDoc())
    with pytest.raises(GovernorUsageUnavailable) as exc:
        s.snapshot("u")
    # Fail CLOSED as corruption — never a silent coerce-to-zero (which would
    # under-count and weaken the cap) and never a raw ValueError/500.
    assert exc.value.reason == "corrupt_counter"


def test_postwrite_read_failure_does_not_deny_a_committed_charge() -> None:
    # The increment COMMITTED; a post-write read blip must NOT raise (which would
    # manufacture a deny for an already-successful charge). Returns best-effort.
    s = _firestore_store_with(_WriteOkReadFailsDoc())
    assert s.add("u", input_tokens=7) == 7  # best-effort = the delta, no raise


# --- AT-097 global (per-total) circuit-breaker --------------------------------
# The third orthogonal limit (PRD §13.2): a fleet-wide token budget per rolling
# window that trips a circuit-breaker, so a coordinated multi-account burst cannot
# drain the shared paid key in seconds. Thresholds are operator-open (§22). A
# fully-injected clock makes every assertion deterministic (no real time).


def _breaker_store(
    *,
    budget: int = 1000,
    window: float = 60.0,
    cooldown: float = 60.0,
    clock_time: list[float],
) -> UsageCounterStore:
    s = UsageCounterStore(
        backend="memory",
        global_token_budget_per_window=budget,
        global_window_seconds=window,
        circuit_breaker_cooldown_seconds=cooldown,
        clock=lambda: clock_time[0],
    )
    s.reset()  # clears both _MEMORY and the process-wide _GLOBAL breaker window
    return s


def test_circuit_breaker_trips_at_global_budget() -> None:
    t = [1000.0]
    s = _breaker_store(budget=1000, clock_time=t)
    s.add("u", input_tokens=600, output_tokens=400)  # window aggregate = 1000
    with pytest.raises(GovernorCircuitBreakerOpen) as exc:
        s.check_circuit_breaker()
    assert exc.value.budget == 1000
    assert exc.value.window_tokens >= 1000
    assert exc.value.retry_after_seconds >= 1


def test_circuit_breaker_aggregates_across_users_not_per_user() -> None:
    # The breaker is PER-TOTAL: two different users, each individually well under
    # both the global budget AND their own 5M lifetime cap, still trip the breaker
    # in aggregate. This is what makes it a *fleet* protection vs the per-user cap.
    t = [1000.0]
    s = _breaker_store(budget=1000, clock_time=t)
    s.add("alice", input_tokens=600)
    s.add("bob", input_tokens=400)
    with pytest.raises(GovernorCircuitBreakerOpen):
        s.check_circuit_breaker()
    # Neither user is individually over anything — only the aggregate tripped.
    assert s.get_total("alice") == 600
    assert s.get_total("bob") == 400


def test_circuit_breaker_under_budget_passes() -> None:
    t = [1000.0]
    s = _breaker_store(budget=1000, clock_time=t)
    s.add("u", input_tokens=999)
    s.check_circuit_breaker()  # 999 < 1000 → must NOT raise


def test_circuit_breaker_cooldown_then_recovers() -> None:
    t = [1000.0]
    s = _breaker_store(budget=1000, window=60.0, cooldown=60.0, clock_time=t)
    s.add("u", input_tokens=1000)
    with pytest.raises(GovernorCircuitBreakerOpen):
        s.check_circuit_breaker()  # trips at t=1000, open until t=1060
    # During the cooldown the breaker stays OPEN (fast-reject) even though the
    # caller did nothing new — a breaker that re-closes immediately is no breaker.
    t[0] = 1030.0
    with pytest.raises(GovernorCircuitBreakerOpen):
        s.check_circuit_breaker()
    # After the cooldown AND the triggering tokens age out of the window → recover.
    t[0] = 1061.0
    s.check_circuit_breaker()  # must NOT raise


def test_circuit_breaker_window_slides() -> None:
    # Tokens older than the window age out, so a steady trickle under budget never
    # trips — only a genuine burst within one window does.
    t = [1000.0]
    s = _breaker_store(budget=1000, window=60.0, cooldown=60.0, clock_time=t)
    s.add("u", input_tokens=600)  # t=1000
    t[0] = 1061.0  # advance past the window; the first 600 must age out
    s.add("u", input_tokens=600)  # t=1061 → window holds only this 600
    s.check_circuit_breaker()  # 600 < 1000 → must NOT raise (proves pruning)


def test_circuit_breaker_disabled_when_budget_non_positive() -> None:
    # Operator can DISABLE the breaker with budget <= 0 (§22 operator-open). When
    # disabled, even a huge burst neither records to the window nor trips.
    t = [1000.0]
    s = _breaker_store(budget=0, clock_time=t)
    s.add("u", input_tokens=10_000_000)
    s.check_circuit_breaker()  # disabled → never raises
