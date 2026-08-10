"""
JWT auth using PyJWT directly (replaces fastapi-jwt-auth which is
incompatible with Pydantic v2).

Provides:
  - create_access_token(user_id)  → str
  - create_refresh_token(user_id) → str
  - decode_token(token)           → user_id | None
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from src.core.config import settings


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "token_type": "access",
        "exp": now + timedelta(seconds=settings.AUTH_JWT_ACCESS_TOKEN_EXPIRES),
        "iat": now,
        "user_id": user_id,
    }
    return jwt.encode(payload, settings.AUTH_JWT_SECRET_KEY, algorithm="HS256")


def create_refresh_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "token_type": "refresh",
        "exp": now + timedelta(seconds=settings.AUTH_JWT_REFRESH_TOKEN_EXPIRES),
        "iat": now,
        "user_id": user_id,
    }
    return jwt.encode(payload, settings.AUTH_JWT_SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> Optional[int]:
    """Decode a JWT and return the user_id, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, settings.AUTH_JWT_SECRET_KEY, algorithms=["HS256"])
        return int(payload.get("user_id"))
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, TypeError, ValueError):
        return None