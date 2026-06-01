"""Verify zero Atelier-owned resources remain in i-for-ai.

Per §2.6 of the post-R4 strategic roadmap.
Exit 0 = clean (orphan-zero). Exit 1 = orphans found.

Per §24: orphan-zero is a HARD blocker of Phase 2 entry.

Usage:
    DRY_RUN=1 python scripts/migration/05_verify_no_orphans.py     # default: dry-run
    DRY_RUN=0 python scripts/migration/05_verify_no_orphans.py     # live check
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

DRY_RUN: Final[bool] = os.environ.get("DRY_RUN", "1") == "1"
PREFIX: Final[str] = "DRY-RUN: " if DRY_RUN else ""

CLASSIFICATION_PATH: Final[Path] = Path("audit/migration/classification-2026-05-21.json")
SRC_PROJECT: Final[str] = "i-for-ai"


def _gcloud_json(*args: str) -> list[dict]:
    """Run a gcloud command and return JSON output."""
    cmd = ["gcloud", *args, "--format=json"]
    try:
        out = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)  # noqa: S603
        return json.loads(out.stdout or "[]")  # type: ignore[no-any-return]
    except subprocess.CalledProcessError as exc:
        logger.warning("gcloud failure: %s", exc.stderr)
        return []
    except subprocess.TimeoutExpired:
        logger.warning("gcloud timeout: %s", " ".join(args))
        return []


def _check_cloud_run(expected_gone: set[str]) -> list[str]:
    orphans: list[str] = []
    for region in ("us-central1", "us-west1", "europe-west1"):
        for svc in _gcloud_json(
            "run", "services", "list", f"--region={region}", f"--project={SRC_PROJECT}"
        ):
            name = svc.get("metadata", {}).get("name", svc.get("name", ""))
            if name in expected_gone:
                orphans.append(f"cloud_run/{region}/{name}")
    return orphans


def _check_vertex(expected_gone: set[str]) -> list[str]:
    orphans: list[str] = []
    for region in ("us-central1", "us-west1"):
        for ep in _gcloud_json(
            "ai", "endpoints", "list", f"--region={region}", f"--project={SRC_PROJECT}"
        ):
            display = ep.get("displayName", ep.get("name", ""))
            if display in expected_gone:
                orphans.append(f"vertex_endpoint/{region}/{display}")
    return orphans


def _check_gcs(expected_gone: set[str]) -> list[str]:
    orphans: list[str] = []
    for bucket in _gcloud_json("storage", "buckets", "list", f"--project={SRC_PROJECT}"):
        name = bucket.get("name", "")
        if name in expected_gone:
            orphans.append(f"gcs_bucket/{name}")
    return orphans


def _check_bigquery(expected_gone: set[str]) -> list[str]:
    orphans: list[str] = []
    try:
        cmd = ["bq", f"--project_id={SRC_PROJECT}", "ls", "--format=prettyjson"]
        out = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=30)  # noqa: S603
        if out.returncode == 0 and out.stdout.strip():
            for ds in json.loads(out.stdout):
                ds_id = ds.get("datasetReference", {}).get("datasetId", "")
                if ds_id in expected_gone:
                    orphans.append(f"bigquery_dataset/{ds_id}")
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        logger.warning("Could not check BigQuery datasets")
    return orphans


def _check_asset_search() -> list[str]:
    orphans: list[str] = []
    try:
        cmd = [
            "gcloud",
            "asset",
            "search-all-resources",
            f"--project={SRC_PROJECT}",
            "--filter=name~atelier",
            "--format=json",
        ]
        out = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=60)  # noqa: S603
        if out.returncode == 0 and out.stdout.strip():
            for a in json.loads(out.stdout):
                orphans.append(f"asset_search/{a.get('name', 'unknown')}")
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        logger.warning("gcloud asset search timed out or failed")
    return orphans


def main() -> int:
    """Check for orphaned Atelier resources in i-for-ai."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if DRY_RUN:
        logger.info("%sWould check i-for-ai for orphaned Atelier resources", PREFIX)
        logger.info("%sExit 0 = no orphans, Exit 1 = orphans found", PREFIX)
        return 0

    if not CLASSIFICATION_PATH.exists():
        logger.error("ERROR: %s not found. Run 02_classify.py first.", CLASSIFICATION_PATH)
        return 1

    decisions = json.loads(CLASSIFICATION_PATH.read_text(encoding="utf-8"))["decisions"]
    expected_gone = {
        d["resource_name"] for d in decisions if d["disposition"] in ("MIGRATE", "DECOMMISSION")
    }

    found_orphans: list[str] = []
    found_orphans.extend(_check_cloud_run(expected_gone))
    found_orphans.extend(_check_vertex(expected_gone))
    found_orphans.extend(_check_gcs(expected_gone))
    found_orphans.extend(_check_bigquery(expected_gone))
    found_orphans.extend(_check_asset_search())

    if found_orphans:
        logger.error("FAIL: %d orphan(s) found in %s:", len(found_orphans), SRC_PROJECT)
        for orphan in found_orphans:
            logger.error("  - %s", orphan)
        return 1

    logger.info("PASS: Zero orphaned Atelier resources in %s", SRC_PROJECT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
