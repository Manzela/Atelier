"""AT-026 Stop registry: TTL eviction prevents leaked / stale Stop flags.

The convergence loop clears a Stop only on the honoring path. A Stop armed for a
run that never reaches (or never finishes) the loop — a failed N1/N2, a raise
before the loop, or a wrong session id — would otherwise live forever in the
process-local registry and could re-halt a much-later resume that reuses the id.
These tests pin the TTL-eviction behaviour that bounds the registry and lets a
stale flag self-expire.
"""

from collections.abc import Iterator

import pytest
from atelier.orchestrator import stop_controller


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    """Each test starts and ends with an empty registry (module-level state)."""
    stop_controller._STOP_REQUESTED.clear()
    yield
    stop_controller._STOP_REQUESTED.clear()


@pytest.mark.unit
def test_stop_within_ttl_is_observed() -> None:
    """A freshly-armed Stop is observable (the honoring path must still fire)."""
    stop_controller.request_stop("session-fresh")
    assert stop_controller.is_stop_requested("session-fresh") is True


@pytest.mark.unit
def test_expired_stop_is_evicted_and_not_observed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Stop older than the TTL is treated as absent and evicted on read.

    Simulates the leak scenario: a Stop is armed, the run never honors it, and
    time advances past the TTL. A later resume on the SAME id must NOT be halted.
    """
    clock = {"now": 1000.0}
    monkeypatch.setattr(stop_controller.time, "monotonic", lambda: clock["now"])

    stop_controller.request_stop("session-leaked")
    assert "session-leaked" in stop_controller._STOP_REQUESTED

    # Advance the clock past the TTL: the next read evicts the stale entry.
    clock["now"] += stop_controller._STOP_TTL_SECONDS + 1.0
    assert stop_controller.is_stop_requested("session-leaked") is False
    assert "session-leaked" not in stop_controller._STOP_REQUESTED


@pytest.mark.unit
def test_arming_a_new_stop_evicts_unrelated_expired_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """request_stop sweeps expired entries so the registry cannot grow unbounded."""
    clock = {"now": 5000.0}
    monkeypatch.setattr(stop_controller.time, "monotonic", lambda: clock["now"])

    stop_controller.request_stop("session-old")
    clock["now"] += stop_controller._STOP_TTL_SECONDS + 1.0
    # Arming a DIFFERENT session must evict the now-expired one.
    stop_controller.request_stop("session-new")

    assert "session-old" not in stop_controller._STOP_REQUESTED
    assert stop_controller.is_stop_requested("session-new") is True


@pytest.mark.unit
def test_clear_stop_removes_entry() -> None:
    """The honoring path's clear_stop bounds the registry (no residual key)."""
    stop_controller.request_stop("session-honored")
    stop_controller.clear_stop("session-honored")
    assert stop_controller.is_stop_requested("session-honored") is False
    assert "session-honored" not in stop_controller._STOP_REQUESTED
