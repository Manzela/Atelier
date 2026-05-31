"""AT-050 DTCG design-tokens source + Style Dictionary build config validation.

Validates:
- design-tokens/tokens.json  — DTCG token source
- design-tokens/build-tokens.mjs — Style Dictionary v4 build script
- package.json               — build script wiring + style-dictionary v4 dep

Repo root is resolved via parents[3] of this file:
  tests/unit/test_tokens.py -> tests/ -> atelier-core/ -> integration-v2.2-trunk/ (root)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ROOT_INDEX = 3
"""parents[] index that resolves to the repo root containing design-tokens/."""


def _find_repo_root() -> Path:
    """Walk parents upward until design-tokens/tokens.json is found.

    Starts from parents[_ROOT_INDEX] as the expected location; falls back to a
    linear scan if the expected index fails.  Raises RuntimeError with a clear
    message if the file is never found.
    """
    this_file = Path(__file__).resolve()
    parents = this_file.parents

    # Fast-path: expected index
    candidate = parents[_ROOT_INDEX]
    if (candidate / "design-tokens" / "tokens.json").exists():
        return candidate

    # Fallback: walk all available parents
    for _i, parent in enumerate(parents):
        if (parent / "design-tokens" / "tokens.json").exists():
            return parent

    raise RuntimeError(
        "Could not locate design-tokens/tokens.json. "
        f"Searched parents of {this_file}. "
        "Ensure the test is run from within the integration-v2.2-trunk worktree."
    )


REPO_ROOT: Path = _find_repo_root()
TOKENS_PATH: Path = REPO_ROOT / "design-tokens" / "tokens.json"
BUILD_MJS_PATH: Path = REPO_ROOT / "design-tokens" / "build-tokens.mjs"
PACKAGE_JSON_PATH: Path = REPO_ROOT / "package.json"


def _collect_leaves(node: Any) -> list[Any]:
    """Recursively collect all DTCG leaf token objects (dicts that have $value)."""
    leaves: list[Any] = []
    if isinstance(node, dict):
        if "$value" in node:
            leaves.append(node)
        else:
            for v in node.values():
                leaves.extend(_collect_leaves(v))
    return leaves


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tokens() -> dict[str, Any]:
    raw = TOKENS_PATH.read_text(encoding="utf-8")
    return json.loads(raw)  # type: ignore[return-value]


@pytest.fixture(scope="module")
def build_mjs_text() -> str:
    return BUILD_MJS_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def package_json() -> dict[str, Any]:
    raw = PACKAGE_JSON_PATH.read_text(encoding="utf-8")
    return json.loads(raw)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Test 1 — tokens.json is valid JSON and parses to a dict
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_tokens_json_valid_json_and_is_dict(tokens: dict[str, Any]) -> None:
    """tokens.json must parse without error and return a top-level dict."""
    assert isinstance(tokens, dict), (
        f"Expected tokens.json to parse as a dict, got {type(tokens).__name__}"
    )


# ---------------------------------------------------------------------------
# Test 2 — DTCG groups present
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("group", ["color", "font", "space", "radius"])
def test_dtcg_required_top_level_groups_present(tokens: dict[str, Any], group: str) -> None:
    """tokens.json must have top-level keys: color, font, space, radius."""
    assert group in tokens, (
        f"Missing required DTCG top-level group '{group}'. Found keys: {list(tokens.keys())}"
    )
    assert isinstance(tokens[group], dict), (
        f"Group '{group}' must be a dict, got {type(tokens[group]).__name__}"
    )


# ---------------------------------------------------------------------------
# Test 3 — DTCG leaf shape: >=10 leaves, all with non-None $value
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_dtcg_leaf_count_and_value_presence(tokens: dict[str, Any]) -> None:
    """All leaf token objects (dicts with $value) must have a non-None $value; >=10 expected."""
    leaves = _collect_leaves(tokens)
    assert len(leaves) >= 10, f"Expected at least 10 DTCG leaf tokens, found {len(leaves)}"
    for leaf in leaves:
        assert leaf["$value"] is not None, f"Found a leaf token with $value == None: {leaf}"


# ---------------------------------------------------------------------------
# Test 4 — color group uses $type "color" and has a hex primary leaf
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_color_group_type_and_primary_hex(tokens: dict[str, Any]) -> None:
    """tokens['color']['$type'] must equal 'color'; primary.$value must be a hex string."""
    color_group = tokens["color"]
    assert color_group.get("$type") == "color", (
        f"Expected tokens['color']['$type'] == 'color', got {color_group.get('$type')!r}"
    )

    primary_leaf = color_group.get("primary")
    assert isinstance(primary_leaf, dict), (
        f"Expected tokens['color']['primary'] to be a dict, got {type(primary_leaf).__name__}"
    )
    primary_value = primary_leaf.get("$value")
    assert isinstance(primary_value, str), (
        f"Expected tokens['color']['primary']['$value'] to be a str, got {type(primary_value).__name__}"
    )
    assert primary_value.startswith("#"), (
        f"Expected tokens['color']['primary']['$value'] to start with '#', got {primary_value!r}"
    )
    assert re.fullmatch(r"#[0-9a-fA-F]{3,8}", primary_value), (
        f"tokens['color']['primary']['$value'] is not a valid hex color: {primary_value!r}"
    )


# ---------------------------------------------------------------------------
# Test 5 — build-tokens.mjs references all four platforms and required strings
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "expected_text",
    [
        # Platform keys
        "css",
        "tailwind",
        "swift",
        "kotlin",
        # Format strings
        "css/variables",
        "javascript/es6",
        "ios-swift/class.swift",
        "compose/object",
        # Build entrypoint
        "buildAllPlatforms",
    ],
)
def test_build_mjs_contains_required_platform_references(
    build_mjs_text: str, expected_text: str
) -> None:
    """build-tokens.mjs must reference all four platforms, their format strings, and buildAllPlatforms."""
    assert expected_text in build_mjs_text, (
        f"build-tokens.mjs does not contain expected string: {expected_text!r}"
    )


# ---------------------------------------------------------------------------
# Test 6 — package.json wires the build correctly
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_package_json_build_tokens_script(package_json: dict[str, Any]) -> None:
    """scripts['build:tokens'] must exist and reference build-tokens.mjs."""
    scripts = package_json.get("scripts", {})
    assert "build:tokens" in scripts, (
        f"package.json missing scripts['build:tokens']. Found scripts: {list(scripts.keys())}"
    )
    script_value = scripts["build:tokens"]
    assert "build-tokens.mjs" in script_value, (
        f"scripts['build:tokens'] must reference build-tokens.mjs, got: {script_value!r}"
    )


@pytest.mark.unit
def test_package_json_style_dictionary_v4_dep(package_json: dict[str, Any]) -> None:
    """devDependencies['style-dictionary'] must be present and pinned to v4."""
    dev_deps = package_json.get("devDependencies", {})
    assert "style-dictionary" in dev_deps, (
        f"package.json devDependencies missing 'style-dictionary'. Found: {list(dev_deps.keys())}"
    )
    sd_version = dev_deps["style-dictionary"]
    assert isinstance(sd_version, str), (
        f"Expected style-dictionary version to be a string, got {type(sd_version).__name__}"
    )
    # Accept "^4.x.y", "4.x.y", "~4.x.y", ">=4", etc. — any form that contains "4" as the major
    version_str = sd_version.lstrip("^~>=")
    major = version_str.split(".")[0]
    assert major == "4", (
        f"PRD pins style-dictionary to v4; found version specifier {sd_version!r} "
        f"(parsed major: {major!r})"
    )
