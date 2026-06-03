"""AT-020b acceptance oracle — Board task-doc emitter (writer for PRD §7A.5).

The emitter drives ONE Firestore doc at
``tenants/{tenant_id}/projects/{project_id}/tasks/{task_id}`` through the EXACT
ordered 6-column Kanban set with NO skips::

    [Brief, Decompose, Awaiting Sign-off, Generating, QA, Done]

These tests are hermetic: they run against an in-memory Firestore double (no
live Firestore, no credentials, no emulator), so ``make verify`` stays
offline-green. They assert structural state-machine properties — the exact
column order, that each transition stamps ``agentRole`` + a non-empty
``statusLine`` (the active ``agentRole`` for the Generating stage), a valid
LexoRank ordering key, and a monotonically advancing ``updated_at`` — never a
specific generated artifact (no test-driven slop).

PRD Reference: §7A.5 (board task-doc schema), §12 (AT-020b), §13.2 (durability
pattern mirrored from AT-095), U6 (statusLine carries the role).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
from atelier.board.board_emitter import (
    BOARD_COLUMN_ORDER,
    BoardEmitter,
    ColumnSkipError,
)
from atelier.models.data_contracts import TenantContext
from atelier.models.enums import BoardColumnId

# --------------------------------------------------------------------------- #
# In-memory Firestore double — records every set/update so a test can read back
# the final doc AND the full transition history. Mirrors only the tiny slice of
# the google.cloud.firestore surface the emitter uses (collection/document/set).
# --------------------------------------------------------------------------- #


class _FakeDoc:
    """A document node that ALSO supports nested ``.collection()`` chaining.

    The emitter's path is six hops deep —
    ``collection(tenants).document(t).collection(projects).document(p)
    .collection(tasks).document(task_id)`` — so a doc node must expose
    ``.collection()`` to mirror the real Firestore fluent API.
    """

    def __init__(self, store: dict[str, Any], path: str) -> None:
        self._store = store
        self._path = path

    @property
    def path(self) -> str:
        return self._path

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self._store, f"{self._path}/{name}")

    def set(self, data: dict[str, Any], *, merge: bool = False) -> None:
        existing = self._store.setdefault(self._path, {})
        if merge:
            existing.update(data)
        else:
            self._store[self._path] = dict(data)

    def get(self) -> Any:
        return _FakeSnapshot(self._store.get(self._path))


class _FakeSnapshot:
    def __init__(self, data: dict[str, Any] | None) -> None:
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return self._data


class _FakeCollection:
    def __init__(self, store: dict[str, Any], prefix: str) -> None:
        self._store = store
        self._prefix = prefix

    def document(self, doc_id: str) -> _FakeDoc:
        return _FakeDoc(self._store, f"{self._prefix}/{doc_id}")


class _FakeFirestore:
    """A minimal in-memory stand-in for ``google.cloud.firestore.Client``."""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        # Every write the emitter performs, in order, for history assertions.
        self.writes: list[dict[str, Any]] = []

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self.store, name)


@pytest.fixture(autouse=True)
def _clean_board_memory() -> Iterator[None]:
    """Reset the process-wide in-memory lane cache between tests (isolation)."""
    from atelier.board.board_emitter import reset_board_memory

    reset_board_memory()
    yield
    reset_board_memory()


@pytest.fixture
def tenant_ctx() -> TenantContext:
    return TenantContext(tenant_id="tenantA", user_id="userA", project_id="projX")


@pytest.fixture
def fake_fs() -> _FakeFirestore:
    return _FakeFirestore()


@pytest.fixture
def emitter(fake_fs: _FakeFirestore) -> Iterator[BoardEmitter]:
    """A BoardEmitter wired to the in-memory double (no live Firestore)."""
    em = BoardEmitter(client=fake_fs)
    # Capture each committed transition for history-based assertions.
    em.add_write_observer(lambda payload: fake_fs.writes.append(dict(payload)))
    return em


# --------------------------------------------------------------------------- #
# THE acceptance test named in the build plan's first_failing_test.
# --------------------------------------------------------------------------- #


class TestBoardEmitter:
    def test_task_doc_transitions_through_six_columns(
        self, emitter: BoardEmitter, fake_fs: _FakeFirestore, tenant_ctx: TenantContext
    ) -> None:
        """One task doc walks the EXACT ordered 6-column set with NO skips.

        Drives the emitter through the full pipeline lifecycle and asserts:
          * the doc visits Brief -> Decompose -> Awaiting Sign-off -> Generating
            -> QA -> Done, in that exact order, no column skipped;
          * every transition stamps a non-empty agentRole + statusLine, with the
            Generating statusLine carrying the active agentRole (U6);
          * each write carries a valid LexoRank and an updated_at;
          * LexoRank advances monotonically across the lifecycle.
        """
        task_id = "task-1"
        # 1. Brief (the root doc is created here).
        emitter.initialize_task_doc(
            tenant_ctx=tenant_ctx,
            task_id=task_id,
            run_id="run-1",
            agent_role="intake",
            status_line="Parsing the brief",
        )
        # 2..6 — the exact remaining ordered columns, each with role + statusLine.
        emitter.transition(
            tenant_ctx=tenant_ctx,
            task_id=task_id,
            column=BoardColumnId.DECOMPOSE,
            agent_role="ux_research",
            status_line="Decomposing into the DDLC specialist plan",
        )
        emitter.transition(
            tenant_ctx=tenant_ctx,
            task_id=task_id,
            column=BoardColumnId.AWAITING_SIGNOFF,
            agent_role="planner",
            status_line="Awaiting human sign-off on scope",
        )
        emitter.transition(
            tenant_ctx=tenant_ctx,
            task_id=task_id,
            column=BoardColumnId.GENERATING,
            agent_role="ui_design",
            status_line="ui_design is rendering the screen",
        )
        emitter.transition(
            tenant_ctx=tenant_ctx,
            task_id=task_id,
            column=BoardColumnId.QA,
            agent_role="judge",
            status_line="Scoring against the convergence gates",
        )
        emitter.transition(
            tenant_ctx=tenant_ctx,
            task_id=task_id,
            column=BoardColumnId.DONE,
            agent_role="orchestrator",
            status_line="Converged",
        )

        # ---- exact-6-column-no-skip --------------------------------------- #
        visited = [w["columnId"] for w in fake_fs.writes]
        assert visited == [c.value for c in BOARD_COLUMN_ORDER], (
            f"columns must walk the exact ordered 6-set, got {visited}"
        )
        assert len(visited) == 6
        assert len(set(visited)) == 6  # no repeats, no skips

        # ---- agentRole + statusLine per stage ----------------------------- #
        for w in fake_fs.writes:
            assert w["agentRole"], "agentRole must be set at every transition"
            assert w["statusLine"], "statusLine must be non-empty at every transition"

        # U6: the Generating statusLine carries the active agentRole.
        gen = next(w for w in fake_fs.writes if w["columnId"] == BoardColumnId.GENERATING.value)
        assert gen["agentRole"] in gen["statusLine"], (
            "Generating statusLine must contain the active agentRole (U6)"
        )

        # ---- LexoRank + updated_at ---------------------------------------- #
        ranks = [w["rank"] for w in fake_fs.writes]
        assert all(isinstance(r, str) and r for r in ranks), "every doc carries a LexoRank"
        assert ranks == sorted(ranks), "LexoRank must advance monotonically (lexical order)"
        assert len(set(ranks)) == len(ranks), "each transition gets a distinct rank"
        for w in fake_fs.writes:
            assert isinstance(w["updated_at"], datetime)

        # ---- the persisted Firestore doc reflects the terminal state ------ #
        final = fake_fs.store[f"tenants/tenantA/projects/projX/tasks/{task_id}"]
        assert final["columnId"] == BoardColumnId.DONE.value
        assert final["task_id"] == task_id
        assert final["run_id"] == "run-1"

    def test_initialize_writes_brief_column_with_valid_rank(
        self, emitter: BoardEmitter, fake_fs: _FakeFirestore, tenant_ctx: TenantContext
    ) -> None:
        emitter.initialize_task_doc(
            tenant_ctx=tenant_ctx,
            task_id="t2",
            run_id="r2",
            agent_role="intake",
            status_line="Parsing the brief",
        )
        doc = fake_fs.store["tenants/tenantA/projects/projX/tasks/t2"]
        assert doc["columnId"] == BoardColumnId.BRIEF.value
        assert doc["agentRole"] == "intake"
        assert doc["statusLine"] == "Parsing the brief"
        assert isinstance(doc["rank"], str)
        assert doc["rank"]
        assert isinstance(doc["updated_at"], datetime)

    def test_skipping_a_column_raises(
        self, emitter: BoardEmitter, tenant_ctx: TenantContext
    ) -> None:
        """A transition that skips a column is a bug — the state machine rejects it."""
        emitter.initialize_task_doc(
            tenant_ctx=tenant_ctx,
            task_id="t3",
            run_id="r3",
            agent_role="intake",
            status_line="Parsing the brief",
        )
        # Brief -> Generating skips Decompose + Awaiting Sign-off.
        with pytest.raises(ColumnSkipError):
            emitter.transition(
                tenant_ctx=tenant_ctx,
                task_id="t3",
                column=BoardColumnId.GENERATING,
                agent_role="ui_design",
                status_line="ui_design rendering",
            )

    def test_backward_transition_raises(
        self, emitter: BoardEmitter, tenant_ctx: TenantContext
    ) -> None:
        """Columns only advance forward — a backward move is a state-machine bug."""
        emitter.initialize_task_doc(
            tenant_ctx=tenant_ctx,
            task_id="t4",
            run_id="r4",
            agent_role="intake",
            status_line="Parsing",
        )
        emitter.transition(
            tenant_ctx=tenant_ctx,
            task_id="t4",
            column=BoardColumnId.DECOMPOSE,
            agent_role="ux_research",
            status_line="Decomposing",
        )
        with pytest.raises(ColumnSkipError):
            emitter.transition(
                tenant_ctx=tenant_ctx,
                task_id="t4",
                column=BoardColumnId.BRIEF,
                agent_role="intake",
                status_line="back",
            )

    def test_write_failure_is_fail_soft(self, tenant_ctx: TenantContext) -> None:
        """A board write failure degrades fail-soft (logged + acknowledged), never crashes.

        The board is an observability surface; a Firestore outage must NOT crash
        the generation run. The emitter returns an acknowledgement record (not an
        exception) so the runner can log degradation and continue.
        """

        class _BoomFirestore(_FakeFirestore):
            def collection(self, name: str) -> _FakeCollection:
                raise RuntimeError("firestore unavailable")

        em = BoardEmitter(client=_BoomFirestore())
        ack = em.initialize_task_doc(
            tenant_ctx=tenant_ctx,
            task_id="t5",
            run_id="r5",
            agent_role="intake",
            status_line="Parsing",
        )
        assert ack.degraded is True
        assert ack.error is not None
        # And a subsequent transition also degrades softly, never raises.
        ack2 = em.transition(
            tenant_ctx=tenant_ctx,
            task_id="t5",
            column=BoardColumnId.DECOMPOSE,
            agent_role="ux_research",
            status_line="Decomposing",
        )
        assert ack2.degraded is True

    def test_lexorank_between_is_strictly_ordered(self) -> None:
        """The inline LexoRank produces a strictly increasing, midpoint-stable key."""
        from atelier.board.lexorank import lexorank_after, lexorank_between

        a = lexorank_after(None)
        b = lexorank_after(a)
        assert a < b
        mid = lexorank_between(a, b)
        assert a < mid < b


# --------------------------------------------------------------------------- #
# End-to-end integration: a REAL AtelierRunner.run() drives ONE task doc through
# the exact ordered 6-column set. Hermetic — every model surface is patched
# offline (no Vertex, no network), the board uses the in-memory double, and the
# usage store is in-memory. This is the §7A.5 acceptance proof: the runner (not
# just the emitter in isolation) walks Brief -> ... -> Done with no skips.
# --------------------------------------------------------------------------- #


def visited_task_id(fake_fs: _FakeFirestore) -> str:
    """The task id the runner used (the session id) — read off the persisted doc."""
    for path, doc in fake_fs.store.items():
        if path.startswith("tenants/t1/projects/p1/tasks/"):
            return str(doc["task_id"])
    raise AssertionError("no task doc was written")


@pytest.mark.anyio
async def test_runner_drives_one_task_doc_through_six_columns(
    fake_fs: _FakeFirestore,
) -> None:
    from unittest.mock import AsyncMock, patch

    from atelier.durability.usage_counter import UsageCounterStore
    from atelier.orchestrator.runner import AtelierRunner
    from google.adk.sessions.in_memory_session_service import InMemorySessionService

    # Reuse the proven offline harness from the AT-095 cap oracle so this test
    # exercises the SAME live run() path every user hits, just with the model
    # surfaces faked. Importing the helpers keeps the patch set single-sourced.
    from tests.unit.test_token_cap import (
        _BRIEF,
        _degraded_stitch,
        _fake_brief,
        _fake_plan,
        _fake_project_ctx,
        _FakeN3aRunner,
        _offline_fixer_directive,
    )

    store = UsageCounterStore(backend="memory")
    store.reset()
    emitter = BoardEmitter(client=fake_fs)
    emitter.add_write_observer(lambda payload: fake_fs.writes.append(dict(payload)))
    runner = AtelierRunner(
        session_service=InMemorySessionService(),
        usage_store=store,
        board_emitter=emitter,
    )
    tenant_ctx = TenantContext(tenant_id="t1", user_id="board-e2e-user", project_id="p1")

    patchers = [
        patch(
            "atelier.intake.brief_parser.BriefParserAgent.parse",
            new=AsyncMock(return_value=_fake_brief()),
        ),
        patch(
            "atelier.orchestrator.planner.PlannerAgent.plan",
            new=AsyncMock(return_value=_fake_plan()),
        ),
        patch("atelier.orchestrator.runner.source_resolver_gate", return_value=True),
        patch(
            "atelier.orchestrator.runner.source_resolver_agent",
            new=AsyncMock(return_value=_fake_project_ctx()),
        ),
        patch(
            "atelier.orchestrator.runner.create_specialist_pipeline",
            side_effect=_degraded_stitch,
        ),
        patch("atelier.orchestrator.runner.Runner", _FakeN3aRunner),
        patch(
            "atelier.nodes.fixer.FixerAgent.fix",
            new=AsyncMock(side_effect=_offline_fixer_directive),
        ),
    ]
    for p in patchers:
        p.start()
    try:
        await runner.run(_BRIEF, tenant_ctx)
    finally:
        for p in reversed(patchers):
            p.stop()

    # The runner drove exactly the ordered 6-column set, no skips, one doc.
    visited = [w["columnId"] for w in fake_fs.writes]
    assert visited == [c.value for c in BOARD_COLUMN_ORDER], (
        f"runner must drive the exact ordered 6-set, got {visited}"
    )
    # agentRole + statusLine populated at every transition; Generating carries the role.
    for w in fake_fs.writes:
        assert w["agentRole"]
        assert w["statusLine"]
    gen = next(w for w in fake_fs.writes if w["columnId"] == BoardColumnId.GENERATING.value)
    assert gen["agentRole"] in gen["statusLine"]
    # Valid, monotonic LexoRanks + an updated_at on every write.
    ranks = [w["rank"] for w in fake_fs.writes]
    assert ranks == sorted(ranks)
    assert len(set(ranks)) == len(ranks)
    assert all(isinstance(w["updated_at"], datetime) for w in fake_fs.writes)
    # The single persisted doc lives at the §7A.5 path and ends at Done.
    final = fake_fs.store["tenants/t1/projects/p1/tasks/" + visited_task_id(fake_fs)]
    assert final["columnId"] == BoardColumnId.DONE.value
