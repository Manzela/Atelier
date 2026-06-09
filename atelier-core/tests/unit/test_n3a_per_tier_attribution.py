"""Per-tier token attribution for the N3a specialist pipeline (finding 0).

The pre-fix runner charged EVERY ADK event to a hardcoded ``"gemini-2.5-flash"``
id, so all specialist spend landed in the Flash tier (15M cap) regardless of the
model a specialist actually runs on. The TokenGenerator runs on Flash-Lite and
``calibrate_model`` can route others to Pro, so per-tier enforcement collapsed to
a single Flash bucket.

This test drives the real ``AtelierRunner.run`` with a fake ADK runner that
emits one usage-bearing event per DDLC specialist (author == specialist name)
and asserts the governor's ``per_tier_tokens`` splits the spend by the
specialist's true tier: the TokenGenerator's tokens land in ``flash_lite``, the
Flash specialists in ``flash``. Under the old single-bucket code ``flash_lite``
would be empty.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from atelier.durability.usage_counter import UsageCounterStore
from atelier.intake.brief_spec import BriefSpec
from atelier.intake.source_resolver import ProjectContext
from atelier.models.data_contracts import TenantContext
from atelier.orchestrator.planner import PlanStep
from atelier.orchestrator.runner import AtelierRunner
from atelier.orchestrator.specialists import SPECIALIST_OUTPUT_KEYS, get_specialist_specs
from google.adk.events.event import Event
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types as genai_types

_BRIEF = "Build a calm editorial landing page for a co-working studio with pricing."
_UID = "per-tier-user"

_VALID_BRIEF_JSON = """
{
    "spec_id": "123e4567-e89b-12d3-a456-426614174000",
    "tenant_id": "t1",
    "project_id": "p1",
    "intent": "build a landing page",
    "visual_register": "editorial",
    "stack": "vanilla-html",
    "design_system_source": "infer",
    "compliance_level": "wcag-aa",
    "convergence_bar": "ship-it",
    "reference_artifacts": [],
    "campaign_scope": null,
    "intake_transcript": [],
    "schema_version": 1,
    "approved_at": "2026-05-25T12:00:00Z",
    "approved_by_user_id": "user1"
}
"""

#: The name of the Flash-Lite specialist (last DDLC stage — TokenGenerator).
_FLASH_LITE_SPECIALIST = next(
    spec.name for spec in get_specialist_specs() if spec.output_key == "tokens"
)


def _fake_brief() -> BriefSpec:
    return BriefSpec.model_validate_json(_VALID_BRIEF_JSON)


def _fake_plan() -> PlanStep:
    return PlanStep(should_run_wrai=False, surfaces=["landing page"], reasoning="test plan")


def _fake_project_ctx() -> ProjectContext:
    return ProjectContext(
        brief=_fake_brief(),
        design_tokens={"primary_color": "#101010"},
        memory_bank_priors=["prior-a"],
    )


def _authored_event(author: str, text: str, *, out_tokens: int) -> Event:
    """An ADK event from one specialist carrying real usage metadata."""
    return Event(
        author=author,
        content=genai_types.Content(role="model", parts=[genai_types.Part(text=text)]),
        usage_metadata=genai_types.GenerateContentResponseUsageMetadata(
            prompt_token_count=10,
            candidates_token_count=out_tokens,
            thoughts_token_count=0,
        ),
    )


class _FakeAuthoredRunner:
    """ADK Runner stand-in: one usage-bearing event per specialist, authored by name."""

    def __init__(self, **_kwargs: Any) -> None:
        pass

    async def run_async(self, **_kwargs: Any) -> AsyncGenerator[Event, None]:
        html = (
            "<!doctype html><html lang='en'><head><title>Studio</title></head>"
            "<body><main><h1>Co-working Studio</h1>"
            "<p>Quiet desks, fast fibre.</p></main></body></html>"
        )
        for name in SPECIALIST_OUTPUT_KEYS:
            spec_name = next(s.name for s in get_specialist_specs() if s.output_key == name)
            text = html if name == SPECIALIST_OUTPUT_KEYS[-1] else f"{name} output"
            yield _authored_event(spec_name, text, out_tokens=1000)


def _degraded_stitch(*_args: Any, **_kwargs: Any) -> tuple[None, Any]:
    from atelier.integrations.stitch_mcp import StitchDegradationInfo

    return None, StitchDegradationInfo(
        is_degraded=True,
        reason="Stitch MCP disabled for hermetic test",
        fallback_mode="direct_generation",
    )


def _offline_fixer_directive(*_args: Any, **_kwargs: Any) -> Any:
    from atelier.nodes.fixer import FixerDirective

    return FixerDirective(
        mutations=[],
        prompt_amendments=["Offline test directive: revise and improve the design."],
        reasoning="Deterministic offline fixer directive (no live LLM call).",
    )


class _PatchStack:
    def __init__(self, patchers: list[Any]) -> None:
        self._patchers = patchers

    def __enter__(self) -> _PatchStack:
        for p in self._patchers:
            p.start()
        return self

    def __exit__(self, *_exc: Any) -> None:
        for p in reversed(self._patchers):
            p.stop()


def _offline() -> _PatchStack:
    return _PatchStack(
        [
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
            patch("atelier.orchestrator.runner.Runner", _FakeAuthoredRunner),
            patch(
                "atelier.nodes.fixer.FixerAgent.fix",
                new=AsyncMock(side_effect=_offline_fixer_directive),
            ),
            # Keep calibration deterministic + offline: use the pinned routing
            # table, never Remote Config / GEMINI_MODEL_ID overrides.
            patch(
                "atelier.models.model_registry.fetch_calibrated_model_from_remote_config",
                return_value=None,
            ),
        ]
    )


def _tenant_ctx() -> TenantContext:
    return TenantContext(tenant_id="t1", user_id=_UID, project_id="p1")


def _fresh_store() -> UsageCounterStore:
    s = UsageCounterStore(backend="memory")
    s.reset()
    return s


@pytest.mark.anyio
async def test_n3a_spend_splits_into_real_tier_buckets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_MODEL_ID", raising=False)
    runner = AtelierRunner(
        session_service=InMemorySessionService(),
        usage_store=_fresh_store(),
        max_iterations=1,
    )
    with _offline():
        await runner.run(_BRIEF, _tenant_ctx())

    per_tier = runner._governor._state.per_tier_tokens
    # The TokenGenerator runs on Flash-Lite — its output tokens must land in the
    # flash_lite bucket, not the Flash bucket (the pre-fix behaviour).
    assert per_tier.get("flash_lite", 0) > 0, (
        f"Flash-Lite specialist spend was not attributed to the flash_lite tier; "
        f"per_tier_tokens={per_tier}"
    )
    # The Flash specialists (UX research, IA, wireframe, UI, interaction) charge
    # the Flash bucket.
    assert per_tier.get("flash", 0) > 0, f"no Flash-tier spend recorded; per_tier_tokens={per_tier}"
    # Sanity: the Flash-Lite specialist is exactly the TokenGenerator (one of six).
    assert _FLASH_LITE_SPECIALIST
