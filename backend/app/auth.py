"""Bearer-token checks. Missing server-side tokens reject every request."""

from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import SecretStr

from app.config import Settings
from app.deps import get_settings_dep

_bearer = HTTPBearer(auto_error=False)


def token_matches(expected: SecretStr | None, supplied: str | None) -> bool:
    if expected is None or not supplied:
        return False
    return hmac.compare_digest(expected.get_secret_value().encode(), supplied.encode())


def _check(expected: SecretStr | None, credentials: HTTPAuthorizationCredentials | None) -> None:
    if not token_matches(expected, credentials.credentials if credentials else None):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")


def require_app_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings_dep),
) -> None:
    _check(settings.app_token, credentials)


def require_custom_llm_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings_dep),
) -> None:
    _check(settings.custom_llm_token, credentials)
