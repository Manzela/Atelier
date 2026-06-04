import os
from unittest.mock import MagicMock, patch

import pytest
from atelier.durability.kms_helper import (
    _kms_enabled,
    decrypt_payload,
    encrypt_payload,
)
from google.cloud import kms


def test_kms_disabled_by_default():
    """Verify that KMS is disabled by default and returns None for payload operations."""
    with patch.dict(os.environ, {}, clear=True):
        assert not _kms_enabled()
        assert encrypt_payload("tenant-abc", b"plaintext") is None
        assert decrypt_payload("tenant-abc", b"ciphertext") is None


def test_kms_enabled_check():
    """Verify that KMS can be enabled via environment variables."""
    with patch.dict(os.environ, {"ATELIER_KMS_ENABLED": "true"}):
        assert _kms_enabled()
    with patch.dict(os.environ, {"ATELIER_KMS_ENABLED": "1"}):
        assert _kms_enabled()
    with patch.dict(os.environ, {"ATELIER_KMS_ENABLED": "yes"}):
        assert _kms_enabled()
    with patch.dict(os.environ, {"ATELIER_KMS_ENABLED": "false"}):
        assert not _kms_enabled()


@patch("google.cloud.kms.KeyManagementServiceClient")
def test_encrypt_and_decrypt_payload_envelope(mock_kms_client_class):
    """Verify envelope encryption and decryption round-trip under mock KMS conditions."""
    mock_client = MagicMock()
    mock_kms_client_class.return_value = mock_client

    mock_client.crypto_key_path.return_value = (
        "projects/proj-123/locations/global/keyRings/ring-abc/cryptoKeys/tenant-tenant-abc"
    )

    generated_deks = []

    def mock_encrypt(request):
        generated_deks.append(request["plaintext"])
        resp = MagicMock()
        resp.ciphertext = b"wrapped-dek-bytes-value"
        return resp

    def mock_decrypt(request):
        assert request["ciphertext"] == b"wrapped-dek-bytes-value"
        resp = MagicMock()
        resp.plaintext = generated_deks[0]
        return resp

    mock_client.encrypt.side_effect = mock_encrypt
    mock_client.decrypt.side_effect = mock_decrypt

    env = {
        "ATELIER_KMS_ENABLED": "true",
        "GOOGLE_CLOUD_PROJECT": "proj-123",
        "GOOGLE_CLOUD_LOCATION": "global",
        "ATELIER_KMS_KEY_RING": "ring-abc",
    }

    with patch.dict(os.environ, env):
        # 1. Encrypt
        plaintext = b"my-sensitive-token-payload"
        envelope = encrypt_payload("tenant-abc", plaintext)
        assert envelope is not None

        # Verify packed envelope structure
        l_wrapped = int.from_bytes(envelope[:4], byteorder="big")
        assert l_wrapped == len(b"wrapped-dek-bytes-value")
        assert envelope[4 : 4 + l_wrapped] == b"wrapped-dek-bytes-value"

        # Verify Key Path was built correctly
        mock_client.crypto_key_path.assert_called_once_with(
            project="proj-123",
            location="global",
            key_ring="ring-abc",
            crypto_key="tenant-tenant-abc",
        )

        # 2. Decrypt
        decrypted = decrypt_payload("tenant-abc", envelope)
        assert decrypted == plaintext


def test_sanitize_tenant_key_direct():
    """Verify that _sanitize_tenant_key filters invalid characters and respects length limits."""
    from atelier.durability.kms_helper import _sanitize_tenant_key

    assert _sanitize_tenant_key("tenant/abc.def") == "tenant_abc_def"
    assert _sanitize_tenant_key("tenant-123_abc") == "tenant-123_abc"
    assert _sanitize_tenant_key("") == "unknown"
    assert len(_sanitize_tenant_key("a" * 100)) == 50
