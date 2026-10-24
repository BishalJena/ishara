"""FastAPI dependencies that read the objects wired into `app.state` by create_app.

They take an HTTPConnection, so they work in both HTTP and WebSocket routes.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from starlette.requests import HTTPConnection

from app.config import Settings
from app.ports import BolnaClient, CallLedger, Composer


def _state(connection: HTTPConnection, name: str):
    value = getattr(connection.app.state, name, None)
    if value is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"{name} not configured")
    return value


def get_settings_dep(connection: HTTPConnection) -> Settings:
    return connection.app.state.settings


def get_composer(connection: HTTPConnection) -> Composer:
    return _state(connection, "composer")


def get_bolna(connection: HTTPConnection) -> BolnaClient:
    return _state(connection, "bolna")


def get_ledger(connection: HTTPConnection) -> CallLedger:
    return _state(connection, "ledger")
