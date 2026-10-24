from __future__ import annotations

from tools.timing import TurnTiming, format_timing_table


def test_table_rows_show_label_latencies_and_outcome() -> None:
    turns = [
        TurnTiming("T1", "a" * 32, draft_latency_s=0.4567, spoken_latency_s=1.2, outcome="spoken"),
        TurnTiming("T3", "b" * 32, draft_latency_s=0.9, outcome="not_delivered"),
        TurnTiming("T5", "c" * 32, outcome="pending"),
        TurnTiming("quick", "d" * 32),
    ]
    lines = format_timing_table(turns).splitlines()
    assert lines[0] == "| Turn | Chips → draft (s) | SEND → spoken (s) | Outcome |"
    assert lines[2:] == [
        "| T1 | 0.46 | 1.20 | spoken |",
        "| T3 | 0.90 | — | not delivered |",
        "| T5 | — | — | no confirmation |",
        "| quick | — | — | not sent |",
    ]


def test_table_never_contains_turn_ids() -> None:
    table = format_timing_table([TurnTiming("T1", "f00dfeed" * 4, outcome="spoken")])
    assert "f00dfeed" not in table
