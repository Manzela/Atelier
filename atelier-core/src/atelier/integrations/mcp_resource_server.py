"""Localhost MCP Resource Server — AT-080 (PRD v2.2 §20).

Exposes secure, isolated Model Context Protocol toolsets for Cloud Storage (GCS),
Firestore, and BigQuery, preventing code containers from having direct access.
"""

from __future__ import annotations

import json
import logging

from firebase_admin import firestore  # type: ignore[attr-defined]
from google.cloud import bigquery  # type: ignore[attr-defined]
from mcp.server.fastmcp import FastMCP

from atelier.auth.firebase import _init_firebase
from atelier.durability.gcs_helper import upload_design_asset

logger = logging.getLogger(__name__)

# Initialize the FastMCP server
mcp = FastMCP("Atelier-Resource-Server")


@mcp.tool()
async def upload_asset(file_path: str, destination_blob_name: str) -> str:
    """Upload a local design asset to Google Cloud Storage.

    Args:
        file_path: Absolute local path to the file.
        destination_blob_name: Target blob path in the GCS bucket.

    Returns:
        The GCS URI (gs://...) or public URL of the uploaded asset.
    """
    try:
        url = upload_design_asset(file_path, destination_blob_name)
    except Exception as exc:
        logger.exception("MCP upload_asset failed")
        return f"Error: {exc}"
    else:
        if url:
            return f"Asset successfully uploaded to: {url}"
        return "GCS is disabled or the upload was skipped (fail-soft)."


@mcp.tool()
async def write_record(collection: str, document_id: str, data_json: str) -> str:
    """Write or update a document in Cloud Firestore.

    Args:
        collection: Firestore collection name.
        document_id: Unique document identifier.
        data_json: JSON-serialized dictionary of document fields.

    Returns:
        A success or error message.
    """
    try:
        app = _init_firebase()
        db = firestore.client(app=app)
        doc_ref = db.collection(collection).document(document_id)

        data = json.loads(data_json)
        if not isinstance(data, dict):
            return "Error: data_json must represent a JSON object/dictionary."

        doc_ref.set(data)
    except Exception as exc:
        logger.exception("MCP write_record failed")
        return f"Error: {exc}"
    else:
        return f"Document {document_id} successfully written to collection {collection}."


@mcp.tool()
async def stream_trajectory(dataset: str, table: str, record_json: str) -> str:
    """Stream a design run trajectory record into BigQuery.

    Args:
        dataset: Target BigQuery dataset ID.
        table: Target BigQuery table ID.
        record_json: JSON-serialized trajectory log row.

    Returns:
        A success or error message.
    """
    try:
        client = bigquery.Client()
        table_ref = client.dataset(dataset).table(table)

        row = json.loads(record_json)
        if not isinstance(row, dict):
            return "Error: record_json must represent a JSON object/dictionary."

        errors = client.insert_rows_json(table_ref, [row])
    except Exception as exc:
        logger.exception("MCP stream_trajectory failed")
        return f"Error: {exc}"
    else:
        if errors:
            return f"BigQuery stream encountered errors: {errors}"
        return f"Row successfully streamed to {dataset}.{table}."


if __name__ == "__main__":
    mcp.run()
