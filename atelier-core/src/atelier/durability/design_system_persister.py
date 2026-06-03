"""Per-tenant design-system persister — AT-053 (persist at sign-off, load next run).

Writes a :class:`~atelier.models.design_system.DesignSystemRecord` at human
sign-off (AT-031) and loads it on the tenant's next run so the design system is
*auto-applied* with no re-specification, then *enforced* by the AT-012 gate.

Backend selection mirrors the AT-095 usage counter (single durability pattern in
this codebase):

* **file** (offline / dev / hermetic test lane) — a real JSON file per tenant
  under ``ATELIER_DESIGN_SYSTEM_DIR`` (default ``<repo>/.atelier/design_systems``
  or, when unset and no repo marker, the system temp dir). The file genuinely
  persists across two ``DesignSystemPersister`` instances *and* across process
  restarts, so the cross-run inheritance assertion holds with **zero** GCP
  credentials and **without** a Firestore emulator. This is the substrate that
  makes ``make verify`` exercise real persistence offline.
* **vertex** (production) — Firestore as the durable record store
  (``tenants/{tenant_id}/design_systems/{run_id}``) *plus* a write into the
  Vertex AI Memory Bank substrate (AT-080) via the injected
  :class:`~atelier.memory.backends.vertex_semantic.VertexSemanticMemoryBackend`
  so the system is queryable as a semantic prior. Firestore is authoritative for
  the exact-token reconstruction; Memory Bank is the AT-080 online substrate.

Failure trichotomy (PRD §):

* **Persist** failure → **fail-soft** at the call site (the run already
  succeeded; a memory-write failure is logged + acknowledged, never fatal). The
  persister returns the record id on success and raises only on a programming
  error the caller would want to see in dev.
* **Load** failure → **fail-soft** here: a missing/corrupt/unavailable system
  returns ``None`` (degrade) with a structured warning. It MUST NOT raise — a
  persistence outage must not break run #2's intake. Critically, an outage
  degrades the *auto-apply* (run #2 falls back to the brief's own tokens); it
  does NOT silently disable enforcement of a system that *did* load.

Symbols verified against google-adk==2.1.0 (AT-002 pin):
    google.cloud.firestore 2.27.0 (installed; same dependency the AT-095 counter
    uses). The Vertex Memory Bank online write goes through the existing
    ``VertexSemanticMemoryBackend.write_semantic`` Protocol method — no new ADK
    symbol is introduced here.

PRD Reference: §12 (AT-053), §20 (memory), §13.2 (durability pattern), AT-080.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from atelier.memory.scope import MemoryScopeKey
from atelier.models.design_system import DesignSystemRecord

if TYPE_CHECKING:
    from atelier.memory.backends.vertex_semantic import VertexSemanticMemoryBackend

logger = logging.getLogger(__name__)

#: The memory "phase" component of the scope key used for design-system writes.
_DESIGN_SYSTEM_PHASE = "design-system"

#: Firestore collection layout (production / vertex backend).
_TENANTS_COLLECTION = "tenants"
_DESIGN_SYSTEMS_COLLECTION = "design_systems"

#: Default GCP project for the Memory Bank scope key when none is configured.
_DEFAULT_PROJECT = "atelier-build-2026"

#: A serialization lock for the file backend so two threads writing the same
#: tenant cannot interleave a partial file (the write is atomic-rename, but the
#: lock keeps the "latest pointer" update coherent).
_FILE_LOCK = threading.Lock()


def _use_file_backend() -> bool:
    """True when the offline file backend should be used (dev / hermetic / tests)."""
    explicit = os.getenv("ATELIER_DESIGN_SYSTEM_BACKEND", "").strip().lower()
    if explicit == "file":
        return True
    if explicit == "vertex":
        return False
    # Mirror the usage-counter heuristic so a single env knob flips both.
    bypass = os.getenv("FIREBASE_DISABLE_AUTH", "").lower() in ("1", "true", "yes")
    is_dev = os.getenv("ATELIER_ENV", "development") == "development"
    backend = os.getenv("SESSION_BACKEND", "memory").strip().lower()
    return bypass or is_dev or backend != "vertex"


def _design_system_dir() -> Path:
    """Resolve the on-disk directory for the file backend (NOT created here).

    Resolution only — the directory is created lazily at write time so a read of
    a never-persisted tenant (and any pipeline that never persists) leaves no
    stray directory behind (test hermeticity).
    """
    configured = os.getenv("ATELIER_DESIGN_SYSTEM_DIR")
    if configured:
        return Path(configured)
    # Prefer a stable repo-local dir so dev runs share one store; fall back to a
    # per-user temp dir when there is no repo marker (e.g. a clean clone run from
    # elsewhere). Never silently scatter files in the CWD.
    repo_marker = Path.cwd() / "pyproject.toml"
    if repo_marker.exists():
        return Path.cwd() / ".atelier" / "design_systems"
    return Path(tempfile.gettempdir()) / "atelier_design_systems"


def _tenant_file(tenant_id: str) -> Path:
    """Return the per-tenant JSON file path (one current system per tenant)."""
    # Sanitize so a hostile tenant id cannot escape the directory. Tenant ids are
    # opaque partition keys; we only ever need a filesystem-safe 1:1 encoding.
    safe = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in tenant_id)
    if not safe:
        safe = "_empty_"
    return _design_system_dir() / f"{safe}.json"


def _project_id() -> str:
    """Resolve the GCP project for Memory Bank scope keys."""
    return os.getenv("GOOGLE_CLOUD_PROJECT") or _DEFAULT_PROJECT


class DesignSystemPersister:
    """Persists and loads the one current design system per tenant (AT-053).

    Construct cheaply per call site; the file backend keeps no in-instance state
    (the JSON file is the source of truth), so two instances see each other's
    writes — that is the cross-run durability the acceptance bar requires.

    Args:
        vertex_backend: Optional Vertex Memory Bank backend (AT-080). When the
            vertex backend is active and this is provided, a persisted system is
            also written into the semantic store as the online substrate. The
            file/Firestore record remains authoritative for exact reconstruction.
    """

    def __init__(self, vertex_backend: VertexSemanticMemoryBackend | None = None) -> None:
        self._vertex_backend = vertex_backend
        self._fs_client: Any = None  # lazily initialised firestore client

    # -- backend resolution --------------------------------------------------

    @property
    def backend(self) -> str:
        return "file" if _use_file_backend() else "vertex"

    def _client(self) -> Any:
        """Lazily obtain the Firestore client (vertex backend only)."""
        if self._fs_client is not None:
            return self._fs_client
        from atelier.auth.firebase import _init_firebase  # noqa: PLC0415

        app = _init_firebase()
        from firebase_admin import firestore as fb_firestore  # noqa: PLC0415

        self._fs_client = fb_firestore.client(app)
        return self._fs_client

    def _doc_ref(self, tenant_id: str, run_id: str) -> Any:
        client = self._client()
        return (
            client.collection(_TENANTS_COLLECTION)
            .document(tenant_id)
            .collection(_DESIGN_SYSTEMS_COLLECTION)
            .document(run_id)
        )

    def _current_pointer_ref(self, tenant_id: str) -> Any:
        """Doc holding the pointer to the tenant's CURRENT system run_id."""
        client = self._client()
        return (
            client.collection(_TENANTS_COLLECTION)
            .document(tenant_id)
            .collection(_DESIGN_SYSTEMS_COLLECTION)
            .document("_current")
        )

    # -- public API ----------------------------------------------------------

    async def persist(
        self,
        *,
        tenant_id: str,
        tokens: dict[str, Any],
        constitution: str | None,
        standards: list[dict[str, Any]],
        run_id: str,
    ) -> str:
        """Persist the tenant's current design system; return its record id (run_id).

        Writing is **last-write-wins** per tenant (one system per tenant, V1): a
        later sign-off (or a user edit) replaces the current system, which is how
        an edit propagates to the next run's enforcement.
        """
        record = DesignSystemRecord(
            tenant_id=tenant_id,
            run_id=run_id,
            tokens=dict(tokens),
            constitution=constitution,
            applicable_standards=list(standards),
        )

        if self.backend == "file":
            self._write_file(record)
            logger.info(
                "AT-053: persisted design system (file backend)",
                extra={"tenant_id": tenant_id, "run_id": run_id, "token_count": len(tokens)},
            )
            return run_id

        # Vertex/production path: Firestore is authoritative; Memory Bank is the
        # online substrate (best-effort, fail-soft — never blocks the run).
        await self._write_firestore(record)
        await self._write_memory_bank(record)
        logger.info(
            "AT-053: persisted design system (vertex backend)",
            extra={"tenant_id": tenant_id, "run_id": run_id, "token_count": len(tokens)},
        )
        return run_id

    async def load(self, tenant_id: str) -> DesignSystemRecord | None:
        """Load the tenant's current design system, or ``None`` if none/unavailable.

        Fail-soft: a missing system, a corrupt blob, or a backend outage all
        return ``None`` with a structured warning — never an exception. The
        caller treats ``None`` as "no persisted system yet" (first run) and
        proceeds with the brief's own tokens.
        """
        try:
            if self.backend == "file":
                return self._read_file(tenant_id)
            return await self._read_firestore(tenant_id)
        except Exception as exc:  # noqa: BLE001 — fail-soft load (see docstring)
            logger.warning(
                "AT-053: design-system load failed (fail-soft → None)",
                exc_info=True,
                extra={
                    "tenant_id": tenant_id,
                    "backend": self.backend,
                    "error_type": type(exc).__name__,
                },
            )
            return None

    # -- file backend --------------------------------------------------------

    def _write_file(self, record: DesignSystemRecord) -> None:
        path = _tenant_file(record.tenant_id)
        # Create the store dir lazily, only when we actually persist (resolution
        # alone must not scatter directories — see _design_system_dir).
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = record.to_memory_content()
        with _FILE_LOCK:
            # Atomic write: tmp file in the same dir, then Path.replace (atomic on
            # POSIX) so a concurrent reader never sees a half-written file.
            fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
            tmp_path = Path(tmp_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                tmp_path.replace(path)
            except OSError:
                # Clean up the temp file on failure; re-raise so persist (which is
                # fail-soft at the call site) records a real error rather than
                # silently dropping the system.
                tmp_path.unlink(missing_ok=True)
                raise

    def _read_file(self, tenant_id: str) -> DesignSystemRecord | None:
        path = _tenant_file(tenant_id)
        if not path.exists():
            return None
        content = path.read_text(encoding="utf-8")
        return DesignSystemRecord.from_memory_content(content)

    # -- firestore backend ---------------------------------------------------

    async def _write_firestore(self, record: DesignSystemRecord) -> None:
        doc_ref = self._doc_ref(record.tenant_id, record.run_id)
        # Stamp the canonical Firestore path back onto the record for provenance.
        stamped = record.model_copy(update={"firestore_doc_path": doc_ref.path})
        doc_ref.set(stamped.to_firestore_dict())
        # Update the per-tenant CURRENT pointer (last-write-wins) so load() reads
        # the latest system without a query/order-by.
        self._current_pointer_ref(record.tenant_id).set({"current_run_id": record.run_id})

    async def _read_firestore(self, tenant_id: str) -> DesignSystemRecord | None:
        pointer = self._current_pointer_ref(tenant_id).get()
        if not pointer.exists:
            return None
        current_run_id = (pointer.to_dict() or {}).get("current_run_id")
        if not current_run_id:
            return None
        snap = self._doc_ref(tenant_id, current_run_id).get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        return DesignSystemRecord.from_firestore_dict(data)

    # -- vertex memory bank (online substrate, AT-080) -----------------------

    async def _write_memory_bank(self, record: DesignSystemRecord) -> None:
        """Best-effort write into the Vertex Memory Bank substrate (fail-soft).

        The Firestore record is authoritative; this write makes the system
        queryable as a semantic prior. A Memory Bank outage must not fail the
        run, so an error here is logged and swallowed *with* an explicit comment
        (the durable record already succeeded above).
        """
        if self._vertex_backend is None:
            return
        scope = MemoryScopeKey(
            project_id=_project_id(),
            phase=_DESIGN_SYSTEM_PHASE,
            actor_id=record.tenant_id,
        )
        try:
            await self._vertex_backend.write_semantic(
                scope=scope,
                content=record.to_memory_content(),
                metadata={"kind": "design-system", "run_id": record.run_id},
            )
        except Exception as exc:  # noqa: BLE001
            # Fail-soft: the authoritative Firestore record already landed; the
            # semantic mirror is an optimization, not a correctness requirement.
            logger.warning(
                "AT-053: Memory Bank mirror write failed (fail-soft; Firestore is authoritative)",
                exc_info=True,
                extra={"tenant_id": record.tenant_id, "error_type": type(exc).__name__},
            )


# -- module-level convenience wrappers (the call sites use these) ------------


async def persist_design_system(
    *,
    tenant_id: str,
    tokens: dict[str, Any],
    constitution: str | None,
    standards: list[dict[str, Any]],
    run_id: str,
    vertex_backend: VertexSemanticMemoryBackend | None = None,
) -> str:
    """Persist a tenant's design system at sign-off; return the record id.

    Thin wrapper over :meth:`DesignSystemPersister.persist` so call sites do not
    need to construct the persister.
    """
    persister = DesignSystemPersister(vertex_backend=vertex_backend)
    return await persister.persist(
        tenant_id=tenant_id,
        tokens=tokens,
        constitution=constitution,
        standards=standards,
        run_id=run_id,
    )


async def load_persisted_design_system(
    tenant_id: str,
    *,
    vertex_backend: VertexSemanticMemoryBackend | None = None,
) -> DesignSystemRecord | None:
    """Load a tenant's current design system (auto-apply on next run), or ``None``.

    Fail-soft: returns ``None`` on absence/outage; never raises.
    """
    if not tenant_id:
        return None
    persister = DesignSystemPersister(vertex_backend=vertex_backend)
    return await persister.load(tenant_id)


__all__ = [
    "DesignSystemPersister",
    "load_persisted_design_system",
    "persist_design_system",
]
