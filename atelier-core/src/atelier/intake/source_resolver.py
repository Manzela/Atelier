"""N2 Source Resolver — pulls context from DESIGN.md and Memory Bank.

Phase 1 Gate requires a deterministic gate and a probabilistic agent.
"""

import asyncio
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from atelier.intake.brief_spec import BriefSpec
from atelier.models.data_contracts import TenantContext


class ProjectContext(BaseModel):
    """Output of N2 Source Resolver.

    Contains the parsed brief, design system tokens, and memory bank priors.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    brief: BriefSpec
    design_tokens: dict[str, Any] = Field(default_factory=dict)
    memory_bank_priors: list[str] = Field(default_factory=list)
    schema_version: int = 1


def source_resolver_gate(tenant_ctx: TenantContext, brief: BriefSpec) -> bool:
    """SourceResolverGate (deterministic).

    Passes if descriptor is present OR brief contains path.
    """
    if tenant_ctx.descriptor is not None:
        return True
    return brief.design_system_source is not None and brief.design_system_source != "infer"


async def pull_design_tokens() -> dict[str, Any]:
    """Stub for pulling DESIGN.md tokens via dmd lint subprocess."""
    # In a real implementation this would run `dmd lint`
    return {"primary_color": "#000000", "font": "Inter"}


async def pull_memory_bank_priors() -> list[str]:
    """Stub for pulling memory bank priors."""
    # In a real implementation this would use VertexAiMemoryBankService
    return ["Prior preference: dark mode"]


async def source_resolver_agent(
    tenant_ctx: TenantContext,  # noqa: ARG001
    brief: BriefSpec,
) -> ProjectContext:
    """SourceResolverAgent (probabilistic).

    Pulls DESIGN.md tokens and Memory Bank priors, returning unified ProjectContext.
    """
    # The real ADK agent would be defined using SequentialAgent or ParallelAgent.
    # We use simple asyncio here for the underlying fetching logic.
    tokens, priors = await asyncio.gather(pull_design_tokens(), pull_memory_bank_priors())

    return ProjectContext(
        brief=brief,
        design_tokens=tokens,
        memory_bank_priors=priors,
    )
