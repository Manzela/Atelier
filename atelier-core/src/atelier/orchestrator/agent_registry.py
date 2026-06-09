"""Agent registry — a single, read-only descriptor view of every Atelier agent.

This module does **not** define any new agent logic. It is a thin, introspective
projection over the real, module-level agent definitions that already drive the
pipeline, so a dashboard / A2A surface / observability layer can enumerate "what
agents exist, which model each is routed to, what prompt each carries, and how
they hand off" without re-deriving any of it.

Single source of truth — every descriptor is built from the live symbols:

    * 6 DDLC specialists  -> ``specialists.get_specialist_specs()``
      (model via ``calibrate_model(spec.task_type)``; tools = ``["stitch_mcp"]``
      iff ``spec.uses_stitch``; prompt = ``spec.role``).
    * Planner (N0)        -> ``planner._PLANNER_SYSTEM_PROMPT`` + ``PlannerAgent``.
    * Brief parser (N1)   -> ``brief_parser.BriefParserAgent`` (no system prompt;
      it constrains output via ``output_schema=BriefSpec``).
    * 5 D-O-R-A-V judges  -> ``llm_judge.JUDGE_PROMPTS`` + ``JUDGE_MODEL_CONFIG``.
    * 4 QA critics        -> ``critique_panel.get_critic_specs()``.
    * Fixer (N3e)         -> ``fixer._FIXER_SYSTEM_PROMPT`` + ``FIXER_MODEL``.

Prompt provenance: specialists carry a runtime override hook
(``_fetch_prompt_from_agent_registry``, gated by ``ATELIER_AGENT_REGISTRY_ENABLED``)
that can pull a prompt from Vertex AI Agent Registry. The descriptor records the
*static* role brief as ``prompt`` (the fallback / build-time source of truth) and
flags ``prompt_source`` as ``"vertex_agent_registry"`` when the hook is enabled,
else ``"static"``. All other agents are always ``"static"``.

This module is import-light by design: it reads already-instantiated, frozen
module constants and pure routing functions. It does not construct any
``LlmAgent`` (no Vertex / network / live-credential dependency), so it is fully
hermetic and fail-soft-friendly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Final, Literal

from atelier.models.model_registry import (
    FIXER_MODEL,
    JUDGE_MODEL_CONFIG,
    TaskType,
    calibrate_model,
    resolve_model_id,
)
from atelier.nodes.fixer import _FIXER_SYSTEM_PROMPT
from atelier.nodes.llm_judge import JUDGE_PROMPTS
from atelier.orchestrator.planner import _PLANNER_SYSTEM_PROMPT
from atelier.orchestrator.specialists import get_specialist_specs

#: The agent ``kind`` taxonomy. Each agent is exactly one of these.
AgentKind = Literal["planner", "specialist", "judge", "critic", "fixer", "intake"]

#: The env var that flips specialist prompt resolution from the static role
#: brief to a Vertex AI Agent Registry lookup (mirrors specialists.py exactly).
_AGENT_REGISTRY_ENV: Final[str] = "ATELIER_AGENT_REGISTRY_ENABLED"
_TRUTHY: Final[frozenset[str]] = frozenset({"1", "true", "yes"})

#: The Stitch MCP toolset label exposed on the (single) Stitch-carrying
#: specialist. Matches the toolset wired in ``specialists.create_specialist_pipeline``.
_STITCH_TOOL: Final[str] = "stitch_mcp"

#: Maps each D-O-R-A-V judge axis to the ``TaskType`` that routes its model, so
#: the descriptor's ``model_id`` reflects the same calibration the live judge uses
#: (``LLMJudge.model_spec`` -> ``JUDGE_MODEL_CONFIG[axis]`` whose model_id is
#: ``calibrate_model(<this task>)``). Keyed by the shared ``JUDGE_PROMPTS`` /
#: ``JUDGE_MODEL_CONFIG`` axis name.
_JUDGE_AXIS_TASK: Final[dict[str, TaskType]] = {
    "brand": TaskType.JUDGE_DESIGN,
    "originality": TaskType.JUDGE_ORIGINALITY,
    "relevance": TaskType.JUDGE_RELEVANCE,
    "accessibility": TaskType.JUDGE_ACCESSIBILITY,
    "visual_clarity": TaskType.JUDGE_VISUAL,
}


@dataclass(frozen=True)
class AgentDescriptor:
    """Read-only identity + wiring record for one Atelier agent.

    Frozen value object — a projection over a live agent definition, safe to
    serialize for a dashboard, A2A agent card, or trace legibility surface.

    Attributes:
        id: Stable, unique slug for the agent (snake/kebab-free; e.g.
            ``"specialist_uidesigner"``, ``"judge_originality"``).
        name: The ADK agent name (or a human label where no ADK name exists).
        kind: One of ``planner | specialist | judge | critic | fixer | intake``.
        adk_type: The ADK/agent primitive the live node uses
            (e.g. ``"LlmAgent"``, ``"SequentialAgent member"``).
        description: One-line agent-card description.
        model_id: The Vertex model id this agent is routed to at build time.
        task_type: The :class:`TaskType` used for model calibration, when the
            agent routes through ``calibrate_model``; ``None`` for agents that
            use a fixed ``ModelSpec`` or the operator-pinned default.
        tools: External tool labels the agent carries (e.g. ``["stitch_mcp"]``).
        prompt: The static system prompt / role brief (the build-time source of
            truth; see ``prompt_source`` for runtime override provenance).
        prompt_source: ``"static"`` (the prompt is the in-repo constant) or
            ``"vertex_agent_registry"`` (a runtime hook may override it).
        upstream_keys: Session-state keys this agent folds into its instruction
            (its hand-off inputs).
        output_key: Session-state key this agent writes its result to, or
            ``None`` (e.g. judges/parsers that return a structured value).
        subagent_of: The container agent this is a member of, or ``None`` for a
            top-level agent.
    """

    id: str
    name: str
    kind: AgentKind
    adk_type: str
    description: str
    model_id: str
    task_type: TaskType | None
    tools: list[str]
    prompt: str
    prompt_source: str
    upstream_keys: list[str] = field(default_factory=list)
    output_key: str | None = None
    subagent_of: str | None = None


def _specialist_prompt_source() -> str:
    """Resolve the specialist prompt provenance from the live env gate.

    Mirrors ``specialists._fetch_prompt_from_agent_registry``: when
    ``ATELIER_AGENT_REGISTRY_ENABLED`` is truthy the runtime prompt may be
    fetched from Vertex AI Agent Registry (fail-soft to the static role); the
    descriptor records that override capability. Otherwise the prompt is the
    in-repo constant.
    """
    enabled = os.getenv(_AGENT_REGISTRY_ENV, "false").strip().lower() in _TRUTHY
    return "vertex_agent_registry" if enabled else "static"


def _specialist_descriptors() -> list[AgentDescriptor]:
    """Build descriptors for the 6 DDLC specialists (N3a, AT-020)."""
    prompt_source = _specialist_prompt_source()
    descriptors: list[AgentDescriptor] = []
    for spec in get_specialist_specs():
        descriptors.append(
            AgentDescriptor(
                id=f"specialist_{spec.name.lower()}",
                name=spec.name,
                kind="specialist",
                adk_type="LlmAgent (DDLCSpecialistPipeline member)",
                description=spec.description,
                model_id=calibrate_model(spec.task_type),
                task_type=spec.task_type,
                tools=[_STITCH_TOOL] if spec.uses_stitch else [],
                prompt=spec.role,
                prompt_source=prompt_source,
                upstream_keys=list(spec.upstream_keys),
                output_key=spec.output_key,
                subagent_of="DDLCSpecialistPipeline",
            )
        )
    return descriptors


def _planner_descriptor() -> AgentDescriptor:
    """Build the descriptor for the PlannerAgent (N0)."""
    return AgentDescriptor(
        id="planner",
        name="atelier_planner",
        kind="planner",
        adk_type="LlmAgent",
        description=(
            "Dynamic DAG router: analyzes the brief and emits a PlanStep that "
            "drives downstream routing (WRAI, ensemble_k, axis weights, "
            "constitution, surfaces)."
        ),
        # The planner uses the operator-pinned default (resolve_model_id), not a
        # per-task calibrated model, so task_type is None.
        model_id=resolve_model_id(),
        task_type=None,
        tools=[],
        prompt=_PLANNER_SYSTEM_PROMPT,
        prompt_source="static",
        upstream_keys=[],
        output_key=None,
    )


def _brief_parser_descriptor() -> AgentDescriptor:
    """Build the descriptor for the BriefParserAgent (N1, intake).

    The brief parser has no system prompt — it constrains the model via
    ``output_schema=BriefSpec``. The descriptor records that explicitly so the
    UI does not render a misleading empty prompt as "missing".
    """
    return AgentDescriptor(
        id="intake_brief_parser",
        name="brief_parser_llm",
        kind="intake",
        adk_type="LlmAgent (output_schema=BriefSpec)",
        description=(
            "Extracts a structured BriefSpec from validated brief text; "
            "schema-constrained (no free-form system prompt)."
        ),
        model_id=resolve_model_id(),
        task_type=None,
        tools=[],
        prompt="(schema-constrained: output_schema=BriefSpec; no system prompt)",
        prompt_source="static",
        upstream_keys=[],
        output_key=None,
    )


def _judge_descriptors() -> list[AgentDescriptor]:
    """Build descriptors for the 5 D-O-R-A-V judges (N3d)."""
    descriptors: list[AgentDescriptor] = []
    for axis, (system_prompt, _user_template) in JUDGE_PROMPTS.items():
        spec = JUDGE_MODEL_CONFIG[axis]
        descriptors.append(
            AgentDescriptor(
                id=f"judge_{axis}",
                name=spec.display_name,
                kind="judge",
                adk_type="LLMJudge",
                description=(
                    f"D-O-R-A-V {axis} judge: scores candidates on the {axis} "
                    "axis (fail-soft to a heuristic scorer when Vertex is down)."
                ),
                model_id=spec.model_id,
                task_type=_JUDGE_AXIS_TASK[axis],
                tools=[],
                prompt=system_prompt,
                prompt_source="static",
                upstream_keys=[],
                output_key=None,
            )
        )
    return descriptors


def _critic_descriptors() -> list[AgentDescriptor]:
    """Build descriptors for the 4 QA critics (AT-021).

    The critics are read here lazily to avoid a hard import cost when the
    registry is consumed only for specialists/judges, and to keep the import
    graph shallow. Critics route through the operator-pinned default model
    (``resolve_model_id`` in ``create_critique_panel``).
    """
    from atelier.nodes.critique_panel import get_critic_specs  # noqa: PLC0415

    descriptors: list[AgentDescriptor] = []
    for spec in get_critic_specs():
        descriptors.append(
            AgentDescriptor(
                id=f"critic_{spec.name.lower()}",
                name=spec.name,
                kind="critic",
                adk_type="LlmAgent (critique ParallelAgent member)",
                description=spec.description,
                model_id=resolve_model_id(),
                task_type=None,
                tools=[],
                prompt=spec.role,
                prompt_source="static",
                upstream_keys=["ui_design"],
                output_key=spec.output_key,
                subagent_of="CritiquePanel",
            )
        )
    return descriptors


def _fixer_descriptor() -> AgentDescriptor:
    """Build the descriptor for the FixerAgent (N3e)."""
    return AgentDescriptor(
        id="fixer",
        name="atelier_fixer",
        kind="fixer",
        adk_type="LlmAgent (output_schema=FixerDirective)",
        description=(
            "Analyzes gate failures and low axis scores and proposes a "
            "FixerDirective (mutations + prompt amendments) for the next iteration."
        ),
        model_id=FIXER_MODEL.model_id,
        task_type=TaskType.FIXER,
        tools=[],
        prompt=_FIXER_SYSTEM_PROMPT,
        prompt_source="static",
        upstream_keys=[],
        output_key=None,
    )


def get_agent_registry() -> list[AgentDescriptor]:
    """Return read-only descriptors for every Atelier agent.

    The complete agent roster, each projected from its live, module-level
    definition (no agent is constructed; nothing touches Vertex / network):
    the planner, the brief parser, the 6 DDLC specialists, the 5 D-O-R-A-V
    judges, the 4 QA critics, and the fixer.

    Returns:
        A list of :class:`AgentDescriptor`, ordered by pipeline position
        (planner -> intake -> specialists -> judges -> critics -> fixer).
    """
    registry: list[AgentDescriptor] = [
        _planner_descriptor(),
        _brief_parser_descriptor(),
        *_specialist_descriptors(),
        *_judge_descriptors(),
        *_critic_descriptors(),
        _fixer_descriptor(),
    ]
    return registry
