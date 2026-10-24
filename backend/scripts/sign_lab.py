"""Sign Lab: the local demo backend with the real composer and voice, for webcam tests.

    cd backend
    uv run python -m scripts.sign_lab                                  # free: templates, silent
    uv run python -m scripts.sign_lab --composer groq --voice sarvam   # Groq drafts, Sarvam voice
    uv run python -m scripts.sign_lab --receptionist manual            # you type her lines

Same server as scripts.local_demo (the real app, CallManager and custom-LLM endpoint;
ScriptedBolna answers the "call", so nothing is dialled), plus:

- `--composer groq`: drafts come from the production GroqComposer (1.5 s budget,
  validator, template fallback). Every draft is printed with its source, and with the
  validator's reasons when the LLM draft fell back.
- `--voice sarvam`: every line the scripted Bolna speaks (disclosure, approved
  replies, holding line, goodbye) is synthesised by Sarvam and played with `afplay`,
  one at a time, without blocking the server.
- `--receptionist manual`: lines typed in this terminal become the receptionist's
  words (captions), so drafts can be checked against any reply. `/silence` fires
  Bolna's silence repeat (the holding line).

Like Bolna, the scripted call also repeats the listen node after 15 s with nobody
talking (scaled by --delay), so the holding line is said then too. The app (or the
Mac bridge) gets the disclosure, every holding line and the goodbye as agent
captions, apart from the receptionist's words.

Keys come only from the repo-root .env (or --env-file), and only for the flags that
need them. Exported variables are ignored, and no Bolna key is ever set.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import shutil
import socket
import sys
import threading
from collections.abc import AsyncIterable, AsyncIterator, Callable, Sequence
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx
from dotenv import dotenv_values
from pydantic import SecretStr

from app import composer as production_composer
from app.calls import CallManager
from app.config import REPO_ROOT, Settings
from app.main import configure_logging, create_app
from app.markers import EVENT_END_CALL, EVENT_USER_REPLY, PROP_REPLY_TEXT
from app.ports import Composer
from app.sarvam import SarvamTTS
from fakes.fake_bolna import FakeRun, RunEnded
from fakes.scripted_call import CALL_PAUSES, RECEPTIONIST_LINES, Pauses, ScriptedBolna
from scripts.lab_composer import ComposerChoice, build_lab_composer
from scripts.lab_voice import VoiceQueue
from scripts.local_demo import (
    DEFAULT_CONTACT,
    DEFAULT_PORT,
    DELIVERY_TIMEOUT_S,
    DEV_APP_TOKEN,
    HOST,
    LocalDemo,
    RunningDemo,
    base_url_for,
    bind_socket,
    local_settings,
    running,
)

VoiceChoice = Literal["none", "sarvam"]
ReceptionistChoice = Literal["script", "manual"]
Log = Callable[[str], None]

DEFAULT_ENV_FILE = REPO_ROOT / ".env"
SILENCE_COMMAND = "/silence"
FREE_FLAGS = "--composer templates --voice none"


class LabSetupError(Exception):
    """The lab can't start as asked; the message says how to fix it."""


# ---- keys ----


@dataclass(frozen=True)
class LabKeys:
    groq_key: SecretStr | None = None
    groq_model: str | None = None
    sarvam_key: SecretStr | None = None


def read_lab_keys(env_file: Path, composer: ComposerChoice, voice: VoiceChoice) -> LabKeys:
    """Read only what the chosen flags need, from `env_file` only. Free mode reads nothing."""
    if composer == "templates" and voice == "none":
        return LabKeys()
    if not env_file.is_file():
        raise LabSetupError(
            f"{env_file} not found; the paid flags read their keys from it. "
            f"Pass --env-file PATH, or run free with {FREE_FLAGS}."
        )
    values = {name: value.strip() for name, value in dotenv_values(env_file).items() if value}

    def need(name: str, flag: str) -> SecretStr:
        if not values.get(name):
            raise LabSetupError(f"{flag} needs {name} in {env_file}. Add it there, or drop {flag}.")
        return SecretStr(values[name])

    keys = LabKeys()
    if composer == "groq":
        default_model = Settings.model_fields["groq_model"].default
        keys = LabKeys(
            groq_key=need("GROQ_API_KEY", "--composer groq"),
            groq_model=values.get("GROQ_MODEL") or default_model,
        )
    if voice == "sarvam":
        keys = LabKeys(keys.groq_key, keys.groq_model, need("SARVAM_API_KEY", "--voice sarvam"))
    return keys


def build_voice(
    choice: VoiceChoice,
    key: SecretStr | None,
    *,
    log: Log,
    which: Callable[[str], str | None] = shutil.which,
    transport: httpx.AsyncBaseTransport | None = None,
) -> VoiceQueue | None:
    if choice == "none":
        return None
    if which("afplay") is None:
        raise LabSetupError(
            "--voice sarvam plays audio with macOS afplay, which isn't on PATH. "
            "Run it on a Mac, or drop --voice sarvam."
        )
    if key is None:
        raise ValueError("--voice sarvam needs SARVAM_API_KEY")
    return VoiceQueue(SarvamTTS(key, transport=transport), log=log)


# ---- the fake Bolna ----


class LabBolna(ScriptedBolna):
    """ScriptedBolna that voices everything the agent says and logs approvals."""

    def __init__(
        self,
        custom_llm_token: str,
        *,
        voice: VoiceQueue | None,
        log: Log,
        webhook_secret: str,
        lines: Sequence[str],
        pauses: Pauses,
    ) -> None:
        super().__init__(
            custom_llm_token, webhook_secret=webhook_secret, lines=lines, pauses=pauses, log=log
        )
        self.voice = voice
        self._out = log

    async def send_event(self, run_id: str, event: str, properties: dict[str, str]) -> None:
        if event == EVENT_USER_REPLY:
            self._out(f"approved (SEND): {properties.get(PROP_REPLY_TEXT, '')}")
        elif event == EVENT_END_CALL:
            self._out("end requested")
        await super().send_event(run_id, event, properties)

    def _say(self, run: FakeRun, text: str) -> None:
        super()._say(run, text)
        if self.voice is not None:
            self.voice.say(text)


@dataclass(frozen=True)
class SignLab:
    demo: LocalDemo
    fake: LabBolna
    voice: VoiceQueue | None
    receptionist: ReceptionistChoice
    log: Log


def build_sign_lab(
    *,
    composer: Composer,
    voice: VoiceQueue | None = None,
    receptionist: ReceptionistChoice = "script",
    app_token: str = DEV_APP_TOKEN,
    contacts: Sequence[str] = (DEFAULT_CONTACT,),
    pauses: Pauses = CALL_PAUSES,
    delivery_timeout_s: float = DELIVERY_TIMEOUT_S,
    log: Log = print,
) -> SignLab:
    settings = local_settings(app_token, contacts)
    assert settings.custom_llm_token is not None and settings.bolna_webhook_secret is not None
    fake = LabBolna(
        settings.custom_llm_token.get_secret_value(),
        webhook_secret=settings.bolna_webhook_secret.get_secret_value(),
        # Manual mode: the scripted receptionist stays quiet; the terminal talks for her.
        lines=RECEPTIONIST_LINES if receptionist == "script" else (),
        pauses=pauses,
        voice=voice,
        log=log,
    )
    ledger = CallManager(settings, composer, fake, delivery_timeout_s=delivery_timeout_s)
    app = create_app(settings, composer=composer, bolna=fake, ledger=ledger)
    demo = LocalDemo(app=app, fake=fake, settings=settings)
    return SignLab(demo=demo, fake=fake, voice=voice, receptionist=receptionist, log=log)


# ---- the manual receptionist ----


def active_run(fake: ScriptedBolna) -> FakeRun | None:
    """The newest call that hasn't ended."""
    return next((run for run in reversed(fake.runs.values()) if not run.ended), None)


async def manual_receptionist(fake: ScriptedBolna, lines: AsyncIterable[str], log: Log) -> None:
    """Each typed line is the receptionist finishing an utterance on the current call."""
    async for raw in lines:
        text = raw.strip()
        if not text:
            continue
        run = active_run(fake)
        if run is None:
            log("no call is up yet: start one from the bridge or the app, then type again")
            continue
        if run.answered is not None and not run.answered.done():
            log("the phone is still ringing; type again once it is answered")
            continue
        try:
            if text == SILENCE_COMMAND:
                log("receptionist stays silent (Bolna's silence repeat)")
                await fake.silence(run.run_id)
            else:
                log(f"receptionist says: {text}")
                await fake.receptionist_says(run.run_id, text)
        except RunEnded:
            log("that call has ended; start a new one")


async def stdin_lines() -> AsyncIterator[str]:
    """Terminal lines via a daemon thread: a pending read never delays exit, and
    /dev/null works (asyncio pipes reject it on macOS)."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def put(line: str | None) -> None:
        with suppress(RuntimeError):  # the loop closed during shutdown
            loop.call_soon_threadsafe(queue.put_nowait, line)

    def read() -> None:
        for line in sys.stdin:
            put(line)
        put(None)

    threading.Thread(target=read, daemon=True).start()
    while (line := await queue.get()) is not None:
        yield line


def _log_failure(log: Log) -> Callable[[asyncio.Task[None]], None]:
    def report(task: asyncio.Task[None]) -> None:
        if not task.cancelled() and (error := task.exception()) is not None:
            log(f"manual receptionist stopped: {error!r}")

    return report


@asynccontextmanager
async def running_lab(
    lab: SignLab, sock: socket.socket, receptionist_lines: AsyncIterable[str] | None = None
) -> AsyncIterator[RunningDemo]:
    """Serve the lab; the voice outlives the server so the goodbye can finish."""
    async with AsyncExitStack() as stack:
        if lab.voice is not None:
            await stack.enter_async_context(lab.voice)
        live = await stack.enter_async_context(running(lab.demo, sock))
        if receptionist_lines is not None:
            reader = asyncio.create_task(manual_receptionist(lab.fake, receptionist_lines, lab.log))
            reader.add_done_callback(_log_failure(lab.log))
            stack.callback(reader.cancel)
        yield live


# ---- CLI ----


def banner(base_url: str, args: argparse.Namespace, keys: LabKeys) -> str:
    drafts = (
        f"Groq {keys.groq_model} (production validator and template fallback)"
        if args.composer == "groq"
        else "templates"
    )
    voice = "Sarvam, played with afplay" if args.voice == "sarvam" else "none (printed only)"
    receptionist = (
        "you type her lines below (Enter sends; /silence = the holding-line repeat)"
        if args.receptionist == "manual"
        else "scripted PLAN §1 lines"
    )
    lines = [
        "Ishara Sign Lab: local backend, nothing is dialled, no Bolna.",
        f"  base URL      {base_url}",
        f"  app token     {args.app_token}",
        f"  contact       {(args.contact or [DEFAULT_CONTACT])[0]}",
        f"  drafts        {drafts}",
        f"  voice         {voice}",
        f"  receptionist  {receptionist}",
    ]
    if args.composer == "groq" or args.voice == "sarvam":
        lines += [
            "",
            "Costs: each chip change is one Groq draft (a fraction of a paisa); each spoken "
            "line is one Sarvam request (about ₹0.1-0.5), including the holding line after "
            "each long silence. Run free with " + FREE_FLAGS + ".",
        ]
    lines += [
        "",
        "Mac bridge, from spikes/recognition (it insists on --confirm-cost; this server "
        "places no real call):",
        f"  APP_TOKEN={args.app_token} artifacts/bridge/.venv/bin/python mac_bridge.py "
        f"--base-url {base_url} --contact {DEFAULT_CONTACT} --confirm-cost --live --camera 0",
        "",
        "Events: 'receptionist says', 'chips', 'groq answered', 'draft (llm|template)',",
        "'  fallback: <why>', 'approved (SEND)', 'agent says', 'voice: playing / done',",
        "'N s of silence' (the holding line follows).",
    ]
    return "\n".join(lines)


def _non_negative(value: str) -> float:
    factor = float(value)
    if factor < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return factor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sign_lab", description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--app-token", default=DEV_APP_TOKEN, help="what the app sends")
    parser.add_argument(
        "--contact", action="append", help=f"allowlisted contact id (default: {DEFAULT_CONTACT})"
    )
    parser.add_argument("--composer", choices=("templates", "groq"), default="templates")
    parser.add_argument("--voice", choices=("none", "sarvam"), default="none")
    parser.add_argument("--receptionist", choices=("script", "manual"), default="script")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help="where --composer groq and --voice sarvam read their keys (default: %(default)s)",
    )
    parser.add_argument(
        "--delay",
        type=_non_negative,
        default=1.0,
        help="scale the ring, receptionist and silence-repeat pauses",
    )
    return parser


def _out(line: str) -> None:
    print(line, flush=True)


async def _serve(lab: SignLab, sock: socket.socket) -> None:
    lines = stdin_lines() if lab.receptionist == "manual" else None
    async with running_lab(lab, sock, lines) as live:
        await live.task


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        keys = read_lab_keys(args.env_file, args.composer, args.voice)
        voice = build_voice(args.voice, keys.sarvam_key, log=_out)
    except LabSetupError as error:
        print(f"sign_lab: {error}", file=sys.stderr, flush=True)
        return 2
    composer = build_lab_composer(
        args.composer, log=_out, groq_key=keys.groq_key, groq_model=keys.groq_model
    )
    lab = build_sign_lab(
        composer=composer,
        voice=voice,
        receptionist=args.receptionist,
        app_token=args.app_token,
        contacts=args.contact or [DEFAULT_CONTACT],
        pauses=CALL_PAUSES.scaled(args.delay),
        log=_out,
    )
    try:
        sock = bind_socket(HOST, args.port)
    except OSError as error:
        _out(f"can't listen on {HOST}:{args.port} ({error.strerror}); try --port")
        return 1
    configure_logging()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # Composer fallbacks are printed on their draft's 'fallback:' line; don't repeat them.
    logging.getLogger(production_composer.__name__).propagate = False
    _out(banner(base_url_for(sock), args, keys))
    with suppress(KeyboardInterrupt):
        asyncio.run(_serve(lab, sock))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
