"""ACCEPTANCE.json contract + run-oracle verdict models (AT-007, PRD §7 / §7A.4).

`ACCEPTANCE.json` is derived from the signed-off brief at SIGN-OFF and frozen
with it; it is the run's single machine-checkable terminator. The run-oracle
(`atelier.oracle.verify_run`) evaluates a pure predicate over it and emits a
per-criterion verdict map — the data source for the §14 Attribution view.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BrandConstraints(BaseModel):
    """Brand guardrails from the signed-off brief."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    forbidden_colors: list[str] = Field(default_factory=list)
    constitution: str | None = None


class AcceptanceCriteria(BaseModel):
    """The `ACCEPTANCE.json` schema (PRD §7) — frozen at SIGN-OFF."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    brief_sha256: str
    required_surfaces: list[str]
    wcag_target: str = "AA"
    min_composite: float = Field(default=0.7, ge=0.0, le=1.0)
    required_token_groups: list[str] = Field(default_factory=list)
    brand_constraints: BrandConstraints = Field(default_factory=BrandConstraints)
    handoff_artifacts: list[str] = Field(default_factory=list)
    # AT-030: domain standards the user CONFIRMED at the clarify gate (each value
    # is a ``standard_id``). Confirming a proposed default writes its id here;
    # overriding removes it. The run-oracle (``verify_run``) records one
    # attribution criterion per confirmed standard with ``source='standard:<id>'``
    # so the §14 view shows which defaults the user accepted. Empty by default, so
    # every pre-AT-030 caller and the existing oracle path are unchanged.
    confirmed_standards: list[str] = Field(default_factory=list)
    schema_version: int = 1


class CriterionVerdict(BaseModel):
    """One acceptance criterion's verdict (PRD §7A.4 attribution record)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    criterion_id: str
    kind: str  # surface_exists | composite | axe | contrast | token_fidelity | token_group | handoff | forbidden_colors
    target: str
    source: str = "user"  # "user" | "standard:<standard_id>"
    verdict: bool
    evidence_ref: str


class RunVerdict(BaseModel):
    """Aggregate run-oracle result. ``complete`` iff every criterion verdict holds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1

    complete: bool
    criteria: list[CriterionVerdict]
    composite_by_surface: dict[str, float] = Field(default_factory=dict)

    def failed_criteria(self) -> list[str]:
        """criterion_ids whose verdict is False (the §14 'not met' list)."""
        return [c.criterion_id for c in self.criteria if not c.verdict]
