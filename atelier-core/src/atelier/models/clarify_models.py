"""AT-030 clarify-gate value objects — Gap, OpenQuestion, ClarifyBatch.

AT-025 already owns the *data* the planner carries on :class:`PlanStep`
(``open_questions``, ``gaps``, ``proposed_defaults`` with the
:class:`atelier.orchestrator.planner.ProposedDefault` record). AT-030 owns the
*decision logic* that turns an under-specified brief into a single, batched
clarify event. These models are the typed inputs/outputs of that logic:

    - :class:`Gap` — one detected coverage gap, classified by the three axes the
      stakes router reads (reversibility, blast_radius, stakes) plus optional
      cited-default provenance for the silent-default path.
    - :class:`OpenQuestion` — a user-facing ask the router emits when a gap is
      too high-stakes/irreversible/global to default silently.
    - :class:`ClarifyBatch` — the single batched emission (PRD §3.5, R15: ask
      once, batched, never drip-fed). Carries the asks AND the cited silent
      defaults so the surface renders one coherent clarify panel.

All models are frozen + ``extra='forbid'`` per the BriefSpec invariants — these
are contracts, not mutable scratch.

PRD Reference: §3.5 (apply domain standards by default; surface what the user
omitted), R15 (single batched authoring surface).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from atelier.orchestrator.planner import ProposedDefault

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


# ---------------------------------------------------------------------------
# Resolve the planner<->clarify_models forward refs without a hard import cycle.
#
# This module does NOT import planner at module top (only under TYPE_CHECKING), so
# importing it never triggers planner. ``ClarifyBatch.proposed_defaults`` refers to
# planner's ``ProposedDefault`` by forward ref; we resolve it here with a local
# runtime import — at this point ``ProposedDefault`` is already defined in planner
# regardless of which module the interpreter loaded first (planner defines it before
# its own bottom-of-module rebuild imports ``Gap``/``OpenQuestion`` from here).
# ---------------------------------------------------------------------------
from atelier.orchestrator.planner import ProposedDefault  # noqa: E402

ClarifyBatch.model_rebuild(_types_namespace={"ProposedDefault": ProposedDefault})
