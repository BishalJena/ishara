"""Mac fallback for the demo (PLAN A4): recognised signs become chips on the backend WebSocket.

`TurnState` owns the turn rules from PLAN §4 and holds no I/O, so the iOS app and this
bridge can be checked against the same behaviour. Nothing here speaks on its own: the
only path to an `approve` message is an explicit SEND or quick reply.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

SIGNS = ("hello", "thankyou", "yes", "no", "sorry", "doctor",
         "today", "tomorrow", "morning", "afternoon", "evening", "time")
MAX_CHIPS = 8  # backend ChipsMessage limit
AGENT_LABEL = "Ishara (voice)"
QUICK_REPLIES = {
    "yes": "Yes.",
    "no": "No.",
    "wait": "Please wait a moment, I'm signing my reply.",
    "repeat": "Sorry, could you please repeat that?",
}

Result = str | None  # a sign from SIGNS, or None when recognition is unsure ("?")
Message = dict[str, object]


def new_turn_id() -> str:
    return uuid.uuid4().hex


class ChipLimit(ValueError):
    """The turn already holds MAX_CHIPS sendable chips."""


@dataclass(frozen=True)
class Draft:
    turn_id: str
    text: str
    source: str


@dataclass
class TurnState:
    """Chips, draft and approvals for one call. Methods return the message to send, or None."""

    new_id: Callable[[], str] = new_turn_id
    chips: list[Result] = field(default_factory=list)
    draft: Draft | None = None
    ended: bool = False
    undelivered: tuple[str, str] | None = None  # (turn_id, text) awaiting a manual re-SEND
    awaiting: dict[str, str] = field(default_factory=dict)  # approved turn_id -> text
    turn_id: str = ""

    def __post_init__(self) -> None:
        self.turn_id = self.turn_id or self.new_id()

    @property
    def sendable(self) -> list[str]:
        """Chips the backend may see; unsure entries stay local."""
        return [chip for chip in self.chips if chip is not None]

    def add(self, result: Result) -> Message | None:
        if result is not None and result not in SIGNS:
            raise ValueError(f"unknown sign {result!r}")
        if self.ended:
            return None
        if result is not None and len(self.sendable) >= MAX_CHIPS:
            raise ChipLimit(f"at most {MAX_CHIPS} chips per turn; remove one (x) or clear (c)")
        before = self.sendable
        self.chips.append(result)
        return self._chips_message(before)

    def remove_last(self) -> Message | None:
        if not self.chips:
            return None
        before = self.sendable
        self.chips.pop()
        return self._chips_message(before)

    def clear(self) -> None:
        """Clear wipes the turn; late drafts for it are ignored because the id changes."""
        if not self.ended:
            self._new_turn()

    def on_draft(self, turn_id: str, text: str, source: str) -> Draft | None:
        if turn_id != self.turn_id or not self.sendable:
            return None
        self.draft = Draft(turn_id, text, source)
        return self.draft

    def approve(self) -> Message | None:
        """SEND: the current turn's draft, else the text that was not delivered. Single use.

        After the call ends there is neither: on_ended wipes both and add() is blocked.
        """
        if self.draft is not None:  # on_draft only keeps drafts for the current turn
            text = self.draft.text
        elif self.undelivered is not None:
            text = self.undelivered[1]
        else:
            return None
        return self._approve(text)

    def quick_reply(self, name: str) -> Message | None:
        text = QUICK_REPLIES[name]
        if self.ended:
            return None
        self._new_turn()
        return self._approve(text)

    def on_spoken(self, turn_id: str) -> str | None:
        """Returns the delivered text. A late confirmation also cancels the pending re-SEND."""
        if self.undelivered is not None and self.undelivered[0] == turn_id:
            text, self.undelivered = self.undelivered[1], None
            return text
        return self.awaiting.pop(turn_id, None)

    def on_not_delivered(self, turn_id: str) -> str | None:
        """Remember the text for a manual re-SEND; never resend here."""
        text = self.awaiting.pop(turn_id, None)
        if text is not None:
            self.undelivered = (turn_id, text)
        return text

    def stop(self) -> Message | None:
        """STOP cancels unspoken output on the backend; it never queues anything new."""
        return None if self.ended else {"type": "stop"}

    def end(self) -> Message | None:
        if self.ended:
            return None
        self.on_ended()
        return {"type": "end"}

    def on_ended(self) -> None:
        """The call is over: wipe everything so nothing can be sent afterwards."""
        self.ended = True
        self.chips, self.draft, self.undelivered = [], None, None
        self.awaiting.clear()

    def _chips_message(self, before: list[str]) -> Message | None:
        after = self.sendable
        if after == before:
            return None
        self.draft = None  # the old draft no longer matches the chips
        return {"type": "chips", "turn_id": self.turn_id, "chips": after}

    def _approve(self, text: str) -> Message:
        message: Message = {"type": "approve", "turn_id": self.turn_id, "text": text}
        self.awaiting[self.turn_id] = text
        self.undelivered = None
        self._new_turn()
        return message

    def _new_turn(self) -> None:
        self.turn_id, self.chips, self.draft = self.new_id(), [], None


class SessionLog:
    """Timestamps event lines; with a path, also appends every event to a JSONL file so a
    session can be reviewed later (recognizer results, chips, drafts, captions, spoken)."""

    def __init__(self, out: Callable[[str], None] = print, path: Path | None = None,
                 now: Callable[[], datetime] = datetime.now) -> None:
        self.out, self.path, self.now = out, path, now
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)  # an unusable path fails before the call

    def show(self, text: str) -> None:
        self.out(f"{self.now():%H:%M:%S} {text}")

    def record(self, source: str, message: Mapping[str, Any]) -> None:
        """source: recognizer, backend (received) or bridge (sent)."""
        if self.path is None:
            return
        entry = {"time": self.now().isoformat(timespec="milliseconds"), "from": source,
                 "message": dict(message)}
        try:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as error:  # a full disk must not end the call; the log just stops
            self.path = None
            self.out(f"! session log stopped: {error}")


# ---- recognition sources ----


class RecognitionSource(Protocol):
    """One `Result` per finished sign segment; the stream ends when the source is done.

    A live recognizer (detector segments -> SignCLIP -> frozen cut-off) is just another
    source: yield the matched sign, or None when no reference is close enough.
    """

    def results(self) -> AsyncIterator[Result]: ...


class _End(Enum):
    DONE = 0  # sentinel that ends a stream


def parse_result(token: str) -> Result:
    token = token.strip().lower()
    if token == "?":
        return None
    if token not in SIGNS:
        raise ValueError(f"unknown sign {token!r}; use one of {', '.join(SIGNS)} or ?")
    return token


class ManualSource:
    """Signs typed in the terminal; the terminal loop feeds each parsed token."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Result | _End] = asyncio.Queue()

    def feed(self, result: Result) -> None:
        self._queue.put_nowait(result)

    def close(self) -> None:
        self._queue.put_nowait(_End.DONE)

    async def results(self) -> AsyncIterator[Result]:
        while (item := await self._queue.get()) is not _End.DONE:
            yield item


@dataclass(frozen=True)
class ReplaySource:
    """Scripted results for rehearsals: each step waits `delay` seconds, then yields."""

    steps: tuple[tuple[float, Result], ...]
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

    @classmethod
    def from_json(cls, text: str,
                  sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> ReplaySource:
        """`["hello", "?", null, {"sign": "doctor", "delay": 1.5}]`; "?" and null are unsure."""
        steps = []
        for item in json.loads(text):
            if isinstance(item, dict):
                if set(item) - {"sign", "delay"} or "sign" not in item:
                    raise ValueError(f"replay step needs 'sign' and optional 'delay': {item}")
                delay, sign = float(item.get("delay", 0)), item["sign"]
                if delay < 0:
                    raise ValueError(f"negative delay in {item}")
            else:
                delay, sign = 0.0, item
            steps.append((delay, None if sign is None else parse_result(sign)))
        return cls(tuple(steps), sleep)

    async def results(self) -> AsyncIterator[Result]:
        for delay, result in self.steps:
            if delay:
                await self.sleep(delay)
            yield result


class BlockingSource:
    """Runs a blocking iterator (webcam loop, model inference) off the event loop."""

    def __init__(self, make_iterator: Callable[[], Iterator[Result]]) -> None:
        self._make_iterator = make_iterator

    async def results(self) -> AsyncIterator[Result]:
        iterator = await asyncio.to_thread(self._make_iterator)
        while (item := await asyncio.to_thread(next, iterator, _End.DONE)) is not _End.DONE:
            yield item


PROVISIONAL_BANNER = "PROVISIONAL — uncalibrated, for trying only"


def result_line(result: Result, **details: object) -> str:
    """One recognizer result as a JSON line: the wire format of `SubprocessSource`."""
    return json.dumps({"sign": result, **details})


def parse_result_details(line: str) -> dict[str, Any]:
    """A whole result line; "sign" is checked, the rest is evidence to show and log."""
    details: dict[str, Any] = json.loads(line)
    sign = details["sign"]
    if sign is None or (isinstance(sign, str) and sign in SIGNS):
        return details
    raise ValueError(f"recognizer sent unknown sign {sign!r}")


def parse_result_line(line: str) -> Result:
    sign: Result = parse_result_details(line)["sign"]
    return sign


CHECK_WORDS = {"similarity": "low similarity", "margin": "low margin",
               "pose": "body seen in too few frames", "hands": "hands seen in too few frames"}


def unsure_why(details: Mapping[str, Any]) -> str | None:
    """Short words for a "?": the failed cut-offs, else the recognizer's reason."""
    if details["sign"] is not None:
        return None
    if checks := details.get("failed_checks"):
        return ", ".join(CHECK_WORDS.get(c, c) for c in checks)
    reason: str | None = details.get("reason")
    return reason


def describe_result(details: Mapping[str, Any]) -> str:
    """One readable line per sign, e.g. `✓ doctor  (doctor 0.83 | time 0.61 | no 0.55;
    margin 0.22; 0.46 s)`. Lines from an older recognizer show what they carry."""
    sign = details["sign"]
    parts = []
    if top := details.get("top"):
        parts.append(" | ".join(f"{c['sign']} {c['similarity']:.2f}" for c in top))
    if (margin := details.get("margin")) is not None:
        parts.append(f"margin {margin:.2f}")
    if (latency_ms := details.get("latency_ms")) is not None:
        parts.append(f"{latency_ms / 1000:.2f} s")
    if why := unsure_why(details):
        parts.append(why)
    line = f"✓ {sign}" if sign is not None else "? unsure"
    if parts:
        line += f"  ({'; '.join(parts)})"
    if details.get("provisional"):
        line += "  [PROVISIONAL]"
    return line


class SubprocessSource:
    """Results from a recognizer running in another Python (the SignCLIP venv has torch,
    this one does not). Its stdout carries `result_line`s; its stderr goes straight to the
    terminal; its stdin is closed so it never competes with typed commands."""

    def __init__(self, argv: Sequence[str], out: Callable[[str], None] = print,
                 log: SessionLog | None = None) -> None:
        self.argv, self.out, self.log = tuple(argv), out, log or SessionLog(out)
        self._warned_provisional = False

    async def results(self) -> AsyncIterator[Result]:
        process = await asyncio.create_subprocess_exec(
            *self.argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE)
        try:
            assert process.stdout is not None  # requested as a pipe above
            async for raw in process.stdout:
                details = parse_result_details(raw.decode())
                if details.get("provisional") and not self._warned_provisional:
                    self._warned_provisional = True
                    self.log.show(f"!!! {PROVISIONAL_BANNER} !!!")
                self.log.show(describe_result(details))
                self.log.record("recognizer", details)
                yield details["sign"]
            if code := await process.wait():
                self.out(f"! live recognizer stopped (exit {code}); type signs instead")
        finally:
            if process.returncode is None:
                process.terminate()
                await process.wait()


# ---- backend client ----


class Transport(Protocol):
    """The slice of a websockets ClientConnection the bridge uses; tests pass a fake."""

    async def send(self, message: str) -> None: ...

    def __aiter__(self) -> AsyncIterator[str | bytes]: ...

    async def close(self) -> None: ...


HELP = (f"signs: {' '.join(SIGNS)}  (? = unsure, never sent)\n"
        "x remove last chip | c clear turn | s SEND draft | q yes|no|wait|repeat quick reply\n"
        "stop cancel unspoken output | e end call | h help")


class Bridge:
    """Connects recognition sources and terminal commands to one call's WebSocket."""

    def __init__(self, transport: Transport, state: TurnState | None = None,
                 out: Callable[[str], None] = print, log: SessionLog | None = None) -> None:
        self.transport, self.out, self.log = transport, out, log or SessionLog(out)
        self.state = state or TurnState()
        self.manual = ManualSource()
        self._tasks: list[asyncio.Task[None]] = []

    async def send(self, message: Message | None) -> None:
        if message is not None:
            await self.transport.send(json.dumps(message))
            self.log.record("bridge", message)

    async def on_result(self, result: Result) -> None:
        try:
            message = self.state.add(result)
        except ChipLimit as error:
            self.out(f"! {error}")
            return
        self._show_chips()
        await self.send(message)

    async def handle_line(self, line: str) -> bool:
        """Runs one terminal line. Returns False when the user ended the call."""
        words = line.split()
        if not words:
            return True
        command, args = words[0].lower(), words[1:]
        if command == "x":
            message = self.state.remove_last()
            self._show_chips()
            await self.send(message)
        elif command == "c":
            self.state.clear()
            self.out("turn cleared")
        elif command == "s":
            await self._send_approval(self.state.approve())
        elif command == "q":
            name = args[0].lower() if len(args) == 1 else ""
            if name not in QUICK_REPLIES:
                self.out(f"! quick reply is one of: {' '.join(QUICK_REPLIES)}")
                return True
            await self._send_approval(self.state.quick_reply(name))
        elif command == "stop":
            await self.send(self.state.stop())
        elif command == "e":
            await self.send(self.state.end())
            self.out("call ended by you; nothing more will be sent")
            return False
        elif command in ("h", "help"):
            self.out(HELP)
        else:
            try:
                results = [parse_result(word) for word in words]
            except ValueError as error:
                self.out(f"! {error}")
                return True
            for result in results:
                self.manual.feed(result)
        return True

    async def on_server(self, raw: str | bytes) -> None:
        message = json.loads(raw)
        self.log.record("backend", message)
        kind = message["type"]
        if kind == "status":
            self.log.show(f"[status] {message['state']}")
            if message["state"] == "speaking":
                self.log.show("Speaking now...")
            elif message["state"] == "ended":
                self.state.on_ended()
                self.log.show("call ended; nothing more will be sent")
        elif kind == "caption":
            # Agent captions are lines our own voice said without a SEND (disclosure,
            # holding line, goodbye). Backends from before `speaker` existed omit it.
            speaker = AGENT_LABEL if message.get("speaker") == "agent" else "receptionist"
            self.log.show(f"{speaker}: {message['text']}")
        elif kind == "draft":
            draft = self.state.on_draft(message["turn_id"], message["text"], message["source"])
            if draft is not None:
                self.log.show(f"draft ({draft.source}): {draft.text}   [s = SEND]")
        elif kind == "spoken":
            if (text := self.state.on_spoken(message["turn_id"])) is not None:
                self.log.show(f"Delivered: {text}")
        elif kind == "not_delivered":
            if (text := self.state.on_not_delivered(message["turn_id"])) is not None:
                self.log.show(f"! not delivered ({message['reason']}), tap SEND again (s): {text}")
        elif kind == "error":
            self.log.show(f"! backend error {message['code']}: {message['message']}")
        else:
            self.log.show(f"(ignored unknown message type {kind!r})")

    async def run(self, lines: AsyncIterator[str],
                  sources: tuple[RecognitionSource, ...] = ()) -> None:
        """Runs until the user ends the call, the terminal closes or the backend hangs up."""
        self.out(HELP)
        try:
            async with asyncio.TaskGroup() as group:
                self._tasks = [group.create_task(self._pump_server()),
                               group.create_task(self._pump_lines(lines)),
                               *(group.create_task(self._pump_source(source))
                                 for source in (self.manual, *sources))]
        finally:
            await self.transport.close()

    async def _send_approval(self, message: Message | None) -> None:
        if message is None:
            self.out("nothing to send yet: wait for a draft" if not self.state.ended
                     else "call ended; nothing will be sent")
            return
        self.log.show(f"SEND: {message['text']}")
        await self.send(message)

    def _show_chips(self) -> None:
        chips = " ".join(f"[{chip or '?'}]" for chip in self.state.chips) or "(none)"
        self.out(f"chips: {chips}")

    async def _pump_server(self) -> None:
        try:
            async for raw in self.transport:
                await self.on_server(raw)
        finally:
            if not self.state.ended:
                self.state.on_ended()
                self.out("connection closed; nothing will be sent")
            self._stop_others()

    async def _pump_lines(self, lines: AsyncIterator[str]) -> None:
        async for line in lines:
            if not await self.handle_line(line):
                break
        self._stop_others()

    async def _pump_source(self, source: RecognitionSource) -> None:
        async for result in source.results():
            await self.on_result(result)

    def _stop_others(self) -> None:
        current = asyncio.current_task()
        for task in self._tasks:
            if task is not current:
                task.cancel()


# ---- command line ----

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"  # gitignored
RECOGNIZER_PYTHON = ARTIFACTS / "signclip" / ".venv" / "bin" / "python"

COST_HEADS_UP = ("Cost heads-up: starting a call makes Bolna dial a real phone from its default "
                 "number (about ₹5.5/min plus telephony). Only allowlisted, consenting numbers.")
PURPOSE = "doctor_appointment"


class BackendError(RuntimeError):
    """The backend refused or could not be reached; the message never contains the token."""


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def base_url(value: str) -> str:
    parts = urllib.parse.urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.query:
        raise argparse.ArgumentTypeError(f"expected http(s)://host[/path], got {value!r}")
    return value.rstrip("/")


def ws_url(base: str, call_id: str) -> str:
    scheme, rest = base.split("://", 1)
    return f"{'wss' if scheme == 'https' else 'ws'}://{rest}/calls/{urllib.parse.quote(call_id)}/ws"


PostJson = Callable[[str, Message, dict[str, str]], Message]


def post_json(url: str, body: Message, headers: dict[str, str]) -> Message:
    request = urllib.request.Request(url, json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            reply: Message = json.loads(response.read())
            return reply
    except urllib.error.HTTPError as error:
        detail = error.read()[:200].decode(errors="replace")
        raise BackendError(f"POST /calls returned HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise BackendError(f"POST /calls failed: {error.reason}") from error


def start_call(base_url: str, contact: str, token: str, confirm_cost: bool,
               post: PostJson = post_json, out: Callable[[str], None] = print) -> str:
    """Asks the backend to dial. Refuses unless the cost was confirmed on the command line."""
    out(COST_HEADS_UP)
    if not confirm_cost:
        raise SystemExit("Not starting a call: re-run with --confirm-cost to accept the cost.")
    reply = post(f"{base_url}/calls", {"contact_id": contact, "purpose": PURPOSE},
                 auth_headers(token))
    call_id = str(reply["call_id"])
    out(f"call {call_id} started: {reply['state']}")
    return call_id


class _WebSocket:
    """Adapts a websockets connection; a dropped connection simply ends the message stream."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    async def send(self, message: str) -> None:
        await self._connection.send(message)

    async def _messages(self) -> AsyncIterator[str | bytes]:
        from websockets.exceptions import ConnectionClosed  # see connect()
        try:
            async for raw in self._connection:
                yield raw
        except ConnectionClosed:
            return

    def __aiter__(self) -> AsyncIterator[str | bytes]:
        return self._messages()

    async def close(self) -> None:
        await self._connection.close()


async def connect(url: str, headers: dict[str, str]) -> Transport:
    # Imported here so the tests run with the standard library alone.
    from websockets.asyncio.client import connect as ws_connect
    from websockets.exceptions import InvalidStatus
    try:
        return _WebSocket(await ws_connect(url, additional_headers=headers))
    except InvalidStatus as error:
        raise BackendError(f"WebSocket refused: HTTP {error.response.status_code}") from error
    except OSError as error:
        raise BackendError(f"WebSocket connection failed: {error.strerror or error}") from error


async def stdin_lines() -> AsyncIterator[str]:
    """Terminal lines via a daemon thread: works for ttys, pipes and files alike, and a
    blocked read never delays exit (asyncio pipes reject /dev/null on macOS)."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | _End] = asyncio.Queue()

    def read() -> None:
        for line in sys.stdin:
            loop.call_soon_threadsafe(queue.put_nowait, line)
        loop.call_soon_threadsafe(queue.put_nowait, _End.DONE)

    threading.Thread(target=read, daemon=True).start()
    while (line := await queue.get()) is not _End.DONE:
        yield line


Connect = Callable[[str, dict[str, str]], Awaitable[Transport]]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mac fallback: send chips to a backend call.")
    parser.add_argument("--base-url", required=True, type=base_url,
                        help="backend, e.g. https://host")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--call-id", help="attach to a call that is already running")
    target.add_argument("--contact", help="start a new call to this contact id, e.g. clinic")
    parser.add_argument("--confirm-cost", action="store_true",
                        help="accept the cost of the call that --contact starts")
    parser.add_argument("--replay", type=Path, help="JSON list of results to play back")
    parser.add_argument("--log", nargs="?", const="", metavar="PATH",
                        help="append recognizer results, chips, drafts, captions and spoken "
                             "confirmations as JSONL (default PATH: artifacts/lab/session-<time>.jsonl)")
    live = parser.add_argument_group(
        "live recognition", "runs live_source.py in the SignCLIP venv; its signs become chips")
    live.add_argument("--live", action="store_true", help="recognise signs from a webcam or clips")
    clips = live.add_mutually_exclusive_group()
    clips.add_argument("--camera", type=int, help="webcam index (default 0)")
    clips.add_argument("--replay-videos", type=Path, metavar="DIR",
                       help="rehearse with saved clips through the same live path")
    live.add_argument("--bundle", type=Path, help="recognition bundle (default: live_source.py's)")
    live.add_argument("--rest-y", type=float, help="skip the 2 s rest calibration; use this line")
    live.add_argument("--recognizer-python", type=Path, default=RECOGNIZER_PYTHON,
                      help="Python of the SignCLIP venv (default: %(default)s)")
    args = parser.parse_args(argv)
    if not args.live and any(getattr(args, name) is not None
                             for name in ("camera", "replay_videos", "bundle", "rest_y")):
        parser.error("--camera, --replay-videos, --bundle and --rest-y need --live")
    if args.log is not None:
        try:
            args.log = session_log_path(args.log)
        except ValueError as error:
            parser.error(str(error))
    return args


def session_log_path(value: str, now: Callable[[], datetime] = datetime.now) -> Path:
    """--log's file; captions and drafts stay inside the gitignored artifacts/ directory."""
    path = Path(value) if value else ARTIFACTS / "lab" / f"session-{now():%Y%m%d-%H%M%S}.jsonl"
    if not path.resolve().is_relative_to(ARTIFACTS.resolve()):
        raise ValueError(f"--log must be inside {ARTIFACTS} so session logs stay out of Git")
    return path


def live_command(args: argparse.Namespace) -> list[str]:
    """The recognizer child's argv; it inherits this process's working directory."""
    command = [str(args.recognizer_python), str(ROOT / "live_source.py")]
    if args.replay_videos is not None:
        command += ["--replay-videos", str(args.replay_videos)]
    else:
        command += ["--camera", str(0 if args.camera is None else args.camera)]
    if args.bundle is not None:
        command += ["--bundle", str(args.bundle)]
    if args.rest_y is not None:
        command += ["--rest-y", str(args.rest_y)]
    return command


def main(argv: list[str] | None = None, env: Mapping[str, str] = os.environ,
         post: PostJson = post_json, connect: Connect = connect,
         lines: Callable[[], AsyncIterator[str]] = stdin_lines,
         out: Callable[[str], None] = print) -> int:
    args = parse_args(argv)
    log = SessionLog(out, args.log)
    if args.log is not None:
        out(f"session log: {args.log}")
    sources: tuple[RecognitionSource, ...] = (
        (ReplaySource.from_json(args.replay.read_text()),) if args.replay else ())
    if args.live:
        if not args.recognizer_python.is_file():
            raise SystemExit(f"No SignCLIP venv at {args.recognizer_python}; set it up first "
                             "(README: Set up SignCLIP separately) or pass --recognizer-python.")
        sources += (SubprocessSource(live_command(args), out, log),)
    token = env.get("APP_TOKEN")
    if not token:
        raise SystemExit("APP_TOKEN is not set in the environment.")

    async def session(call_id: str) -> None:
        transport = await connect(ws_url(args.base_url, call_id), auth_headers(token))
        out(f"connected to call {call_id}")
        log.record("bridge", {"type": "connected", "call_id": call_id})
        await Bridge(transport, out=out, log=log).run(lines(), sources)

    try:
        call_id = args.call_id or start_call(args.base_url, args.contact, token,
                                             args.confirm_cost, post, out)
        asyncio.run(session(call_id))
    except BackendError as error:
        out(f"! {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
