"""Signing utilities for hazardous intents."""

from __future__ import annotations

import hmac
import secrets
from typing import Optional

from common.config import settings


def sign_payload(payload: str, key: Optional[str] = None) -> str:
    secret = (key or settings.hazard_signing_key or "").encode("utf-8")
    if not secret:
        raise RuntimeError("Hazard signing key not configured")
    digest = hmac.new(secret, payload.encode("utf-8"), "sha256").hexdigest()
    return digest


def verify_signature(payload: str, signature: str, key: Optional[str] = None) -> bool:
    secret = (key or settings.hazard_signing_key or "").encode("utf-8")
    if not secret:
        return False
    expected = hmac.new(secret, payload.encode("utf-8"), "sha256").hexdigest()
    return secrets.compare_digest(expected, signature)
