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


@pytest.mark.unit
class TestStitchMcpTransport:
    """Lock the MCP transport for the Stitch toolset.

    Regression guard: ``stitch.googleapis.com/mcp`` is a stateless Streamable
    HTTP server. It was previously reached with ``SseConnectionParams``, whose
    SSE handshake the server never answers — ADK then retried for tens of
    minutes and every generation silently fell back to direct mode without the
    Stitch design tools. The toolset must use ``StreamableHTTPConnectionParams``.
    """

    def test_toolset_uses_streamable_http_transport(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Avoid a Secret Manager call — _get_api_key short-circuits on this env.
        monkeypatch.setenv("STITCH_API_KEY", "fake-key-for-test")

        from atelier.integrations.stitch_mcp import get_stitch_mcp_toolset
        from google.adk.tools.mcp_tool.mcp_session_manager import (
            StreamableHTTPConnectionParams,
        )

        toolset = get_stitch_mcp_toolset()
        params = toolset._connection_params

        # Streamable HTTP, not SSE — the type itself is the regression guard
        # (SseConnectionParams and StreamableHTTPConnectionParams are disjoint).
        assert type(params).__name__ == "StreamableHTTPConnectionParams"
        assert isinstance(params, StreamableHTTPConnectionParams)
        assert params.url == "https://stitch.googleapis.com/mcp"
        assert params.headers is not None
        assert params.headers["Authorization"] == "Bearer fake-key-for-test"
