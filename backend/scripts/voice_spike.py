"""Guided runner for the nine V4 voice checks (PLAN.md §6). Places a REAL call.

    cd backend
    uv run python -m scripts.voice_spike --base-url https://<app>.herokuapp.com \\
        --contact clinic --confirm-cost [--checks 1,2,5]

Talk to the teammate on a side channel; the runner says what to ask them. After the
call ends, a dated, redacted section is appended to docs/experiments/voice.md.
APP_TOKEN comes from the environment or the repo-root .env.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path

import httpx

from app.config import REPO_ROOT, Settings
from tools.call_runner import MissingTokenError, OpenSocket, app_token, live_call
from tools.connection import auth_headers, open_call_socket
from tools.cost import cost_confirmed
from tools.results import append_run, render_run_section
from tools.voice_checks import CHECK_NUMBERS, CheckContext, Observer, SpikeTiming, run_checks

DEFAULT_RESULTS = REPO_ROOT / "docs" / "experiments" / "voice.md"


def parse_checks(text: str) -> list[int]:
    try:
        numbers = [int(part) for part in text.split(",") if part.strip()]
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"expected numbers like 1,2,5: {text!r}") from error
    unknown = sorted(set(numbers) - set(CHECK_NUMBERS))
    if not numbers or unknown:
        raise argparse.ArgumentTypeError(f"checks must be among 1-9, got {text!r}")
    return numbers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="voice_spike", description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--contact", required=True, help="contact id, e.g. clinic")
    parser.add_argument(
        "--confirm-cost", action="store_true", help="required: this places a paid call"
    )
    parser.add_argument(
        "--checks",
        type=parse_checks,
        default=list(CHECK_NUMBERS),
        help="comma-separated check numbers (default: all nine; 7 always runs last)",
    )
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    return parser


async def run(
    args: argparse.Namespace,
    client: httpx.AsyncClient,
    open_socket: OpenSocket,
    observer: Observer,
    *,
    timing: SpikeTiming | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    now: Callable[[], datetime] = datetime.now,
) -> int:
    started_at = now()
    try:
        async with live_call(client, args.contact, open_socket, observer.out) as call:
            ctx = CheckContext(call.session, observer, timing or SpikeTiming(), sleep)
            results = await run_checks(ctx, args.checks)
    except httpx.HTTPStatusError as error:
        observer.out(f"POST /calls refused: HTTP {error.response.status_code}")
        return 1
    turns = call.session.turns
    scrub = {call.call_id, *(turn.turn_id for turn in turns)}
    section = render_run_section(started_at, results, turns, scrub)
    observer.out(section)
    append_run(args.results, section)
    observer.out(f"appended to {args.results}")
    return 0


async def _ask(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


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
                args,
                client,
                lambda call_id: open_call_socket(args.base_url, call_id, token),
                Observer(ask=_ask, out=print),
            )

    return asyncio.run(_main())


if __name__ == "__main__":
    raise SystemExit(main())
