"""MCP resource server tests (AT-080) + P0 mcp-authz regression.

The write tools in ``mcp_resource_server`` use the Firebase Admin SDK and a
default-credentialled BigQuery/GCS client, which bypass ``firestore.rules`` and
IAM-scoped end-user tokens. They must therefore enforce, in code:

* authentication via the ``ATELIER_MCP_RESOURCE_TOKEN`` shared secret
  (fail-closed when the secret is unset),
* a collection/dataset/prefix allowlist, and
* generic error strings that never echo server internals.

The success-path tests below pass a valid token and allowlisted targets; the
security tests assert the rejections and that no Admin-SDK client is ever
constructed on the rejected paths.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from atelier.integrations import mcp_resource_server
from atelier.integrations.mcp_resource_server import (
    _GENERIC_ERROR,
    stream_trajectory,
    upload_asset,
    write_record,
)

_TOKEN = "test-shared-secret"  # noqa: S105  # test fixture, not a real secret


@pytest.fixture(autouse=True)
def _set_token(monkeypatch):
    """Configure the server secret for every test (the default state)."""
    monkeypatch.setenv("ATELIER_MCP_RESOURCE_TOKEN", _TOKEN)


# --------------------------------------------------------------------------- #
# Success paths (authenticated + allowlisted)                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@patch("atelier.integrations.mcp_resource_server.upload_design_asset")
async def test_upload_asset_success(mock_upload):
    """Verify upload_asset tool delegates to upload_design_asset helper."""
    mock_upload.return_value = "gs://my-bucket/assets/asset.png"

    res = await upload_asset(
        file_path="image.png",
        destination_blob_name="assets/asset.png",
        auth_token=_TOKEN,
    )

    assert "Asset successfully uploaded to: gs://my-bucket/assets/asset.png" in res
    mock_upload.assert_called_once_with("image.png", "assets/asset.png")


@pytest.mark.asyncio
@patch("atelier.integrations.mcp_resource_server.upload_design_asset")
async def test_upload_asset_fail_soft(mock_upload):
    """Verify upload_asset tool fail-soft behavior when helper returns None."""
    mock_upload.return_value = None

    res = await upload_asset(
        file_path="image.png",
        destination_blob_name="assets/asset.png",
        auth_token=_TOKEN,
    )

    assert "GCS is disabled or the upload was skipped" in res


@pytest.mark.asyncio
@patch("atelier.integrations.mcp_resource_server.firestore")
@patch("atelier.integrations.mcp_resource_server._init_firebase")
async def test_write_record_success(mock_init_fb, mock_firestore):
    """Verify write_record tool instantiates Firestore client and writes data."""
    mock_db = MagicMock()
    mock_firestore.client.return_value = mock_db

    mock_collection = MagicMock()
    mock_db.collection.return_value = mock_collection

    mock_document = MagicMock()
    mock_collection.document.return_value = mock_document

    res = await write_record(
        collection="design_systems",
        document_id="doc_123",
        data_json='{"key": "value"}',
        auth_token=_TOKEN,
    )

    assert "Document doc_123 successfully written" in res
    mock_db.collection.assert_called_once_with("design_systems")
    mock_collection.document.assert_called_once_with("doc_123")
    mock_document.set.assert_called_once_with({"key": "value"})


@pytest.mark.asyncio
@patch("atelier.integrations.mcp_resource_server.bigquery")
async def test_stream_trajectory_success(mock_bq):
    """Verify stream_trajectory tool instantiates BigQuery client and inserts row."""
    mock_client = MagicMock()
    mock_bq.Client.return_value = mock_client
    mock_client.insert_rows_json.return_value = []  # No errors

    res = await stream_trajectory(
        dataset="atelier_telemetry",
        table="my_table",
        record_json='{"session_id": "sess-1", "converged": true}',
        auth_token=_TOKEN,
    )

    assert "Row successfully streamed" in res
    mock_client.insert_rows_json.assert_called_once()
    args, _ = mock_client.insert_rows_json.call_args
    assert args[1] == [{"session_id": "sess-1", "converged": True}]


# --------------------------------------------------------------------------- #
# P0 mcp-authz: authentication                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@patch("atelier.integrations.mcp_resource_server._init_firebase")
async def test_write_record_rejects_missing_token(mock_init_fb):
    """No auth_token -> unauthorized, and no Admin-SDK client is constructed."""
    res = await write_record(
        collection="design_systems",
        document_id="doc_123",
        data_json='{"key": "value"}',
    )
    assert res == "Error: unauthorized."
    mock_init_fb.assert_not_called()


@pytest.mark.asyncio
@patch("atelier.integrations.mcp_resource_server._init_firebase")
async def test_write_record_rejects_wrong_token(mock_init_fb):
    """A wrong auth_token -> unauthorized; the write never runs."""
    res = await write_record(
        collection="design_systems",
        document_id="doc_123",
        data_json='{"key": "value"}',
        auth_token="not-the-secret",  # noqa: S106  # deliberately wrong test value
    )
    assert res == "Error: unauthorized."
    mock_init_fb.assert_not_called()


@pytest.mark.asyncio
@patch("atelier.integrations.mcp_resource_server._init_firebase")
async def test_write_record_fail_closed_when_secret_unset(mock_init_fb, monkeypatch):
    """Server is fail-closed: with no configured secret, even a token is rejected."""
    monkeypatch.delenv("ATELIER_MCP_RESOURCE_TOKEN", raising=False)
    res = await write_record(
        collection="design_systems",
        document_id="doc_123",
        data_json='{"key": "value"}',
        auth_token="anything",  # noqa: S106  # token is irrelevant; server is fail-closed
    )
    assert res == "Error: unauthorized."
    mock_init_fb.assert_not_called()


@pytest.mark.asyncio
@patch("atelier.integrations.mcp_resource_server.bigquery")
async def test_stream_trajectory_rejects_missing_token(mock_bq):
    """Unauthenticated BigQuery stream is rejected before any client is built."""
    res = await stream_trajectory(
        dataset="atelier_telemetry",
        table="my_table",
        record_json='{"x": 1}',
    )
    assert res == "Error: unauthorized."
    mock_bq.Client.assert_not_called()


@pytest.mark.asyncio
@patch("atelier.integrations.mcp_resource_server.upload_design_asset")
async def test_upload_asset_rejects_missing_token(mock_upload):
    """Unauthenticated upload is rejected before the helper is invoked."""
    res = await upload_asset(
        file_path="image.png",
        destination_blob_name="assets/asset.png",
    )
    assert res == "Error: unauthorized."
    mock_upload.assert_not_called()


# --------------------------------------------------------------------------- #
# P0 mcp-authz: allowlist                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@patch("atelier.integrations.mcp_resource_server._init_firebase")
async def test_write_record_rejects_non_allowlisted_collection(mock_init_fb):
    """An authenticated write to a non-allowlisted collection is forbidden."""
    res = await write_record(
        collection="arbitrary_collection",
        document_id="doc_123",
        data_json='{"key": "value"}',
        auth_token=_TOKEN,
    )
    assert res == "Error: target not permitted."
    mock_init_fb.assert_not_called()


@pytest.mark.asyncio
@patch("atelier.integrations.mcp_resource_server._init_firebase")
async def test_write_record_rejects_unscoped_collection(mock_init_fb):
    """An empty (unscoped) collection is rejected."""
    res = await write_record(
        collection="",
        document_id="doc_123",
        data_json='{"key": "value"}',
        auth_token=_TOKEN,
    )
    assert res == "Error: target not permitted."
    mock_init_fb.assert_not_called()


@pytest.mark.asyncio
@patch("atelier.integrations.mcp_resource_server.bigquery")
async def test_stream_trajectory_rejects_non_allowlisted_dataset(mock_bq):
    """An authenticated stream to a non-allowlisted dataset is forbidden."""
    res = await stream_trajectory(
        dataset="some_other_dataset",
        table="my_table",
        record_json='{"x": 1}',
        auth_token=_TOKEN,
    )
    assert res == "Error: target not permitted."
    mock_bq.Client.assert_not_called()


@pytest.mark.asyncio
@patch("atelier.integrations.mcp_resource_server.upload_design_asset")
async def test_upload_asset_rejects_non_allowlisted_prefix(mock_upload):
    """An authenticated upload outside an allowlisted prefix is forbidden."""
    res = await upload_asset(
        file_path="image.png",
        destination_blob_name="../etc/passwd",
        auth_token=_TOKEN,
    )
    assert res == "Error: target not permitted."
    mock_upload.assert_not_called()


# --------------------------------------------------------------------------- #
# P0 mcp-authz: errors must not echo internals                                #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@patch("atelier.integrations.mcp_resource_server.firestore")
@patch("atelier.integrations.mcp_resource_server._init_firebase")
async def test_write_record_error_is_generic(mock_init_fb, mock_firestore):
    """An exception during the write returns a generic string, not the internals."""
    secret_detail = "projects/atelier-build-2026/databases/(default)/internal-path"  # noqa: S105  # pragma: allowlist secret
    mock_db = MagicMock()
    mock_firestore.client.return_value = mock_db
    mock_db.collection.side_effect = RuntimeError(secret_detail)

    res = await write_record(
        collection="design_systems",
        document_id="doc_123",
        data_json='{"key": "value"}',
        auth_token=_TOKEN,
    )

    assert res == _GENERIC_ERROR
    assert secret_detail not in res
    assert "RuntimeError" not in res


@pytest.mark.asyncio
@patch("atelier.integrations.mcp_resource_server.bigquery")
async def test_stream_trajectory_row_errors_are_generic(mock_bq):
    """Row-level BigQuery errors are not echoed back to the caller."""
    secret_detail = "schema mismatch on column ssn at row offset 7"  # noqa: S105  # pragma: allowlist secret
    mock_client = MagicMock()
    mock_bq.Client.return_value = mock_client
    mock_client.insert_rows_json.return_value = [{"errors": secret_detail}]

    res = await stream_trajectory(
        dataset="atelier_telemetry",
        table="my_table",
        record_json='{"x": 1}',
        auth_token=_TOKEN,
    )

    assert res == _GENERIC_ERROR
    assert secret_detail not in res


@pytest.mark.asyncio
@patch("atelier.integrations.mcp_resource_server.upload_design_asset")
async def test_upload_asset_error_is_generic(mock_upload):
    """An exception during upload returns a generic string, not the internals."""
    secret_detail = "/Users/secret/path/credentials.json"  # noqa: S105  # pragma: allowlist secret
    mock_upload.side_effect = RuntimeError(secret_detail)

    res = await upload_asset(
        file_path="image.png",
        destination_blob_name="assets/asset.png",
        auth_token=_TOKEN,
    )

    assert res == _GENERIC_ERROR
    assert secret_detail not in res


# Defensive: the module exposes the configured allowlists/secret env name.
def test_security_constants_present():
    assert mcp_resource_server._AUTH_TOKEN_ENV == "ATELIER_MCP_RESOURCE_TOKEN"  # noqa: S105  # env-var name, not a secret
    assert "design_systems" in mcp_resource_server._DEFAULT_FIRESTORE_COLLECTIONS
    assert "atelier_telemetry" in mcp_resource_server._DEFAULT_BQ_DATASETS
    # The generic error must not look like a Python exception repr.
    assert json.dumps(_GENERIC_ERROR)  # serializable, plain string
