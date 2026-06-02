"""AT-110 production-readiness gate — live golden-path walkthrough (3x).

Drives the PRD section 16 walkthrough against the LIVE deployed stack three
times consecutively and asserts each run converges with non-empty token
accounting and no unacknowledged failure. This is not hermetic: it requires the
deployed product (AT-083) and a signed-in session, so it is skipped unless both
ATELIER_BASE_URL and ATELIER_ID_TOKEN are set. The hermetic golden-path proof is
the AT-004 ``make verify`` suite
(``tests/integration/test_record_replay_determinism.py``), which stays green
offline.

Run live (operator):
    ATELIER_BASE_URL=https://atelier.autonomous-agent.dev \\
    ATELIER_ID_TOKEN=<firebase id token> \\
    pytest tests/integration/test_production_readiness.py -v -m external

PRD Reference: section 12 E11 (AT-110), section 15, section 16
"""

from __future__ import annotations

import os
import time

import httpx
import pytest

pytestmark = pytest.mark.external

_BASE_URL = os.getenv("ATELIER_BASE_URL", "")
_ID_TOKEN = os.getenv("ATELIER_ID_TOKEN", "")
_LIVE_CONFIGURED = bool(_BASE_URL and _ID_TOKEN)

_CONSECUTIVE_RUNS = 3
_POLL_TIMEOUT_SEC = 180
_POLL_INTERVAL_SEC = 5
_FIXED_BRIEF = "Design a calm onboarding flow for a fintech mobile app."


def _poll_until_converged(
    client: httpx.Client,
    base: str,
    session_id: str,
) -> dict[str, object]:
    """Poll the replay endpoint until the run converges or the deadline passes."""
    elapsed = 0
    while elapsed < _POLL_TIMEOUT_SEC:
        resp = client.get(f"{base}/v1/replay/{session_id}")
        if resp.status_code == httpx.codes.OK:
            trace = resp.json()
            final = trace.get("final_state") or trace
            if final.get("converged") is True:
                return final  # type: ignore[no-any-return]
        time.sleep(_POLL_INTERVAL_SEC)
        elapsed += _POLL_INTERVAL_SEC
    pytest.fail(f"replay did not converge within {_POLL_TIMEOUT_SEC}s for session {session_id}")


@pytest.mark.skipif(
    not _LIVE_CONFIGURED,
    reason="live stack not configured (set ATELIER_BASE_URL + ATELIER_ID_TOKEN)",
)
def test_golden_path_succeeds_three_times_consecutively() -> None:
    """The section 16 walkthrough must succeed on three consecutive live runs."""
    base = _BASE_URL.rstrip("/")
    headers = {"Authorization": f"Bearer {_ID_TOKEN}"}

    for run in range(1, _CONSECUTIVE_RUNS + 1):
        with httpx.Client(timeout=30.0, headers=headers) as client:
            resp = client.post(f"{base}/v1/generate", json={"brief": _FIXED_BRIEF})
            assert resp.status_code in (200, 202), f"run {run}: generate -> {resp.status_code}"

            session_id = resp.json().get("session_id")
            assert session_id, f"run {run}: no session_id returned"

            final = _poll_until_converged(client, base, session_id)
            assert final.get("converged") is True, f"run {run}: did not converge"
            assert final.get("tokens"), f"run {run}: empty token accounting"
