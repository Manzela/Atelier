"""Stitch MCP Integration — Design system management via Google Stitch.

Stitch provides a design system API that Atelier uses for:
    - Creating project-scoped design systems (color, typography, shape)
    - Generating UI screens from text descriptions
    - Applying design systems consistently across surfaces
    - Fetching rendered screen images and source code

This module wraps the Stitch MCP tools into a typed Python interface
that the N3a Generator and EvoDesign nodes can consume.

MCP Server: ``stitch`` (Antigravity IDE native)
API Enablement: ``stitch.googleapis.com`` on project ``i-for-ai``
Auth: Google default credentials (``manzela@tngshopper.com``)

PRD Reference: §6.3 (Pipeline nodes — design system inference)
Audit Reference: §2 (C8 — MCP integration), FA-003
ADR Reference: 0010 (MCP-first tool integration)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class StitchFont(StrEnum):
    """Available fonts in the Stitch design system.

    Maps to Stitch API ``FONT_*`` enum values. Only the most relevant
    fonts for Atelier's target output are included here.
    """

    INTER = "INTER"
    MANROPE = "MANROPE"
    DM_SANS = "DM_SANS"
    OUTFIT = "OUTFIT"
    PLUS_JAKARTA_SANS = "PLUS_JAKARTA_SANS"
    SPACE_GROTESK = "SPACE_GROTESK"
    GEIST = "GEIST"
    SORA = "SORA"
    IBM_PLEX_SANS = "IBM_PLEX_SANS"
    ROBOTO_FLEX = "ROBOTO_FLEX"
    PLAYFAIR_DISPLAY = "PLAYFAIR_DISPLAY"
    EB_GARAMOND = "EB_GARAMOND"
    MONTSERRAT = "MONTSERRAT"
    NOTO_SANS = "NOTO_SANS"


class StitchColorMode(StrEnum):
    """Color mode for the design system."""

    LIGHT = "LIGHT"
    DARK = "DARK"


class StitchColorVariant(StrEnum):
    """Dynamic color system variant."""

    MONOCHROME = "MONOCHROME"
    NEUTRAL = "NEUTRAL"
    TONAL_SPOT = "TONAL_SPOT"
    VIBRANT = "VIBRANT"
    EXPRESSIVE = "EXPRESSIVE"
    FIDELITY = "FIDELITY"
    CONTENT = "CONTENT"


class StitchRoundness(StrEnum):
    """Corner roundness presets."""

    ROUND_TWO = "ROUND_TWO"
    ROUND_FOUR = "ROUND_FOUR"
    ROUND_EIGHT = "ROUND_EIGHT"
    ROUND_TWELVE = "ROUND_TWELVE"
    ROUND_FULL = "ROUND_FULL"


@dataclass(frozen=True)
class StitchDesignSystemSpec:
    """Specification for a Stitch design system.

    This maps to the ``create_design_system`` MCP tool's request schema.
    Used by the N3a Generator to translate a BriefSpec into a design system.

    Attributes:
        display_name: Human-readable name for the design system.
        headline_font: Font for headlines and display text.
        body_font: Font for body text and paragraphs.
        color_mode: Light or dark mode.
        primary_color: Primary brand color in hex (e.g., ``"#1a73e8"``).
        roundness: Corner roundness preset.
        color_variant: Dynamic color system variant.
        secondary_color: Optional override for secondary color.
        tertiary_color: Optional override for tertiary color.
        neutral_color: Optional override for neutral color.
        design_md: Optional markdown design instructions.
    """

    display_name: str
    headline_font: StitchFont = StitchFont.INTER
    body_font: StitchFont = StitchFont.INTER
    color_mode: StitchColorMode = StitchColorMode.LIGHT
    primary_color: str = "#1a73e8"
    roundness: StitchRoundness = StitchRoundness.ROUND_EIGHT
    color_variant: StitchColorVariant = StitchColorVariant.TONAL_SPOT
    secondary_color: str | None = None
    tertiary_color: str | None = None
    neutral_color: str | None = None
    design_md: str | None = None

    def to_mcp_args(self) -> dict[str, Any]:
        """Convert to Stitch MCP ``create_design_system`` arguments.

        Returns:
            Dictionary matching the MCP tool's expected schema.
        """
        theme: dict[str, Any] = {
            "colorMode": self.color_mode.value,
            "headlineFont": self.headline_font.value,
            "bodyFont": self.body_font.value,
            "customColor": self.primary_color,
            "roundness": self.roundness.value,
        }

        if self.color_variant:
            theme["colorVariant"] = self.color_variant.value
        if self.secondary_color:
            theme["overrideSecondaryColor"] = self.secondary_color
        if self.tertiary_color:
            theme["overrideTertiaryColor"] = self.tertiary_color
        if self.neutral_color:
            theme["overrideNeutralColor"] = self.neutral_color
        if self.design_md:
            theme["designMd"] = self.design_md

        return {
            "designSystem": {
                "displayName": self.display_name,
                "theme": theme,
            },
        }


@dataclass(frozen=True)
class StitchScreenSpec:
    """Specification for generating a screen via Stitch MCP.

    Attributes:
        project_id: Stitch project ID.
        prompt: Text description of the screen to generate.
        screen_type: Type of screen (e.g., ``"landing_page"``).
        design_system_id: Optional design system to apply.
    """

    project_id: str
    prompt: str
    screen_type: str = "web_page"
    design_system_id: str | None = None

    def to_mcp_args(self) -> dict[str, Any]:
        """Convert to Stitch MCP ``generate_screen_from_text`` arguments.

        Returns:
            Dictionary matching the MCP tool's expected schema.
        """
        args: dict[str, Any] = {
            "projectId": self.project_id,
            "prompt": self.prompt,
        }
        if self.design_system_id:
            args["designSystemId"] = self.design_system_id
        return args


# ---------------------------------------------------------------------------
# Visual Register → Stitch Design System Mapping
# ---------------------------------------------------------------------------
# Maps BriefSpec.visual_register values to default Stitch configurations.
# Used by N3a Generator to auto-create design systems from briefs.

VISUAL_REGISTER_DEFAULTS: dict[str, StitchDesignSystemSpec] = {
    "corporate": StitchDesignSystemSpec(
        display_name="Corporate",
        headline_font=StitchFont.INTER,
        body_font=StitchFont.INTER,
        color_mode=StitchColorMode.LIGHT,
        primary_color="#1a73e8",
        roundness=StitchRoundness.ROUND_FOUR,
        color_variant=StitchColorVariant.NEUTRAL,
    ),
    "luxury": StitchDesignSystemSpec(
        display_name="Luxury",
        headline_font=StitchFont.PLAYFAIR_DISPLAY,
        body_font=StitchFont.DM_SANS,
        color_mode=StitchColorMode.DARK,
        primary_color="#c9a96e",
        roundness=StitchRoundness.ROUND_TWO,
        color_variant=StitchColorVariant.MONOCHROME,
    ),
    "startup": StitchDesignSystemSpec(
        display_name="Startup",
        headline_font=StitchFont.SPACE_GROTESK,
        body_font=StitchFont.PLUS_JAKARTA_SANS,
        color_mode=StitchColorMode.LIGHT,
        primary_color="#6c5ce7",
        roundness=StitchRoundness.ROUND_TWELVE,
        color_variant=StitchColorVariant.VIBRANT,
    ),
    "editorial": StitchDesignSystemSpec(
        display_name="Editorial",
        headline_font=StitchFont.EB_GARAMOND,
        body_font=StitchFont.NOTO_SANS,
        color_mode=StitchColorMode.LIGHT,
        primary_color="#2d3436",
        roundness=StitchRoundness.ROUND_TWO,
        color_variant=StitchColorVariant.NEUTRAL,
    ),
    "saas": StitchDesignSystemSpec(
        display_name="SaaS Platform",
        headline_font=StitchFont.GEIST,
        body_font=StitchFont.GEIST,
        color_mode=StitchColorMode.LIGHT,
        primary_color="#0070f3",
        roundness=StitchRoundness.ROUND_EIGHT,
        color_variant=StitchColorVariant.TONAL_SPOT,
    ),
    "brutalist": StitchDesignSystemSpec(
        display_name="Brutalist",
        headline_font=StitchFont.IBM_PLEX_SANS,
        body_font=StitchFont.IBM_PLEX_SANS,
        color_mode=StitchColorMode.LIGHT,
        primary_color="#000000",
        roundness=StitchRoundness.ROUND_TWO,
        color_variant=StitchColorVariant.MONOCHROME,
    ),
    "playful": StitchDesignSystemSpec(
        display_name="Playful",
        headline_font=StitchFont.OUTFIT,
        body_font=StitchFont.OUTFIT,
        color_mode=StitchColorMode.LIGHT,
        primary_color="#ff6b6b",
        roundness=StitchRoundness.ROUND_FULL,
        color_variant=StitchColorVariant.EXPRESSIVE,
    ),
}


def get_design_system_for_register(visual_register: str) -> StitchDesignSystemSpec:
    """Look up the default Stitch design system for a visual register.

    Falls back to ``"corporate"`` if the register is not recognized.

    Args:
        visual_register: The visual register from BriefSpec (e.g., ``"luxury"``).

    Returns:
        A StitchDesignSystemSpec with sensible defaults for the register.
    """
    key = visual_register.lower().strip()
    return VISUAL_REGISTER_DEFAULTS.get(key, VISUAL_REGISTER_DEFAULTS["corporate"])
