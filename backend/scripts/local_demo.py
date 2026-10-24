"""A free local backend for the whole PLAN.md §1 call: no Bolna, no Groq, nothing dialled.

    cd backend
    uv run python -m scripts.local_demo                 # http://127.0.0.1:8000
    uv run python -m scripts.local_demo --b24 --delay 0.5

The real app (create_app with CallManager, the custom-LLM endpoint and template
drafts) serves the iOS app or the Mac bridge. ScriptedBolna stands in for Bolna and
the receptionist: it rings, answers, says the §1 receptionist lines as captions, and
fetches every approved reply from this server's own custom-LLM endpoint over HTTP, so
the full backend path runs. What the agent "speaks" is printed to stdout.

The app also gets the voice's own lines as agent captions: the disclosure when the
call is answered, the holding line after 15 s with nobody talking (Bolna's silence
repeat, scaled by --delay) and the goodbye after End.

Settings are built here, explicitly: the repo `.env` is never read, and no API key is
set, so nothing can reach a paid service.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import secrets
import socket
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, replace

import httpx
import uvicorn
from fastapi import FastAPI

from app.calls import CallManager
from app.composer import TemplateComposer
from app.config import Settings
from app.main import configure_logging, create_app
from fakes.scripted_call import CALL_PAUSES, Pauses, ScriptedBolna

HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEV_APP_TOKEN = "ishara-local-demo"
DEFAULT_CONTACT = "clinic"
DELIVERY_TIMEOUT_S = 10.0  # CallManager's default: SEND without `spoken` → not_delivered
STARTUP_TIMEOUT_S = 5.0


def synthetic_number(index: int) -> str:
    """A well-formed E.164 value for the allowlist. Never dialled: the fake answers."""
    return f"+9100000000{index:02d}"


def local_settings(app_token: str, contacts: Sequence[str]) -> Settings:
    """Every secret is passed explicitly, so neither `.env` nor exported variables
    (a real GROQ_API_KEY, BOLNA_API_KEY, ...) can leak into the local server."""
    recipients = ",".join(f"{contact}={synthetic_number(i)}" for i, contact in enumerate(contacts))
    return Settings(
        _env_file=None,
        app_token=app_token,
        custom_llm_token=secrets.token_urlsafe(16),
        bolna_webhook_secret=secrets.token_urlsafe(16),
        bolna_api_key=None,
        bolna_agent_id=None,
        groq_api_key=None,
        sarvam_api_key=None,
        public_base_url=None,
        allowed_recipients=recipients,
    )


@dataclass(frozen=True)
class LocalDemo:
    app: FastAPI
    fake: ScriptedBolna
    settings: Settings


def build_local_demo(
    *,
    app_token: str = DEV_APP_TOKEN,
    contacts: Sequence[str] = (DEFAULT_CONTACT,),
    pauses: Pauses = CALL_PAUSES,
    talk_over_once: bool = False,
    delivery_timeout_s: float = DELIVERY_TIMEOUT_S,
    log: Callable[[str], None] = print,
) -> LocalDemo:
    settings = local_settings(app_token, contacts)
    assert settings.custom_llm_token is not None and settings.bolna_webhook_secret is not None
    fake = ScriptedBolna(
        settings.custom_llm_token.get_secret_value(),
        webhook_secret=settings.bolna_webhook_secret.get_secret_value(),
        # The talked-over SEND must time out in the app before she finishes talking.
        pauses=replace(pauses, talk_over_s=delivery_timeout_s + pauses.reply_s),
        talk_over_once=talk_over_once,
        log=log,
    )
    composer = TemplateComposer()
    ledger = CallManager(settings, composer, fake, delivery_timeout_s=delivery_timeout_s)
    app = create_app(settings, composer=composer, bolna=fake, ledger=ledger)
    return LocalDemo(app=app, fake=fake, settings=settings)


def bind_socket(host: str, port: int) -> socket.socket:
    """Bind before serving, so port 0 (tests) yields a known free port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError:
        sock.close()
        raise
    return sock


def base_url_for(sock: socket.socket) -> str:
    host, port = sock.getsockname()[:2]
    return f"http://{host}:{port}"


@dataclass(frozen=True)
class RunningDemo:
    base_url: str
    server: uvicorn.Server
    task: asyncio.Task[None]


@asynccontextmanager
async def running(
    demo: LocalDemo, sock: socket.socket, startup_timeout_s: float = STARTUP_TIMEOUT_S
) -> AsyncIterator[RunningDemo]:
    """Serve on `sock` and point the fake's HTTP client at this same server."""
    base_url = base_url_for(sock)
    config = uvicorn.Config(
        demo.app, lifespan="off", log_config=None, log_level="warning", access_log=False
    )
    server = uvicorn.Server(config)
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as http:
        demo.fake.attach(http)
        task = asyncio.create_task(server.serve(sockets=[sock]))
        try:
            async with asyncio.timeout(startup_timeout_s):
                while not server.started:
                    if task.done():
                        task.result()
                        raise RuntimeError("the local server stopped during startup")
                    await asyncio.sleep(0.01)
            yield RunningDemo(base_url=base_url, server=server, task=task)
        finally:
            server.should_exit = True
            await task


def banner(base_url: str, app_token: str, contacts: Sequence[str], talk_over: bool) -> str:
    contact = contacts[0]
    lines = [
        "Ishara local demo backend: no Bolna, no Groq, nothing is dialled; template drafts.",
        f"  base URL   {base_url}",
        f"  app token  {app_token}",
        f"  contacts   {', '.join(contacts)}",
        "",
        "iOS simulator (ios/Ishara/Config/Secrets.xcconfig), run with -IsharaDriver live:",
        f"  ISHARA_BACKEND_URL = {base_url.replace('://', ':/$()/', 1)}",
        f"  ISHARA_APP_TOKEN = {app_token}",
        "  (the simulator shares the Mac's network, so 127.0.0.1 reaches this server)",
        "",
        "Mac bridge, from spikes/recognition (it insists on --confirm-cost; this server",
        "costs nothing):",
        f"  APP_TOKEN={app_token} artifacts/bridge/.venv/bin/python mac_bridge.py "
        f"--base-url {base_url} --contact {contact} --confirm-cost --live",
        "",
        "Scripted app instead (from backend/):",
        f"  APP_TOKEN={app_token} uv run python -m scripts.fake_app --base-url {base_url} "
        f"script --contact {contact} --confirm-cost",
    ]
    if talk_over:
        lines += [
            "",
            f"B24: the receptionist talks over the first SEND of each call. Expect "
            f'"not delivered" after {DELIVERY_TIMEOUT_S:g} s, then SEND again.',
        ]
    return "\n".join(lines)


def _non_negative(value: str) -> float:
    factor = float(value)
    if factor < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return factor


def _token(value: str) -> str:
    if not value.strip():
        raise argparse.ArgumentTypeError("can't be blank")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="local_demo", description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--app-token", type=_token, default=DEV_APP_TOKEN, help="what the app sends"
    )
    parser.add_argument(
        "--contact",
        action="append",
        help=f"allowlisted contact id, repeatable (default: {DEFAULT_CONTACT})",
    )
    parser.add_argument(
        "--b24", action="store_true", help="the receptionist talks over the first SEND once"
    )
    parser.add_argument(
        "--delay",
        type=_non_negative,
        default=1.0,
        help="scale the ring and receptionist pauses (0.5 = twice as fast)",
    )
    return parser


def _out(line: str) -> None:
    print(line, flush=True)


async def _serve(demo: LocalDemo, sock: socket.socket) -> None:
    async with running(demo, sock) as live:
        await live.task


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    contacts = args.contact or [DEFAULT_CONTACT]
    demo = build_local_demo(
        app_token=args.app_token,
        contacts=contacts,
        pauses=CALL_PAUSES.scaled(args.delay),
        talk_over_once=args.b24,
        log=_out,
    )
    try:
        sock = bind_socket(HOST, args.port)
    except OSError as error:
        _out(f"can't listen on {HOST}:{args.port} ({error.strerror}); try --port")
        return 1
    configure_logging()
    # One line per fake-Bolna request (and the webhook secret in each URL) is noise here.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    _out(banner(base_url_for(sock), args.app_token, contacts, args.b24))
    # uvicorn shuts down cleanly on Ctrl-C, then re-raises the signal.
    with suppress(KeyboardInterrupt):
        asyncio.run(_serve(demo, sock))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
