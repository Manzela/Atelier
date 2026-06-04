"""GCP Cloud Storage helper — visual asset uploads and persistence (AT-080).

Provides transparent uploading of design screenshots and assets to GCS.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import cast

logger = logging.getLogger(__name__)

_DEFAULT_BUCKET = "atelier-generation-assets"


def _gcs_enabled() -> bool:
    """True when Cloud Storage asset persistence is enabled."""
    is_prod = os.getenv("SESSION_BACKEND", "memory").strip().lower() == "vertex"
    explicit = os.getenv("ATELIER_GCS_ENABLED", "").lower() in ("1", "true", "yes")
    return is_prod or explicit


def upload_design_asset(file_path: str | Path, destination_blob_name: str) -> str | None:
    """Upload a local file to GCS and return its public URL or gs:// URI.

    Fail-soft: returns None if GCS is disabled or fails.
    """
    if not _gcs_enabled():
        return None

    try:
        from google.cloud import storage  # type: ignore[attr-defined] # noqa: PLC0415

        client = storage.Client()
        bucket_name = os.getenv("ATELIER_ASSET_BUCKET", _DEFAULT_BUCKET)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)

        blob.upload_from_filename(str(file_path), content_type="image/png")

        use_public_url = os.getenv("ATELIER_USE_PUBLIC_GCS_URL", "false").lower() in (
            "1",
            "true",
            "yes",
        )
        if use_public_url:
            result_url = cast("str", blob.public_url)
        else:
            result_url = f"gs://{bucket_name}/{destination_blob_name}"

    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "GCS upload failed for asset %s: %s (fail-soft)",
            destination_blob_name,
            exc,
            exc_info=True,
        )
        return None
    else:
        return result_url
