#!/usr/bin/env python3
"""Script to extract UI/UX Pro Max knowledge base and upload to GCS for Vertex RAG.

This script fetches the CSV datasets from the nextlevelbuilder/ui-ux-pro-max-skill
repository and uploads them to a designated GCS bucket. Vertex AI Agent Builder
will then index this bucket for the Atelier RAG Datastore.
"""

import logging
import urllib.request

from google.cloud import storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Core datasets to extract for the RAG datastore
DATASETS: list[str] = [
    "css-patterns.csv",
    "google-fonts.csv",
    "material-icons.csv",
    "color-palettes.csv",
    "a11y-guidelines.csv",
    "interaction-patterns.csv",
]

BASE_URL = "https://raw.githubusercontent.com/nextlevelbuilder/ui-ux-pro-max-skill/main/data"


def extract_and_upload(project_id: str, bucket_name: str) -> None:
    """Fetch datasets and upload to GCS."""
    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)

    if not bucket.exists():
        logger.info("Bucket %s does not exist. Creating...", bucket_name)
        bucket.create(location="US")

    for dataset in DATASETS:
        url = f"{BASE_URL}/{dataset}"
        blob = bucket.blob(f"rag_ingest/{dataset}")

        logger.info("Fetching %s...", dataset)
        try:
            # URL is built from the trusted BASE_URL constant (https only).
            with urllib.request.urlopen(url) as response:  # noqa: S310
                content = response.read()
                blob.upload_from_string(content, content_type="text/csv")
                logger.info("Successfully uploaded %s to gs://%s/rag_ingest/", dataset, bucket_name)
        except Exception:
            logger.exception("Failed to fetch or upload %s", dataset)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, help="GCP Project ID")
    parser.add_argument("--bucket", required=True, help="GCS Bucket Name")
    args = parser.parse_args()

    extract_and_upload(args.project, args.bucket)
