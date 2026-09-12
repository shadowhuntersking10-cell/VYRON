"""Field-level encryption for sensitive at-rest data.

Used for: supplier credentials, payout destination details, sensitive listing
delivery payloads. Key is derived from SESSION_SECRET — never hardcoded.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from vyron.config import settings
from vyron.errors import VyronError

_fernet: Fernet | None = None


class EncryptionUnavailableError(VyronError):
    code = "ENCRYPTION_NOT_CONFIGURED"
    http_status = 503
    default_message = "Field encryption is not configured (SESSION_SECRET missing)."


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if not settings.session_secret or len(settings.session_secret) < 32:
            raise EncryptionUnavailableError()
        digest = hashlib.sha256((settings.session_secret + "::vyron-field-encryption").encode()).digest()
        _fernet = Fernet(base64.urlsafe_b64encode(digest))
    return _fernet


def encrypt_str(plaintext: str) -> str:
    if plaintext is None:
        raise ValueError("Cannot encrypt None")
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_str(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise VyronError("Encrypted data could not be decrypted (wrong SESSION_SECRET?).", code="DECRYPTION_FAILED") from exc


def encrypt_json(obj: dict | list) -> str:
    import json

    return encrypt_str(json.dumps(obj, ensure_ascii=False, default=str))


def decrypt_json(ciphertext: str):
    import json

    return json.loads(decrypt_str(ciphertext))


def mask_secret(value: str, visible: int = 4) -> str:
    """For admin UIs: never display secrets, only a masked hint."""
    if not value:
        return ""
    if len(value) <= visible:
        return "*" * len(value)
    return "*" * (len(value) - visible) + value[-visible:]
