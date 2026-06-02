"""N3a DDLC role-specialist pipeline — AT-020 (replaces the K=3 generic ensemble).

PRD v2.2 §3.2 / §12 E2: the root Coordinator dispatches a ``SequentialAgent`` of
six Design-Development-Life-Cycle (DDLC) specialists. Each writes a unique
``output_key`` into shared session state, in production order::

    UX Researcher        -> ux_research
    IA / User-Flows      -> ia_flows
    Wireframer           -> wireframe
    UI Designer          -> ui_design
    Interaction Designer -> interaction_spec
    Token Generator      -> tokens

Each specialist's instruction is *state-aware*: it folds in the upstream
specialists' outputs (and, for the UX Researcher, the WRAI ``research_findings``)
so the sequence is a genuine hand-off rather than six independent prompts. Only
the UI Designer carries the Stitch MCP toolset (the visual-generation step); the
others are reasoning/spec roles. Stitch degradation is surfaced to the caller
exactly as the prior ensemble did (AG-06 / FIX-3).

ADK best practice (google-adk 2.1.0, the pinned wheel): every agent carries a
``description`` (its agent-card identity, used for observability and any future
LLM-routed delegation); dynamic, state-aware instructions use an
``InstructionProvider`` callable rather than ``{var}`` string templating (which
raises on a missing key); cross-agent hand-off uses ``output_key`` state writes;
and Model Armor is attached via ``generate_content_config`` on every model call.

.. note:: ``SequentialAgent`` carries an upstream deprecation hint pointing at a
    ``Workflow`` API. In the pinned ``google-adk==2.1.0`` ``google.adk.Workflow``
    **is** public, but it is a node-graph DSL (constructor takes ``edges`` /
    ``graph`` / ``max_concurrency``, not ``sub_agents``) — migrating is a
    non-trivial Node/Edge rewrite, not a version bump. So ``SequentialAgent``
    remains the correct primitive for an ordered sub-agent container and is what
    PRD §3.2 / AT-020 mandate. Per ADR-0001 (wrap-don't-fork) we defer the rewrite.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from google.adk.agents.llm_agent import InstructionProvider, LlmAgent
from google.adk.agents.sequential_agent import (
    SequentialAgent,  # Deprecated: Workflow (public node-graph DSL, not a sub_agents container) — rewrite deferred per ADR-0001
)
from google.genai import types as genai_types

from atelier.integrations.stitch_mcp import (
    StitchDegradationInfo,
    try_get_stitch_mcp_toolset,
)
from atelier.models.model_armor_callbacks import (
    model_armor_after_callback,
    model_armor_before_callback,
)
from atelier.models.model_registry import resolve_model_id
from atelier.models.safety import default_model_armor_config

if TYPE_CHECKING:
    from google.adk.agents import BaseAgent
    from google.adk.agents.readonly_context import ReadonlyContext
    from google.adk.models.base_llm import BaseLlm
    from google.adk.tools.base_toolset import BaseToolset

#: PRD v2.2 §3.2 / §12 AT-020 — the DDLC specialists' ``output_key`` set, in
#: production order. Single source of truth: the runner, the legibility trace
#: (AT-026), and the AT-020 acceptance oracle all import this tuple.
SPECIALIST_OUTPUT_KEYS: Final[tuple[str, ...]] = (
    "ux_research",
    "ia_flows",
    "wireframe",
    "ui_design",
    "interaction_spec",
    "tokens",
)

#: WRAI grounded-research findings land here (AT-025); the UX Researcher consumes
#: them when present, else works from the signed-off brief in the user message.
_WRAI_STATE_KEY: Final[str] = "research_findings"


@dataclass(frozen=True)
class _SpecialistSpec:
    """Static definition of one DDLC specialist — identity + hand-off contract.

    Attributes:
        name: ADK agent name (unique within the pipeline).
        output_key: Session-state key this specialist writes its result to.
        description: ADK agent-card description (observability / routing).
        role: The senior-design-partner role brief (the static instruction core).
        upstream_keys: State keys this specialist folds into its instruction when
            present (its hand-off inputs from earlier specialists / WRAI).
        uses_stitch: Whether this specialist receives the Stitch MCP toolset.
    """

    name: str
    output_key: str
    description: str
    role: str
    upstream_keys: tuple[str, ...] = field(default_factory=tuple)
    uses_stitch: bool = False


_SPECIALISTS: Final[tuple[_SpecialistSpec, ...]] = (
    _SpecialistSpec(
        name="UXResearcher",
        output_key="ux_research",
        description="Synthesizes users, jobs-to-be-done, and UX success criteria from the brief and WRAI findings.",
        role=(
            "You are the UX Researcher on a senior design team. From the signed-off "
            "brief and any grounded research findings, synthesize: the target users "
            "and their jobs-to-be-done, the top user needs and pain points, and the "
            "measurable UX success criteria this design must satisfy. Be specific and "
            "evidence-led, and name the standards a credible team would treat as table "
            "stakes for this project type. Output a tight research brief."
        ),
        upstream_keys=(_WRAI_STATE_KEY,),
    ),
    _SpecialistSpec(
        name="IAFlowDesigner",
        output_key="ia_flows",
        description="Defines the information architecture, navigation model, and primary user flows.",
        role=(
            "You are the Information Architect. Using the UX research, define the "
            "information architecture and the primary user flows: the screen/section "
            "inventory, the navigation model, and the step-by-step flow for each key "
            "task. Make the structure explicit enough that a wireframer can lay it out "
            "without guessing."
        ),
        upstream_keys=("ux_research",),
    ),
    _SpecialistSpec(
        name="Wireframer",
        output_key="wireframe",
        description="Produces low-fidelity structural layouts (semantic regions, hierarchy) per screen.",
        role=(
            "You are the Wireframer. Translate the information architecture into a "
            "low-fidelity structural layout for each screen: semantic regions "
            "(header / nav / main / aside / footer), content hierarchy, and component "
            "placement. Describe structure and hierarchy, not visual style — that is "
            "the UI Designer's job."
        ),
        upstream_keys=("ia_flows", "ux_research"),
    ),
    _SpecialistSpec(
        name="UIDesigner",
        output_key="ui_design",
        description="Generates the high-fidelity, self-contained HTML/CSS for the screen (Stitch-first).",
        role=(
            "You are the UI Designer. Produce the high-fidelity, self-contained "
            "HTML/CSS for the requested screen, faithfully realizing the wireframe and "
            "honoring the design tokens and any reference styling. Prefer the Stitch "
            "design tool when available; if it is unavailable, generate accessible, "
            "semantic HTML/CSS directly. The output must be a single shippable artifact."
        ),
        upstream_keys=("wireframe", _WRAI_STATE_KEY),
        uses_stitch=True,
    ),
    _SpecialistSpec(
        name="InteractionDesigner",
        output_key="interaction_spec",
        description="Specifies component states, transitions, and keyboard/ARIA interaction behavior.",
        role=(
            "You are the Interaction Designer. For the UI design, specify the "
            "interaction and motion behavior: component states (hover / focus / active "
            "/ disabled), transitions and micro-interactions, and keyboard + ARIA "
            "behaviors. Every interactive element must have a defined focus-visible "
            "state. "
            'Emit ONLY a JSON object: {"interactions":[{"element":"<selector/name>",'
            '"trigger":"hover|focus|active|disabled|keyboard",'
            '"effect":"<what changes>"},...]}. '
            "Include at least one focus or keyboard interaction so every interactive "
            "element has a focus-visible state."
        ),
        upstream_keys=("ui_design",),
    ),
    _SpecialistSpec(
        name="TokenGenerator",
        output_key="tokens",
        description="Extracts the design into a DTCG-shaped, semantically-named design-token set.",
        role=(
            "You are the Token Generator. Extract the design decisions in the UI "
            "design into a DTCG-shaped design-token set (color, typography, spacing, "
            "radius, elevation) with semantic names. These tokens are the single "
            "source of truth the zero-tolerance token gate enforces, so they must "
            "cover every value the design uses."
        ),
        upstream_keys=("ui_design",),
    ),
)

# Fail-loud invariant: the specialist roster and the published output-key contract
# must never drift apart (the runner + AT-020 oracle depend on this equality).
if tuple(spec.output_key for spec in _SPECIALISTS) != SPECIALIST_OUTPUT_KEYS:
    raise RuntimeError(
        "DDLC specialist drift: _SPECIALISTS output_keys do not match "
        "SPECIALIST_OUTPUT_KEYS in order"
    )


def _build_instruction(spec: _SpecialistSpec) -> InstructionProvider:
    """Compose a state-aware instruction provider for one specialist.

    The returned callable yields the role brief plus any upstream specialist
    outputs already in session state, so the sequence is a genuine hand-off.
    Missing upstream keys are skipped — the pipeline never crashes on a
    not-yet-produced or absent upstream artifact (e.g. WRAI unavailable, R8).
    """

    def _provider(ctx: ReadonlyContext) -> str:
        sections = [spec.role]
        for key in spec.upstream_keys:
            upstream = ctx.state.get(key)
            if upstream:
                sections.append(f"\n\n--- UPSTREAM CONTEXT [{key}] ---\n{upstream}")
        return "".join(sections)

    return _provider


def create_specialist_pipeline(
    *, model: str | BaseLlm | None = None
) -> tuple[SequentialAgent, StitchDegradationInfo]:  # type: ignore[no-any-unimported]
    """Build the DDLC role-specialist ``SequentialAgent`` (N3a) — AT-020.

    Replaces the K=3 generic ``ParallelAgent`` ensemble with six DDLC specialists
    that run in production order, each writing a unique ``output_key`` into shared
    session state (:data:`SPECIALIST_OUTPUT_KEYS`). Only the UI Designer holds the
    Stitch MCP toolset; degradation is surfaced to the caller (AG-06 / FIX-3).

    Args:
        model: Override the served model — a Vertex model id (str) or, for
            hermetic tests, a ``BaseLlm`` instance. Defaults to the pinned served
            id from :func:`resolve_model_id` (AT-024).

    Returns:
        ``(SequentialAgent, StitchDegradationInfo)`` — the pipeline plus the
        Stitch degradation state for session metadata.
    """
    resolved_model: str | BaseLlm = resolve_model_id() if model is None else model
    stitch_toolset, degradation = try_get_stitch_mcp_toolset()

    sub_agents: list[BaseAgent] = []
    for spec in _SPECIALISTS:
        toolsets: Sequence[BaseToolset] = (
            [stitch_toolset] if spec.uses_stitch and stitch_toolset is not None else []
        )
        sub_agents.append(
            LlmAgent(
                name=spec.name,
                model=resolved_model,
                description=spec.description,
                output_key=spec.output_key,
                instruction=_build_instruction(spec),
                before_model_callback=model_armor_before_callback,
                after_model_callback=model_armor_after_callback,
                tools=list(toolsets),
                generate_content_config=genai_types.GenerateContentConfig(
                    model_armor_config=default_model_armor_config(),
                ),
            )
        )

    return (
        SequentialAgent(
            name="DDLCSpecialistPipeline",
            description=(
                "Ordered DDLC design pipeline: UX research -> IA/flows -> wireframe "
                "-> UI design -> interaction spec -> design tokens (AT-020)."
            ),
            sub_agents=sub_agents,
        ),
        degradation,
    )
