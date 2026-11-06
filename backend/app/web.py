"""Browser session, contacts and bounded landmark inference for the web call desk."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from app.auth import require_app_token, token_matches
from app.config import Settings
from app.contacts import parse_contacts
from app.deps import get_settings_dep
from app.web_auth import (
    COOKIE,
    SESSION_SECONDS,
    issue_session,
    same_origin,
    secure_cookie,
    valid_session,
)
from app.web_recognition import MAX_BYTES

router = APIRouter(prefix="/web")


@router.get("/session")
def session(request: Request, settings: Settings = Depends(get_settings_dep)) -> dict:
    return {"authenticated": valid_session(settings, request.cookies.get(COOKIE))}


@router.post("/session")
async def login(request: Request, settings: Settings = Depends(get_settings_dep)) -> Response:
    if not same_origin(settings, request.headers.get("origin"), str(request.base_url)):
        raise HTTPException(403, "Open the app from its own address.")
    attempts = getattr(request.app.state, "web_login_attempts", None)
    if attempts is None:
        attempts = request.app.state.web_login_attempts = defaultdict(deque)
    key = request.client.host if request.client else "unknown"
    recent = attempts[key]
    now = time.monotonic()
    while recent and recent[0] < now - 60:
        recent.popleft()
    if len(recent) >= 8:
        raise HTTPException(429, "Wait a minute before trying again.")
    recent.append(now)
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 2048:
            raise HTTPException(400, "Enter the demo access code.")
    import json

    try:
        body = json.loads(raw)
        code = body.get("code") if isinstance(body, dict) else None
    except (ValueError, UnicodeError):
        code = None
    if not isinstance(code, str) or not token_matches(settings.app_token, code):
        raise HTTPException(401, "That access code wasn't accepted.")
    recent.clear()
    response = Response(status_code=204)
    response.set_cookie(
        COOKIE,
        issue_session(settings),
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=secure_cookie(settings, str(request.base_url)),
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/logout", dependencies=[Depends(require_app_token)])
def logout() -> Response:
    response = Response(status_code=204)
    response.delete_cookie(COOKIE, httponly=True, samesite="strict")
    return response


@router.get("/contacts", dependencies=[Depends(require_app_token)])
def contacts(settings: Settings = Depends(get_settings_dep)) -> dict:
    return {
        "contacts": [
            {"id": key, "name": key.replace("-", " ").replace("_", " ").title(), "number": value}
            for key, value in parse_contacts(settings.allowed_recipients).items()
        ]
    }


@router.get("/recognition", dependencies=[Depends(require_app_token)])
def recognition_config(request: Request) -> dict:
    recognizer = request.app.state.web_recognizer
    return {
        "available": recognizer.available,
        "vocabulary": recognizer.bundle["vocabulary"],
        "provisional": True,
        "max_seconds": 4,
    }


@router.post("/recognize", dependencies=[Depends(require_app_token)])
async def recognize(request: Request) -> dict:
    recognizer = request.app.state.web_recognizer
    if not recognizer.available:
        raise HTTPException(503, "Signing isn't available right now. You can still type.")
    if request.headers.get("content-type", "").split(";")[0] != "application/octet-stream":
        raise HTTPException(415, "Expected landmark coordinates.")
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "Record one sign at a time, up to four seconds.")
    try:
        return await run_in_threadpool(recognizer.recognize, bytes(raw))
    except ValueError as error:
        raise HTTPException(400, "The sign clip was incomplete. Please try again.") from error
    except Exception as error:
        raise HTTPException(503, "That sign couldn't be read. You can still type.") from error
