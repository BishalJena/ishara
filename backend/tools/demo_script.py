"""The rehearsed clinic call from PLAN.md §1, driven automatically through the session.

T0 (disclosure), T2 and T4 (receptionist) happen on the phone; this plays the user's
turns T1, T3 (with the planned wrong chip removed before SEND, 3b) and T5. The caller
ends the call (T6) with `AppSession.hang_up` on every exit path.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from app.protocol import NotDeliveredMessage, Sign
from tools.app_client import NOT_DELIVERED_NOTICE, AppSession
from tools.timing import TurnTiming

ChipEdit = tuple[Literal["add", "remove"], Sign]


@dataclass(frozen=True)
class ScriptTurn:
    label: str
    edits: tuple[ChipEdit, ...]


DEMO_SCRIPT: tuple[ScriptTurn, ...] = (
    ScriptTurn("T1", (("add", "hello"), ("add", "doctor"), ("add", "tomorrow"))),
    ScriptTurn(
        "T3",
        (("add", "no"), ("add", "evening"), ("remove", "evening"), ("add", "morning")),
    ),
    ScriptTurn("T5", (("add", "yes"), ("add", "thankyou"))),
)


@dataclass(frozen=True)
class Pacing:
    first_caption_wait_s: float = 10.0
    caption_timeout_s: float = 45.0
    sign_gap_s: float = 1.5
    draft_timeout_s: float = 5.0
    spoken_timeout_s: float = 30.0


class ScriptAbortedError(Exception):
    """A turn could not continue (no draft to approve)."""


async def _await_caption(
    session: AppSession, since: int, timeout: float, what: str, log: Callable[[str], None]
) -> None:
    try:
        await session.wait_for_caption(since=since, timeout=timeout)
    except TimeoutError:
        log(f"no {what} within {timeout:g} s, continuing")


async def _sign(session: AppSession, turn: ScriptTurn, pacing: Pacing) -> None:
    """Apply each chip edit like a sign landing (or ✕ tapped), waiting for its draft."""
    for operation, sign in turn.edits:
        since = session.mark()
        sent = await (session.add_chip(sign) if operation == "add" else session.remove_chip(sign))
        if sent:
            try:
                await session.wait_for_draft(since=since, timeout=pacing.draft_timeout_s)
            except TimeoutError as error:
                raise ScriptAbortedError(
                    f"{turn.label}: no draft within {pacing.draft_timeout_s:g} s"
                ) from error
        await asyncio.sleep(pacing.sign_gap_s)


async def run_demo_script(
    session: AppSession, pacing: Pacing, log: Callable[[str], None] = print
) -> list[TurnTiming]:
    since = session.mark()
    await _await_caption(session, since, pacing.first_caption_wait_s, "first caption", log)
    for index, turn in enumerate(DEMO_SCRIPT):
        if index:
            await _await_caption(
                session, since, pacing.caption_timeout_s, "receptionist caption", log
            )
        session.new_turn(turn.label)
        await _sign(session, turn, pacing)
        since = session.mark()
        turn_id = await session.send()
        log(f"{turn.label}: SEND")
        try:
            outcome = await session.wait_for_outcome(
                turn_id, since=since, timeout=pacing.spoken_timeout_s
            )
        except TimeoutError:
            log(f"{turn.label}: no spoken confirmation within {pacing.spoken_timeout_s:g} s")
            continue
        if isinstance(outcome, NotDeliveredMessage):
            log(f"{turn.label}: {NOT_DELIVERED_NOTICE} (the script never resends)")
    return session.turns
