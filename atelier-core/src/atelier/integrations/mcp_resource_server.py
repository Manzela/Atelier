"""Localhost MCP Resource Server — AT-080 (PRD v2.2 §20).

Exposes secure, isolated Model Context Protocol toolsets for Cloud Storage (GCS),
Firestore, and BigQuery, preventing code containers from having direct access.

Security boundary (P0 mcp-authz)
--------------------------------
The write tools below use the Firebase **Admin SDK** and a default-credentialled
BigQuery/GCS client. Those clients bypass ``firestore.rules`` and IAM-scoped
end-user tokens entirely, so an unauthenticated caller reaching this server can
write arbitrary documents/rows/objects. The mitigations are:

1.  **Authentication.** Every write tool requires an ``auth_token`` that must
    match the server-side shared secret ``ATELIER_MCP_RESOURCE_TOKEN``. The
    check is *fail-closed*: if no secret is configured the server refuses all
    writes rather than running open. Comparison is constant-time.

2.  **Allowlists.** Firestore collections, BigQuery datasets, and GCS
    destination prefixes are validated against allowlists (env-overridable).
    Empty/unscoped targets and anything outside the allowlist are rejected
    *before* any client is constructed.

3.  **Generic errors.** Failures return a fixed, non-descriptive string; the
    underlying exception (paths, IDs, stack) is only ever written to the local
    server log, never echoed to the MCP caller.

Transport boundary
------------------
``mcp.run()`` defaults to the stdio transport, i.e. the server is reachable
only by the parent process that spawned it — it does not bind a network socket.
Operators MUST keep it on stdio (or a loopback-only HTTP transport behind the
shared secret) and never expose it on a public interface. The shared-secret
gate above is what enforces the boundary if a future transport change makes it
network-reachable.
"""

from __future__ import annotations

import json
import logging
import os
import secrets

from firebase_admin import firestore  # type: ignore[attr-defined]
from google.cloud import bigquery  # type: ignore[attr-defined]
from mcp.server.fastmcp import FastMCP

from atelier.auth.firebase import _init_firebase
from atelier.durability.gcs_helper import upload_design_asset

logger = logging.getLogger(__name__)

# Initialize the FastMCP server
mcp = FastMCP("Atelier-Resource-Server")

# --------------------------------------------------------------------------- #
# Authorization / allowlist configuration                                     #
# --------------------------------------------------------------------------- #

# Single generic failure string returned to callers. Never include the
# underlying exception, target identifiers, or any other server internals here.
_GENERIC_ERROR = "Error: request rejected."
_UNAUTHORIZED = "Error: unauthorized."
_FORBIDDEN_TARGET = "Error: target not permitted."

# Env var holding the shared secret every write tool must present. When unset
# the server is fail-closed: all writes are rejected.
_AUTH_TOKEN_ENV = "ATELIER_MCP_RESOURCE_TOKEN"  # noqa: S105  # name of an env var, not a secret

# Default allowlists mirror exactly what the application legitimately writes.
# Each can be overridden/extended via a comma-separated env var.
_DEFAULT_FIRESTORE_COLLECTIONS = frozenset(
    {"design_systems", "projects", "tasks", "tenants", "usage", "users"}
)
_DEFAULT_BQ_DATASETS = frozenset({"atelier_telemetry"})
_DEFAULT_GCS_PREFIXES = frozenset({"designs/", "assets/", "screenshots/", "generations/"})


def _allowlist_from_env(env_var: str, defaults: frozenset[str]) -> frozenset[str]:
    """Build an allowlist from a comma-separated env override, else defaults."""
    raw = os.getenv(env_var, "").strip()
    if not raw:
        return defaults
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


def _check_auth(auth_token: str | None) -> bool:
    """Constant-time check of the caller token against the server secret.

    Fail-closed: returns ``False`` when the server secret is unset, so the
    server never runs open by accident.
    """
    expected = os.getenv(_AUTH_TOKEN_ENV, "").strip()
    if not expected:
        logger.error(
            "MCP resource server is unauthenticated: %s is not set; rejecting write.",
            _AUTH_TOKEN_ENV,
        )
        return False
    if not auth_token:
        return False
    return secrets.compare_digest(str(auth_token), expected)


def _is_allowed(value: str | None, allowlist: frozenset[str]) -> bool:
    """True only when ``value`` is non-empty and present in the allowlist."""
    return bool(value) and value in allowlist


def _is_allowed_prefix(blob_name: str | None, prefixes: frozenset[str]) -> bool:
    """True only when ``blob_name`` is non-empty and under an allowed prefix."""
    if not blob_name:
        return False
    return any(blob_name.startswith(prefix) for prefix in prefixes)


@mcp.tool()
async def upload_asset(
    file_path: str, destination_blob_name: str, auth_token: str | None = None
) -> str:
    """Upload a local design asset to Google Cloud Storage.

    Args:
        file_path: Absolute local path to the file.
        destination_blob_name: Target blob path in the GCS bucket. Must fall
            under an allowlisted prefix.
        auth_token: Shared secret matching ``ATELIER_MCP_RESOURCE_TOKEN``.

    Returns:
        The GCS URI (gs://...) or public URL of the uploaded asset.
    """
    if not _check_auth(auth_token):
        return _UNAUTHORIZED

    prefixes = _allowlist_from_env("ATELIER_MCP_GCS_PREFIXES", _DEFAULT_GCS_PREFIXES)
    if not _is_allowed_prefix(destination_blob_name, prefixes):
        logger.warning(
            "MCP upload_asset rejected: blob %r outside allowlisted prefixes.",
            destination_blob_name,
        )
        return _FORBIDDEN_TARGET

    try:
        url = upload_design_asset(file_path, destination_blob_name)
    except Exception:
        logger.exception("MCP upload_asset failed")
        return _GENERIC_ERROR
    else:
        if url:
            return f"Asset successfully uploaded to: {url}"
        return "GCS is disabled or the upload was skipped (fail-soft)."


@mcp.tool()
async def write_record(
    collection: str, document_id: str, data_json: str, auth_token: str | None = None
) -> str:
    """Write or update a document in Cloud Firestore.

    Args:
        collection: Firestore collection name. Must be allowlisted.
        document_id: Unique document identifier.
        data_json: JSON-serialized dictionary of document fields.
        auth_token: Shared secret matching ``ATELIER_MCP_RESOURCE_TOKEN``.

    Returns:
        A success or error message.
    """
    if not _check_auth(auth_token):
        return _UNAUTHORIZED

    collections = _allowlist_from_env(
        "ATELIER_MCP_FIRESTORE_COLLECTIONS", _DEFAULT_FIRESTORE_COLLECTIONS
    )
    if not _is_allowed(collection, collections) or not document_id:
        logger.warning(
            "MCP write_record rejected: collection %r / document %r not permitted.",
            collection,
            document_id,
        )
        return _FORBIDDEN_TARGET

    try:
        data = json.loads(data_json)
        if not isinstance(data, dict):
            return "Error: data_json must represent a JSON object/dictionary."

        app = _init_firebase()
        db = firestore.client(app=app)
        doc_ref = db.collection(collection).document(document_id)
        doc_ref.set(data)
    except Exception:
        logger.exception("MCP write_record failed")
        return _GENERIC_ERROR
    else:
        return f"Document {document_id} successfully written to collection {collection}."


@mcp.tool()
async def stream_trajectory(
    dataset: str, table: str, record_json: str, auth_token: str | None = None
) -> str:
    """Stream a design run trajectory record into BigQuery.

    Args:
        dataset: Target BigQuery dataset ID. Must be allowlisted.
        table: Target BigQuery table ID.
        record_json: JSON-serialized trajectory log row.
        auth_token: Shared secret matching ``ATELIER_MCP_RESOURCE_TOKEN``.

    Returns:
        A success or error message.
    """
    if not _check_auth(auth_token):
        return _UNAUTHORIZED

    datasets = _allowlist_from_env("ATELIER_MCP_BQ_DATASETS", _DEFAULT_BQ_DATASETS)
    if not _is_allowed(dataset, datasets) or not table:
        logger.warning(
            "MCP stream_trajectory rejected: dataset %r / table %r not permitted.",
            dataset,
            table,
        )
        return _FORBIDDEN_TARGET

    try:
        row = json.loads(record_json)
        if not isinstance(row, dict):
            return "Error: record_json must represent a JSON object/dictionary."

        client = bigquery.Client()
        table_ref = client.dataset(dataset).table(table)
        errors = client.insert_rows_json(table_ref, [row])
    except Exception:
        logger.exception("MCP stream_trajectory failed")
        return _GENERIC_ERROR
    else:
        if errors:
            logger.error("BigQuery stream returned row-level errors: %s", errors)
            return _GENERIC_ERROR
        return f"Row successfully streamed to {dataset}.{table}."


if __name__ == "__main__":
    mcp.run()
