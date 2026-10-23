"""Path A text-to-speech (task A5): POST /tts via Sarvam.

The user dials from the Phone app; on SEND the app posts the approved sentence here,
plays the returned WAV, and Add Audio in Calls injects it into the call. This request
is Path A's approval, so each turn_id may produce audio at most once.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import HTTPConnection

from app.auth import require_app_token
from app.config import Settings
from app.deps import get_settings_dep
from app.protocol import MAX_SPOKEN_CHARS, TurnId
from app.sarvam import SarvamError, SarvamTTS

logger = logging.getLogger(__name__)

router = APIRouter()


class TTSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    turn_id: TurnId
    text: str = Field(min_length=1, max_length=MAX_SPOKEN_CHARS)


class TurnClaims:
    """Process-local set of turn_ids that are being or have been voiced."""

    def __init__(self) -> None:
        self._claimed: set[str] = set()

    def claim(self, turn_id: str) -> bool:
        if turn_id in self._claimed:
            return False
        self._claimed.add(turn_id)
        return True

    def release(self, turn_id: str) -> None:
        self._claimed.discard(turn_id)


# Async so both run on the event loop: the check-then-set needs no lock.
async def get_turn_claims(connection: HTTPConnection) -> TurnClaims:
    state = connection.app.state
    if getattr(state, "tts_turn_claims", None) is None:
        state.tts_turn_claims = TurnClaims()
    return state.tts_turn_claims


async def get_speech_client(
    connection: HTTPConnection, settings: Settings = Depends(get_settings_dep)
) -> SarvamTTS:
    if settings.sarvam_api_key is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "text-to-speech not configured")
    transport: httpx.AsyncBaseTransport | None = getattr(
        connection.app.state, "sarvam_transport", None
    )
    return SarvamTTS(settings.sarvam_api_key, transport=transport)


@router.post("/tts", dependencies=[Depends(require_app_token)])
async def speak(
    request: TTSRequest,
    speech: SarvamTTS = Depends(get_speech_client),
    claims: TurnClaims = Depends(get_turn_claims),
) -> Response:
    if not claims.claim(request.turn_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "turn already voiced")
    try:
        wav = await speech.synthesize(request.text)
    except SarvamError as exc:
        # Nothing reached the user, so SEND may be tapped again for this turn.
        claims.release(request.turn_id)
        logger.warning("tts failed for turn %s: %s", request.turn_id, exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "text-to-speech failed") from None
    return Response(content=wav, media_type="audio/wav")
