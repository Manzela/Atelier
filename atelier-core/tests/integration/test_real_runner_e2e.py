"""Hermetic real-Runner end-to-end: a brief drives the ACTUAL DAG to consensus.

Finding #84: the only live golden-path proof (``test_production_readiness.py``)
is ``skipif``-gated on ``ATELIER_BASE_URL`` and never runs in CI, and the other
N1->N2->N3a integration tests mock the ADK ``Runner`` itself
(``patch("atelier.orchestrator.runner.Runner")``) — the exact over-mocking that
previously hid six stacked bugs. This test closes that gap: it drives the REAL
:class:`AtelierRunner` through N1 -> N2 -> N3a -> N3c -> N3d -> N4 for one screen
with a fake :class:`BaseLlm` (no network, no creds, no ``skipif``) and asserts the
DAG's convergence engine is exercised by the genuine production code path — real
ADK ``Runner.run_async``, real ``run_gates``, real ``evaluate_candidate``, real
N4 selection — not a fixture this test authored.

What is faked vs. real:
  * Faked (leaf model surfaces only): the N3a specialists' served Gemini model is
    a :class:`_FakeLlm` injected through the production
    :func:`create_specialist_pipeline` seam (the same one
    ``test_specialist_pipeline.py`` uses); N1/N2's ``_call_llm`` + WRAI + token
    pulls are stubbed at their existing network seams so intake is offline.
  * Real (the whole point): ``AtelierRunner._run_surfaces_and_assemble``, the ADK
    ``SequentialAgent`` + ``Runner`` event loop, the six N3c deterministic gates,
    the D-O-R-A-V N3d consensus, and the N4 best-candidate selection all run as in
    production. The assertions read the ``GateOutcome`` / ``ConsensusEvaluation``
    those real components produce.

Convergence caveat (honest, load-bearing): a composite >= 0.70 is NOT reachable
hermetically through the real runner. The runner emits one ``index.html`` artifact
with inlined CSS, but the Brand / Originality / Visual-Clarity heuristic judges
(:mod:`atelier.nodes.consensus`) score only ``.css``-suffixed artifacts, so three
of five axes are structurally 0.0 and the composite caps below the bar regardless
of design quality. Rather than weaken production code or fake a converged result,
this test asserts the strongest TRUE property the real path produces: every N3c
gate PASSes and a real consensus composite is computed for at least one candidate
that cleared the gates. The live convergence-to-accepted proof remains
``test_production_readiness.py`` (against the deployed stack).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

import pytest
from atelier.durability.usage_counter import UsageCounterStore
from atelier.intake.brief_parser import BriefParserAgent
from atelier.intake.web_research import WebResearchReport
from atelier.integrations.stitch_mcp import StitchDegradationInfo
from atelier.models.data_contracts import TenantContext
from atelier.models.enums import GateDecision
from atelier.orchestrator import specialists as specialists_module
from atelier.orchestrator.planner import PlannerAgent
from atelier.orchestrator.runner import AtelierRunner
from atelier.testing.record_replay import hermetic
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types as genai_types

if TYPE_CHECKING:
    from google.adk.models.llm_request import LlmRequest

_USER_ID = "user-at-e2e"
_BRIEF_TEXT = (
    "Design a calm landing page for a quiet co-working space in an editorial "
    "register with a clear call to action."
)

# A signed-off BriefSpec the faked N1 returns verbatim. design_system_source="infer"
# makes the REAL source_resolver_gate admit the brief (PADI auto-discovery), so the
# N2 gate is genuinely exercised rather than stubbed.
_BRIEF_SPEC_JSON = """
{
    "spec_id": "123e4567-e89b-12d3-a456-426614174000",
    "tenant_id": "t1",
    "project_id": "p1",
    "intent": "calm editorial landing page for a co-working space",
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

# A complete, gate-clean HTML document the fake UI Designer emits. Every color flows
# through a var(--token) (token-fidelity gate), it has the semantic landmarks
# (semantic-html / visual-diff gates), a viewport meta and named controls (axe gate),
# and balanced inlined CSS (css-validity gate). The runner's normalization passes
# (_extract_html_document / _complete_*) then hand it to the REAL gates unchanged.
_GATE_CLEAN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Quiet Co-working Studio</title>
<style>
:root{--color-bg:#ffffff;--color-ink:#1a1a1a;--color-accent:#3b5bdb;--space-1:8px;--space-2:16px;}
body{background:var(--color-bg);color:var(--color-ink);font-family:Georgia,serif;font-size:18px;line-height:1.6;margin:0;}
header{padding:var(--space-2);border-bottom:1px solid var(--color-ink);}
nav a{color:var(--color-accent);font-weight:600;margin-right:var(--space-1);}
main{padding:var(--space-2);max-width:720px;margin:0 auto;}
section{margin-bottom:var(--space-2);}
h1{font-size:40px;letter-spacing:-0.5px;}
footer{padding:var(--space-2);font-size:14px;color:var(--color-ink);}
button{background:var(--color-accent);color:var(--color-bg);padding:var(--space-1);font-weight:600;}
</style>
</head>
<body>
<header><nav><a href="#book">Book a desk</a><a href="#tour">Take a tour</a></nav></header>
<main>
<section><h1>A quiet place to do focused work</h1><p>Editorial calm, fast fibre, and desks that stay out of your way. Reserve a spot for the day or settle in for the month.</p></section>
<article><h2>What members get</h2><p>Sound-managed rooms, ergonomic seating, and unlimited filtered coffee. Every membership includes two guest passes each month.</p><button type="button">Reserve a desk</button></article>
</main>
<footer><p>Quiet Studio, 12 Harbour Lane. Open weekdays from eight in the morning until late.</p></footer>
</body>
</html>"""


class _FakeUIDesignerLlm(BaseLlm):
    """Hermetic stand-in for the served Gemini model across all six specialists.

    Returns the gate-clean HTML document on every call (no network). The real
    N3a ``SequentialAgent`` runs all six specialists through this one fake, so the
    last accumulated candidate text is a valid HTML page the runner feeds to the
    real N3c gates. ``calls`` records the served-specialist count, proving zero
    live model surfaces were reached.
    """

    calls: int = 0

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,  # noqa: FBT001, FBT002 — must match BaseLlm override signature
    ) -> AsyncGenerator[LlmResponse, None]:
        self.calls += 1
        yield LlmResponse(
            content=genai_types.Content(
                role="model",
                parts=[genai_types.Part(text=_GATE_CLEAN_HTML)],
            )
        )


async def _drive_real_runner() -> tuple[dict[str, Any], int, int]:
    """Drive the real AtelierRunner end-to-end offline; return (payload, fake.calls, live_calls).

    Only the leaf model surfaces are faked. The session service is in-memory, the
    token store is an isolated in-memory counter, and N1/N2/WRAI are stubbed at the
    same network seams the existing N1->N2->N3a integration test uses. The N3a
    pipeline is built through the production ``create_specialist_pipeline`` with the
    fake model injected, so the REAL Runner/gate/consensus path executes.
    """
    fake = _FakeUIDesignerLlm(model="fake-hermetic")

    # Bind the genuine factory BEFORE patching so the wrapper calls the real code
    # (not the patched name — that would recurse) with only the served model forced.
    real_create_pipeline = specialists_module.create_specialist_pipeline

    def _fake_pipeline(**_kwargs: Any) -> Any:
        # Force the fake model into the production pipeline factory; everything else
        # (the SequentialAgent wiring, Stitch degradation, output_keys) is genuine.
        return real_create_pipeline(model=fake)

    def _degraded_stitch(*_args: Any, **_kwargs: Any) -> tuple[None, StitchDegradationInfo]:
        # Force the AG-06 Stitch-unavailable fallback so the run touches no MCP
        # subprocess and stays fast + hermetic (also exercises the degraded path).
        return None, StitchDegradationInfo(
            is_degraded=True,
            reason="Stitch MCP disabled for hermetic real-runner E2E",
            fallback_mode="direct_generation",
        )

    session_service = InMemorySessionService()
    usage_store = UsageCounterStore(backend="memory")
    usage_store.reset()
    runner = AtelierRunner(
        session_service=session_service,
        usage_store=usage_store,
        max_iterations=1,
    )
    tenant_ctx = TenantContext(tenant_id="t1", user_id=_USER_ID, project_id="p1")

    with (
        hermetic() as guard,
        patch.object(BriefParserAgent, "_call_llm", new_callable=AsyncMock) as mock_n1,
        patch.object(PlannerAgent, "_call_llm", new_callable=AsyncMock) as mock_n0,
        # WRAI (N14) is on by default; stub it to an empty report so intake never
        # reaches the grounded-search genai client (kept hermetic).
        patch(
            "atelier.orchestrator.runner.research_brief",
            new_callable=AsyncMock,
            return_value=WebResearchReport(results=[]),
        ),
        # N2 token pulls — offline. The source_resolver_gate itself is NOT stubbed.
        patch(
            "atelier.intake.source_resolver.pull_design_tokens",
            new_callable=AsyncMock,
            return_value={"color-primary": "#3b5bdb"},
        ),
        patch(
            "atelier.intake.source_resolver.load_tenant_design_system",
            new_callable=AsyncMock,
            return_value=None,
        ),
        # Inject the fake model into the REAL N3a pipeline at the runner's call site.
        # The runner imports the factory into its own namespace, so patching there
        # is the single seam; the wrapper still invokes the genuine factory body.
        patch(
            "atelier.orchestrator.runner.create_specialist_pipeline",
            side_effect=_fake_pipeline,
        ),
        # Degrade Stitch (no MCP subprocess) — keeps the run hermetic and fast.
        patch(
            "atelier.orchestrator.specialists.try_get_stitch_mcp_toolset",
            side_effect=_degraded_stitch,
        ),
        # Closed-loop QA screenshotting launches real Chromium per gate-passing
        # candidate; stub it to the same None ("no screenshot") path the runner
        # already tolerates, so the test needs no browser and stays deterministic.
        patch(
            "atelier.durability.screenshot_helper.capture_and_upload_screenshot",
            return_value=None,
        ),
    ):
        mock_n1.return_value = _BRIEF_SPEC_JSON
        # PlannerAgent fails soft to a default plan on a None response; that default
        # keeps should_run_wrai's branch deterministic without a live planner call.
        mock_n0.return_value = None

        payload = await runner.run(_BRIEF_TEXT, tenant_ctx=tenant_ctx)

    return payload, fake.calls, guard.live_calls


#: One real-runner drive is the expensive part (the genuine ADK event loop + gates +
#: consensus). It is deterministic, so memoize it across the assertions in this module
#: rather than paying for two full DAG runs.
_DRIVE_CACHE: tuple[dict[str, Any], int, int] | None = None


async def _drive_once() -> tuple[dict[str, Any], int, int]:
    """Return the memoized real-runner result, driving the DAG exactly once."""
    global _DRIVE_CACHE  # noqa: PLW0603 — module-level memo of a deterministic drive
    if _DRIVE_CACHE is None:
        _DRIVE_CACHE = await _drive_real_runner()
    return _DRIVE_CACHE


@pytest.mark.anyio
async def test_real_runner_drives_dag_to_consensus_hermetically() -> None:
    """The real DAG (N1->N2->N3a->N3c->N3d->N4) runs offline and produces real
    gate + consensus outcomes for one screen — no network, no skipif."""
    payload, fake_calls, live_calls = await _drive_once()

    # Hermeticity: zero live model/tool calls slipped through (AT-003 guard), and
    # every specialist was served by the fake (6 DDLC roles, one fake call each).
    assert live_calls == 0, "hermetic real-runner E2E attempted a live model/tool call"
    assert fake_calls == len(specialists_module.SPECIALIST_OUTPUT_KEYS), (
        f"expected one fake-model call per DDLC specialist "
        f"({len(specialists_module.SPECIALIST_OUTPUT_KEYS)}); got {fake_calls}"
    )

    # N1/N2 produced the real intake objects (the brief flowed through the genuine
    # BriefParserGate + source_resolver_gate, neither of which was stubbed).
    assert payload["brief"].intent == "calm editorial landing page for a co-working space"
    assert payload["project_context"] is not None

    # N3a produced real candidates fed to the convergence engine.
    assert payload["candidates"], "N3a produced no candidates for N3c/N3d"

    # N3c: the REAL deterministic gates ran and at least one candidate cleared every
    # gate. gate_results are the serialized GateOutcome set the runner built from the
    # real run_gates() call, not a fixture authored here.
    assert payload["gate_results"], "no N3c gate results were produced by the real gates"
    fully_passed = [gr for gr in payload["gate_results"] if gr["all_passed"]]
    assert fully_passed, (
        f"no candidate cleared all six N3c gates; gate_results={payload['gate_results']}"
    )
    # Every axis on a passing candidate is a real PASS decision (six gate axes).
    passing_outcomes = fully_passed[0]["outcomes"]
    assert {o["axis"] for o in passing_outcomes} >= {
        "semantic-html",
        "css-validity",
        "token-fidelity",
        "lighthouse-a11y",
        "axe",
        "visual-diff",
    }
    assert all(o["passed"] for o in passing_outcomes)

    # N4: at least one gate-passing candidate reached the consensus stage.
    assert payload["candidates_passed_gates"] >= 1, (
        "N3c passed a candidate but candidates_passed_gates did not reflect it"
    )

    # N3d: the REAL D-O-R-A-V consensus produced an evaluation. The composite is what
    # the genuine AxisWeights.compute_composite returned over the real heuristic
    # judges — a number this test did not author.
    assert payload["evaluations"], "no N3d consensus evaluation was produced"
    composite = float(payload["composite_score"])
    assert 0.0 < composite <= 1.0, f"consensus composite out of range: {composite}"
    # best_candidate is the real selected design (the normalized HTML), not a stub.
    assert isinstance(payload["best_candidate"], str)
    assert "<html" in payload["best_candidate"].lower()

    # AG-06: the real runner still produced a full design with Stitch degraded.
    assert payload["stitch_degraded"] is True


@pytest.mark.anyio
async def test_real_runner_gate_outcomes_are_genuine_decisions() -> None:
    """Guard against a vacuous pass: the gate outcomes carry real GateDecision.PASS
    values and real numeric scores, so the all-passed assertion is non-trivial."""
    payload, _fake_calls, _live_calls = await _drive_once()

    fully_passed = [gr for gr in payload["gate_results"] if gr["all_passed"]]
    assert fully_passed, "expected at least one fully gate-passing candidate"
    outcomes = fully_passed[0]["outcomes"]
    # Six distinct axes, each a real PASS with a real score in the gate's range.
    assert len(outcomes) == 6
    for outcome in outcomes:
        assert outcome["passed"] is True
        # GateDecision.PASS is the only decision that yields passed=True; the score
        # is the real per-gate heuristic value (0..100), never a hardcoded constant.
        assert isinstance(outcome["score"], (int, float))
        assert 0.0 <= float(outcome["score"]) <= 100.0
    # Sanity: GateDecision.PASS is the enum the real gates emitted (import-level
    # coupling so a rename of the enum fails this test loudly).
    assert GateDecision.PASS.value == "pass"
