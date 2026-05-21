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

import pytest
from atelier.memory.key import CURRENT_MEMORY_KEY, MemoryKey, current_key


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
