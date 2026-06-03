"""N2 Source Resolver — pulls context from DESIGN.md and Memory Bank.

v1.0 implementation Gate requires a deterministic gate and a probabilistic agent.
"""

import asyncio
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from atelier.durability.design_system_persister import load_persisted_design_system
from atelier.intake.brief_spec import BriefSpec
from atelier.models.data_contracts import TenantContext
from atelier.models.design_system import DesignSystemRecord, serialize_priors


class ProjectContext(BaseModel):
    """Output of N2 Source Resolver.

    Contains the parsed brief, design system tokens, and memory bank priors.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    brief: BriefSpec
    design_tokens: dict[str, Any] = Field(default_factory=dict)
    memory_bank_priors: list[str] = Field(default_factory=list)
    #: AT-053: the tenant's PERSISTED design system, auto-applied from a prior
    #: signed-off run. ``None`` when no system is persisted yet (the tenant's
    #: first run). The AT-012 token-fidelity gate enforces this set zero-tolerance
    #: — an off-system literal in this run is REJECTed, never silently merged.
    persisted_design_tokens: dict[str, Any] | None = None
    schema_version: int = 1


def source_resolver_gate(tenant_ctx: TenantContext, brief: BriefSpec) -> bool:
    """SourceResolverGate (deterministic precondition for N2).

    N2's ``source_resolver_agent`` is fail-soft (PRD §21): it always returns a
    valid ``ProjectContext``. It resolves from a tenant descriptor or an explicit
    DESIGN.md path when one is present, and otherwise auto-discovers a DESIGN.md
    and falls back to safe design-token defaults. All four source modes resolve:

      - ``tenant_ctx.descriptor`` present → resolve from prior project state
      - explicit DESIGN.md path           → parse that file
      - ``"infer"``                       → PADI auto-discovery (StackChoice docs)
      - ``None``                          → auto-discover, then safe defaults

    ``"infer"`` and ``None`` are first-class resolution modes, not failures. An
    earlier revision returned ``False`` for both, which broke the golden path:
    ``brief_parser`` never sets ``design_system_source`` (so it defaults to
    ``None``) and the API constructs ``TenantContext`` without a descriptor, so
    *every* first brief failed N2 before reaching generation. The gate now fails
    closed only on a structurally malformed source — an empty-string path, which
    is neither a real file nor an auto-discovery sentinel.
    """
    if tenant_ctx.descriptor is not None:
        return True
    # None (auto-discover + defaults), "infer" (PADI), and any non-empty path are
    # all resolvable by the fail-soft agent. Only an empty-string path is invalid.
    return brief.design_system_source is None or bool(brief.design_system_source)


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

    A ``dmd lint`` subprocess call provides higher-fidelity token validation
    when the dmd binary is available in the deployment environment.

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


async def load_tenant_design_system(
    tenant_id: str | None = None,
) -> DesignSystemRecord | None:
    """Load the tenant's PERSISTED design system (AT-053), or ``None``.

    Fail-soft: a missing system or a persistence outage returns ``None`` (no
    persisted system → the tenant's first run, or a degraded auto-apply) — it
    never raises. Critically, a ``None`` here degrades only *auto-apply*; it does
    NOT disable enforcement of a system that already loaded into a run.

    Args:
        tenant_id: The tenant scope. ``None`` short-circuits to ``None`` (no
            tenant → nothing to load).

    Returns:
        The persisted :class:`DesignSystemRecord`, or ``None``.
    """
    if not tenant_id:
        return None
    return await load_persisted_design_system(tenant_id)


async def pull_memory_bank_priors(tenant_id: str | None = None) -> list[str]:
    """Return memory-bank priors for ``tenant_id`` — the persisted system, auto-applied.

    AT-053: the priors are now sourced from the tenant's PERSISTED design system
    (written at the prior run's sign-off), so run #2 inherits run #1's tokens +
    constitution with NO re-specification. When no system is persisted yet (a
    tenant's first run), this returns an empty list — there are no priors to
    apply, and the generator works from the brief alone. Fail-soft: a persistence
    outage degrades to an empty prior list (logged downstream), never an
    exception.

    The structured authorized token set used by the AT-012 enforcement gate is
    carried separately on ``ProjectContext.persisted_design_tokens`` (set in
    :func:`source_resolver_agent`); these strings are the human/model-readable
    rendering of the same system for the generator anchor.

    Args:
        tenant_id: The tenant scope for prior retrieval.

    Returns:
        List of prior strings (empty when no system is persisted), most-relevant
        first.
    """
    record = await load_tenant_design_system(tenant_id)
    if record is None:
        return []
    return serialize_priors(record)


async def source_resolver_agent(
    tenant_ctx: TenantContext,
    brief: BriefSpec,
) -> ProjectContext:
    """SourceResolverAgent (probabilistic).

    Pulls DESIGN.md tokens (via pure-Python parsing), the tenant's persisted
    design system (AT-053), and Memory Bank priors, returning a unified
    ProjectContext. Every fetch is fail-soft per PRD §21 — failures yield safe
    defaults, never exceptions.

    AT-053 auto-apply: when the tenant has a PERSISTED design system, its tokens
    are auto-applied as the run's defaults (the brief did not re-specify them) and
    its authorized set is threaded onto ``persisted_design_tokens`` so the AT-012
    gate can enforce it zero-tolerance. Explicit DESIGN.md tokens for THIS run
    still win over the inherited defaults (an in-run override is layered on top of
    the persisted base — the gate then decides fidelity), so a tenant can evolve a
    system; but absent any explicit source, run #2 simply inherits run #1.
    """
    tokens, record = await asyncio.gather(
        pull_design_tokens(brief.design_system_source),
        load_tenant_design_system(tenant_ctx.tenant_id),
    )

    persisted_tokens: dict[str, Any] | None = None
    if record is not None:
        persisted_tokens = dict(record.tokens)
        priors = serialize_priors(record)
        # Auto-apply: the persisted system is the BASE. When this run resolved
        # tokens from a REAL DESIGN.md (an explicit in-run override), those layer
        # on top so a tenant can evolve the system and the gate then judges
        # fidelity. But when ``pull_design_tokens`` only returned its synthetic
        # safe-defaults (no DESIGN.md present — ``_source == "defaults"``), those
        # placeholders MUST NOT clobber the persisted system: run #2 with no
        # explicit source inherits run #1 verbatim (no re-specification). This is
        # the whole point — an absent source means "use my saved system", not
        # "reset to library defaults".
        is_synthetic_defaults = tokens.get("_source") == "defaults"
        merged = dict(persisted_tokens)
        if not is_synthetic_defaults:
            merged.update(tokens)
        elif "_source" in tokens:
            # Preserve only the provenance marker; keep the persisted values.
            merged["_source"] = tokens["_source"]
        tokens = merged
    else:
        priors = []

    return ProjectContext(
        brief=brief,
        design_tokens=tokens,
        memory_bank_priors=priors,
        persisted_design_tokens=persisted_tokens,
    )
