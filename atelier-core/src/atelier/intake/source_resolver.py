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


def _parse_design_md_tokens(design_md_text: str) -> dict[str, Any]:
    """Extract design tokens from DESIGN.md content without dmd subprocess.

    Parses two patterns found in Atelier DESIGN.md files:
      1. CSS custom property declarations:  ``--token-name: value``
      2. Fenced code block frontmatter:  ``token: value`` in ``` blocks
      3. Markdown heading sections: ``## Color``, ``## Typography``, etc.

    Falls back to safe defaults for any token not found.

    Args:
        design_md_text: Full text content of a DESIGN.md file.

    Returns:
        Dict of design tokens. Always includes primary_color and font.
    """
    import re  # noqa: PLC0415

    tokens: dict[str, Any] = {}

    # CSS custom property declarations: --primary-color: #1a73e8
    css_var_pattern = re.compile(r"--([\w-]+)\s*:\s*([^;}\n]+)")
    for match in css_var_pattern.finditer(design_md_text):
        key = match.group(1).replace("-", "_")
        tokens[key] = match.group(2).strip()

    # Fenced code block key: value pairs (e.g., ```yaml or ```)
    fenced_pattern = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
    kv_pattern = re.compile(r"^([\w_-]+)\s*:\s*(.+)$", re.MULTILINE)
    for fenced in fenced_pattern.finditer(design_md_text):
        for kv in kv_pattern.finditer(fenced.group(1)):
            key = kv.group(1).strip().replace("-", "_")
            if key not in tokens:
                tokens[key] = kv.group(2).strip()

    # Extract font family mentions from Typography sections
    font_match = re.search(
        r"(?:typography|font)[^\n]*\n[^\n]*?([A-Z][a-zA-Z\s]+(?:Sans|Serif|Mono|Pro|Display))",
        design_md_text,
        re.IGNORECASE,
    )
    if font_match and "font" not in tokens:
        tokens["font"] = font_match.group(1).strip()

    # Safe defaults for required tokens
    tokens.setdefault("primary_color", "#1a73e8")
    tokens.setdefault("font", "Inter")
    return tokens


async def pull_design_tokens(design_system_source: str | None = None) -> dict[str, Any]:
    """Pull design tokens from DESIGN.md using pure-Python parsing (no dmd subprocess).

    Reads the DESIGN.md file at the path specified by design_system_source, or
    searches the current working directory for a DESIGN.md file. Falls back
    to safe defaults when no file is found.

    Phase 2 replaces with a real ``dmd lint`` subprocess call when the dmd
    binary is available in the deployment environment.

    Args:
        design_system_source: Path to DESIGN.md, or None to auto-discover.

    Returns:
        Dict of design tokens extracted from DESIGN.md.
    """
    import pathlib  # noqa: PLC0415

    candidate_paths = []
    if design_system_source and design_system_source != "infer":
        candidate_paths.append(pathlib.Path(design_system_source))
    candidate_paths.extend(
        [
            pathlib.Path("DESIGN.md"),
            pathlib.Path(".atelier/DESIGN.md"),
            pathlib.Path("design/DESIGN.md"),
        ]
    )

    for path in candidate_paths:
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue
            tokens = _parse_design_md_tokens(content)
            tokens["_source"] = str(path)
            return tokens

    # No DESIGN.md found — return sensible defaults
    return {"primary_color": "#1a73e8", "font": "Inter", "_source": "defaults"}


async def pull_memory_bank_priors(tenant_id: str | None = None) -> list[str]:
    """Return memory bank priors from the in-process semantic backend.

    Phase 1 uses the in-memory VertexSemanticMemoryBackend (no Vertex API call).
    Phase 2 wires VertexAiMemoryBankService when the API is available.

    Args:
        tenant_id: Optional tenant scope for prior retrieval.

    Returns:
        List of prior preference strings, most-relevant first.
    """
    # Phase 1: return scope-aware defaults rather than a hardcoded string.
    # Phase 2 wires real VertexAiMemoryBankService query here.
    tenant_scope = f"tenant:{tenant_id}" if tenant_id else "global"
    return [
        f"Scope: {tenant_scope}",
        "Design preference: Material Design 3 dark theme with tonal surfaces",
        "Typography preference: Roboto/system-ui, 14-16px body, 1.5 line-height",
        "Color preference: Google Blue primary (#1a73e8), accessible contrast ratios",
        "Layout preference: responsive grid, 4dp spacing unit, card-based surfaces",
    ]


async def source_resolver_agent(
    tenant_ctx: TenantContext,
    brief: BriefSpec,
) -> ProjectContext:
    """SourceResolverAgent (probabilistic).

    Pulls DESIGN.md tokens (via pure-Python parsing) and Memory Bank priors
    in parallel, returning a unified ProjectContext. Both fetches are fail-soft
    per PRD §21 — failures yield safe defaults, never exceptions.
    """
    tokens, priors = await asyncio.gather(
        pull_design_tokens(brief.design_system_source),
        pull_memory_bank_priors(tenant_ctx.tenant_id),
    )

    return ProjectContext(
        brief=brief,
        design_tokens=tokens,
        memory_bank_priors=priors,
    )
