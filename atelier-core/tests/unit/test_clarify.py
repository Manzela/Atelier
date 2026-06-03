"""AT-030 — clarify-gate decision logic (uncertainty-gated, event-driven).

These tests pin the contract for the seven acceptance clauses:

  (A) a CLEAR brief asks 0 questions and proposes 0 defaults;
  (B) an under-specified brief in a recognizable domain emits ONE batch with
      >=1 *cited* proposed_default covering a domain-standard component the user
      omitted;
  (C) a high-stakes / irreversible gap is ALWAYS asked (open_questions), never
      silently defaulted;
  (D) a cheap + locally-reversible gap is silently defaulted WITH a citation
      (proposed_defaults), never asked;
  (E) confirming a default writes the matching ACCEPTANCE.json criterion;
      overriding it removes that criterion;
  (F) questions are batched (one emission), not drip-fed;
  (G) a synthetic new-ambiguity re-fires the gate exactly once — a
      <=2-events-per-surface cap holds.

AT-025 owns the *data* on ``PlanStep`` (open_questions/gaps/proposed_defaults);
AT-030 owns the *decision logic* tested here. The decision logic is a pure
function (``clarify_gate``) plus a small assessment (``assess_specification``)
and the ACCEPTANCE read/modify helpers — none of which call the network.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from atelier.gates.clarify import (
    CLARIFY_SURFACE_REFIRE_CAP,
    ClarifyBatch,
    apply_clarify_answers,
    clarify_gate,
    confirm_default,
    override_default,
    should_refire,
)
from atelier.intake.research_findings import ResearchFindings
from atelier.intake.standards_extractor import load_standards_pack
from atelier.models.acceptance import AcceptanceCriteria
from atelier.models.clarify_models import Gap, OpenQuestion, ProposedDefault
from atelier.orchestrator.planner import (
    PlanStep,
    assess_specification,
)

# ---------------------------------------------------------------------------
# Fixtures — real research findings (no mocks for the standards substrate)
# ---------------------------------------------------------------------------

#: A fully-specified brief: a single concrete component, a named visual register,
#: an explicit stack, an explicit accessibility target, and a stated audience.
_CLEAR_BRIEF = (
    "Build a single primary Submit button for a contact form. "
    "Visual register: brutalist, monochrome. Stack: vanilla HTML + CSS. "
    "Accessibility target: WCAG 2.2 AA. Audience: desktop users on a marketing "
    "landing page. The button submits the form and shows a success message; it "
    "performs no destructive or irreversible action."
)

#: An under-specified brief that *does* land in a recognizable domain
#: (saas-dashboard) but omits the standard components the domain expects
#: (card cap, progressive disclosure, non-color encodings).
_UNDERSPEC_DASHBOARD_BRIEF = "Make me an analytics dashboard."


def _findings(brief: str) -> ResearchFindings:
    """Real ResearchFindings: cross-cutting substrate + the brief's domain pack."""
    from atelier.intake.standards_extractor import infer_domain

    domain = infer_domain(brief)
    return ResearchFindings(
        applicable_standards=load_standards_pack(domain),
        domain=domain,
    )


def _acceptance(*, surfaces: list[str] | None = None) -> AcceptanceCriteria:
    return AcceptanceCriteria(
        run_id="run-test",
        brief_sha256="0" * 64,
        required_surfaces=surfaces or ["analytics dashboard"],
    )


def _cheap_local_gap() -> Gap:
    return Gap(
        decision_id="dash-card-cap",
        dimension="scope",
        description="Default summary card count not specified.",
        reversibility="cheap",
        blast_radius="local",
        stakes="low",
        recommended_value="5-7 cards",
        citation_url="https://www.pencilandpaper.io/articles/ux-pattern-analysis-data-tables",
        rationale="Respect working-memory limits (dash-card-cap).",
    )


def _high_stakes_gap() -> Gap:
    return Gap(
        decision_id="auth-method",
        dimension="safety",
        description="Authentication method for the admin surface not specified.",
        reversibility="costly",
        blast_radius="global",
        stakes="high",
        recommended_value=None,
        citation_url=None,
        rationale=None,
    )


# ---------------------------------------------------------------------------
# (A) CLEAR brief asks 0 questions  [first_failing_test]
# ---------------------------------------------------------------------------


def test_assess_specification_clear_brief_returns_no_questions() -> None:
    """A fully-specified brief scores low ambiguity and surfaces no unsafe gaps."""
    assessment = assess_specification(_CLEAR_BRIEF)
    assert assessment.ambiguity_score <= 0.3
    assert assessment.unsafe_gaps == []

    plan = PlanStep().with_clarify_assessment(assessment, _findings(_CLEAR_BRIEF))
    assert len(plan.open_questions) == 0
    assert len(plan.proposed_defaults) == 0


# ---------------------------------------------------------------------------
# (B) UNDER-SPECIFIED brief -> ONE batch with >=1 cited proposed_default
# ---------------------------------------------------------------------------


def test_assess_specification_under_specified_yields_gaps_and_defaults() -> None:
    """An under-specified brief scores high ambiguity across multiple dimensions."""
    assessment = assess_specification(_UNDERSPEC_DASHBOARD_BRIEF)
    assert assessment.ambiguity_score >= 0.33
    # At least two dimensions are ambiguous (the >=2-ambiguous emission rule).
    ambiguous = [d for d, s in assessment.dimension_scores.items() if s < 0.5]
    assert len(ambiguous) >= 2


def test_clarify_gate_under_specified_emits_one_cited_default() -> None:
    """ONE batch, >=1 proposed_default covering an omitted domain-standard, cited."""
    findings = _findings(_UNDERSPEC_DASHBOARD_BRIEF)
    plan = PlanStep().with_clarify_assessment(
        assess_specification(_UNDERSPEC_DASHBOARD_BRIEF), findings
    )
    emitted: list[ClarifyBatch] = []
    batch = clarify_gate(
        plan=plan,
        acceptance=_acceptance(),
        research_findings=findings,
        emit=emitted.append,
    )
    # Exactly one emission (batched, not drip-fed).
    assert len(emitted) == 1
    assert emitted[0] is batch
    # >=1 cited proposed_default, each carrying provenance + rationale.
    assert len(batch.proposed_defaults) >= 1
    for d in batch.proposed_defaults:
        assert d.citation_url.startswith("http")
        assert d.rule
    # The default covers a domain-standard component (e.g. card cap) the
    # bare brief never mentioned.
    covered = {d.standard_id for d in batch.proposed_defaults}
    assert covered & {"dash-card-cap", "dash-progressive-disclosure", "dash-not-color-only"}


# ---------------------------------------------------------------------------
# (C) HIGH-STAKES / IRREVERSIBLE gap is ALWAYS asked
# ---------------------------------------------------------------------------


def test_clarify_gate_high_stakes_gap_in_open_questions_not_defaults() -> None:
    """A high-stakes/irreversible/global gap routes to open_questions only."""
    gap = _high_stakes_gap()
    plan = PlanStep(gaps_detail=[gap])
    batch = clarify_gate(
        plan=plan,
        acceptance=_acceptance(),
        research_findings=_findings(_UNDERSPEC_DASHBOARD_BRIEF),
        emit=lambda _b: None,
    )
    asked_ids = {q.id for q in batch.open_questions}
    defaulted_ids = {d.standard_id for d in batch.proposed_defaults}
    assert gap.decision_id in asked_ids
    assert gap.decision_id not in defaulted_ids


# ---------------------------------------------------------------------------
# (D) CHEAP + LOCAL gap silently defaulted WITH citation
# ---------------------------------------------------------------------------


def test_clarify_gate_cheap_local_gap_in_defaults_with_citation() -> None:
    """A cheap + locally-reversible + low-stakes gap is defaulted, cited, not asked."""
    gap = _cheap_local_gap()
    plan = PlanStep(gaps_detail=[gap])
    batch = clarify_gate(
        plan=plan,
        acceptance=_acceptance(),
        research_findings=_findings(_UNDERSPEC_DASHBOARD_BRIEF),
        emit=lambda _b: None,
    )
    defaulted = {d.standard_id: d for d in batch.proposed_defaults}
    asked_ids = {q.id for q in batch.open_questions}
    assert gap.decision_id in defaulted
    assert gap.decision_id not in asked_ids
    # The silent default still carries a citation (provenance is non-negotiable).
    assert defaulted[gap.decision_id].citation_url.startswith("http")


# ---------------------------------------------------------------------------
# (E) CONFIRM writes ACCEPTANCE criterion / OVERRIDE removes it
# ---------------------------------------------------------------------------


def test_clarify_gate_confirm_default_writes_acceptance_criterion() -> None:
    """Confirming a proposed default writes a matching ACCEPTANCE criterion."""
    default = ProposedDefault(
        standard_id="dash-card-cap",
        name="Pencil & Paper — Data-table UX",
        rule="Cap the default summary to 5-7 cards/metrics.",
        citation_url="https://www.pencilandpaper.io/articles/ux-pattern-analysis-data-tables",
        trust_score=0.8,
        domain="saas-dashboard",
    )
    acceptance = _acceptance()
    before = set(acceptance.confirmed_standards)
    updated = confirm_default(acceptance, default)
    # The matching criterion now exists, attributed to the standard.
    assert default.standard_id in updated.confirmed_standards
    assert set(updated.confirmed_standards) - before == {default.standard_id}
    # The run-oracle surfaces it as an attribution criterion (source=standard:<id>).
    from atelier.oracle.verify_run import verify_run

    verdict = verify_run(updated, {})
    standard_rows = [c for c in verdict.criteria if c.kind == "standard"]
    assert any(c.source == f"standard:{default.standard_id}" and c.verdict for c in standard_rows)


def test_clarify_gate_override_removes_criterion() -> None:
    """Overriding a previously-confirmed default removes its ACCEPTANCE criterion."""
    default = ProposedDefault(
        standard_id="dash-card-cap",
        name="Pencil & Paper — Data-table UX",
        rule="Cap the default summary to 5-7 cards/metrics.",
        citation_url="https://www.pencilandpaper.io/articles/ux-pattern-analysis-data-tables",
        trust_score=0.8,
        domain="saas-dashboard",
    )
    acceptance = confirm_default(_acceptance(), default)
    assert default.standard_id in acceptance.confirmed_standards
    reverted = override_default(acceptance, default)
    assert default.standard_id not in reverted.confirmed_standards


def test_apply_clarify_answers_confirm_and_override_roundtrip() -> None:
    """A user-answer map drives confirm (write) and override (remove) together."""
    confirmed = ProposedDefault(
        standard_id="dash-card-cap",
        name="cap",
        rule="Cap cards 5-7.",
        citation_url="https://www.pencilandpaper.io/articles/ux-pattern-analysis-data-tables",
        trust_score=0.8,
        domain="saas-dashboard",
    )
    overridden = ProposedDefault(
        standard_id="dash-bar-over-pie",
        name="bars",
        rule="Prefer bars over pie.",
        citation_url="https://www.pencilandpaper.io/articles/ux-pattern-analysis-data-tables",
        trust_score=0.8,
        domain="saas-dashboard",
    )
    batch = ClarifyBatch(proposed_defaults=[confirmed, overridden])
    # Both start applied (a silent default is applied unless overridden); the
    # user explicitly overrides the second.
    acceptance = _acceptance()
    acceptance = confirm_default(acceptance, confirmed)
    acceptance = confirm_default(acceptance, overridden)
    answers = {"dash-card-cap": "confirmed", "dash-bar-over-pie": "override"}
    result = apply_clarify_answers(acceptance, batch, answers)
    assert "dash-card-cap" in result.confirmed_standards
    assert "dash-bar-over-pie" not in result.confirmed_standards


# ---------------------------------------------------------------------------
# (F) batched, not drip-fed
# ---------------------------------------------------------------------------


def test_clarify_gate_one_batch_emission() -> None:
    """All questions + defaults ship in a single emission (one ClarifyBatch)."""
    plan = PlanStep(gaps_detail=[_high_stakes_gap(), _cheap_local_gap()])
    emitted: list[ClarifyBatch] = []
    clarify_gate(
        plan=plan,
        acceptance=_acceptance(),
        research_findings=_findings(_UNDERSPEC_DASHBOARD_BRIEF),
        emit=emitted.append,
    )
    assert len(emitted) == 1
    # The single batch carries both routes at once (no iterative drip).
    assert len(emitted[0].open_questions) == 1
    assert len(emitted[0].proposed_defaults) >= 1


# ---------------------------------------------------------------------------
# (G) synthetic new-ambiguity re-fires exactly once (<=2-events/surface cap)
# ---------------------------------------------------------------------------


def test_clarify_gate_re_fire_cap_enforced_at_two_events() -> None:
    """A new downstream ambiguity re-fires once; a third is suppressed by the cap."""
    surface = "analytics dashboard"
    # Event 1: the initial gate emission on this surface.
    assert should_refire(surface, prior_event_count=0) is True
    # Event 2: a synthetic new standard (not in the original batch) re-fires once.
    assert should_refire(surface, prior_event_count=1) is True
    # Event 3: the cap holds — no third emission on the same surface.
    assert should_refire(surface, prior_event_count=2) is False
    assert CLARIFY_SURFACE_REFIRE_CAP == 2


def test_clarify_gate_clear_brief_does_not_emit() -> None:
    """A clear brief (no gaps, low ambiguity) emits nothing — the gate stays silent."""
    plan = PlanStep().with_clarify_assessment(
        assess_specification(_CLEAR_BRIEF), _findings(_CLEAR_BRIEF)
    )
    emitted: list[ClarifyBatch] = []
    batch = clarify_gate(
        plan=plan,
        acceptance=_acceptance(surfaces=["submit button"]),
        research_findings=_findings(_CLEAR_BRIEF),
        emit=emitted.append,
    )
    assert emitted == []
    assert batch.open_questions == []
    assert batch.proposed_defaults == []


def test_clarify_models_are_frozen_and_strict() -> None:
    """Gap / OpenQuestion are immutable and reject unknown fields."""
    q = OpenQuestion(id="q1", text="?", why_it_matters="m", dimension="scope")
    with pytest.raises(Exception):
        q.text = "mutated"  # type: ignore[misc]
    with pytest.raises(Exception):
        OpenQuestion(id="q1", text="?", why_it_matters="m", dimension="scope", junk=1)  # type: ignore[call-arg]


# Touch UTC/datetime/uuid4 imports so the lints stay honest if fixtures evolve.
_ = (UTC, datetime, uuid4)
