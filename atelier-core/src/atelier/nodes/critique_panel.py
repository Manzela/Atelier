"""QA critique panel + synthesizer — AT-021 (PRD v2.2 §3.2 / §12 E2).

The QA stage of the DDLC pipeline. Two complementary layers:

1. **Deterministic synthesizer** (:func:`synthesize_panel`) — the *gating* verdict.
   It composes the **deterministic gate-floor** (the N3c gate battery + the
   standalone WCAG contrast oracle, AT-012/013) with the **D-O-R-A-V judge
   composite** (:func:`atelier.nodes.consensus.evaluate_candidate` →
   :meth:`AxisWeights.compute_composite`). A candidate PASSES the panel iff it
   clears *both* — every deterministic gate AND the weighted composite ≥ the
   convergence threshold (0.70). A gate failure forces the reported panel
   composite below the threshold with margin (:data:`GATE_FAIL_CAP`), so a
   skeleton / low-contrast / token-drift candidate can never score ≥ 0.70 on
   judge "vibes" alone. This is the **deterministic-gate-first** spine — the
   anti-inverted-gate guarantee (G2) enforced at the QA layer (AT-021 acceptance
   #3, mirrors AT-010). D-O-R-A-V is retained (PRD line 109 "D-O-R-A-V + Nielsen
   scorecard"); this panel is additive.

2. **ADK `ParallelAgent` critique panel** (:func:`create_critique_panel`) — the
   *narrative* layer. Four critics (Accessibility, Nielsen-heuristic, Visual-QA
   [advisory], Brand/Coherence) run concurrently, each writing a unique
   ``output_key``, producing qualitative critiques that feed the Fixer. Visual-QA
   is **advisory** (never gates, R6). Nielsen votes **presence only** (the ten
   heuristics land in AT-022); severity is never auto-acted
   (``<no_llm_severity_authority>``). Per ADR-0001 we pin ``ParallelAgent`` on the
   current ``google-adk==2.1.0`` and migrate to ``Workflow`` once it ships public.

PRD Reference: §3.2 (QA panel), §12 AT-021, §7 (convergence). ADR-0001.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from google.adk.agents.llm_agent import InstructionProvider, LlmAgent
from google.adk.agents.parallel_agent import (
    ParallelAgent,  # Deprecation(adk-3.0): migrate -> Workflow when public
)
from google.genai import types as genai_types

from atelier.gates.contrast import check_wcag_contrast
from atelier.gates.runner import run_gates
from atelier.models.enums import GateAxis, GateDecision
from atelier.models.model_registry import resolve_model_id
from atelier.models.safety import default_model_armor_config
from atelier.nodes.consensus import CONVERGENCE_DEFAULT, ConsensusEvaluation, evaluate_candidate

if TYPE_CHECKING:
    from uuid import UUID

    from google.adk.agents import BaseAgent
    from google.adk.agents.readonly_context import ReadonlyContext
    from google.adk.models.base_llm import BaseLlm

    from atelier.models.axis_weights import AxisWeights
    from atelier.models.data_contracts import CandidateUI
    from atelier.nodes.llm_judge import JudgeClient

#: The N3c deterministic gate battery the panel floor runs (PRD §6.3 N3c).
PANEL_GATE_AXES: Final[tuple[GateAxis, ...]] = (
    GateAxis.SEMANTIC_HTML,
    GateAxis.LIGHTHOUSE_PERF,
    GateAxis.TOKEN_FIDELITY,
    GateAxis.LIGHTHOUSE_A11Y,
    GateAxis.AXE,
    GateAxis.VISUAL_DIFF,
)

#: When the deterministic floor fails, the reported panel composite is capped at
#: this value — strictly below the 0.70 convergence threshold, with margin — so a
#: gate-failing candidate can never read as "converged" on judge composite alone.
#: Aligns with the data-contract T3 rule (composite < 0.5 OR any gate fails →
#: rejected).
GATE_FAIL_CAP: Final[float] = 0.5


@dataclass(frozen=True)
class PanelVerdict:
    """The QA panel's gating verdict for one candidate.

    Attributes:
        candidate_id: UUID of the evaluated candidate.
        panel_composite: The gated composite in ``[0.0, 1.0]`` — equals the
            raw D-O-R-A-V composite when the deterministic floor passes, else
            capped at :data:`GATE_FAIL_CAP` (< threshold, with margin).
        passed: ``True`` iff the floor passed AND the raw composite ≥ threshold.
        floor_passed: Whether every deterministic gate (battery + contrast) passed.
        raw_composite: The ungated D-O-R-A-V composite (judge "vibes" alone).
        gate_failures: Names of the gate axes that REJECTed (empty if none).
        contrast_passed: Whether the standalone WCAG contrast oracle passed.
        consensus: The full per-axis D-O-R-A-V evaluation (for provenance/trace).
    """

    candidate_id: UUID
    panel_composite: float
    passed: bool
    floor_passed: bool
    raw_composite: float
    gate_failures: tuple[str, ...]
    contrast_passed: bool
    consensus: ConsensusEvaluation


def synthesize_panel(
    candidate: CandidateUI,
    weights: AxisWeights,
    *,
    threshold: float = CONVERGENCE_DEFAULT,
    seed: int | None = None,
    judge_mode: str | None = None,
    judge_client: JudgeClient | None = None,
) -> PanelVerdict:
    """Synthesize the QA panel verdict: deterministic gate-floor ∧ judge composite.

    The synthesizer is the convergence oracle for the QA stage. It is pure with
    respect to its inputs (deterministic given ``seed``) and never trusts the
    judge composite in isolation: a candidate that fails any deterministic gate
    is capped below the convergence threshold regardless of how the probabilistic
    judges scored it (anti-inverted-gate, G2 / AT-021 #3).

    Args:
        candidate: The candidate UI to evaluate.
        weights: D-O-R-A-V axis weights driving :meth:`AxisWeights.compute_composite`.
        threshold: Convergence threshold the composite must meet (default 0.70).
        seed: Forwarded to the anti-bias shuffle so the evaluation is reproducible
            in tests; pass ``None`` in production.
        judge_mode: Optional judge mode forwarded to :func:`evaluate_candidate`.
        judge_client: Optional injected LLM judge client (tests pass a fake).

    Returns:
        A frozen :class:`PanelVerdict`.
    """
    gate_result = run_gates(candidate, list(PANEL_GATE_AXES))
    contrast = check_wcag_contrast(candidate)
    contrast_passed = contrast.decision == GateDecision.PASS

    gate_failures = tuple(
        outcome.axis.value
        for outcome in gate_result.outcomes
        if outcome.decision == GateDecision.REJECT
    )
    floor_passed = gate_result.all_passed and contrast_passed

    consensus = evaluate_candidate(
        candidate,
        weights,
        convergence_threshold=threshold,
        seed=seed,
        judge_mode=judge_mode,
        judge_client=judge_client,
    )
    raw_composite = consensus.composite_score

    panel_composite = raw_composite if floor_passed else round(min(raw_composite, GATE_FAIL_CAP), 4)
    passed = floor_passed and raw_composite >= threshold

    return PanelVerdict(
        candidate_id=candidate.candidate_id,
        panel_composite=panel_composite,
        passed=passed,
        floor_passed=floor_passed,
        raw_composite=raw_composite,
        gate_failures=gate_failures,
        contrast_passed=contrast_passed,
        consensus=consensus,
    )


# ---------------------------------------------------------------------------
# §3.2 ADK ParallelAgent critique panel (narrative layer)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CriticSpec:
    """Static definition of one QA critic (identity + critique brief).

    Attributes:
        name: ADK agent name (unique within the panel).
        output_key: Session-state key this critic writes its critique to.
        description: ADK agent-card description.
        role: The critic's static instruction core.
        advisory: When ``True`` the critic is advisory only — its critique never
            gates convergence (R6); the deterministic floor + judge composite gate.
    """

    name: str
    output_key: str
    description: str
    role: str
    advisory: bool = False


#: The four §3.2 QA critics, each writing a unique session-state key.
CRITIQUE_OUTPUT_KEYS: Final[tuple[str, ...]] = (
    "critique_accessibility",
    "critique_nielsen",
    "critique_visual_qa",
    "critique_brand_coherence",
)

_CRITICS: Final[tuple[_CriticSpec, ...]] = (
    _CriticSpec(
        name="AccessibilityCritic",
        output_key="critique_accessibility",
        description="Audits the design for WCAG 2.2 AA issues (contrast, semantics, ARIA, focus order).",
        role=(
            "You are the Accessibility critic. Audit the design for WCAG 2.2 AA "
            "issues: colour contrast, semantic landmarks, ARIA correctness, focus "
            "order, and keyboard operability. List concrete, located findings — the "
            "deterministic gates already hard-fail clear violations, so add what they "
            "cannot see. Do not assign a numeric verdict; report findings only."
        ),
    ),
    _CriticSpec(
        name="NielsenHeuristicCritic",
        output_key="critique_nielsen",
        description="Flags Nielsen usability-heuristic violations as PRESENCE only (severity is a human gate).",
        role=(
            "You are the Nielsen usability-heuristic critic. For each of Nielsen's "
            "ten heuristics, report only whether a violation is PRESENT or ABSENT in "
            "this design, with a one-line locator. Vote presence only — never assign "
            "or act on severity; severity is a human decision. (The full ten-heuristic "
            "presence vote is completed in AT-022.)"
        ),
    ),
    _CriticSpec(
        name="VisualQACritic",
        output_key="critique_visual_qa",
        description="Advisory visual-quality read (rhythm, hierarchy, balance) — never gates.",
        role=(
            "You are the Visual-QA critic. Give an advisory read on visual quality: "
            "spacing rhythm, typographic hierarchy, alignment, and balance. This is "
            "ADVISORY ONLY and never gates convergence — frame findings as suggestions "
            "the designer may weigh, not blocking defects."
        ),
        advisory=True,
    ),
    _CriticSpec(
        name="BrandCoherenceCritic",
        output_key="critique_brand_coherence",
        description="Checks brand/design-system coherence: token discipline, palette, voice consistency.",
        role=(
            "You are the Brand/Coherence critic. Assess design-system coherence: are "
            "colours, type, spacing, and radii drawn consistently from the design "
            "tokens; is the brand voice coherent across the screen? The zero-tolerance "
            "token gate already hard-fails off-token values — add coherence judgements "
            "it cannot make. Report findings only; do not assign a numeric verdict."
        ),
    ),
)

# Fail-loud invariant: the critic roster and the published critique-key contract
# must never drift apart.
if tuple(critic.output_key for critic in _CRITICS) != CRITIQUE_OUTPUT_KEYS:
    raise RuntimeError(
        "QA critic drift: _CRITICS output_keys do not match CRITIQUE_OUTPUT_KEYS in order"
    )

#: The converged design the critics read from shared session state (the UI
#: Designer's output_key, AT-020). Critics fall back to the user message when absent.
_DESIGN_STATE_KEY: Final[str] = "ui_design"


def _build_critic_instruction(spec: _CriticSpec) -> InstructionProvider:
    """Compose a state-aware instruction provider for one critic.

    The returned callable yields the critic's role brief plus the converged UI
    design from session state when present (so the critic critiques the actual
    artifact rather than a description). A missing design key is skipped — the
    panel never crashes when invoked before a design exists.
    """

    def _provider(ctx: ReadonlyContext) -> str:
        design = ctx.state.get(_DESIGN_STATE_KEY)
        if design:
            return f"{spec.role}\n\n--- DESIGN UNDER REVIEW [{_DESIGN_STATE_KEY}] ---\n{design}"
        return spec.role

    return _provider


def create_critique_panel(*, model: str | BaseLlm | None = None) -> ParallelAgent:  # type: ignore[no-any-unimported]
    """Build the §3.2 QA critique ``ParallelAgent`` (AT-021).

    Four critics run concurrently, each writing a unique ``output_key``
    (:data:`CRITIQUE_OUTPUT_KEYS`). Visual-QA is advisory; Nielsen votes presence
    only. The panel produces narrative critiques; the *gating* verdict is the
    deterministic :func:`synthesize_panel` — the critics inform the Fixer, they do
    not gate convergence (R6).

    Args:
        model: Override the served model — a Vertex model id (str) or, for
            hermetic tests, a ``BaseLlm`` instance. Defaults to
            :func:`resolve_model_id` (AT-024).

    Returns:
        An ADK ``ParallelAgent`` of the four QA critics.
    """
    resolved_model: str | BaseLlm = resolve_model_id() if model is None else model

    sub_agents: list[BaseAgent] = []
    for spec in _CRITICS:
        sub_agents.append(
            LlmAgent(
                name=spec.name,
                model=resolved_model,
                description=spec.description,
                output_key=spec.output_key,
                instruction=_build_critic_instruction(spec),
                generate_content_config=genai_types.GenerateContentConfig(
                    model_armor_config=default_model_armor_config(),
                ),
            )
        )

    return ParallelAgent(
        name="QACritiquePanel",
        description=(
            "Concurrent QA critique panel: Accessibility, Nielsen-heuristic, "
            "Visual-QA (advisory), Brand/Coherence — each writes a unique state key "
            "(AT-021). Gating is the deterministic synthesize_panel; critics inform "
            "the Fixer."
        ),
        sub_agents=sub_agents,
    )


__all__ = [
    "CRITIQUE_OUTPUT_KEYS",
    "GATE_FAIL_CAP",
    "PANEL_GATE_AXES",
    "PanelVerdict",
    "create_critique_panel",
    "synthesize_panel",
]
