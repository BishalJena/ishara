"""Typed commands for the interactive fake app, mapped onto the app session."""

from __future__ import annotations

import shlex
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from tools.app_client import AppSession

HELP = """commands:
  chips <sign> [<sign> ...]  replace this turn's chips ('?' is shown, never sent)
  rm <chip>                  remove a chip (✕); resends chips with the same turn id
  send                       approve this turn's latest draft (SEND), then start a new turn
  say "text"                 approve exact text on a fresh turn (quick reply)
  new                        start a new turn (Clear)
  stop                       STOP: cancel unspoken output
  end                        end the call and quit
  help                       show this"""


@dataclass(frozen=True)
class Chips:
    signs: tuple[str, ...]


@dataclass(frozen=True)
class Remove:
    chip: str


@dataclass(frozen=True)
class Say:
    text: str


@dataclass(frozen=True)
class Simple:
    name: str  # send | new | stop | end | help


Command = Chips | Remove | Say | Simple
_SIMPLE = ("send", "new", "stop", "end", "help")


def parse_command(line: str) -> Command:
    """Raises ValueError with a user-facing message for anything unrecognised."""
    words = shlex.split(line)
    if not words:
        raise ValueError("empty command; type help")
    name, args = words[0].lower(), words[1:]
    if name == "chips" and args:
        return Chips(tuple(args))
    if name == "rm" and len(args) == 1:
        return Remove(args[0])
    if name == "say" and args:
        return Say(" ".join(args))
    if name in _SIMPLE and not args:
        return Simple(name)
    raise ValueError(f"cannot parse {line!r}; type help")


async def execute(session: AppSession, command: Command, out: Callable[[str], None]) -> bool:
    """Run one command. Returns False once the user ended the call."""
    match command:
        case Chips(signs=signs):
            if not await session.set_chips(signs):
                out("chips unchanged for the backend (only '?' changed); nothing sent")
        case Remove(chip=chip):
            await session.remove_chip(chip)
        case Say(text=text):
            await session.say(text)
            out(f"SEND (quick reply): {text}")
        case Simple(name="send"):
            text = session.draft.text if session.draft else ""
            await session.send()  # raises NoDraftError when there is no draft
            out(f"SEND: {text}")
        case Simple(name="new"):
            session.new_turn()
            out("new turn")
        case Simple(name="stop"):
            await session.stop()
        case Simple(name="end"):
            await session.end()
            return False
        case Simple(name="help"):
            out(HELP)
    return True


async def run_commands(
    session: AppSession,
    read_line: Callable[[], Awaitable[str | None]],
    out: Callable[[str], None],
    recoverable: tuple[type[Exception], ...],
) -> None:
    """Read and run commands until `end`, EOF or the socket closes. Errors listed in
    `recoverable` (bad input, no draft yet) are shown and the loop continues."""
    while not session.closed and (line := await read_line()) is not None:
        if not line.strip():
            continue
        try:
            keep_going = await execute(session, parse_command(line), out)
        except recoverable as error:
            out(f"! {error}")
            continue
        if not keep_going:
            return
