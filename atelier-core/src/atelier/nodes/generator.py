"""N3a Generator — template-based candidate UI synthesis.

This is the v1.0 implementation implementation of the N3a node in the 8-node DAG.
v1.0 implementation is intentionally template-driven: no LLM calls, no Vertex AI, no
network I/O. The generator's job is to produce a deterministic, gate-clean
:class:`CandidateUI` from a :class:`BriefSpec` + :class:`SurfaceState` pair
so that downstream gates (N3c) and tests have something concrete to chew on.

The ADK-orchestrated LLM path (respecting ``visual_register`` and ``stack``)
routes through the DDLC SequentialAgent when fully wired. The function
signatures defined here are stable — the generation strategy is the only
thing that changes between phases.

PRD Reference: §6.3 N3a (Generator)
ADR Reference: 0007 (worktree discipline) — v1.0 implementation scope only
"""

from uuid import UUID, uuid4

from atelier.a2ui.surface import build_design_system_surface
from atelier.intake.brief_spec import BriefSpec, VisualRegister
from atelier.models.data_contracts import CandidateUI, SurfaceState

# ---------------------------------------------------------------------------
# Per-register palette / typography lookup
# ---------------------------------------------------------------------------

#: Per-visual-register design token defaults. Each entry is a tuple of
#: ``(primary, surface, ink, font_stack)`` — a deliberately small set of
#: tokens that exercises the token-fidelity gate without bloating the
#: template. Tokens are derived from the project's DESIGN.md when available.
_REGISTER_TOKENS: dict[VisualRegister, tuple[str, str, str, str]] = {
    VisualRegister.EDITORIAL: (
        "#1a1a1a",
        "#fafaf7",
        "#0a0a0a",
        '"Newsreader", "Georgia", serif',
    ),
    VisualRegister.DENSE_DATA: (
        "#0a66c2",
        "#f4f6fa",
        "#0a0a0a",
        '"Inter", "Helvetica Neue", sans-serif',
    ),
    VisualRegister.PLAYFUL: (
        "#ff5d8f",
        "#fff8ed",
        "#2a1a3d",
        '"Quicksand", "Comic Neue", sans-serif',
    ),
    VisualRegister.BRUTALIST: (
        "#000000",
        "#ffffff",
        "#000000",
        '"Space Mono", "Courier New", monospace',
    ),
    VisualRegister.CORPORATE: (
        "#0b3d91",
        "#ffffff",
        "#1f1f1f",
        '"Public Sans", "Arial", sans-serif',
    ),
    VisualRegister.CUSTOM: (
        "#444444",
        "#fefefe",
        "#111111",
        '"Inter", "Helvetica Neue", sans-serif',
    ),
}


def _register_token_map(register: VisualRegister) -> dict[str, str]:
    """Flatten a register's token tuple to the ``{name: value}`` shape A2UI needs.

    Mirrors the CSS custom properties emitted by :func:`_render_css` (so the
    governed A2UI design-system panel shows exactly the tokens the generated HTML
    actually consumes via ``var()``). The names use the Style-Dictionary kebab
    naming the frontend AT-044 panel expects (``color-primary`` etc.).

    Args:
        register: The :class:`VisualRegister` whose token tuple drives the map.

    Returns:
        Ordered ``{token_name: value}`` mapping for the four register tokens plus
        the shared spacing base.
    """
    primary, surface, ink, font_stack = _REGISTER_TOKENS[register]
    return {
        "color-primary": primary,
        "color-surface": surface,
        "color-ink": ink,
        "font-body": font_stack,
        "space-base": "1rem",
    }


# ---------------------------------------------------------------------------
# Template synthesis
# ---------------------------------------------------------------------------


def _escape_html(text: str) -> str:
    """Minimal HTML escape — enough for body text in the template path.

    Args:
        text: Untrusted string to inline into HTML body content.

    Returns:
        The same string with ``&``, ``<``, ``>``, and ``"`` replaced by their
        named entities.
    """
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def _render_css(register: VisualRegister) -> str:
    """Render the CSS artifact for a given visual register.

    The CSS declares every token as a CSS custom property and references each
    one at least once via ``var()``. This keeps the token-fidelity gate
    (:func:`atelier.gates.deterministic.check_token_fidelity`) happy on
    every template-generated candidate.

    Args:
        register: The :class:`VisualRegister` whose tokens drive the output.

    Returns:
        A multi-line CSS string with token declarations under ``:root`` and
        ``var()`` references in selectors that map to the HTML landmarks.
    """
    primary, surface, ink, font_stack = _REGISTER_TOKENS[register]
    return f""":root {{
  --color-primary: {primary};
  --color-surface: {surface};
  --color-ink: {ink};
  --font-body: {font_stack};
  --space-base: 1rem;
}}

body {{
  background: var(--color-surface);
  color: var(--color-ink);
  font-family: var(--font-body);
  margin: 0;
  padding: 0;
}}

header,
nav,
main,
section,
article,
footer {{
  padding: var(--space-base);
}}

header {{
  border-bottom: 1px solid var(--color-primary);
}}

nav a {{
  color: var(--color-primary);
  margin-right: var(--space-base);
}}

footer {{
  border-top: 1px solid var(--color-primary);
}}
"""


def _render_html(brief: BriefSpec, surface: SurfaceState) -> str:
    """Render the HTML artifact for a surface, including all 6 semantic landmarks.

    Embedding every HTML5 landmark guarantees a PASS from
    :func:`atelier.gates.deterministic.check_semantic_html`. The intent and
    surface brief are escaped before inlining to avoid template injection
    from untrusted user input.

    Args:
        brief: The :class:`BriefSpec` whose ``intent`` drives the page title.
        surface: The :class:`SurfaceState` whose ``brief`` drives the article
            copy.

    Returns:
        A complete HTML document string ready to be written as
        ``index.html``.
    """
    title = _escape_html(surface.name)
    intent = _escape_html(brief.intent)
    brief_text = _escape_html(surface.brief)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <link rel="stylesheet" href="main.css" />
</head>
<body>
  <header>
    <h1>{title}</h1>
    <p>{intent}</p>
  </header>
  <nav>
    <a href="#main">Skip to content</a>
  </nav>
  <main id="main">
    <section>
      <article>
        <h2>{title}</h2>
        <p>{brief_text}</p>
      </article>
    </section>
  </main>
  <footer>
    <small>Generated by Atelier (template path)</small>
  </footer>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_candidate(
    brief: BriefSpec,
    surface: SurfaceState,
    *,
    iteration: int = 0,
    parent_candidate_id: UUID | None = None,
) -> CandidateUI:
    """Synthesize a :class:`CandidateUI` from a BriefSpec + SurfaceState.

    v1.0 implementation is template-driven: the brief's :class:`VisualRegister` selects a
    palette + typography combination, and the surface's name + brief drive the
    page content. The output is deterministic given the same inputs (modulo
    the random ``candidate_id``).

    Args:
        brief: The frozen :class:`BriefSpec` carrying intent and visual
            register.
        surface: The :class:`SurfaceState` whose ``surface_id`` is wired into
            the returned candidate.
        iteration: Zero-indexed generation iteration number. Increments on
            every regenerate / fixer pass; defaults to ``0`` for the first
            generation.
        parent_candidate_id: For crossover mutations, the parent's
            :class:`UUID`. ``None`` for initial generation.

    Returns:
        A :class:`CandidateUI` with two artifacts (``index.html`` and
        ``main.css``), no ``mutation_op`` (template-path is not a mutation),
        and a fresh ``candidate_id``.

    Examples:
        >>> from datetime import UTC, datetime
        >>> from uuid import uuid4
        >>> from atelier.intake.brief_spec import (
        ...     BriefSpec,
        ...     VisualRegister,
        ...     StackChoice,
        ...     ComplianceLevel,
        ...     ConvergenceBar,
        ... )
        >>> from atelier.models.enums import SurfaceType
        >>> brief = BriefSpec(
        ...     spec_id=uuid4(),
        ...     tenant_id="tnt",
        ...     project_id="prj",
        ...     intent="Make booking easier",
        ...     visual_register=VisualRegister.EDITORIAL,
        ...     stack=StackChoice.VANILLA_HTML,
        ...     compliance_level=ComplianceLevel.WCAG_AA,
        ...     convergence_bar=ConvergenceBar.SHIP_IT,
        ...     approved_at=datetime.now(UTC),
        ...     approved_by_user_id="usr",
        ... )
        >>> surface = SurfaceState(
        ...     surface_id=uuid4(),
        ...     name="hero",
        ...     type=SurfaceType.PAGE,
        ...     brief="A hero with CTA",
        ... )
        >>> candidate = generate_candidate(brief, surface)
        >>> "index.html" in candidate.artifacts
        True
    """
    html = _render_html(brief, surface)
    css = _render_css(brief.visual_register)
    # Governed A2UI (ADR-0011): emit the AT-044 design-system panel as an A2UI
    # v0.10-SDK/v0.9-wire surface into the carrier slot. This is the Studio CHROME
    # only — the design deliverable stays portable HTML in ``artifacts`` (untouched).
    # NOTE(P0.5 gate-before-emit): the fail-closed governance gate (axe/contrast +
    # D-O-R-A-V + token enforcement on the surface, REJECT → CUSTOM event per
    # ADR-0011 §2) hooks in HERE — validate ``a2ui_surface`` before it is carried
    # forward, in a later slice. P0.4 emits the additive payload only.
    a2ui_surface = build_design_system_surface(
        _register_token_map(brief.visual_register),
        surface_id=f"design-system-{surface.surface_id}",
    )
    return CandidateUI(
        candidate_id=uuid4(),
        surface_id=surface.surface_id,
        iteration=iteration,
        parent_candidate_id=parent_candidate_id,
        mutation_op=None,
        artifacts={
            "index.html": html,
            "main.css": css,
        },
        a2ui_payload={"messages": a2ui_surface},
    )
