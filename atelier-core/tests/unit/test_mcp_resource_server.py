import json
from unittest.mock import MagicMock, patch

import pytest
from atelier.integrations.mcp_resource_server import (
    stream_trajectory,
    upload_asset,
    write_record,
)


@pytest.mark.asyncio
@patch("atelier.integrations.mcp_resource_server.upload_design_asset")
async def test_upload_asset_success(mock_upload):
    """Verify upload_asset tool delegates to upload_design_asset helper."""
    mock_upload.return_value = "gs://my-bucket/asset.png"

    res = await upload_asset(file_path="image.png", destination_blob_name="asset.png")

    assert "Asset successfully uploaded to: gs://my-bucket/asset.png" in res
    mock_upload.assert_called_once_with("image.png", "asset.png")


@pytest.mark.asyncio
@patch("atelier.integrations.mcp_resource_server.upload_design_asset")
async def test_upload_asset_fail_soft(mock_upload):
    """Verify upload_asset tool fail-soft behavior when helper returns None."""
    mock_upload.return_value = None

    res = await upload_asset(file_path="image.png", destination_blob_name="asset.png")

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
        collection="my_collection",
        document_id="doc_123",
        data_json='{"key": "value"}',
    )

    assert "Document doc_123 successfully written" in res
    mock_db.collection.assert_called_once_with("my_collection")
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
        dataset="my_dataset",
        table="my_table",
        record_json='{"session_id": "sess-1", "converged": true}',
    )

    assert "Row successfully streamed" in res
    mock_client.insert_rows_json.assert_called_once()
    args, _ = mock_client.insert_rows_json.call_args
    assert args[1] == [{"session_id": "sess-1", "converged": True}]
