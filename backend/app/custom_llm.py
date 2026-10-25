"""Bolna custom-LLM endpoint (task V2): POST /v1/chat/completions.

Bolna calls this with the OpenAI SDK (streaming chat completions, bearer token as the
only header, no call or execution id), so the call, node and turn come from the
marker block in the node prompt (app.markers). Request kinds and the reply each gets:

- routing: system prompt starts "Routing Guidelines", tools `transition_to_<node>` /
  `stay_on_current_node`, tool_choice "required". Its "Node Objective" embeds the node
  prompt with variables filled in, so it carries our marker block and the approved
  text; it must be recognised first. Reply: no tool call, which Bolna treats as "stay".
- hang-up check: system prompt asks for `{"hangup": "Yes" or "No"}`. Reply: "No"; we
  end calls only through the end_call event.
- voicemail check: asks for `{"is_voicemail": ...}`. Reply: "No".
- listen node: forward new receptionist utterances as captions; reply with nothing,
  or the holding line when the latest user message is Bolna's `[silence]` repeat (the
  app sees that line as an agent caption).
- speak node: speak the approved text only if the ledger grants the single-use claim.
- anything else: empty reply.

Sources: https://www.bolna.ai/docs/custom-llm-inference.md (OpenAI format, bearer
auth, extra_body sent on turns, graph routing, end-of-call and voicemail checks),
https://www.bolna.ai/docs/graph-agent/edges-and-routing.md,
https://www.bolna.ai/docs/graph-agent/static-nodes.md (`[silence]`), and Bolna's open
source runtime (github.com/bolna-ai/bolna: agent_types/graph_agent.py, llms/openai_llm.py)
for the routing, hang-up and voicemail request formats. The hosted service may differ;
the shape log (app.shape_log) records what really arrives.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from functools import partial

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import Response

from app.auth import require_custom_llm_token
from app.deps import get_ledger
from app.markers import HOLDING_LINE, SILENCE_MARKER, MarkerBlock, parse_marker_block
from app.openai_chat import DEFAULT_MODEL, ChatCompletionRequest, completion, sse_events
from app.ports import CallLedger
from app.shape_log import log_shape, request_shape
from app.utterances import UtteranceTracker

router = APIRouter()

ROUTING_PROMPT_PREFIX = "Routing Guidelines"
ROUTING_STAY_TOOL = "stay_on_current_node"
ROUTING_TOOL_PREFIX = "transition_to_"
HANGUP_KEY = "hangup"
VOICEMAIL_KEY = "is_voicemail"


class RequestKind(StrEnum):
    ROUTING = "routing"
    HANGUP_CHECK = "hangup_check"
    VOICEMAIL_CHECK = "voicemail_check"
    LISTEN = "listen"
    SPEAK = "speak"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Reply:
    content: str
    outcome: str
    spoken_turn: tuple[str, str] | None = None


def is_routing(body: ChatCompletionRequest) -> bool:
    if body.tool_choice == "required":
        return True
    if any(
        name == ROUTING_STAY_TOOL or name.startswith(ROUTING_TOOL_PREFIX)
        for name in body.tool_names()
    ):
        return True
    return any(
        text.lstrip().startswith(ROUTING_PROMPT_PREFIX) for text in body.texts_by_role("system")
    )


def find_marker(body: ChatCompletionRequest) -> MarkerBlock | None:
    for text in body.texts_by_role("system"):
        if marker := parse_marker_block(text):
            return marker
    return None


def classify(body: ChatCompletionRequest) -> tuple[RequestKind, MarkerBlock | None]:
    if is_routing(body):
        return RequestKind.ROUTING, None
    if marker := find_marker(body):
        return RequestKind(marker.node), marker
    system = "\n".join(body.texts_by_role("system"))
    if f'"{HANGUP_KEY}"' in system:
        return RequestKind.HANGUP_CHECK, None
    if f'"{VOICEMAIL_KEY}"' in system:
        return RequestKind.VOICEMAIL_CHECK, None
    return RequestKind.UNKNOWN, None


def _is_silence(text: str) -> bool:
    return text.strip().startswith(SILENCE_MARKER)


def receptionist_utterances(body: ChatCompletionRequest) -> list[str]:
    stripped = (text.strip() for text in body.texts_by_role("user"))
    return [text for text in stripped if text and not _is_silence(text)]


def latest_user_is_silence(body: ChatCompletionRequest) -> bool:
    users = body.texts_by_role("user")
    return bool(users) and _is_silence(users[-1])


async def decide(
    body: ChatCompletionRequest,
    kind: RequestKind,
    marker: MarkerBlock | None,
    ledger: CallLedger,
    tracker: UtteranceTracker,
) -> Reply:
    if kind == RequestKind.HANGUP_CHECK:
        return Reply(json.dumps({HANGUP_KEY: "No"}), "json_no")
    if kind == RequestKind.VOICEMAIL_CHECK:
        return Reply(json.dumps({VOICEMAIL_KEY: "No"}), "json_no")
    if marker is None:
        return Reply("", "silent")

    new_utterances = tracker.take_new(marker.call_id, receptionist_utterances(body))
    for text in new_utterances:
        await ledger.record_caption(marker.call_id, text)

    if marker.node == "listen":
        if latest_user_is_silence(body):
            if await _delegated_line(ledger, marker.call_id, None) is not None:
                return Reply("", "silent")  # a delegated agent waits quietly
            await ledger.record_agent_line(marker.call_id, HOLDING_LINE)
            return Reply(HOLDING_LINE, "holding_line")
        heard = " ".join(new_utterances).strip()
        if heard and (say := await _delegated_line(ledger, marker.call_id, heard)):
            return Reply(say, "delegate")
        return Reply("", "silent")

    # parse_marker_block only returns a speak block with both fields filled in.
    assert marker.turn_id is not None and marker.reply_text is not None
    if not await ledger.claim_reply(marker.call_id, marker.turn_id, marker.reply_text):
        return Reply("", "claim_refused")
    return Reply(marker.reply_text, "reply", spoken_turn=(marker.call_id, marker.turn_id))


async def _delegated_line(ledger: CallLedger, call_id: str, heard: str | None) -> str | None:
    """The delegated agent's next line (D9), or None for live calls / ledgers without it.
    `heard` None only asks whether the call is delegated."""
    reply = getattr(ledger, "delegate_reply", None)
    if reply is None:
        return None
    if heard is None:
        is_delegated = getattr(ledger, "is_delegated", None)
        return "" if is_delegated is not None and await is_delegated(call_id) else None
    return await reply(call_id, heard)


async def stream_completion(
    model: str, content: str, on_complete: Callable[[], Awaitable[None]] | None
) -> AsyncIterator[str]:
    """Stream the reply, then run `on_complete` only if every event was sent."""
    for event in sse_events(model, content):
        yield event
    if on_complete is not None:
        await on_complete()


def get_tracker(request: Request) -> UtteranceTracker:
    return request.app.state.utterance_tracker


@router.post("/v1/chat/completions", dependencies=[Depends(require_custom_llm_token)])
async def chat_completions(
    body: ChatCompletionRequest,
    ledger: CallLedger = Depends(get_ledger),
    tracker: UtteranceTracker = Depends(get_tracker),
) -> Response:
    kind, marker = classify(body)
    reply = await decide(body, kind, marker, ledger, tracker)
    log_shape(
        request_shape(body, kind=kind, node=marker.node if marker else None, outcome=reply.outcome)
    )

    on_complete = None
    if reply.spoken_turn is not None:
        on_complete = partial(ledger.mark_spoken, *reply.spoken_turn)

    model = body.model or DEFAULT_MODEL
    if body.stream:
        return StreamingResponse(
            stream_completion(model, reply.content, on_complete),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )
    background = BackgroundTask(on_complete) if on_complete is not None else None
    return JSONResponse(completion(model, reply.content), background=background)
