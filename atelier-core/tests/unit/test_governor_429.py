"""Governor handling of a SUSTAINED Vertex 429 (RESOURCE_EXHAUSTED).

The MAPE-K governor self-heals transient 429/503 with bounded backoff. When a
429 persists beyond the self-heal budget (the model-side per-minute quota is
genuinely saturated), the governor must surface it as the graceful, domain
``GovernorRateLimitExceeded`` — which the API maps to an honest HTTP-429
"too many requests, please wait and try again" — NOT re-raise the raw provider
error, which the stream handler would render as a generic "Pipeline error".
"""

from __future__ import annotations

import atelier.orchestrator.governor as gov
import pytest
from atelier.orchestrator.governor import GovernorRateLimitExceeded, MetacognitiveGovernor


class _Vertex429Error(Exception):
    """Mimics google.genai.errors.ClientError str() for a 429."""


@pytest.mark.unit
@pytest.mark.anyio
async def test_sustained_vertex_429_surfaces_as_graceful_rate_limit(monkeypatch) -> None:
    # Don't actually sleep through the self-heal backoff.
    async def _no_sleep(*_a, **_k) -> None:
        return None

    monkeypatch.setattr(gov.asyncio, "sleep", _no_sleep)

    async def _always_429() -> str:
        raise _Vertex429Error(
            "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'status': 'RESOURCE_EXHAUSTED'}}"
        )

    governor = MetacognitiveGovernor()
    with pytest.raises(GovernorRateLimitExceeded):
        await governor.run_with_governance(_always_429, step_id="n3a-specialist")


@pytest.mark.unit
@pytest.mark.anyio
async def test_non_rate_limit_self_heal_error_still_raises_raw(monkeypatch) -> None:
    """A sustained 503 (not a rate limit) keeps its raw FAIL_LOUD propagation."""

    async def _no_sleep(*_a, **_k) -> None:
        return None

    monkeypatch.setattr(gov.asyncio, "sleep", _no_sleep)

    class _Vertex503Error(Exception):
        pass

    async def _always_503() -> str:
        raise _Vertex503Error("503 Service Unavailable")

    governor = MetacognitiveGovernor()
    with pytest.raises(_Vertex503Error):
        await governor.run_with_governance(_always_503, step_id="n3a-specialist")
