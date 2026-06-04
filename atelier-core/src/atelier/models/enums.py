"""Canonical enum definitions for the Atelier pipeline.

Every enum is ``str``-based for JSON serialization compatibility.
Values are kebab-case (``"dense-data"``) for API/config consistency.

These enums form the leaf of the import hierarchy — no Atelier imports.

PRD Reference: §9 (Data contracts) + §6.3 (Pipeline nodes)
"""

from enum import StrEnum

# ---------------------------------------------------------------------------
# Design Specification Enums (used in BriefSpec)
# ---------------------------------------------------------------------------


class VisualRegister(StrEnum):
    """Visual style register governing CSC-D constitution selection (N6).

    Each register maps to a different judge weighting profile via N15 MJG.
    """

    EDITORIAL = "editorial"
    DENSE_DATA = "dense-data"
    PLAYFUL = "playful"
    BRUTALIST = "brutalist"
    CORPORATE = "corporate"
    CUSTOM = "custom"


class StackChoice(StrEnum):
    """Technology stack for generated output.

    ``INFER_FROM_PATH`` triggers N4 PADI auto-detection.
    """

    VANILLA_HTML = "vanilla-html"
    REACT_TAILWIND = "react-tailwind"
    NEXTJS_TAILWIND = "nextjs-tailwind"
    VUE = "vue"
    SVELTE = "svelte"
    ASTRO = "astro"
    SAGE_PHP = "sage-php"
    INFER_FROM_PATH = "infer"


class ComplianceLevel(StrEnum):
    """Accessibility/regulatory compliance tier for deterministic gates."""

    NONE = "none"
    WCAG_AA = "wcag-aa"
    WCAG_AAA = "wcag-aaa"
    REGULATORY = "regulatory"


class ConvergenceBar(StrEnum):
    """Quality threshold the agent must reach before convergence.

    - ``SHIP_IT``:        ≥ 85% composite D-O-R-A-V
    - ``PRODUCTION``:     ≥ 95% (default for paying customers)
    - ``PERFECTIONIST``:  100% (may not converge; useful for benchmarks)
    """

    SHIP_IT = "ship-it"
    PRODUCTION = "production"
    PERFECTIONIST = "perfectionist"


# ---------------------------------------------------------------------------
# Surface / Campaign Enums
# ---------------------------------------------------------------------------


class SurfaceType(StrEnum):
    """Type of design surface within a campaign."""

    PAGE = "page"
    COMPONENT = "component"
    TEMPLATE = "template"
    SCREEN = "screen"


# ---------------------------------------------------------------------------
# Board / Kanban Enums (PRD §7A.5 — writer AT-020b, reader AT-041)
# ---------------------------------------------------------------------------


class BoardColumnId(StrEnum):
    """The ordered, exact Kanban column set for the Board task-doc (PRD §7A.5).

    A run drives ONE ``tenants/{tenant_id}/projects/{id}/tasks/{task_id}`` doc
    through these six columns **in declaration order, with NO skips**. The
    string values are the canonical display names the dashboard reader (AT-041)
    matches on, so they are the prose labels from the PRD — not machine-mangled
    identifiers. Declaration order IS the legal transition order; the emitter
    derives the forward-only state machine from :data:`__members__` so the order
    is single-sourced here (changing a column means changing this enum).
    """

    BRIEF = "Brief"
    DECOMPOSE = "Decompose"
    AWAITING_SIGNOFF = "Awaiting Sign-off"
    GENERATING = "Generating"
    QA = "QA"
    DONE = "Done"


# ---------------------------------------------------------------------------
# Pipeline Gate Enums (N3c deterministic gates)
# ---------------------------------------------------------------------------


class GateAxis(StrEnum):
    """Deterministic gate axes evaluated in N3c.

    Each gate produces a binary PASS/REJECT/DEFER decision.
    Six gates per PRD §6.3 N3c.
    """

    LIGHTHOUSE_A11Y = "lighthouse-a11y"
    LIGHTHOUSE_PERF = "lighthouse-perf"
    AXE = "axe"
    TOKEN_FIDELITY = "token-fidelity"
    SEMANTIC_HTML = "semantic-html"
    VISUAL_DIFF = "visual-diff"
    RESPONSIVE = "responsive"
    CSS_VALIDITY = "css-validity"


class GateDecision(StrEnum):
    """Outcome of a single deterministic gate evaluation."""

    PASS = "pass"
    REJECT = "reject"
    DEFER = "defer"


# ---------------------------------------------------------------------------
# Judge / Consensus Enums (N3d ConsensusAgent)
# ---------------------------------------------------------------------------


class JudgeAxis(StrEnum):
    """D-O-R-A-V judge axes evaluated in N3d ConsensusAgent.

    Each axis uses task-aware model routing per audit §7:
        - D (Brand)      → Gemini 3 Flash (vision)
        - O (Originality) → Gemini 2.5 Pro (thinking)
        - R (Relevance)   → Gemini 3 Flash + Grounding
        - A (Accessibility) → Det gate + Flash-Lite (supplementary)
        - V (Visual-clarity) → Gemini 3 Flash + Gemini Embedding 2
    """

    BRAND = "brand"
    ORIGINALITY = "originality"
    RELEVANCE = "relevance"
    ACCESSIBILITY = "accessibility"
    VISUAL_CLARITY = "visual-clarity"


class ConsensusDecision(StrEnum):
    """Outcome of the ConsensusAgent (N3d) deliberation."""

    CONVERGED = "converged"
    RETRY = "retry"
    DEFER_HUMAN = "defer-human"


# ---------------------------------------------------------------------------
# EvoDesign Enums (N3e Fixer / N5 EvoDesign)
# ---------------------------------------------------------------------------


class MutationOp(StrEnum):
    """Mutation operator applied by N3e Fixer (Hebbian mutator).

    Six mutation operators per PRD §6.3 N3e + EvoDesign (N5).
    """

    LAYOUT_SHIFT = "layout-shift"
    PALETTE_SWAP = "palette-swap"
    TYPOGRAPHY_SHIFT = "typography-shift"
    DENSITY_ADJUST = "density-adjust"
    COMPONENT_SWAP = "component-swap"
    CROSSOVER = "crossover"


# ---------------------------------------------------------------------------
# User Signal Enums (Trajectory / Flywheel)
# ---------------------------------------------------------------------------


class UserSignal(StrEnum):
    """Explicit user signal on a generated candidate.

    Used in TrajectoryRecord for DPO preference pair extraction:
        - ``ACCEPT`` → always "chosen" in DPO pairs
        - ``REJECT`` → always "rejected" in DPO pairs
        - ``NEUTRAL`` → scored by composite only
    """

    ACCEPT = "accept"
    REJECT = "reject"
    NEUTRAL = "neutral"


# ---------------------------------------------------------------------------
# Interaction Spec Enums (AT-023 InteractionDesigner output contract)
# ---------------------------------------------------------------------------


class InteractionTrigger(StrEnum):
    """Interaction trigger type for :class:`~atelier.models.interaction.DeclaredInteraction`.

    Used by the ``InteractionDesigner`` DDLC specialist to enumerate the
    component states it specifies.  At least one ``FOCUS`` or ``KEYBOARD``
    entry is required in every valid :class:`~atelier.models.interaction.InteractionSpec`
    (WCAG 2.4.7 / PRD R-accessibility).
    """

    HOVER = "hover"
    FOCUS = "focus"
    ACTIVE = "active"
    DISABLED = "disabled"
    KEYBOARD = "keyboard"
