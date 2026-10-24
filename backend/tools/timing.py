"""Per-turn timings measured from WebSocket events, and the table printed after a run.

Times are seconds on the tool's monotonic clock. `spoken` means the backend saw the
custom-LLM stream finish, which is not the same as first audio on the phone.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

Outcome = Literal["not_sent", "pending", "spoken", "not_delivered"]

OUTCOME_LABELS: dict[Outcome, str] = {
    "not_sent": "not sent",
    "pending": "no confirmation",
    "spoken": "spoken",
    "not_delivered": "not delivered",
}


@dataclass
class TurnTiming:
    """Filled in as events arrive. `turn_id` is for matching only; never print or save it."""

    label: str
    turn_id: str
    draft_latency_s: float | None = None
    spoken_latency_s: float | None = None
    outcome: Outcome = "not_sent"


def _seconds(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def format_timing_table(turns: Iterable[TurnTiming]) -> str:
    """Markdown table of labels, latencies and outcomes. Turn ids are left out on purpose."""
    rows = [
        "| Turn | Chips → draft (s) | SEND → spoken (s) | Outcome |",
        "|---|---|---|---|",
    ]
    rows += [
        f"| {turn.label} | {_seconds(turn.draft_latency_s)} | "
        f"{_seconds(turn.spoken_latency_s)} | {OUTCOME_LABELS[turn.outcome]} |"
        for turn in turns
    ]
    return "\n".join(rows)
