"""Call session layer (task V6): POST /calls, the app WebSocket, Bolna status webhooks
and the CallLedger used by the custom-LLM endpoint.

Turn and approval rules live in app/sessions.py; this module does the I/O around them
(Bolna, the composer, the app socket and the delivery timer). Status messages are
derived from state diffs, so every path that changes the state reports it.

Recipient numbers never leave this module: not in responses, messages or logs.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import Coroutine
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket, status
from pydantic import BaseModel, ValidationError
from starlette.websockets import WebSocketDisconnect

from app import markers
from app.auth import require_app_token, token_matches
from app.bolna_status import ExecutionUpdate, call_state_for
from app.config import Settings
from app.contacts import parse_contacts
from app.deps import get_ledger, get_settings_dep
from app.ports import BolnaClient, BolnaError, CallLedger, Composer
from app.protocol import (
    ApproveMessage,
    CallState,
    CaptionMessage,
    ChipsMessage,
    ComposeRequest,
    DraftMessage,
    EndMessage,
    ErrorMessage,
    NotDeliveredMessage,
    SpokenMessage,
    StartCallRequest,
    StartCallResponse,
    StatusMessage,
    StopMessage,
    app_message_adapter,
)
from app.sessions import CallSession, Turn, TurnRejected

log = logging.getLogger(__name__)

CLOSE_UNAUTHORIZED = 4401
CLOSE_UNKNOWN_CALL = 4404
CLOSE_REPLACED = 4409

NO_CONFIRMATION = "no_confirmation"
BOLNA_UNREACHABLE = "bolna_unreachable"


class UnknownContact(Exception):
    pass


class CallStartFailed(Exception):
    pass


class _AppLink:
    """The one active app socket of a call."""

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.open = True

    async def send(self, message: BaseModel) -> None:
        if not self.open:
            return
        try:
            await self.websocket.send_text(message.model_dump_json())
        except WebSocketDisconnect:
            self.open = False

    async def close(self, code: int) -> None:
        if not self.open:
            return
        self.open = False
        with contextlib.suppress(WebSocketDisconnect):
            await self.websocket.close(code=code)


_Snapshot = tuple[CallState, Turn | None]


class CallManager(CallLedger):
    def __init__(
        self,
        settings: Settings,
        composer: Composer,
        bolna: BolnaClient,
        *,
        delivery_timeout_s: float = 10.0,
    ) -> None:
        self._contacts = parse_contacts(settings.allowed_recipients)
        self._composer = composer
        self._bolna = bolna
        self._delivery_timeout_s = delivery_timeout_s
        self._sessions: dict[str, CallSession] = {}
        self._call_by_run: dict[str, str] = {}
        self._links: dict[str, _AppLink] = {}
        self._timers: dict[str, asyncio.Task[None]] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    # ---- REST ----

    async def start_call(self, request: StartCallRequest) -> StartCallResponse:
        number = self._contacts.get(request.contact_id)
        if number is None:
            raise UnknownContact(request.contact_id)
        session = CallSession(call_id=uuid.uuid4().hex, purpose=request.purpose)
        self._sessions[session.call_id] = session
        user_data = {markers.USER_DATA_CALL_ID: session.call_id}
        try:
            run_id = await self._bolna.start_call(number, user_data)
        except BolnaError as error:
            session.advance(CallState.ERROR)
            log.warning("call %s: Bolna start failed (%s)", session.call_id, type(error).__name__)
            raise CallStartFailed from error
        session.run_id = run_id
        self._call_by_run[run_id] = session.call_id
        log.info("call %s: dialing contact %s", session.call_id, request.contact_id)
        return StartCallResponse(call_id=session.call_id, state=session.state)

    async def apply_bolna_status(self, update: ExecutionUpdate) -> None:
        call_id = self._call_by_run.get(update.run_id)
        line = call_state_for(update.status)
        if call_id is None or line is None:
            return
        session = self._sessions[call_id]
        before = self._snapshot(session)
        session.advance(line)
        await self._publish(session, before)

    # ---- app socket ----

    def has_call(self, call_id: str) -> bool:
        return call_id in self._sessions

    async def attach(self, call_id: str, websocket: WebSocket) -> _AppLink:
        """Make this socket the call's app socket, replacing (closing) any older one."""
        link = _AppLink(websocket)
        old = self._links.get(call_id)
        self._links[call_id] = link
        if old is not None:
            await old.close(CLOSE_REPLACED)
        await link.send(StatusMessage(state=self._sessions[call_id].state))
        return link

    async def detach(self, call_id: str, link: _AppLink) -> None:
        """The app socket went away: per the edge-case table nothing unseen gets sent,
        so an approval Bolna has not picked up yet is revoked."""
        link.open = False
        if self._links.get(call_id) is not link:
            return
        del self._links[call_id]
        session = self._sessions[call_id]
        before = self._snapshot(session)
        session.revoke_unclaimed()
        await self._publish(session, before)

    async def handle_app_message(self, call_id: str, link: _AppLink, raw: str) -> None:
        if self._links.get(call_id) is not link:
            return
        session = self._sessions[call_id]
        try:
            message = app_message_adapter.validate_json(raw)
        except ValidationError:
            await link.send(ErrorMessage(code="bad_message", message="Unrecognised message."))
            return
        try:
            match message:
                case ChipsMessage():
                    await self._on_chips(session, message)
                case ApproveMessage():
                    await self._on_approve(session, message)
                case StopMessage():
                    await self._on_stop(session)
                case EndMessage():
                    await self._on_end(session)
        except TurnRejected as rejected:
            await self._send(session, ErrorMessage(code=rejected.code, message=rejected.message))

    async def _on_chips(self, session: CallSession, message: ChipsMessage) -> None:
        before = self._snapshot(session)
        turn = session.set_chips(message.turn_id, message.chips)
        await self._publish(session, before)
        if turn.chips:
            self._spawn(self._compose(session, turn, turn.chips_rev))

    async def _compose(self, session: CallSession, turn: Turn, chips_rev: int) -> None:
        request = ComposeRequest(
            turn_id=turn.turn_id,
            chips=list(turn.chips),
            purpose=session.purpose,
            last_caption=session.last_caption,
        )
        draft = await self._composer.compose(request)
        if session.draft_is_current(turn.turn_id, chips_rev):
            await self._send(
                session, DraftMessage(turn_id=turn.turn_id, text=draft.text, source=draft.source)
            )

    async def _on_approve(self, session: CallSession, message: ApproveMessage) -> None:
        before = self._snapshot(session)
        turn = session.approve(message.turn_id, message.text)
        # Publish first: it cancels the timer of an approval this new turn superseded.
        await self._publish(session, before)
        self._timers[session.call_id] = self._spawn(self._expire_later(session, turn.turn_id))
        assert session.run_id is not None  # approve() requires a run id
        properties = {markers.PROP_REPLY_TEXT: message.text, markers.PROP_TURN_ID: turn.turn_id}
        try:
            await self._bolna.send_event(session.run_id, markers.EVENT_USER_REPLY, properties)
        except BolnaError as error:
            log.warning("call %s: user_reply failed (%s)", session.call_id, type(error).__name__)
            await self._fail_delivery(session, turn.turn_id, BOLNA_UNREACHABLE)

    async def _on_stop(self, session: CallSession) -> None:
        before = self._snapshot(session)
        session.stop()
        if not await self._publish(session, before):
            await self._send(session, StatusMessage(state=session.state))

    async def _on_end(self, session: CallSession) -> None:
        before = self._snapshot(session)
        if not session.advance(CallState.ENDED):
            await self._send(session, StatusMessage(state=session.state))
            return
        await self._publish(session, before)
        if session.run_id is None:
            return
        try:
            await self._bolna.send_event(session.run_id, markers.EVENT_END_CALL, {})
        except BolnaError as error:
            log.warning("call %s: end_call failed (%s)", session.call_id, type(error).__name__)
            await self._send(
                session,
                ErrorMessage(code="end_failed", message="Could not reach Bolna to hang up."),
            )

    # ---- delivery timer ----

    async def _expire_later(self, session: CallSession, turn_id: str) -> None:
        await asyncio.sleep(self._delivery_timeout_s)
        await self._fail_delivery(session, turn_id, NO_CONFIRMATION)

    async def _fail_delivery(self, session: CallSession, turn_id: str, reason: str) -> None:
        before = self._snapshot(session)
        if session.fail_delivery(turn_id):
            await self._send(session, NotDeliveredMessage(turn_id=turn_id, reason=reason))
        await self._publish(session, before)

    # ---- CallLedger (custom-LLM endpoint) ----

    async def record_caption(self, call_id: str, text: str) -> None:
        session = self._sessions.get(call_id)
        if session is None or session.finished:
            return
        before = self._snapshot(session)
        session.hear_caption(text)
        await self._publish(session, before)
        await self._send(session, CaptionMessage(text=text, at=time.time()))

    async def claim_reply(self, call_id: str, turn_id: str, text: str) -> bool:
        session = self._sessions.get(call_id)
        return session is not None and session.claim(turn_id, text)

    async def mark_spoken(self, call_id: str, turn_id: str) -> None:
        session = self._sessions.get(call_id)
        if session is None:
            return
        before = self._snapshot(session)
        if session.mark_spoken(turn_id):
            await self._send(session, SpokenMessage(turn_id=turn_id))
        await self._publish(session, before)

    # ---- helpers ----

    @staticmethod
    def _snapshot(session: CallSession) -> _Snapshot:
        return session.state, session.in_flight

    async def _publish(self, session: CallSession, before: _Snapshot) -> bool:
        """Stop the delivery timer once its turn left flight, and report a state change.
        Returns whether a status message was sent."""
        state, in_flight = before
        if in_flight is not None and session.in_flight is not in_flight:
            self._cancel_timer(session.call_id)
        if session.state == state:
            return False
        await self._send(session, StatusMessage(state=session.state))
        return True

    def _cancel_timer(self, call_id: str) -> None:
        timer = self._timers.pop(call_id, None)
        # The timer itself settles the turn on expiry; it must not cancel itself.
        if timer is not None and timer is not asyncio.current_task():
            timer.cancel()

    async def _send(self, session: CallSession, message: BaseModel) -> None:
        link = self._links.get(session.call_id)
        if link is not None:
            await link.send(message)

    def _spawn(self, coroutine: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task


# ---- routes ----

router = APIRouter()


def get_manager(ledger: CallLedger = Depends(get_ledger)) -> CallManager:
    if not isinstance(ledger, CallManager):
        raise TypeError("app.state.ledger must be a CallManager for the call routes")
    return ledger


@router.post("/calls", dependencies=[Depends(require_app_token)])
async def start_call(
    body: StartCallRequest, manager: CallManager = Depends(get_manager)
) -> StartCallResponse:
    try:
        return await manager.start_call(body)
    except UnknownContact as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "contact not allowed") from error
    except CallStartFailed as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "could not start the call") from error


def _bearer_token(header: str | None) -> str | None:
    scheme, _, token = (header or "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" else None


@router.websocket("/calls/{call_id}/ws")
async def call_socket(
    websocket: WebSocket,
    call_id: str,
    settings: Settings = Depends(get_settings_dep),
    manager: CallManager = Depends(get_manager),
) -> None:
    # Accept first so the app sees a close code instead of a bare handshake failure.
    await websocket.accept()
    if not token_matches(settings.app_token, _bearer_token(websocket.headers.get("authorization"))):
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return
    if not manager.has_call(call_id):
        await websocket.close(code=CLOSE_UNKNOWN_CALL)
        return
    link = await manager.attach(call_id, websocket)
    # A replaced socket is closed by the server, so stop reading instead of hitting
    # starlette's "not connected" error on the next receive.
    with contextlib.suppress(WebSocketDisconnect):
        while link.open:
            raw = await websocket.receive_text()
            await manager.handle_app_message(call_id, link, raw)
    await manager.detach(call_id, link)


@router.post(markers.WEBHOOK_PATH + "/{secret}", status_code=status.HTTP_204_NO_CONTENT)
async def bolna_webhook(
    secret: str,
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    manager: CallManager = Depends(get_manager),
) -> Response:
    if not token_matches(settings.bolna_webhook_secret, secret):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    try:
        update = ExecutionUpdate.model_validate_json(await request.body())
    except ValidationError as error:
        # FastAPI's default 422 would echo the payload, which holds the recipient number.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "bad payload") from error
    await manager.apply_bolna_status(update)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
