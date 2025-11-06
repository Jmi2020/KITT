"""Shared OAuth2 / JWT helpers."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Dict, List, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


@lru_cache(maxsize=1)
def get_admin_credentials() -> Dict[str, str]:
    """Return admin credentials from ADMIN_USERS env (format: user:secret;...)."""

    raw = os.getenv("ADMIN_USERS", "").strip()
    result: Dict[str, str] = {}
    if not raw:
        return result
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        user, secret = entry.split(":", 1)
        result[user.strip()] = secret.strip()
    return result


def check_secret(password: str, stored_secret: str) -> bool:
    """Compare password with stored secret (bcrypt hash or plain text)."""

    if stored_secret.startswith("$2b$"):
        return verify_password(password, stored_secret)
    return stored_secret == password


def create_access_token(
    subject: str, expires_minutes: Optional[int] = None, roles: Optional[List[str]] = None
) -> str:
    expire = datetime.utcnow() + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "exp": expire}
    if roles:
        payload["roles"] = roles
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload.get("sub")
    except JWTError:
        return None


__all__ = [
    "verify_password",
    "hash_password",
    "create_access_token",
    "decode_access_token",
    "get_admin_credentials",
    "check_secret",
]
