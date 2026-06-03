"""AT-030 clarify-gate value objects — Gap, OpenQuestion, ProposedDefault, ClarifyBatch.

AT-025 owns the *data* the planner carries on :class:`PlanStep`
(``open_questions``, ``gaps``, ``proposed_defaults`` with the
:class:`ProposedDefault` record). AT-030 owns the *decision logic* that turns an
under-specified brief into a single, batched clarify event. These models are the
typed inputs/outputs of that logic:

    - :class:`Gap` — one detected coverage gap, classified by the three axes the
      stakes router reads (reversibility, blast_radius, stakes) plus optional
      cited-default provenance for the silent-default path.
    - :class:`OpenQuestion` — a user-facing ask the router emits when a gap is
      too high-stakes/irreversible/global to default silently.
    - :class:`ProposedDefault` — a cited, trust-scored domain Tier-1 standard the
      planner proposes applying by default (AT-025). Defined here so the value
      object flows one-way ``clarify_models → planner`` (no import cycle).
    - :class:`ClarifyBatch` — the single batched emission (PRD §3.5, R15: ask
      once, batched, never drip-fed). Carries the asks AND the cited silent
      defaults so the surface renders one coherent clarify panel.

All models are frozen + ``extra='forbid'`` per the BriefSpec invariants — these
are contracts, not mutable scratch.

PRD Reference: §3.5 (apply domain standards by default; surface what the user
omitted), R15 (single batched authoring surface).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: The three classification axes the stakes router reads off a :class:`Gap`.
Reversibility = Literal["cheap", "costly"]
BlastRadius = Literal["local", "global"]
Stakes = Literal["low", "high"]


class Gap(BaseModel):
    """One detected coverage gap in the brief, classified for the stakes router.

    The router asks (emits an :class:`OpenQuestion`) when a gap is high-stakes OR
    irreversible (``reversibility == "costly"``) OR globally-scoped
    (``blast_radius == "global"``); otherwise it silently applies the cited
    default. A gap that carries a default MUST carry its citation — a default
    Atelier applies on the user's behalf is always attributable (PRD §3.5).

    Attributes:
        decision_id: Stable id for the decision this gap concerns. When the gap
            maps to a domain standard this is the ``standard_id`` so the silent
            default and the ACCEPTANCE criterion share one key.
        dimension: Which of the six assessment dimensions surfaced this gap
            (objective | done_criteria | scope | constraints | environment | safety).
        description: Human-readable statement of what is missing.
        reversibility: ``"cheap"`` (locally undoable) vs ``"costly"`` (expensive
            or irreversible to change later).
        blast_radius: ``"local"`` (one surface/component) vs ``"global"``
            (cross-cutting; touches auth/data/brand/legal).
        stakes: ``"low"`` vs ``"high"`` — the headline severity.
        recommended_value: The value Atelier would apply by default (if any).
        citation_url: Provenance for the recommended default (required when the
            gap is silently defaulted; ``None`` for ask-only gaps).
        rationale: Why the default is recommended (surfaced in the clarify panel).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str = Field(min_length=1)
    dimension: str
    description: str
    reversibility: Reversibility
    blast_radius: BlastRadius
    stakes: Stakes
    recommended_value: str | None = None
    citation_url: str | None = None
    rationale: str | None = None

    def must_ask(self) -> bool:
        """True iff this gap is too consequential to default silently.

        Fail-closed bias: any high-stakes, irreversible, or globally-scoped gap is
        asked. Only a cheap + local + low-stakes gap is eligible for a silent,
        cited default.
        """
        return (
            self.stakes == "high" or self.reversibility == "costly" or self.blast_radius == "global"
        )


class OpenQuestion(BaseModel):
    """A user-facing ask emitted for a gap the router will not default silently.

    Attributes:
        id: Stable id (mirrors the originating gap's ``decision_id`` so an answer
            can be reconciled back to the gap and written to the brief transcript).
        text: The question shown to the user.
        why_it_matters: One sentence on the downstream consequence — so the user
            understands *why* Atelier paused rather than guessing.
        dimension: The assessment dimension this question covers.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    why_it_matters: str = Field(min_length=1)
    dimension: str


class ProposedDefault(BaseModel):
    """A domain Tier-1 standard the planner proposes applying by default (AT-025).

    Surfaced from :class:`atelier.intake.research_findings.ResearchFindings` so the
    clarify-gate (AT-030) can decide ask-vs-silent. Each carries its full
    provenance — a default Atelier applies on the user's behalf is always
    attributable to a cited, trust-scored source (PRD §3.5).

    Defined here (not in :mod:`atelier.orchestrator.planner`) so the value object
    flows one-way ``clarify_models → planner``: planner imports it as a real
    top-level name, clarify_models imports nothing from planner. This keeps the
    two modules acyclic (CodeQL ``py/unsafe-cyclic-import``).

    Attributes:
        standard_id: The source standard's stable id (e.g. ``"dash-card-cap"``).
        name: Human-readable source title.
        rule: The imperative rule text being proposed as a default.
        citation_url: The authoritative source URL (never empty).
        trust_score: Trust seed in ``[0.0, 1.0]``.
        domain: The project-type scope the standard applies to.
    """

    model_config = ConfigDict(frozen=True)

    standard_id: str
    name: str
    rule: str
    citation_url: str
    trust_score: float = Field(ge=0.0, le=1.0)
    domain: str


class ClarifyBatch(BaseModel):
    """The single batched clarify emission (R15: ask once, never drip-fed).

    Carries both the user-facing asks (``open_questions``) and the cited silent
    defaults (``proposed_defaults``) plus the raw classified ``gaps`` for audit,
    so the clarify panel renders one coherent surface.

    Attributes:
        open_questions: Asks the user must answer before scope-lock.
        proposed_defaults: Cited domain-standard defaults Atelier applies unless
            the user overrides them.
        gaps: The classified gaps that produced the above (audit trail).
        surface: The surface name this batch was gated for (re-fire bookkeeping).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    open_questions: list[OpenQuestion] = Field(default_factory=list)
    proposed_defaults: list[ProposedDefault] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    surface: str = ""

    def is_empty(self) -> bool:
        """True when there is nothing to ask and nothing to propose."""
        return not self.open_questions and not self.proposed_defaults
