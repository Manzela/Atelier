"""AT-095 — UsageCounterStore oracle (per-user lifetime token counter).

Hermetic (in-memory backend); no Firestore / network. Covers the store contract
the cap enforcement rides on: cumulative accumulation, atomic-style growth,
the input/output/thinking breakdown (G15), the per-window rate limit (acceptance
(f)), backend selection, and the process-wide singleton.
"""

from __future__ import annotations

import pytest
from atelier.durability.usage_counter import (
    TOKEN_CAP_DEFAULT,
    UsageCounterStore,
    get_usage_store,
    reset_usage_store_singleton,
)
from atelier.orchestrator.governor import GovernorRateLimitExceeded


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
