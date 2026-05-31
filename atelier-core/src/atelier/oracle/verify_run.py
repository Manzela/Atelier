"""Run-completion oracle (AT-007, PRD §7) — `verify_run`.

A **pure predicate** the runner evaluates: a product run is COMPLETE iff every
`ACCEPTANCE.json` condition holds. The composite is **independently recomputed
from the non-LLM oracles ONLY** (structure/content floor + real axe-core AT-011
+ DTCG token-fidelity AT-012 + WCAG 2.2 AA contrast AT-013). It MUST NOT read
the agent-written `converged`/`composite` (those come from the AT-021 LLM panel
and would let a rubber-stamped skeleton pass — G2 at the run level).

It returns a per-criterion verdict map (the §14 Attribution data source). A
run-oracle that returns true on a known-bad artifact is a P0 defect (§8).

**Oracle independence (§8):** this module imports the deterministic GATES only —
never the generator (`atelier.nodes.*`). A CI grep enforces it (test_verify_run).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from atelier.gates.axe_core import check_axe
from atelier.gates.contrast import check_wcag_contrast
from atelier.gates.deterministic import (
    _COLOR_LITERAL_PATTERN,
    _collect_style_text,
    _is_skeleton,
    _normalize_color,
    check_token_fidelity,
)
from atelier.models.acceptance import AcceptanceCriteria, CriterionVerdict, RunVerdict
from atelier.models.enums import GateDecision

if TYPE_CHECKING:
    from atelier.models.data_contracts import CandidateUI, GateOutcome

#: Number of non-LLM oracle scores averaged into the recomputed composite.
_COMPOSITE_ORACLE_COUNT = 4


def _structure_score(html: str) -> float:
    """100 for substantive HTML, 0 for empty/skeleton (the content floor)."""
    if not html or not html.strip():
        return 0.0
    return 0.0 if _is_skeleton(html) else 100.0


def _surface_composite(
    candidate: CandidateUI,
) -> tuple[float, GateOutcome, GateOutcome, GateOutcome]:
    """Recompute a surface's composite (0-1) from the four non-LLM oracles.

    Returns ``(composite, axe, token, contrast)``. Deliberately ignores any
    agent-written ``converged``/``composite`` on the candidate.
    """
    html = candidate.artifacts.get("index.html", "")
    structure = _structure_score(html)
    axe = check_axe(candidate)
    token = check_token_fidelity(candidate)
    contrast = check_wcag_contrast(candidate)
    oracle_total = structure + (axe.score or 0.0) + (token.score or 0.0) + (contrast.score or 0.0)
    composite = oracle_total / _COMPOSITE_ORACLE_COUNT / 100.0
    return composite, axe, token, contrast


def _find_tokens_json(surfaces: dict[str, CandidateUI]) -> dict[str, object] | None:
    """Parse the shared ``tokens.json`` handoff artifact, if present + valid."""
    for candidate in surfaces.values():
        raw = candidate.artifacts.get("tokens.json")
        if raw:
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, ValueError, TypeError):
                return None  # invalid DTCG → caller treats as missing (fail-closed)
            return parsed if isinstance(parsed, dict) else None
    return None


def verify_run(acceptance: AcceptanceCriteria, surfaces: dict[str, CandidateUI]) -> RunVerdict:
    """Evaluate the §7 run-completion predicate; COMPLETE iff every criterion holds.

    Args:
        acceptance: the frozen ``ACCEPTANCE.json`` contract.
        surfaces: final candidate per required surface name (``{name: CandidateUI}``).
            Agent-written convergence state on the candidates is ignored — the
            oracle recomputes from artifacts.

    Returns:
        :class:`RunVerdict` with ``complete`` and the per-criterion verdict map.
    """
    criteria: list[CriterionVerdict] = []
    composite_by_surface: dict[str, float] = {}

    # ---- Conditions 1-3 + contrast, per required surface ------------------
    for name in acceptance.required_surfaces:
        candidate = surfaces.get(name)
        html = candidate.artifacts.get("index.html", "") if candidate else ""
        exists = bool(candidate and html and html.strip())
        criteria.append(
            CriterionVerdict(
                criterion_id=f"surface:{name}:exists",
                kind="surface_exists",
                target="non-empty index.html",
                verdict=exists,
                evidence_ref="present" if exists else "missing/empty index.html",
            )
        )
        if not candidate:
            composite_by_surface[name] = 0.0
            continue

        composite, axe, token, contrast = _surface_composite(candidate)
        composite_by_surface[name] = round(composite, 4)

        criteria.append(
            CriterionVerdict(
                criterion_id=f"surface:{name}:composite",
                kind="composite",
                target=f">= {acceptance.min_composite}",
                verdict=composite >= acceptance.min_composite,
                evidence_ref=f"recomputed composite {composite:.3f} (non-LLM oracles only)",
            )
        )
        criteria.append(
            CriterionVerdict(
                criterion_id=f"surface:{name}:axe",
                kind="axe",
                target="0 critical/serious",
                verdict=axe.decision is GateDecision.PASS,
                evidence_ref=axe.diagnostic,
            )
        )
        criteria.append(
            CriterionVerdict(
                criterion_id=f"surface:{name}:contrast",
                kind="contrast",
                target=f"WCAG {acceptance.wcag_target}",
                verdict=contrast.decision is GateDecision.PASS,
                evidence_ref=contrast.diagnostic,
            )
        )
        criteria.append(
            CriterionVerdict(
                criterion_id=f"surface:{name}:token_fidelity",
                kind="token_fidelity",
                target="0 off-token color literals",
                verdict=token.decision is GateDecision.PASS,
                evidence_ref=token.diagnostic,
            )
        )

    # ---- Condition 4 (cont.): required DTCG token groups present ----------
    tokens_json = _find_tokens_json(surfaces)
    for group in acceptance.required_token_groups:
        present = bool(tokens_json) and group in tokens_json  # type: ignore[operator]
        criteria.append(
            CriterionVerdict(
                criterion_id=f"token_group:{group}",
                kind="token_group",
                target=f"tokens.json has '{group}'",
                source="standard:dtcg",
                verdict=present,
                evidence_ref="present"
                if present
                else "missing from tokens.json (or no valid tokens.json)",
            )
        )

    # ---- Condition 5: handoff bundle complete -----------------------------
    all_artifact_names = {n for c in surfaces.values() for n in c.artifacts}
    for artifact in acceptance.handoff_artifacts:
        # "style-dictionary outputs" is a logical group verified by the AT-050 CI
        # build gate; the oracle checks the concrete file artifacts it can see.
        if "style-dictionary" in artifact.lower():
            present = bool(
                tokens_json
            )  # SD compiles from a valid tokens.json (AT-050 CI proves the build)
            ref = "tokens.json valid (SD round-trip gated by AT-050 CI)"
        else:
            present = artifact in all_artifact_names
            ref = "present" if present else "missing from handoff bundle"
        criteria.append(
            CriterionVerdict(
                criterion_id=f"handoff:{artifact}",
                kind="handoff",
                target=artifact,
                verdict=present,
                evidence_ref=ref,
            )
        )

    # ---- Brand: forbidden colors must not appear in any surface's styles --
    forbidden = {_normalize_color(c) for c in acceptance.brand_constraints.forbidden_colors}
    if forbidden:
        used: set[str] = set()
        for candidate in surfaces.values():
            style_text = _collect_style_text(candidate.artifacts)
            used |= {_normalize_color(lit) for lit in _COLOR_LITERAL_PATTERN.findall(style_text)}
        violations = sorted(forbidden & used)
        criteria.append(
            CriterionVerdict(
                criterion_id="forbidden_colors",
                kind="forbidden_colors",
                target=f"none of {sorted(forbidden)}",
                verdict=not violations,
                evidence_ref="clean" if not violations else f"used forbidden: {violations}",
            )
        )

    # Condition 6 (no orphan criteria) is structural: every criterion above is
    # derived from an ACCEPTANCE.json field, so the map IS the criteria set.
    complete = all(c.verdict for c in criteria)
    return RunVerdict(
        complete=complete, criteria=criteria, composite_by_surface=composite_by_surface
    )
