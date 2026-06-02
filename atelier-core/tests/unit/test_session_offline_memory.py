"""AT-080 offline acceptance — InMemorySessionService round-trips with no network.

Drives the ``memory`` backend session service through create_session ->
get_session and asserts state round-trips with zero network access. This is the
offline lane exercised by ``make verify`` (``SESSION_BACKEND=memory``).

PRD Reference: §12 E8 (AT-080) — "memory -> make verify offline passes"
"""

from __future__ import annotations

import pytest
from atelier.orchestrator.backend_factory import create_session_service

_APP = "atelier"
_USER = "test-user"


@pytest.mark.anyio
async def test_offline_session_roundtrip() -> None:
    svc = create_session_service("memory")

    created = await svc.create_session(app_name=_APP, user_id=_USER, state={"brief": "demo"})
    assert created.id

    fetched = await svc.get_session(app_name=_APP, user_id=_USER, session_id=created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.state.get("brief") == "demo"


@pytest.mark.anyio
async def test_offline_session_missing_returns_none() -> None:
    svc = create_session_service("memory")

    missing = await svc.get_session(app_name=_APP, user_id=_USER, session_id="does-not-exist")
    assert missing is None
