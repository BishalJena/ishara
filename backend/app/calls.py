"""Call session layer (task V6): POST /calls, the app WebSocket, Bolna status webhooks
and the CallLedger used by the custom-LLM endpoint.

Turn and approval rules live in app/sessions.py; this module does the I/O around them
(Bolna, the composer, the app socket and the delivery timer). Status messages are
derived from state diffs, so every path that changes the state reports it.

Lines the voice says without a SEND reach the app as `caption {speaker: "agent"}`: the
disclosure once when the call goes live, the holding line whenever the custom LLM
returns it, and the goodbye after a successful `end_call`. Approved replies are not
echoed (the app shows them on `spoken`), and agent lines never touch turns, approvals
or the receptionist caption the composer reads.

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
from app.delegate import (
    ASK_TIMEOUT_S,
    CALLBACK_LINE,
    Brain,
    Decision,
    DelegateState,
    Exchange,
    brief_from,
    build_brief,
    build_notes,
)
from app.deps import get_ledger, get_settings_dep
from app.ports import BolnaClient, BolnaError, CallLedger, Composer
from app.protocol import (
    AnswerMessage,
    ApproveMessage,
    AskMessage,
    AskOption,
    AskResolvedMessage,
    BriefRequest,
    BriefResponse,
    CallNotes,
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
    TranscriptEntry,
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


class UnknownBrief(Exception):
    pass


END_AFTER_DONE_S = 6.0  # a delegated agent that promised a callback hangs up after this


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
_NOT_YET_LIVE = frozenset({CallState.DIALING, CallState.RINGING})


class CallManager(CallLedger):
    def __init__(
        self,
        settings: Settings,
        composer: Composer,
        bolna: BolnaClient,
        *,
        delivery_timeout_s: float = 10.0,
        brain: Brain | None = None,
        ask_timeout_s: float = ASK_TIMEOUT_S,
        end_after_done_s: float = END_AFTER_DONE_S,
    ) -> None:
        self._contacts = parse_contacts(settings.allowed_recipients)
        self._composer = composer
        self._bolna = bolna
        self._brain = brain or Brain(None)
        self._delivery_timeout_s = delivery_timeout_s
        self._ask_timeout_s = ask_timeout_s
        self._end_after_done_s = end_after_done_s
        self._sessions: dict[str, CallSession] = {}
        self._call_by_run: dict[str, str] = {}
        self._links: dict[str, _AppLink] = {}
        self._timers: dict[str, asyncio.Task[None]] = {}
        self._ask_timers: dict[str, asyncio.Task[None]] = {}
        self._asks: dict[str, tuple[str, tuple[AskOption, ...]]] = {}  # ask_id -> call, options
        self._briefs: dict[str, tuple[BriefRequest, BriefResponse]] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    # ---- REST ----

    def create_brief(self, request: BriefRequest) -> BriefResponse:
        response = build_brief(request)
        self._briefs[response.brief_id] = (request, response)
        return response

    def notes(self, call_id: str) -> CallNotes | None:
        session = self._sessions.get(call_id)
        if session is None:
            return None
        delegate = session.delegate if isinstance(session.delegate, DelegateState) else None
        return build_notes(
            call_id,
            delegate.brief if delegate else None,
            list(session.transcript),
            list(delegate.answers) if delegate else [],
            session.bolna_summary,
            session.finished,
        )

    async def start_call(self, request: StartCallRequest) -> StartCallResponse:
        number = self._contacts.get(request.contact_id)
        if number is None:
            raise UnknownContact(request.contact_id)
        delegate = None
        brief = None
        if request.mode == "delegated":
            # Starting the call is the brief's one approval: it is used up here, before
            # the dial is awaited, so a second request with the same id can't dial too.
            brief = self._briefs.pop(request.brief_id or "", None)
            if brief is None:
                raise UnknownBrief(request.brief_id)
            delegate = DelegateState(brief_from(*brief), attended=request.attended)
        session = CallSession(
            call_id=uuid.uuid4().hex, purpose=request.purpose, mode=request.mode, delegate=delegate
        )
        self._sessions[session.call_id] = session
        user_data = {markers.USER_DATA_CALL_ID: session.call_id}
        try:
            run_id = await self._bolna.start_call(number, user_data)
        except BolnaError as error:
            session.advance(CallState.ERROR)
            if brief is not None and request.brief_id is not None:
                self._briefs[request.brief_id] = brief  # nothing was dialled
            log.warning("call %s: Bolna start failed (%s)", session.call_id, type(error).__name__)
            raise CallStartFailed from error
        session.run_id = run_id
        self._call_by_run[run_id] = session.call_id
        log.info("call %s: dialing contact %s", session.call_id, request.contact_id)
        if session.mode != "live":
            log.info(
                "call %s: %s call, attended=%s", session.call_id, session.mode, request.attended
            )
        return StartCallResponse(call_id=session.call_id, state=session.state, mode=session.mode)

    async def apply_bolna_status(self, update: ExecutionUpdate) -> None:
        call_id = self._call_by_run.get(update.run_id)
        if call_id is None:
            return
        session = self._sessions[call_id]
        if update.summary:
            session.bolna_summary = update.summary
        line = call_state_for(update.status)
        if line is None:
            return
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
                case AnswerMessage():
                    await self._on_answer(session, message)
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
            return
        # end_call moves Bolna to its static goodbye node.
        await self._send_agent_line(session, markers.GOODBYE)

    # ---- delegated calls (D9) ----

    async def is_delegated(self, call_id: str) -> bool:
        session = self._sessions.get(call_id)
        return session is not None and isinstance(session.delegate, DelegateState)

    async def delegate_reply(self, call_id: str, heard: str) -> str | None:
        session = self._sessions.get(call_id)
        delegate = session.delegate if session is not None else None
        if session is None or session.finished or not isinstance(delegate, DelegateState):
            return None
        if delegate.pending_ask is not None:
            # The receptionist spoke while we wait for the user: hold the line, ask nothing new.
            return None
        if delegate.outcome is not None:
            # The brief is settled and the agent is about to hang up: nothing new is said,
            # agreed or asked (a different time offered now would otherwise open a second ask).
            return None
        if session.in_flight is not None:
            # A delegated line (the opening, the user's answer) is on its way to Bolna's
            # speak node; a line from here too would be said twice or over it (B24).
            return None
        if delegate.deciding:
            # Bolna sent another receptionist turn while the brain (Groq) still thinks
            # about the last one: one decision at a time, so one line and at most one ask.
            return None
        delegate.deciding = True
        try:
            decision = await self._brain.reply(delegate, heard)
        finally:
            delegate.deciding = False
        if session.finished:
            return None  # the call ended while the brain was thinking
        delegate.exchanges.append(Exchange(heard, decision.say))
        delegate.opened = True
        self._note(session, "agent", decision.say)
        await self._send_agent_line(session, decision.say)
        if decision.ask is not None:
            await self._open_ask(session, delegate, decision)
        elif decision.done:
            self._finish_delegate(session, delegate)
        return decision.say

    async def _open_ask(
        self, session: CallSession, delegate: DelegateState, decision: Decision
    ) -> None:
        assert decision.ask is not None
        question, options = decision.ask
        ask_id = uuid.uuid4().hex
        delegate.pending_ask = ask_id
        self._asks[ask_id] = (session.call_id, options)
        await self._send(
            session,
            AskMessage(
                ask_id=ask_id,
                question=question,
                options=list(options),
                fallback=CALLBACK_LINE,
                timeout_s=self._ask_timeout_s,
            ),
        )
        self._ask_timers[ask_id] = self._spawn(self._ask_timeout(session, ask_id))

    async def _ask_timeout(self, session: CallSession, ask_id: str) -> None:
        await asyncio.sleep(self._ask_timeout_s)
        await self._resolve_ask(session, ask_id, CALLBACK_LINE, "timeout")

    async def _on_answer(self, session: CallSession, message: AnswerMessage) -> None:
        entry = self._asks.get(message.ask_id)
        delegate = session.delegate
        if entry is None or entry[0] != session.call_id or not isinstance(delegate, DelegateState):
            await self._send(
                session,
                ErrorMessage(code="unknown_ask", message="That question is no longer open."),
            )
            return
        spoken = next((o.spoken for o in entry[1] if o.choice == message.choice), None)
        if spoken is None:
            await self._send(
                session, ErrorMessage(code="bad_choice", message="Not one of the options.")
            )
            return
        timer = self._ask_timers.pop(message.ask_id, None)
        if timer is not None:
            timer.cancel()
        if message.choice == "wait":
            # The agent holds the line; the question stays open and the timer restarts.
            self._ask_timers[message.ask_id] = self._spawn(
                self._ask_timeout(session, message.ask_id)
            )
            await self._speak_line(
                session, spoken, f"ask-{message.ask_id}-wait-{uuid.uuid4().hex[:6]}"
            )
            return
        await self._resolve_ask(session, message.ask_id, spoken, "user")

    async def _resolve_ask(
        self, session: CallSession, ask_id: str, spoken: str, source: str
    ) -> None:
        entry = self._asks.pop(ask_id, None)
        self._ask_timers.pop(ask_id, None)
        delegate = session.delegate
        if entry is None or not isinstance(delegate, DelegateState) or session.finished:
            return
        delegate.pending_ask = None
        await self._send(session, AskResolvedMessage(ask_id=ask_id, spoken=spoken, source=source))  # type: ignore[arg-type]
        await self._speak_line(session, spoken, f"ask-{ask_id}")
        if source == "timeout" or spoken.startswith("Yes"):
            self._finish_delegate(session, delegate)

    async def _speak_line(self, session: CallSession, text: str, turn_id: str) -> None:
        """Inject `text` through the verbatim speak node, as if the user had tapped SEND."""
        before = self._snapshot(session)
        try:
            turn = session.approve(turn_id, text)
        except TurnRejected as rejected:
            log.info("call %s: cannot speak delegated line (%s)", session.call_id, rejected.code)
            return
        await self._publish(session, before)
        self._timers[session.call_id] = self._spawn(self._expire_later(session, turn.turn_id))
        assert session.run_id is not None
        properties = {markers.PROP_REPLY_TEXT: text, markers.PROP_TURN_ID: turn.turn_id}
        try:
            await self._bolna.send_event(session.run_id, markers.EVENT_USER_REPLY, properties)
        except BolnaError as error:
            log.warning(
                "call %s: delegated line failed (%s)", session.call_id, type(error).__name__
            )
            await self._fail_delivery(session, turn.turn_id, BOLNA_UNREACHABLE)

    def _finish_delegate(self, session: CallSession, delegate: DelegateState) -> None:
        if delegate.outcome is None:
            delegate.outcome = "done"
            self._spawn(self._end_after(session))

    async def _end_after(self, session: CallSession) -> None:
        await asyncio.sleep(self._end_after_done_s)
        if not session.finished:
            await self._on_end(session)

    def _cancel_ask_timers(self, call_id: str) -> None:
        for ask_id, (owner, _) in list(self._asks.items()):
            if owner == call_id:
                self._asks.pop(ask_id, None)
                timer = self._ask_timers.pop(ask_id, None)
                if timer is not None and timer is not asyncio.current_task():
                    timer.cancel()

    def _note(self, session: CallSession, speaker: str, text: str) -> None:
        session.transcript.append(TranscriptEntry(speaker=speaker, text=text, at=time.time()))  # type: ignore[arg-type]

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
        self._note(session, "receptionist", text)
        await self._publish(session, before)
        await self._send(session, CaptionMessage(text=text, at=time.time()))

    async def record_agent_line(self, call_id: str, text: str) -> None:
        session = self._sessions.get(call_id)
        if session is None or session.finished:
            return
        await self._send_agent_line(session, text)

    async def claim_reply(self, call_id: str, turn_id: str, text: str) -> bool:
        session = self._sessions.get(call_id)
        return session is not None and session.claim(turn_id, text)

    async def mark_spoken(self, call_id: str, turn_id: str) -> None:
        session = self._sessions.get(call_id)
        if session is None:
            return
        before = self._snapshot(session)
        spoken_text = session.in_flight.approved_text if session.in_flight is not None else None
        if session.mark_spoken(turn_id):
            if spoken_text:
                self._note(session, "agent", spoken_text)
                delegate = session.delegate
                if turn_id.startswith("ask-") and isinstance(delegate, DelegateState):
                    # Only an answer the receptionist heard counts in the notes; one that
                    # was never delivered must not turn into "booked".
                    delegate.answers.append(spoken_text)
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
        if session.finished:
            # However the call ended (the app, Bolna's webhook, the agent), an open
            # question can no longer be answered or time out into speech.
            self._cancel_ask_timers(session.call_id)
        await self._send(session, StatusMessage(state=session.state))
        if state in _NOT_YET_LIVE and session.line is CallState.IN_CALL:
            # Bolna plays its static welcome message (the disclosure) as the call
            # connects. The line only moves forward, so this happens once per call.
            self._note(session, "agent", markers.DISCLOSURE)
            await self._send_agent_line(session, markers.DISCLOSURE)
            delegate = session.delegate
            if isinstance(delegate, DelegateState) and not delegate.opened:
                # D9: the agent states the brief's request right after the disclosure
                # instead of waiting for the receptionist to speak first. Awaited, not
                # spawned: when a caption made the line live, the listen request that
                # carried it must already see the opening in flight.
                opening = self._brain.rules.opening(delegate)
                delegate.opened = True
                delegate.exchanges.append(Exchange("", opening))
                await self._speak_line(session, opening, "delegate-open")
        return True

    async def _send_agent_line(self, session: CallSession, text: str) -> None:
        await self._send(session, CaptionMessage(text=text, at=time.time(), speaker="agent"))

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
    except UnknownBrief as error:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "unknown brief; create it with POST /briefs"
        ) from error
    except CallStartFailed as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "could not start the call") from error


@router.post("/briefs", dependencies=[Depends(require_app_token)])
def create_brief(body: BriefRequest, manager: CallManager = Depends(get_manager)) -> BriefResponse:
    return manager.create_brief(body)


@router.get("/calls/{call_id}/notes", dependencies=[Depends(require_app_token)])
def call_notes(call_id: str, manager: CallManager = Depends(get_manager)) -> CallNotes:
    notes = manager.notes(call_id)
    if notes is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown call")
    return notes


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
