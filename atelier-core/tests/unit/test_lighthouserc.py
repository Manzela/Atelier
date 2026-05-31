"""Validates the repo-root lighthouserc.json configuration (AT-013 / CI budget).

The file is located at:
  Path(__file__).resolve().parents[3] / "lighthouserc.json"

which resolves to the integration-v2.2-trunk worktree root (one level above
atelier-core/). Verified empirically: parents[0]=unit, parents[1]=tests,
parents[2]=atelier-core, parents[3]=integration-v2.2-trunk.
"""

import json
from pathlib import Path

import pytest

_LIGHTHOUSERC = Path(__file__).resolve().parents[3] / "lighthouserc.json"


# ---------------------------------------------------------------------------
# 1. File existence and valid JSON
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_lighthouserc_exists() -> None:
    """lighthouserc.json must exist at the worktree root."""
    assert _LIGHTHOUSERC.exists(), f"lighthouserc.json not found at {_LIGHTHOUSERC}"


@pytest.mark.unit
def test_lighthouserc_valid_json() -> None:
    """lighthouserc.json must be valid JSON (no parse errors)."""
    text = _LIGHTHOUSERC.read_text()
    # Raises json.JSONDecodeError if malformed — that becomes a test failure.
    json.loads(text)


# ---------------------------------------------------------------------------
# Fixture: parse once, reuse across assertion tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def lhrc() -> dict:  # type: ignore[type-arg]
    """Parsed lighthouserc.json as a Python dict."""
    return json.loads(_LIGHTHOUSERC.read_text())


@pytest.fixture(scope="module")
def assertions(lhrc: dict) -> dict:  # type: ignore[type-arg]
    """The ci.assert.assertions mapping."""
    return lhrc["ci"]["assert"]["assertions"]


# ---------------------------------------------------------------------------
# 2. Required keys present in assertions
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "key",
    ["largest-contentful-paint", "total-blocking-time", "cumulative-layout-shift"],
)
def test_required_assertion_key_present(assertions: dict, key: str) -> None:  # type: ignore[type-arg]
    """Each of the three Core Web Vital keys must be present in assertions."""
    assert key in assertions, f"Missing required assertion key: {key!r}"


# ---------------------------------------------------------------------------
# 3. Exact assertion values
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_lcp_assertion_value(assertions: dict) -> None:  # type: ignore[type-arg]
    """largest-contentful-paint must be ['error', {'maxNumericValue': 2500}]."""
    entry = assertions["largest-contentful-paint"]
    assert entry == ["error", {"maxNumericValue": 2500}], f"Unexpected LCP assertion: {entry!r}"


@pytest.mark.unit
def test_tbt_assertion_max_numeric_value(assertions: dict) -> None:  # type: ignore[type-arg]
    """total-blocking-time maxNumericValue must be exactly 200."""
    entry = assertions["total-blocking-time"]
    assert entry[1]["maxNumericValue"] == 200, (
        f"Unexpected TBT maxNumericValue: {entry[1].get('maxNumericValue')!r}"
    )


@pytest.mark.unit
def test_cls_assertion_max_numeric_value(assertions: dict) -> None:  # type: ignore[type-arg]
    """cumulative-layout-shift maxNumericValue must be exactly 0.1."""
    entry = assertions["cumulative-layout-shift"]
    assert entry[1]["maxNumericValue"] == 0.1, (
        f"Unexpected CLS maxNumericValue: {entry[1].get('maxNumericValue')!r}"
    )


# ---------------------------------------------------------------------------
# 4. Error level on each of the three Core Web Vitals
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "key",
    ["largest-contentful-paint", "total-blocking-time", "cumulative-layout-shift"],
)
def test_assertion_uses_error_level(assertions: dict, key: str) -> None:  # type: ignore[type-arg]
    """Each Core Web Vital assertion must use the 'error' severity level."""
    entry = assertions[key]
    assert entry[0] == "error", f"Expected level 'error' for {key!r}, got {entry[0]!r}"
