"""Classify each i-for-ai resource as MIGRATE | DECOMMISSION | LEAVE_NON_ATELIER.

Per §2.2 of the post-R4 strategic roadmap.

Input:  audit/migration/inventory-i-for-ai-<date>.json
Output: audit/migration/classification-<date>.json

Usage:
    DRY_RUN=1 python scripts/migration/02_classify.py          # default: dry-run
    DRY_RUN=0 python scripts/migration/02_classify.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

logger = logging.getLogger(__name__)

DRY_RUN: Final[bool] = os.environ.get("DRY_RUN", "1") == "1"
PREFIX: Final[str] = "DRY-RUN: " if DRY_RUN else ""

INVENTORY_PATH: Final[Path] = Path("audit/migration/inventory-i-for-ai-2026-05-21.json")
OUTPUT_PATH: Final[Path] = Path(
    f"audit/migration/classification-{datetime.now(tz=UTC).strftime('%Y-%m-%d')}.json"
)


class Disposition(StrEnum):
    MIGRATE = "MIGRATE"
    DECOMMISSION = "DECOMMISSION"
    LEAVE_NON_ATELIER = "LEAVE_NON_ATELIER"


@dataclass(frozen=True, slots=True)
class ResourceDecision:
    resource_kind: str
    resource_name: str
    disposition: Disposition
    rationale: str
    estimated_monthly_cost_usd: float = 0.0


def is_atelier_owned(name: str) -> bool:
    """Heuristic: resource name contains atelier-related tokens."""
    lowered = name.lower()
    return any(token in lowered for token in ("atelier", "webgen", "consensus", "dpo-judge"))


def _classify_cloud_run(resources: dict[str, Any], decisions: list[ResourceDecision]) -> None:
    for svc in resources.get("cloud_run", []):
        name = svc.get("metadata", {}).get("name", svc.get("name", ""))
        disp = Disposition.MIGRATE if is_atelier_owned(name) else Disposition.LEAVE_NON_ATELIER
        decisions.append(
            ResourceDecision(
                "cloud_run",
                name,
                disp,
                f"{'Atelier-owned' if disp == Disposition.MIGRATE else 'Non-Atelier'} Cloud Run service",
            )
        )


def _classify_vertex(resources: dict[str, Any], decisions: list[ResourceDecision]) -> None:
    for ep in resources.get("vertex_endpoints_us_central1", []):
        name = ep.get("displayName", ep.get("name", ""))
        deployed = ep.get("deployedModels", [])
        if not deployed:
            decisions.append(
                ResourceDecision(
                    "vertex_endpoint", name, Disposition.DECOMMISSION, "Empty endpoint — orphan"
                )
            )
        elif is_atelier_owned(name):
            decisions.append(
                ResourceDecision(
                    "vertex_endpoint",
                    name,
                    Disposition.MIGRATE,
                    "Atelier endpoint",
                    float(len(deployed)) * 200.0,
                )
            )
        else:
            decisions.append(
                ResourceDecision(
                    "vertex_endpoint", name, Disposition.LEAVE_NON_ATELIER, "Non-Atelier endpoint"
                )
            )


def _classify_generic(resources: dict[str, Any], decisions: list[ResourceDecision]) -> None:
    for kind in (
        "gcs_buckets",
        "bigquery_datasets",
        "service_accounts",
        "pubsub_topics",
        "secrets",
        "scheduler_jobs",
        "workflows",
        "cloud_functions",
        "cloud_build_triggers",
        "artifact_registry",
    ):
        for resource in resources.get(kind, []):
            name = resource.get("name", resource.get("email", ""))
            if is_atelier_owned(name):
                decisions.append(
                    ResourceDecision(kind, name, Disposition.MIGRATE, f"Atelier-owned {kind}")
                )


def classify(inventory: dict[str, Any]) -> list[ResourceDecision]:
    """Classify every resource in the inventory."""
    decisions: list[ResourceDecision] = []
    resources = inventory.get("resources", {})
    _classify_cloud_run(resources, decisions)
    _classify_vertex(resources, decisions)
    _classify_generic(resources, decisions)
    return decisions


def main() -> None:
    """Entry point."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if DRY_RUN:
        logger.info("%sWould read inventory from %s", PREFIX, INVENTORY_PATH)
        logger.info("%sWould write classification to %s", PREFIX, OUTPUT_PATH)
        return

    if not INVENTORY_PATH.exists():
        logger.error("ERROR: %s not found. Run 01_inventory.sh first.", INVENTORY_PATH)
        sys.exit(1)

    inventory: dict[str, Any] = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    decisions = classify(inventory)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps({"decisions": [asdict(d) for d in decisions]}, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("Wrote %d decisions to %s", len(decisions), OUTPUT_PATH)


if __name__ == "__main__":
    main()
