"""Signed, expiring browser sessions. Native clients keep their bearer-token auth."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from urllib.parse import urlsplit

from app.config import Settings

COOKIE = "ishara_session"
SESSION_SECONDS = 8 * 60 * 60


def _signature(settings: Settings, payload: str) -> str:
    key = settings.app_token.get_secret_value() if settings.app_token else ""
    return hmac.new(key.encode(), ("ishara-web:" + payload).encode(), hashlib.sha256).hexdigest()


def issue_session(settings: Settings, *, now: float | None = None) -> str:
    payload = f"{int(time.time() if now is None else now)}.{secrets.token_hex(16)}"
    return payload + "." + _signature(settings, payload)


def valid_session(settings: Settings, token: str | None, *, now: float | None = None) -> bool:
    if not settings.app_token or not token or len(token) > 160:
        return False
    try:
        issued, nonce, signature = token.split(".")
        age = (time.time() if now is None else now) - int(issued)
    except (ValueError, TypeError):
        return False
    return (
        0 <= age < SESSION_SECONDS
        and len(nonce) == 32
        and hmac.compare_digest(
            signature.encode(), _signature(settings, issued + "." + nonce).encode()
        )
    )


def same_origin(settings: Settings, origin: str | None, base_url: str) -> bool:
    if not origin or origin == "null":
        return False
    allowed = {base_url.rstrip("/")}
    if settings.public_base_url:
        allowed.add(settings.public_base_url.rstrip("/"))
    return origin.rstrip("/") in allowed


def browser_authenticated(
    settings: Settings, token: str | None, origin: str | None, base_url: str, *, write: bool
) -> bool:
    return valid_session(settings, token) and (
        (not write and origin is None) or same_origin(settings, origin, base_url)
    )


def secure_cookie(settings: Settings, base_url: str) -> bool:
    return urlsplit(settings.public_base_url or base_url).scheme == "https"
