"""Hierarchical Memory — typed Protocol surface (ADR 0029).

Three tiers, three backends, one Protocol. The orchestrator never knows
which backend it's hitting; the implementation chooses by `MemoryTier`.

Episodic: BigQuery `atelier_trajectories.session_events` (TTL 30 days).
Semantic: Vertex AI Memory Bank, scope = (tenant_id, project_id).
Procedural: Vertex AI Memory Bank, scope = ("global", "atelier-procedural").

All reads enforce the active MemoryKey via current_key(); IAM Conditions
on aiplatform.googleapis.com/memoryScope (CEL ACL-on-read) provide a second
layer of defense at the Google Cloud authorization layer.

numpy is TYPE_CHECKING-gated by design (not as a workaround). This is the
Protocol surface — it defines the type contract that backends implement. The
annotation `embedding: NDArray[np.float32] | None` carries meaning for static
analysis and documentation; the type is not enforced at runtime. Ruff TC002
enforces this pattern: third-party imports used only for type annotations
belong in the TYPE_CHECKING block. Concrete backends (BigQuery episodic,
Vertex Memory Bank semantic/procedural) import numpy directly in their own
modules when they construct MemoryEvent instances at runtime. numpy 2.4.6
is in requirements.lock since the numpy lockfile add.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Final, Protocol

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


class MemoryTier(StrEnum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


@dataclass(frozen=True, slots=True)
class MemoryEvent:
    """A single episodic event — written once, may be queried during the session,
    consolidated into semantic memory on session end.
    """

    event_id: str
    occurred_at: datetime
    node_name: str
    payload: dict[str, str | int | float | bool]
    embedding: NDArray[np.float32] | None


@dataclass(frozen=True, slots=True)
class MemoryQueryResult:
    """Returned from semantic/procedural queries — passages with provenance."""

    passage: str
    similarity: float
    tier: MemoryTier
    source_event_ids: tuple[str, ...]
    written_at: datetime


DEFAULT_TTL: Final[dict[MemoryTier, timedelta]] = {
    MemoryTier.EPISODIC: timedelta(days=30),
    MemoryTier.SEMANTIC: timedelta(days=365 * 2),
    MemoryTier.PROCEDURAL: timedelta(days=365 * 5),
}


class HierarchicalMemory(Protocol):
    """All three tiers behind one interface. Implementations select backend by tier."""

    async def write_episodic(self, event: MemoryEvent) -> None:
        """Append to BigQuery `atelier_trajectories.session_events`.

        Scoped by current_key().session_id. Fail-loud on LookupError
        (no key bound) per the failure trichotomy — no memory write is safe
        without the active MemoryKey.
        """
        ...

    async def query_semantic(
        self,
        *,
        query_text: str,
        top_k: int = 5,
        min_similarity: float = 0.7,
    ) -> tuple[MemoryQueryResult, ...]:
        """Vector search against Vertex Memory Bank.

        Scope filter pinned to (current_key().tenant_id, current_key().project_id).
        IAM Conditions also enforce this at the Google Cloud authorization layer
        — defense in depth, never single-rely on the in-process check.
        """
        ...

    async def lookup_procedural(
        self,
        *,
        query_text: str,
        top_k: int = 3,
        min_similarity: float = 0.8,
    ) -> tuple[MemoryQueryResult, ...]:
        """Vector search against the GLOBAL procedural namespace.

        Caller has already exhausted semantic; procedural is the fallback
        distilled knowledge from the DPO flywheel. NEVER bleeds tenant data
        because the procedural namespace is populated only from DPO-flywheel
        outputs, which were AND-gated for non-tenant-specific patterns (§21).
        """
        ...

    async def consolidate_session(self) -> None:
        """End-of-session consolidation: episodic → semantic.

        Read all episodic events from the current session, extract patterns
        worth keeping (Mem0 ADD-only single-pass extraction per Mem0
        April 2026), embed them, and write to semantic memory.
        """
        ...
