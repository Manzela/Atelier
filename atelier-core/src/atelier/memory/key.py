"""Multi-tenant memory key — bound via contextvars.ContextVar (ADR 0029).

Set at request-entry middleware (Cloud Run); read by every memory operation.
NEVER pass tenant_id / project_id as a function argument — that's how
cross-tenant leaks happen. Always read from the ContextVar.

PEP 567 guarantees propagation across `await`, `asyncio.TaskGroup` children,
and `asyncio.to_thread`. Does NOT propagate across process boundaries — OK
because Cloud Run runs `concurrency=1` per request for the orchestrator path.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MemoryKey:
    """The full key used for every memory read/write.

    Attributes:
        tenant_id: Stable across the tenant's lifetime; isolates from other tenants.
        project_id: A tenant's distinct design project (e.g. "redesign-2026-Q3");
            isolates across projects within a tenant.
        session_id: Per-conversation; episodic memory is cleared on session end.
    """

    tenant_id: str
    project_id: str
    session_id: str


CURRENT_MEMORY_KEY: contextvars.ContextVar[MemoryKey] = contextvars.ContextVar("atelier_memory_key")


def current_key() -> MemoryKey:
    """Resolve the active memory key.

    Raises:
        LookupError: No middleware bound the key. Fail-loud per the failure
            trichotomy — no memory operation is safe without the key.
    """
    return CURRENT_MEMORY_KEY.get()
