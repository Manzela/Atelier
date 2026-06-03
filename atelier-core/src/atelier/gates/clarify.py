"""AT-030 — clarify gate (uncertainty-gated, event-driven; extends PlanStep).

The clarify gate is the anti-railroad surface. AT-025 populates the *data* on
:class:`~atelier.orchestrator.planner.PlanStep` (the classified ``gaps_detail`` and
the cited ``proposed_defaults``); AT-030 — this module — owns the DECISION LOGIC:

  - **Stakes router** (:func:`route_gaps`): a high-stakes, irreversible, or
    globally-scoped gap is ALWAYS asked (an :class:`OpenQuestion`); a cheap +
    locally-reversible + low-stakes gap is silently defaulted WITH its citation
    (a :class:`ProposedDefault`). Fail-closed bias: when in doubt, ask.
  - **Batched emission** (:func:`clarify_gate`): every ask and every cited
    default ship in ONE :class:`ClarifyBatch` (PRD R15 — never drip-fed). A clear
    brief emits nothing; the gate stays silent.
  - **ACCEPTANCE read/modify** (:func:`confirm_default` / :func:`override_default`
    / :func:`apply_clarify_answers`): confirming a default writes the matching
    ``standard_id`` into ``ACCEPTANCE.json``'s ``confirmed_standards`` (the
    run-oracle then records it as a ``source='standard:<id>'`` attribution
    criterion); overriding removes it.
  - **Event-driven re-fire cap** (:func:`should_refire`): a synthetic downstream
    new-ambiguity re-fires the gate exactly once. The
    :data:`CLARIFY_SURFACE_REFIRE_CAP` (== 2) holds — a third event on the same
    surface is suppressed. NO ``LoopAgent`` (a fixed-round loop would re-ask every
    turn); the gate is fired by an uncertainty signal, not a loop counter
    (verified project override §24).

Durable human-in-the-loop is built on the SAME native ADK primitive AT-031
(sign-off) uses, verified against ``google-adk==2.1.0``:
``google.adk.tools.long_running_tool.LongRunningFunctionTool`` wrapping
:func:`await_clarify`, which calls ``ToolContext.request_confirmation`` (verified
signature ``(self, *, hint: str | None = None, payload: Any | None = None) -> None``)
so the runner emits the ``adk_request_confirmation`` halt and waits for a confirmed
``ToolConfirmation`` carrying the user's answers.

PRD Reference: §3.5 (surface what the user omitted; apply standards by default),
R15 (single batched authoring surface), §1/§16 (pause for a human).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any

# <no_unverified_apis>: verified against the installed google-adk==2.1.0 wheel
# (see also gates/signoff.py, which uses the identical primitives):
#   - google.adk.tools.long_running_tool.LongRunningFunctionTool
#   - google.adk.tools.tool_context.ToolContext  (.request_confirmation present)
#   - google.adk.tools.tool_confirmation.ToolConfirmation  (@experimental in 2.1.0)
# These are runtime imports (not TYPE_CHECKING-gated) because ADK introspects the
# await_clarify signature to build the tool's function declaration and must resolve
# the ToolContext annotation at runtime. LoopAgent EXISTS in 2.1.0 but is
# deliberately NOT imported (event-driven gate, not a fixed loop — override §24).
from google.adk.tools.long_running_tool import LongRunningFunctionTool
from google.adk.tools.tool_context import ToolContext  # noqa: TC002 — ADK signature introspection

from atelier.models.clarify_models import ClarifyBatch, Gap, OpenQuestion
from atelier.orchestrator.planner import PlanStep, ProposedDefault

if TYPE_CHECKING:
    from atelier.intake.research_findings import ResearchFindings
    from atelier.models.acceptance import AcceptanceCriteria

logger = logging.getLogger(__name__)

#: Stable stage id recorded against the clarify boundary (mirrors SIGNOFF_STAGE_ID).
CLARIFY_STAGE_ID: str = "pre_scope_clarify"

#: Hard cap on clarify events per surface. The first emission plus at most ONE
#: re-fire on a downstream new-ambiguity signal — a third event is suppressed so a
#: pathological re-derivation cannot drip-feed the user indefinitely (R15).
CLARIFY_SURFACE_REFIRE_CAP: int = 2

#: User-answer verbs the gate understands when reconciling a clarify batch.
_CONFIRM_VERBS = frozenset({"confirmed", "confirm", "accept", "accepted", "yes", "ok"})
_OVERRIDE_VERBS = frozenset({"override", "overridden", "reject", "rejected", "no", "change"})


# ---------------------------------------------------------------------------
# Stakes router
# ---------------------------------------------------------------------------


def route_gaps(
    gaps: list[Gap],
    proposed_defaults: list[ProposedDefault],
) -> tuple[list[OpenQuestion], list[ProposedDefault]]:
    """Split gaps into user-facing asks vs. cited silent defaults.

    A gap is ASKED (becomes an :class:`OpenQuestion`) iff :meth:`Gap.must_ask`
    holds — high-stakes OR irreversible OR globally-scoped. Otherwise it is
    silently DEFAULTED: a :class:`ProposedDefault` is emitted, preferring the
    plan's already-cited default for the same ``decision_id`` and falling back to
    a default synthesized from the gap's own citation. A silent default with no
    citation is DROPPED (and the gap is asked instead) — Atelier never applies an
    un-attributable default on the user's behalf (PRD §3.5).

    Args:
        gaps: The classified gaps (typically ``plan.gaps_detail``).
        proposed_defaults: Cited defaults the plan already carries (AT-025).

    Returns:
        ``(open_questions, silent_defaults)``. Both lists are de-duplicated on id.
    """
    by_id = {d.standard_id: d for d in proposed_defaults}
    asks: list[OpenQuestion] = []
    defaults: list[ProposedDefault] = []
    seen_ask: set[str] = set()
    seen_default: set[str] = set()

    for gap in gaps:
        if gap.must_ask():
            if gap.decision_id in seen_ask:
                continue
            seen_ask.add(gap.decision_id)
            asks.append(
                OpenQuestion(
                    id=gap.decision_id,
                    text=_ask_text(gap),
                    why_it_matters=gap.description,
                    dimension=gap.dimension,
                )
            )
            continue

        # Cheap + local + low-stakes: silently default WITH a citation.
        default = by_id.get(gap.decision_id) or _default_from_gap(gap)
        if default is None or not default.citation_url.startswith("http"):
            # No citeable default available — fail closed: ask rather than apply an
            # un-attributable default.
            if gap.decision_id not in seen_ask:
                seen_ask.add(gap.decision_id)
                asks.append(
                    OpenQuestion(
                        id=gap.decision_id,
                        text=_ask_text(gap),
                        why_it_matters=gap.description,
                        dimension=gap.dimension,
                    )
                )
            continue
        if default.standard_id in seen_default:
            continue
        seen_default.add(default.standard_id)
        defaults.append(default)

    return asks, defaults


def _ask_text(gap: Gap) -> str:
    """Compose the user-facing question text for an asked gap."""
    return (
        f"{gap.description} How should Atelier handle the '{gap.dimension}' "
        "decision before it locks scope?"
    )


def _default_from_gap(gap: Gap) -> ProposedDefault | None:
    """Synthesize a :class:`ProposedDefault` from a gap's own cited recommendation."""
    if not gap.citation_url or not gap.recommended_value:
        return None
    return ProposedDefault(
        standard_id=gap.decision_id,
        name=gap.decision_id,
        rule=gap.recommended_value,
        citation_url=gap.citation_url,
        trust_score=0.8,
        domain=gap.dimension,
    )


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


def clarify_gate(
    plan: PlanStep,
    acceptance: AcceptanceCriteria,
    research_findings: ResearchFindings | None,
    emit: Callable[[ClarifyBatch], Any],
) -> ClarifyBatch:
    """Run the clarify gate over a plan; emit ONE batch iff anything is warranted.

    Pure decision function (no network, no class state). It:

      1. Routes ``plan.gaps_detail`` through :func:`route_gaps`.
      2. Falls back to the plan's cited ``proposed_defaults`` when the plan carries
         defaults but no classified gaps (the AT-025-only path) so an
         under-specified brief still surfaces its cited domain defaults.
      3. Builds a single :class:`ClarifyBatch` and calls ``emit`` exactly once —
         and only when the batch is non-empty (a clear brief stays silent).

    Args:
        plan: The enriched :class:`PlanStep` (carries ``gaps_detail`` +
            ``proposed_defaults``).
        acceptance: The current ACCEPTANCE contract (read-only here; mutation
            happens in :func:`apply_clarify_answers` once answers arrive).
        research_findings: The frozen research findings (cited defaults source);
            tolerated as ``None`` (degraded research — gaps still route).
        emit: Sink for the batched clarify event (e.g. the runner's
            ``progress_callback`` adapter). Called at most once.

    Returns:
        The :class:`ClarifyBatch` (empty when the gate stays silent).
    """
    surface = acceptance.required_surfaces[0] if acceptance.required_surfaces else ""

    # The cited-default source: the plan's own ``proposed_defaults`` (AT-025). When
    # the plan has CLASSIFIED gaps but is missing the cited defaults to satisfy
    # them (a degraded ``with_research``), fall back to the domain Tier-1 standards
    # off the findings so a low-stakes gap still gets a cited silent default rather
    # than being forced into an ask. This fallback NEVER manufactures defaults for a
    # plan with no gaps — a clear brief stays silent (acceptance A). ``research_findings``
    # is tolerated as ``None``.
    plan_defaults = list(plan.proposed_defaults)
    if plan.gaps_detail and not plan_defaults and research_findings is not None:
        plan_defaults = [
            ProposedDefault(
                standard_id=s.standard_id,
                name=s.name,
                rule=s.rule,
                citation_url=s.citation_url,
                trust_score=s.trust_score,
                domain=s.domain,
            )
            for s in research_findings.proposed_defaults()
        ]

    asks, silent_defaults = route_gaps(list(plan.gaps_detail), plan_defaults)

    # AT-025-only path: a plan enriched by ``with_research`` (not yet by
    # ``with_clarify_assessment``) carries cited defaults but no classified gaps.
    # Surface those cited defaults so the under-specified brief still gets its
    # domain standards proposed (acceptance B), without inventing asks.
    if not plan.gaps_detail and plan_defaults:
        silent_defaults = _dedupe_defaults(plan_defaults)

    batch = ClarifyBatch(
        open_questions=asks,
        proposed_defaults=silent_defaults,
        gaps=list(plan.gaps_detail),
        surface=surface,
    )

    if batch.is_empty():
        logger.info(
            "AT-030 clarify gate: silent (clear brief)",
            extra={"surface": surface},
        )
        return batch

    logger.info(
        "AT-030 clarify gate: emitting one batch",
        extra={
            "surface": surface,
            "open_questions": len(batch.open_questions),
            "proposed_defaults": len(batch.proposed_defaults),
        },
    )
    emit(batch)
    return batch


def _dedupe_defaults(defaults: list[ProposedDefault]) -> list[ProposedDefault]:
    """De-duplicate proposed defaults on ``standard_id``, preserving order."""
    seen: set[str] = set()
    out: list[ProposedDefault] = []
    for d in defaults:
        if d.standard_id in seen:
            continue
        seen.add(d.standard_id)
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# ACCEPTANCE.json read/modify — confirm writes / override removes
# ---------------------------------------------------------------------------


def confirm_default(
    acceptance: AcceptanceCriteria,
    default: ProposedDefault,
) -> AcceptanceCriteria:
    """Return a copy of ``acceptance`` with ``default``'s standard CONFIRMED.

    Writes ``default.standard_id`` into ``confirmed_standards`` (idempotent — a
    repeat confirm is a no-op). The run-oracle then records the standard as a
    ``source='standard:<id>'`` attribution criterion. AcceptanceCriteria is frozen,
    so this returns a NEW instance.
    """
    if default.standard_id in acceptance.confirmed_standards:
        return acceptance
    updated = [*acceptance.confirmed_standards, default.standard_id]
    return acceptance.model_copy(update={"confirmed_standards": updated})


def override_default(
    acceptance: AcceptanceCriteria,
    default: ProposedDefault,
) -> AcceptanceCriteria:
    """Return a copy of ``acceptance`` with ``default``'s standard REMOVED.

    Overriding a default the user declined removes its ``standard_id`` from
    ``confirmed_standards`` (idempotent — removing an absent id is a no-op), so the
    run-oracle emits no attribution criterion for it.
    """
    if default.standard_id not in acceptance.confirmed_standards:
        return acceptance
    updated = [s for s in acceptance.confirmed_standards if s != default.standard_id]
    return acceptance.model_copy(update={"confirmed_standards": updated})


def apply_clarify_answers(
    acceptance: AcceptanceCriteria,
    batch: ClarifyBatch,
    answers: Mapping[str, str],
) -> AcceptanceCriteria:
    """Apply a user-answer map to the proposed defaults in ``batch``.

    For each proposed default, the user's verb decides the ACCEPTANCE write:
      - a CONFIRM verb (or NO answer — silent defaults are applied unless declined)
        confirms the standard (:func:`confirm_default`);
      - an OVERRIDE verb removes it (:func:`override_default`).

    An unrecognized verb is treated as a confirm (the default stands) and logged,
    rather than silently dropped — :ref:`no_silent_error_suppression`.

    Args:
        acceptance: The current ACCEPTANCE contract.
        batch: The emitted clarify batch (its ``proposed_defaults`` are the
            decisions in play).
        answers: ``{standard_id: verb}``. A missing key means "no answer" →
            the silent default is APPLIED (confirmed).

    Returns:
        A new AcceptanceCriteria reflecting every decision.
    """
    result = acceptance
    for default in batch.proposed_defaults:
        verb = str(answers.get(default.standard_id, "confirmed")).strip().lower()
        if verb in _OVERRIDE_VERBS:
            result = override_default(result, default)
        elif verb in _CONFIRM_VERBS:
            result = confirm_default(result, default)
        else:
            logger.info(
                "AT-030 clarify: unrecognized answer verb %r for %s; treating as confirm",
                verb,
                default.standard_id,
            )
            result = confirm_default(result, default)
    return result


# ---------------------------------------------------------------------------
# Event-driven re-fire cap (no LoopAgent)
# ---------------------------------------------------------------------------


def should_refire(surface: str, prior_event_count: int) -> bool:
    """Decide whether a (re-)fire of the clarify gate is allowed for ``surface``.

    Event-driven, not loop-driven: the caller fires this on a NEW-ambiguity signal
    (e.g. a downstream standard not in the original batch). The initial emission is
    event 0; a single re-fire (event 1) is permitted; the
    :data:`CLARIFY_SURFACE_REFIRE_CAP` (== 2) suppresses any third event on the
    same surface. This bounds the gate at <=2 events/surface even under
    pathological re-derivation (R15) — and replaces a ``LoopAgent`` fixed loop,
    which would re-ask on every turn (verified override §24).

    Args:
        surface: The surface the clarify event concerns (re-fire is per-surface).
        prior_event_count: How many clarify events have already fired for this
            surface (0 for the first).

    Returns:
        ``True`` iff a further clarify event is within the cap.
    """
    if prior_event_count < 0:
        raise ValueError(f"prior_event_count must be >= 0, got {prior_event_count}")
    allowed = prior_event_count < CLARIFY_SURFACE_REFIRE_CAP
    if not allowed:
        logger.info(
            "AT-030 clarify re-fire suppressed (cap reached)",
            extra={"surface": surface, "prior_event_count": prior_event_count},
        )
    return allowed


# ---------------------------------------------------------------------------
# Durable human-in-the-loop tool (native ADK long-running primitive)
# ---------------------------------------------------------------------------


def _clarify_hint(batch: ClarifyBatch) -> str:
    """Compose the human-facing confirmation hint for a clarify batch."""
    n_ask = len(batch.open_questions)
    n_def = len(batch.proposed_defaults)
    return (
        "Atelier found gaps in the brief and is paused for your input. "
        f"{n_ask} question(s) need an answer; {n_def} cited default(s) will be "
        "applied unless you override them. Confirm to proceed."
    )


def await_clarify(
    tool_context: ToolContext,
    batch_summary: str = "",
) -> dict[str, Any]:
    """Long-running clarify tool — requests human input, then yields.

    Mirrors :func:`atelier.gates.signoff.await_signoff`: it calls
    ``ToolContext.request_confirmation`` (verified ADK 2.1.0 symbol) so the runner
    emits the native ``adk_request_confirmation`` halt and stops issuing model
    calls until a confirmed ``ToolConfirmation`` (carrying the user's answers)
    resumes the call. Wrapped in :data:`AWAIT_CLARIFY_TOOL`.

    Args:
        tool_context: ADK tool context (must carry a ``function_call_id``).
        batch_summary: Short human-readable summary of the clarify batch.

    Returns:
        A "pending" response dict.
    """
    tool_context.request_confirmation(
        hint=batch_summary or "Atelier is paused for your clarify input.",
        payload={"stage": CLARIFY_STAGE_ID, "summary": batch_summary},
    )
    return {"status": "AWAITING_CLARIFY", "stage": CLARIFY_STAGE_ID}


#: The production tool: ``await_clarify`` wrapped as a native ADK long-running tool
#: so the runner emits the ``adk_request_confirmation`` halt and waits for answers.
AWAIT_CLARIFY_TOOL: LongRunningFunctionTool = LongRunningFunctionTool(func=await_clarify)
