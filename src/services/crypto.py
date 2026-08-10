"""
Symmetric encryption helpers for user-supplied AI API keys.

Replaces apps/content_plans/crypto.py from the Django version.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from src.core.config import settings


_FERNET_INSTANCE: Fernet | None = None


def _get_fernet() -> Fernet:
    global _FERNET_INSTANCE
    if _FERNET_INSTANCE is not None:
        return _FERNET_INSTANCE

    key = settings.AI_KEY_FERNET_KEY
    if not key:
        # Dev fallback: derive a deterministic 32-byte key from the JWT secret.
        digest = hashlib.sha256(settings.AUTH_JWT_SECRET_KEY.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
    elif isinstance(key, str):
        key = key.encode("utf-8")

    _FERNET_INSTANCE = Fernet(key)
    return _FERNET_INSTANCE


def encrypt(plaintext: str) -> bytes:
    if plaintext is None:
        raise ValueError("plaintext required")
    return _get_fernet().encrypt(plaintext.encode("utf-8"))


def decrypt(ciphertext) -> str:
    if not ciphertext:
        return ""
    if isinstance(ciphertext, memoryview):
        ciphertext = bytes(ciphertext)
    if isinstance(ciphertext, str):
        ciphertext = ciphertext.encode("utf-8")
    try:
        return _get_fernet().decrypt(ciphertext).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt API key") from exc