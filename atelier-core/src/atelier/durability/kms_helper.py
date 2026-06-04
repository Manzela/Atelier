"""GCP Cloud KMS helper — per-tenant cryptographic isolation and GDPR erasure (AT-053).

Provides transparent encryption and decryption of tenant-isolated data
using tenant-specific Cloud KMS keys.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Configurable environment settings
_DEFAULT_LOCATION = "global"
_DEFAULT_KEY_RING = "atelier-tenant-keys"
_HEADER_LEN = 4


def _kms_enabled() -> bool:
    """True when KMS-based per-tenant cryptographic isolation is enabled."""
    return os.getenv("ATELIER_KMS_ENABLED", "").lower() in ("1", "true", "yes")


def _sanitize_tenant_key(tenant_id: str) -> str:
    """Sanitize tenant ID to meet GCP KMS key naming requirements (A-Z, a-z, 0-9, -, _)."""
    safe = "".join(ch if (ch.isalnum() or ch in "-_") else "_" for ch in tenant_id)
    if not safe:
        safe = "unknown"
    return safe[:50]


def encrypt_payload(tenant_id: str, plaintext: bytes) -> bytes | None:
    """Encrypt a payload using envelope encryption.

    Generates a unique local symmetric key (DEK), encrypts the data using Fernet,
    wraps the DEK using the tenant-specific KMS KEK, and packs the envelope.
    """
    if not _kms_enabled():
        return None

    try:
        from cryptography.fernet import Fernet  # noqa: PLC0415
        from google.cloud import kms  # type: ignore[attr-defined] # noqa: PLC0415

        client = kms.KeyManagementServiceClient()

        project = os.getenv("GOOGLE_CLOUD_PROJECT", "atelier-build-2026")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", _DEFAULT_LOCATION)
        key_ring = os.getenv("ATELIER_KMS_KEY_RING", _DEFAULT_KEY_RING)

        # Generate a unique Data Encryption Key (DEK)
        dek = Fernet.generate_key()
        f = Fernet(dek)
        ciphertext = f.encrypt(plaintext)

        safe_tenant = _sanitize_tenant_key(tenant_id)
        key_name = client.crypto_key_path(
            project=project,
            location=location,
            key_ring=key_ring,
            crypto_key=f"tenant-{safe_tenant}",
        )

        # Wrap the DEK using Cloud KMS
        response = client.encrypt(
            request={
                "name": key_name,
                "plaintext": dek,
            }
        )
        wrapped_dek = response.ciphertext

        # Pack envelope: 4 bytes length of wrapped DEK + wrapped DEK + ciphertext
        l_bytes = len(wrapped_dek).to_bytes(4, byteorder="big")
        return l_bytes + wrapped_dek + ciphertext
    except Exception:
        logger.exception(
            "KMS envelope encryption failed for tenant %s",
            tenant_id,
            extra={"tenant_id": tenant_id},
        )
        raise


def decrypt_payload(tenant_id: str, ciphertext_envelope: bytes) -> bytes | None:
    """Decrypt an envelope-encrypted payload.

    Unpacks the wrapped DEK and ciphertext, decrypts (unwraps) the DEK using
    Cloud KMS, and decrypts the data payload using the unwrapped DEK.
    """
    if not _kms_enabled():
        return None

    try:
        from cryptography.fernet import Fernet  # noqa: PLC0415
        from google.cloud import kms  # type: ignore[attr-defined] # noqa: PLC0415

        client = kms.KeyManagementServiceClient()

        project = os.getenv("GOOGLE_CLOUD_PROJECT", "atelier-build-2026")
        location = os.getenv("GOOGLE_CLOUD_LOCATION", _DEFAULT_LOCATION)
        key_ring = os.getenv("ATELIER_KMS_KEY_RING", _DEFAULT_KEY_RING)

        if len(ciphertext_envelope) < _HEADER_LEN:
            raise ValueError("Invalid ciphertext envelope: too short.")

        l_wrapped = int.from_bytes(ciphertext_envelope[:_HEADER_LEN], byteorder="big")
        if len(ciphertext_envelope) < _HEADER_LEN + l_wrapped:
            raise ValueError("Invalid ciphertext envelope: truncated.")

        wrapped_dek = ciphertext_envelope[_HEADER_LEN : _HEADER_LEN + l_wrapped]
        ciphertext = ciphertext_envelope[_HEADER_LEN + l_wrapped :]

        safe_tenant = _sanitize_tenant_key(tenant_id)
        key_name = client.crypto_key_path(
            project=project,
            location=location,
            key_ring=key_ring,
            crypto_key=f"tenant-{safe_tenant}",
        )

        # Unwrap the DEK using Cloud KMS
        response = client.decrypt(
            request={
                "name": key_name,
                "ciphertext": wrapped_dek,
            }
        )
        dek = response.plaintext

        # Decrypt payload using unwrapped DEK
        f = Fernet(dek)
        return f.decrypt(ciphertext)
    except Exception:
        logger.exception(
            "KMS envelope decryption failed for tenant %s",
            tenant_id,
            extra={"tenant_id": tenant_id},
        )
        raise
