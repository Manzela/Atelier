"""Constitution registry — CSC-D (Constitution Selector Component — Design).

Selects the appropriate design constitution based on BriefSpec.visual_register.
Constitutions are YAML files in the ``consensus/constitutions/`` directory.

Each constitution defines:
    - Quality principles with names, descriptions, and weights
    - Scoring thresholds (minimum_pass, target, exceptional)
    - Applicable visual registers

The constitutions are mounted read-only in Docker (FA-009) to prevent
any agent from modifying the quality standards during execution.

PRD Reference: §6.3 (N6 CSC-D), F0213-F0214
Audit Reference: §4 (C6, FA-021)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ConstitutionPrinciple:
    """A single design principle from a constitution.

    Attributes:
        principle_id: Short identifier (e.g., ``"P1"``).
        name: Human-readable name.
        description: Full description of the principle.
        weight: Relative importance weight (default 1.0).
    """

    principle_id: str
    name: str
    description: str
    weight: float = 1.0


@dataclass(frozen=True)
class ConstitutionScoring:
    """Scoring thresholds for a constitution.

    Attributes:
        minimum_pass: Minimum composite score to pass (0.0-1.0).
        target: Target score for good quality (0.0-1.0).
        exceptional: Score threshold for exceptional quality (0.0-1.0).
    """

    minimum_pass: float = 0.70
    target: float = 0.85
    exceptional: float = 0.95


@dataclass(frozen=True)
class Constitution:
    """A design constitution — a set of quality standards.

    Attributes:
        name: Constitution name (e.g., ``"apple-grade"``).
        version: Schema version for forward compatibility.
        applies_to: List of visual registers this constitution covers.
        principles: Ordered list of design principles.
        scoring: Scoring threshold configuration.
    """

    name: str
    version: int
    applies_to: tuple[str, ...]
    principles: tuple[ConstitutionPrinciple, ...]
    scoring: ConstitutionScoring


def _parse_constitution(data: dict[str, Any]) -> Constitution:
    """Parse a constitution from YAML data.

    Args:
        data: Parsed YAML dictionary.

    Returns:
        A Constitution instance.

    Raises:
        KeyError: If required fields are missing.
    """
    principles = tuple(
        ConstitutionPrinciple(
            principle_id=p["id"],
            name=p["name"],
            description=p.get("description", "").strip(),
            weight=float(p.get("weight", 1.0)),
        )
        for p in data.get("principles", [])
    )

    scoring_data = data.get("scoring", {})
    scoring = ConstitutionScoring(
        minimum_pass=float(scoring_data.get("minimum_pass", 0.70)),
        target=float(scoring_data.get("target", 0.85)),
        exceptional=float(scoring_data.get("exceptional", 0.95)),
    )

    return Constitution(
        name=data["name"],
        version=int(data.get("version", 1)),
        applies_to=tuple(data.get("applies_to", [])),
        principles=principles,
        scoring=scoring,
    )


def load_constitutions(
    constitutions_dir: Path | None = None,
) -> dict[str, Constitution]:
    """Load all constitutions from the constitutions directory.

    Args:
        constitutions_dir: Path to the directory containing YAML files.
            Defaults to ``consensus/constitutions/`` relative to project root.

    Returns:
        Dictionary mapping constitution name to Constitution instance.
    """
    if constitutions_dir is None:
        # Default: project root / consensus / constitutions
        constitutions_dir = Path(__file__).parents[4] / "consensus" / "constitutions"

    constitutions: dict[str, Constitution] = {}

    if not constitutions_dir.exists():
        return constitutions

    for yaml_file in sorted(constitutions_dir.glob("*.yaml")):
        with yaml_file.open() as f:
            data = yaml.safe_load(f)
        if data:
            constitution = _parse_constitution(data)
            constitutions[constitution.name] = constitution

    return constitutions


def select_constitution(
    visual_register: str,
    constitutions: dict[str, Constitution] | None = None,
) -> Constitution | None:
    """Select the best constitution for a visual register.

    Searches loaded constitutions for one whose ``applies_to`` list
    contains the given visual register. Returns the first match.

    Args:
        visual_register: The visual register from BriefSpec.
        constitutions: Pre-loaded constitutions. If None, loads from disk.

    Returns:
        The matching Constitution, or None if no match found.
    """
    if constitutions is None:
        constitutions = load_constitutions()

    register_lower = visual_register.lower().strip()

    for constitution in constitutions.values():
        if register_lower in constitution.applies_to:
            return constitution

    return None
