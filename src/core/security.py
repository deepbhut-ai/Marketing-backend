"""
Password hashing — compatible with Django's password hashers.

Django stores passwords as ``pbkdf2_sha256$iterations$salt$hash``.
We use passlib's django_context to verify existing Django passwords,
and hash new passwords the same way.
"""
from passlib.context import CryptContext

# django_crypto_context verifies Django-format hashes (pbkdf2_sha256, etc.)
pwd_context = CryptContext(
    schemes=["django_pbkdf2_sha256", "pbkdf2_sha256", "bcrypt"],
    deprecated="auto",
)


def hash_password(plain: str) -> str:
    """Hash a password in Django pbkdf2_sha256 format."""
    from passlib.hash import django_pbkdf2_sha256
    return django_pbkdf2_sha256.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against a Django-format hash."""
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False