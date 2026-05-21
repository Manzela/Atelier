"""Tests for constitution registry (FA-021)."""

from __future__ import annotations

from pathlib import Path

import pytest
from atelier.models.constitution_registry import (
    Constitution,
    ConstitutionScoring,
    _parse_constitution,
    load_constitutions,
    select_constitution,
)

CONSENSUS_DIR = Path(__file__).parents[3] / "consensus" / "constitutions"


@pytest.mark.unit
class TestConstitutionParsing:
    """Verify YAML constitution parsing."""

    def test_parse_minimal(self) -> None:
        data = {
            "name": "test",
            "version": 1,
            "applies_to": ["corporate"],
            "principles": [
                {"id": "P1", "name": "Test Principle", "description": "Test", "weight": 1.5},
            ],
            "scoring": {"minimum_pass": 0.7, "target": 0.85, "exceptional": 0.95},
        }
        c = _parse_constitution(data)
        assert c.name == "test"
        assert c.version == 1
        assert len(c.principles) == 1
        assert c.principles[0].weight == 1.5

    def test_parse_defaults(self) -> None:
        data = {"name": "minimal", "principles": []}
        c = _parse_constitution(data)
        assert c.version == 1
        assert c.applies_to == ()
        assert c.scoring.minimum_pass == 0.70

    def test_frozen(self) -> None:
        c = Constitution(
            name="test",
            version=1,
            applies_to=(),
            principles=(),
            scoring=ConstitutionScoring(),
        )
        with pytest.raises(AttributeError):
            c.name = "changed"  # type: ignore[misc]


@pytest.mark.unit
class TestLoadConstitutions:
    """Verify loading constitutions from disk."""

    def test_load_from_consensus_dir(self) -> None:
        if not CONSENSUS_DIR.exists():
            pytest.skip("consensus/constitutions/ not found")
        constitutions = load_constitutions(CONSENSUS_DIR)
        assert len(constitutions) >= 2
        assert "apple-grade" in constitutions
        assert "brutalist" in constitutions

    def test_apple_grade_has_principles(self) -> None:
        if not CONSENSUS_DIR.exists():
            pytest.skip("consensus/constitutions/ not found")
        constitutions = load_constitutions(CONSENSUS_DIR)
        apple = constitutions["apple-grade"]
        assert len(apple.principles) >= 7
        assert apple.scoring.minimum_pass == 0.70

    def test_brutalist_applies_to_brutalist(self) -> None:
        if not CONSENSUS_DIR.exists():
            pytest.skip("consensus/constitutions/ not found")
        constitutions = load_constitutions(CONSENSUS_DIR)
        brut = constitutions["brutalist"]
        assert "brutalist" in brut.applies_to

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        assert load_constitutions(tmp_path) == {}

    def test_nonexistent_dir_returns_empty(self) -> None:
        assert load_constitutions(Path("/nonexistent/path")) == {}


@pytest.mark.unit
class TestSelectConstitution:
    """Verify constitution selection by visual register."""

    def test_select_luxury(self) -> None:
        if not CONSENSUS_DIR.exists():
            pytest.skip("consensus/constitutions/ not found")
        constitutions = load_constitutions(CONSENSUS_DIR)
        result = select_constitution("luxury", constitutions)
        assert result is not None
        assert result.name == "apple-grade"

    def test_select_brutalist(self) -> None:
        if not CONSENSUS_DIR.exists():
            pytest.skip("consensus/constitutions/ not found")
        constitutions = load_constitutions(CONSENSUS_DIR)
        result = select_constitution("brutalist", constitutions)
        assert result is not None
        assert result.name == "brutalist"

    def test_select_unknown_returns_none(self) -> None:
        if not CONSENSUS_DIR.exists():
            pytest.skip("consensus/constitutions/ not found")
        constitutions = load_constitutions(CONSENSUS_DIR)
        result = select_constitution("unknown_register", constitutions)
        assert result is None

    def test_case_insensitive(self) -> None:
        if not CONSENSUS_DIR.exists():
            pytest.skip("consensus/constitutions/ not found")
        constitutions = load_constitutions(CONSENSUS_DIR)
        result = select_constitution("LUXURY", constitutions)
        assert result is not None
