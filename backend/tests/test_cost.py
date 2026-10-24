from __future__ import annotations

from tools.cost import CONFIRM_HINT, COST_HEADS_UP, cost_confirmed


def test_unconfirmed_prints_heads_up_and_hint_and_refuses() -> None:
    lines: list[str] = []
    assert cost_confirmed(False, lines.append) is False
    assert lines == [COST_HEADS_UP, CONFIRM_HINT]


def test_confirmed_still_prints_heads_up_first() -> None:
    lines: list[str] = []
    assert cost_confirmed(True, lines.append) is True
    assert lines == [COST_HEADS_UP]


def test_heads_up_names_the_price() -> None:
    assert "₹5.5/min" in COST_HEADS_UP
    assert "₹20-30" in COST_HEADS_UP
