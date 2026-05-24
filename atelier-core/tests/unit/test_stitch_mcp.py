"""Tests for Stitch MCP integration wrapper (FA-003)."""

from __future__ import annotations

import pytest
from atelier.integrations.stitch_mcp import (
    VISUAL_REGISTER_DEFAULTS,
    StitchColorMode,
    StitchDesignSystemSpec,
    StitchFont,
    StitchScreenSpec,
    get_design_system_for_register,
)


@pytest.mark.unit
class TestStitchDesignSystemSpec:
    """Verify Stitch design system specification construction."""

    def test_default_spec(self) -> None:
        spec = StitchDesignSystemSpec(display_name="Test")
        assert spec.display_name == "Test"
        assert spec.primary_color == "#1a73e8"
        assert spec.headline_font == StitchFont.INTER

    def test_to_mcp_args_minimal(self) -> None:
        spec = StitchDesignSystemSpec(display_name="Minimal")
        args = spec.to_mcp_args()

        assert "designSystem" in args
        ds = args["designSystem"]
        assert ds["displayName"] == "Minimal"
        assert ds["theme"]["colorMode"] == "LIGHT"
        assert ds["theme"]["customColor"] == "#1a73e8"

    def test_to_mcp_args_with_overrides(self) -> None:
        spec = StitchDesignSystemSpec(
            display_name="Full",
            secondary_color="#00ff00",
            tertiary_color="#0000ff",
            neutral_color="#ffffff",
            design_md="# Brand Guide\nPremium look.",
        )
        args = spec.to_mcp_args()
        theme = args["designSystem"]["theme"]

        assert theme["overrideSecondaryColor"] == "#00ff00"
        assert theme["overrideTertiaryColor"] == "#0000ff"
        assert theme["overrideNeutralColor"] == "#ffffff"
        assert "# Brand Guide" in theme["designMd"]

    def test_frozen(self) -> None:
        spec = StitchDesignSystemSpec(display_name="Test")
        with pytest.raises(AttributeError):
            spec.display_name = "Changed"  # type: ignore[misc]


@pytest.mark.unit
class TestStitchScreenSpec:
    """Verify Stitch screen spec construction."""

    def test_to_mcp_args(self) -> None:
        spec = StitchScreenSpec(
            project_id="proj_123",
            prompt="Create a pricing page with three tiers",
        )
        args = spec.to_mcp_args()
        assert args["projectId"] == "proj_123"
        assert "pricing page" in args["prompt"]

    def test_with_design_system(self) -> None:
        spec = StitchScreenSpec(
            project_id="proj_123",
            prompt="Landing page",
            design_system_id="ds_456",
        )
        args = spec.to_mcp_args()
        assert args["designSystemId"] == "ds_456"


@pytest.mark.unit
class TestVisualRegisterMapping:
    """Verify visual register → design system defaults."""

    def test_all_registers_present(self) -> None:
        expected = {"corporate", "luxury", "startup", "editorial", "saas", "brutalist", "playful"}
        assert set(VISUAL_REGISTER_DEFAULTS.keys()) == expected

    def test_luxury_is_dark_mode(self) -> None:
        spec = get_design_system_for_register("luxury")
        assert spec.color_mode == StitchColorMode.DARK

    def test_brutalist_is_monochrome(self) -> None:
        spec = get_design_system_for_register("brutalist")
        assert spec.primary_color == "#000000"

    def test_unknown_register_falls_back(self) -> None:
        spec = get_design_system_for_register("unknown_register")
        assert spec.display_name == "Corporate"

    def test_case_insensitive(self) -> None:
        spec = get_design_system_for_register("LUXURY")
        assert spec.color_mode == StitchColorMode.DARK

    def test_whitespace_trimmed(self) -> None:
        spec = get_design_system_for_register("  startup  ")
        assert spec.headline_font == StitchFont.SPACE_GROTESK
