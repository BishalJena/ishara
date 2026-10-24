"""Behave like the iOS app against a backend (PLAN.md §3). Places a REAL call.

    cd backend
    uv run python -m scripts.fake_app --base-url http://127.0.0.1:8000 \\
        interactive --contact clinic --confirm-cost
    uv run python -m scripts.fake_app --base-url https://<app>.herokuapp.com \\
        script --contact clinic --confirm-cost

APP_TOKEN comes from the environment or the repo-root .env.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import threading
from collections.abc import Awaitable, Callable

import httpx
from pydantic import ValidationError

from app.config import Settings
from tools.app_client import AppSession, NoDraftError
from tools.call_runner import LiveCall, MissingTokenError, OpenSocket, app_token, live_call
from tools.connection import auth_headers, open_call_socket
from tools.cost import cost_confirmed
from tools.demo_script import Pacing, ScriptAbortedError, run_demo_script
from tools.interactive import HELP, run_commands
from tools.timing import format_timing_table

STDIN_POLL_S = 0.5
ReadLine = Callable[[], Awaitable[str | None]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fake_app", description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("interactive", "type chips/send/say/stop/end yourself"),
        ("script", "play the PLAN §1 clinic script automatically"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--contact", required=True, help="contact id, e.g. clinic")
        command.add_argument(
            "--confirm-cost", action="store_true", help="required: this places a paid call"
        )
        if name == "script":
            defaults = Pacing()
            command.add_argument(
                "--first-caption-wait", type=float, default=defaults.first_caption_wait_s
            )
            command.add_argument(
                "--caption-timeout", type=float, default=defaults.caption_timeout_s
            )
            command.add_argument("--sign-gap", type=float, default=defaults.sign_gap_s)
            command.add_argument("--draft-timeout", type=float, default=defaults.draft_timeout_s)
            command.add_argument("--spoken-timeout", type=float, default=defaults.spoken_timeout_s)
    return parser


def pacing_from(args: argparse.Namespace) -> Pacing:
    return Pacing(
        first_caption_wait_s=args.first_caption_wait,
        caption_timeout_s=args.caption_timeout,
        sign_gap_s=args.sign_gap,
        draft_timeout_s=args.draft_timeout,
        spoken_timeout_s=args.spoken_timeout,
    )


def stdin_reader(session: AppSession) -> ReadLine:
    """Lines from a daemon thread, so a pending input never blocks exit. Returns None
    on EOF or once the call socket has closed."""
    loop = asyncio.get_running_loop()
    lines: asyncio.Queue[str | None] = asyncio.Queue()
    pending: asyncio.Task[str | None] | None = None

    def feed() -> None:
        for line in sys.stdin:
            loop.call_soon_threadsafe(lines.put_nowait, line.rstrip("\n"))
        loop.call_soon_threadsafe(lines.put_nowait, None)

    threading.Thread(target=feed, daemon=True).start()

    async def read_line() -> str | None:
        nonlocal pending
        while not session.closed:
            # Keep one get() alive across polls so a line is never lost to a cancel.
            pending = pending or asyncio.create_task(lines.get())
            done, _ = await asyncio.wait({pending}, timeout=STDIN_POLL_S)
            if done:
                line, pending = pending.result(), None
                return line
        return None

    return read_line


async def drive(
    args: argparse.Namespace,
    call: LiveCall,
    out: Callable[[str], None],
    read_line: ReadLine | None = None,
) -> int:
    session = call.session
    if args.command == "interactive":
        out(HELP)
        await run_commands(
            session,
            read_line or stdin_reader(session),
            out,
            (ValueError, NoDraftError, ValidationError),
        )
        return 0
    try:
        await run_demo_script(session, pacing_from(args), out)
    except ScriptAbortedError as error:
        out(f"script stopped: {error}")
        return 1
    return 0


async def run(
    args: argparse.Namespace,
    client: httpx.AsyncClient,
    open_socket: OpenSocket,
    out: Callable[[str], None] = print,
    read_line: ReadLine | None = None,
) -> int:
    try:
        async with live_call(client, args.contact, open_socket, out) as call:
            code = await drive(args, call, out, read_line)
            session = call.session
    except httpx.HTTPStatusError as error:
        out(f"POST /calls refused: HTTP {error.response.status_code}")
        return 1
    out(format_timing_table(session.turns))
    return code


def main(argv: list[str] | None = None, settings: Settings | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not cost_confirmed(args.confirm_cost):
        return 2
    try:
        token = app_token(settings or Settings())
    except MissingTokenError as error:
        print(error)
        return 2

    async def _main() -> int:
        async with httpx.AsyncClient(
            base_url=args.base_url, headers=auth_headers(token), timeout=30
        ) as client:
            return await run(
                args, client, lambda call_id: open_call_socket(args.base_url, call_id, token)
            )

    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())
