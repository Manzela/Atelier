"""Unit tests for MemoryKey + CURRENT_MEMORY_KEY ContextVar (§20.2).

Repo convention is `@pytest.mark.anyio` (anyio 4.13 ships its own pytest plugin
inside the core package; pytest-asyncio is not in requirements.lock). The
asyncio backend is the default, so asyncio.TaskGroup / asyncio.to_thread /
asyncio.get_running_loop() continue to work unchanged — only the marker
decorator differs from a vanilla pytest-asyncio setup.
"""

from __future__ import annotations

import asyncio
import contextvars
from datetime import UTC, datetime

import numpy as np
import pytest
from atelier.memory.key import CURRENT_MEMORY_KEY, MemoryKey, current_key
from atelier.memory.protocol import HierarchicalMemory, MemoryEvent


@pytest.mark.unit
def test_memory_key_is_frozen() -> None:
    key = MemoryKey(tenant_id="t1", project_id="p1", session_id="s1")
    with pytest.raises(AttributeError):
        key.tenant_id = "mutated"  # type: ignore[misc]


@pytest.mark.unit
def test_memory_key_is_hashable() -> None:
    a = MemoryKey(tenant_id="t1", project_id="p1", session_id="s1")
    b = MemoryKey(tenant_id="t1", project_id="p1", session_id="s1")
    assert hash(a) == hash(b)
    assert {a, b} == {a}


@pytest.mark.unit
def test_current_key_raises_lookup_error_when_unbound() -> None:
    """A fresh contextvars.Context has no binding — current_key() must fail-loud.

    Run the probe inside a copied Context so any outer test-runner binding is
    excluded from the lookup. The contract per §20.2 is: unbound ⇒ LookupError,
    no swallow per <no_silent_error_suppression>.
    """

    def probe() -> object:
        try:
            return current_key()
        except LookupError as exc:
            return exc

    result = contextvars.copy_context().run(probe)
    if not isinstance(result, LookupError):
        pytest.fail(
            f"Expected LookupError when CURRENT_MEMORY_KEY unbound, got {result!r}. "
            "Outer test runner must not leave a binding."
        )


@pytest.mark.unit
def test_current_key_returns_bound_value() -> None:
    key = MemoryKey(tenant_id="t1", project_id="p1", session_id="s1")
    token = CURRENT_MEMORY_KEY.set(key)
    try:
        assert current_key() == key
    finally:
        CURRENT_MEMORY_KEY.reset(token)


@pytest.mark.unit
@pytest.mark.anyio
async def test_current_key_propagates_across_await() -> None:
    key = MemoryKey(tenant_id="t1", project_id="p1", session_id="s1")
    token = CURRENT_MEMORY_KEY.set(key)
    try:

        async def inner() -> MemoryKey:
            await asyncio.sleep(0)
            return current_key()

        assert await inner() == key
    finally:
        CURRENT_MEMORY_KEY.reset(token)


@pytest.mark.unit
@pytest.mark.anyio
async def test_current_key_propagates_into_task_group_children() -> None:
    """PEP 567: ContextVar values are captured at task-creation time and
    propagate into asyncio.TaskGroup children. The §20.2 isolation contract
    depends on this.
    """
    key = MemoryKey(tenant_id="t1", project_id="p1", session_id="s1")
    captured: list[MemoryKey] = []

    async def child() -> None:
        captured.append(current_key())

    token = CURRENT_MEMORY_KEY.set(key)
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(child())
            tg.create_task(child())
            tg.create_task(child())
    finally:
        CURRENT_MEMORY_KEY.reset(token)

    assert captured == [key, key, key]


@pytest.mark.unit
@pytest.mark.anyio
async def test_current_key_isolated_per_task_via_run_in_context() -> None:
    """Tenant A and Tenant B run in parallel without leaking, each launched in
    its own context copy. This is the per-request isolation pattern the FastAPI
    middleware will use.
    """
    key_a = MemoryKey(tenant_id="A", project_id="p1", session_id="s1")
    key_b = MemoryKey(tenant_id="B", project_id="p1", session_id="s1")

    captured: dict[str, MemoryKey] = {}

    async def tenant_workload(label: str) -> None:
        await asyncio.sleep(0.01)
        captured[label] = current_key()

    async def run_in_isolated_ctx(label: str, key: MemoryKey) -> None:
        ctx = contextvars.copy_context()

        async def bound() -> None:
            CURRENT_MEMORY_KEY.set(key)
            await tenant_workload(label)

        task = asyncio.get_running_loop().create_task(bound(), context=ctx)
        await task

    await asyncio.gather(
        run_in_isolated_ctx("A", key_a),
        run_in_isolated_ctx("B", key_b),
    )

    assert captured == {"A": key_a, "B": key_b}


@pytest.mark.unit
@pytest.mark.anyio
async def test_current_key_isolated_under_to_thread() -> None:
    """asyncio.to_thread propagates ContextVars per PEP 567 / asyncio docs.
    Required so any sync DB driver call still sees the right tenant.
    """
    key = MemoryKey(tenant_id="t1", project_id="p1", session_id="s1")
    token = CURRENT_MEMORY_KEY.set(key)
    try:

        def sync_probe() -> MemoryKey:
            return current_key()

        assert await asyncio.to_thread(sync_probe) == key
    finally:
        CURRENT_MEMORY_KEY.reset(token)


@pytest.mark.unit
def test_memory_key_equality_includes_all_three_fields() -> None:
    base = MemoryKey(tenant_id="t1", project_id="p1", session_id="s1")
    assert base != MemoryKey(tenant_id="t2", project_id="p1", session_id="s1")
    assert base != MemoryKey(tenant_id="t1", project_id="p2", session_id="s1")
    assert base != MemoryKey(tenant_id="t1", project_id="p1", session_id="s2")


@pytest.mark.unit
def test_memory_key_slots_no_dict() -> None:
    """slots=True means no __dict__ — saves memory and prevents typo'd attr assignment."""
    key = MemoryKey(tenant_id="t1", project_id="p1", session_id="s1")
    assert not hasattr(key, "__dict__")


@pytest.mark.unit
def test_hierarchical_memory_protocol_is_runtime_unchecked_but_structural() -> None:
    """typing.Protocol with no @runtime_checkable: structural check only at mypy
    time. This test documents that contract — runtime isinstance is intentionally
    not supported (forces all conformance checks into static analysis, where they
    catch incomplete implementations BEFORE deploy rather than at request time).
    """

    class Incomplete:
        async def write_episodic(self, event: object) -> None:
            return None

    # No runtime check — Incomplete passes isinstance only if @runtime_checkable.
    # We do NOT mark HierarchicalMemory @runtime_checkable; assert that here.
    with pytest.raises(TypeError):
        isinstance(Incomplete(), HierarchicalMemory)  # type: ignore[misc]


# ---- MemoryEvent runtime ndarray tests (unblocked by R7-01 numpy lockfile) --
# These tests were not possible at T2 time (numpy not in lockfile).
# Antigravity R7-01 (917b251) added numpy 2.4.6. The TYPE_CHECKING guard
# in memory/protocol.py is intentional (ruff TC002 design), but at test
# runtime numpy IS available, so tests can construct MemoryEvent with real
# ndarrays even though the Protocol annotation is TYPE_CHECKING-gated.


@pytest.mark.unit
def test_memory_event_can_be_constructed_with_embedding() -> None:
    """MemoryEvent accepts a real float32 ndarray as the embedding field.

    The embedding field is typed `NDArray[np.float32] | None` per spec §20 —
    None during writes from nodes that don't compute embeddings; non-None when
    the session-consolidation pipeline embeds the event for semantic search.
    """
    embedding = np.zeros(768, dtype=np.float32)
    event = MemoryEvent(
        event_id="evt-001",
        occurred_at=datetime(2026, 5, 24, tzinfo=UTC),
        node_name="brief_parse",
        payload={"token_count": 120, "confidence": 0.95},
        embedding=embedding,
    )
    assert event.embedding is not None
    assert event.embedding.shape == (768,)
    assert event.embedding.dtype == np.float32


@pytest.mark.unit
def test_memory_event_embedding_can_be_none() -> None:
    """MemoryEvent.embedding is Optional — None is valid pre-consolidation."""
    event = MemoryEvent(
        event_id="evt-002",
        occurred_at=datetime(2026, 5, 24, tzinfo=UTC),
        node_name="emit",
        payload={"status": "ok"},
        embedding=None,
    )
    assert event.embedding is None


@pytest.mark.unit
def test_memory_event_is_frozen() -> None:
    """MemoryEvent is a one-shot episodic record — reassignment must raise."""
    embedding = np.zeros(768, dtype=np.float32)
    event = MemoryEvent(
        event_id="evt-003",
        occurred_at=datetime(2026, 5, 24, tzinfo=UTC),
        node_name="judge_candidates",
        payload={"kappa": 0.82},
        embedding=embedding,
    )
    with pytest.raises(Exception):  # FrozenInstanceError is AttributeError subtype
        event.event_id = "mutated"  # type: ignore[misc]
