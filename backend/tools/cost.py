"""Cost guard for tools that make the backend place a real Bolna call."""

from __future__ import annotations

from collections.abc import Callable

COST_HEADS_UP = (
    "Cost heads-up: this asks the backend to place a REAL Bolna call to the allowlisted "
    "contact. Bolna costs about ₹5.5/min plus telephony; a V4 spike is about ₹20-30."
)
CONFIRM_HINT = "Not starting a call. Re-run with --confirm-cost once the founder has approved it."


def cost_confirmed(confirm_cost: bool, out: Callable[[str], None] = print) -> bool:
    """Always print the heads-up; return True only when `--confirm-cost` was given."""
    out(COST_HEADS_UP)
    if not confirm_cost:
        out(CONFIRM_HINT)
    return confirm_cost
