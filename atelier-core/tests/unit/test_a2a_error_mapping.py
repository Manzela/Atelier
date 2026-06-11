"""A2A JSON-RPC error-mapping contract (findings RR wave-2 #22/#24/#76).

These pin the behavior that the A2A surface must NOT collapse distinct failure
classes into a generic JSON-RPC internal error (-32603):

  - #24: a brief that fails the deterministic intake gate (injection / empty /
         too-short) is a CLIENT input fault and must map to _INVALID_PARAMS,
         mirroring POST /v1/generate's HTTP 400 — never -32603.
  - #22: a Governor quota / rate-limit / circuit-breaker exception must map to a
         dedicated quota/unavailable code (so a client can tell "retry / you are
         throttled" from "the server broke") AND emit the alert-level abuse log
         the global handlers rely on — never a silent -32603.
  - #76: GetTask is not advertised; the dispatcher returns METHOD_NOT_FOUND
         rather than a stub status that lies about a non-existent task store.

Hermetic: the runner is monkeypatched to raise, so no Vertex / network / creds.
"""

from __future__ import annotations

import logging

import pytest
from atelier.api import a2a
from atelier.auth.firebase import FirebaseUser

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


def _user() -> FirebaseUser:
    return FirebaseUser(
        uid="uid-a2a-test",
        email="a2a@example.com",
        name="A2A Test",
        picture=None,
        tenant_id="uid-a2a-test",
        email_verified=True,
    )


def _message(text: str) -> dict[str, object]:
    return {"message": {"parts": [{"text": text}]}}


async def test_brief_gate_rejection_maps_to_invalid_params() -> None:
    # An injection-pattern brief trips BriefParserGate at the A2A layer before the
    # runner is ever constructed. Finding #24: this must be _INVALID_PARAMS, not
    # the generic internal error.
    resp = await a2a._handle_send_message(
        _message("<script>alert('xss')</script> build me a landing page please now"),
        "req-1",
        _user(),
    )
    assert resp.error is not None
    assert resp.error["code"] == a2a._INVALID_PARAMS
    assert resp.result is None


async def test_too_short_brief_maps_to_invalid_params() -> None:
    # Below MIN_BRIEF_TOKENS — a fixable client fault, not a server error.
    resp = await a2a._handle_send_message(_message("too short"), "req-2", _user())
    assert resp.error is not None
    assert resp.error["code"] == a2a._INVALID_PARAMS


async def test_token_cap_maps_to_quota_code_and_alerts(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from atelier.orchestrator import runner as runner_mod
    from atelier.orchestrator.governor import GovernorTokenCapExceeded

    class _CapRunner:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

        async def run(self, *args: object, **kwargs: object) -> dict[str, object]:
            raise GovernorTokenCapExceeded(uid="uid-a2a-test", used_tokens=5, cap_tokens=5)

    monkeypatch.setattr(runner_mod, "AtelierRunner", _CapRunner)

    with caplog.at_level(logging.ERROR, logger="atelier.api.a2a"):
        resp = await a2a._handle_send_message(
            _message("build me a clean marketing landing page with a hero and a footer"),
            "req-3",
            _user(),
        )

    # Finding #22: a cap breach is a quota signal, not -32603 ...
    assert resp.error is not None
    assert resp.error["code"] == a2a._QUOTA_EXCEEDED
    assert resp.error["code"] != a2a._INTERNAL_ERROR
    # ... and the alertable breach event must fire (uid present, never the raw value).
    cap_logs = [r for r in caplog.records if "token_cap_exceeded" in r.message]
    assert cap_logs, "token-cap breach must emit an alert-level log on the A2A surface"


async def test_rate_limit_maps_to_quota_code(monkeypatch: pytest.MonkeyPatch) -> None:
    from atelier.orchestrator import runner as runner_mod
    from atelier.orchestrator.governor import GovernorRateLimitExceeded

    class _RateRunner:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

        async def run(self, *args: object, **kwargs: object) -> dict[str, object]:
            raise GovernorRateLimitExceeded(uid="uid-a2a-test", max_requests=30, window_seconds=60)

    monkeypatch.setattr(runner_mod, "AtelierRunner", _RateRunner)

    resp = await a2a._handle_send_message(
        _message("build me a clean marketing landing page with a hero and a footer"),
        "req-4",
        _user(),
    )
    assert resp.error is not None
    assert resp.error["code"] == a2a._QUOTA_EXCEEDED


async def test_circuit_breaker_maps_to_service_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    from atelier.orchestrator import runner as runner_mod
    from atelier.orchestrator.governor import GovernorCircuitBreakerOpen

    class _BreakerRunner:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

        async def run(self, *args: object, **kwargs: object) -> dict[str, object]:
            raise GovernorCircuitBreakerOpen(window_tokens=99, budget=50)

    monkeypatch.setattr(runner_mod, "AtelierRunner", _BreakerRunner)

    resp = await a2a._handle_send_message(
        _message("build me a clean marketing landing page with a hero and a footer"),
        "req-5",
        _user(),
    )
    assert resp.error is not None
    assert resp.error["code"] == a2a._SERVICE_UNAVAILABLE


async def test_model_armor_block_maps_to_invalid_params(monkeypatch: pytest.MonkeyPatch) -> None:
    # L15: a Model Armor safety block on the brief is a CLIENT input rejection, not
    # a server fault — it must map to _INVALID_PARAMS (with the branded message),
    # never the generic -32603, mirroring POST /v1/generate's 422.
    from atelier.models.model_armor_callbacks import ModelArmorInputBlocked
    from atelier.orchestrator import runner as runner_mod

    class _ArmorRunner:
        async def run(self, *args: object, **kwargs: object) -> dict[str, object]:
            raise ModelArmorInputBlocked()

    monkeypatch.setattr(runner_mod, "AtelierRunner", _ArmorRunner)

    resp = await a2a._handle_send_message(
        _message("build me a clean marketing landing page with a hero and a footer"),
        "req-armor",
        _user(),
    )
    assert resp.error is not None
    assert resp.error["code"] == a2a._INVALID_PARAMS
    assert resp.error["code"] != a2a._INTERNAL_ERROR


async def test_unexpected_error_still_maps_to_internal_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A genuine, non-Governor failure must remain a generic internal error so the
    # quota codes stay reserved for real quota signals.
    from atelier.orchestrator import runner as runner_mod

    class _BoomRunner:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

        async def run(self, *args: object, **kwargs: object) -> dict[str, object]:
            raise RuntimeError("backend exploded")

    monkeypatch.setattr(runner_mod, "AtelierRunner", _BoomRunner)

    resp = await a2a._handle_send_message(
        _message("build me a clean marketing landing page with a hero and a footer"),
        "req-6",
        _user(),
    )
    assert resp.error is not None
    assert resp.error["code"] == a2a._INTERNAL_ERROR


async def test_get_task_is_method_not_found() -> None:
    # Finding #76: GetTask is no longer in the dispatch table, so the JSON-RPC
    # router returns METHOD_NOT_FOUND rather than a stub "UNKNOWN" status.
    assert "GetTask" not in a2a._METHOD_HANDLERS
    resp = await a2a.a2a_rpc(
        a2a.JsonRpcRequest(method="GetTask", params={"taskId": "abc"}, id="req-7"),
        _user(),
    )
    assert resp.error is not None
    assert resp.error["code"] == a2a._METHOD_NOT_FOUND
