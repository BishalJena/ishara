"""Find receptionist utterances that are new since the previous custom-LLM request.

Bolna resends the conversation on every request, but only the latest 50 messages,
so the front of the history can drop off while new turns are appended. With eager
end-of-turn it can also send a short stub of the latest utterance and later replace
it with the full, longer one. Ambiguous cases resolve towards forwarding less: a
missed caption is better than a duplicated one.
"""

from __future__ import annotations


def new_utterances(seen: list[str], current: list[str]) -> list[str]:
    """Utterances in `current` that were not in `seen` (the previous request's list)."""
    for dropped in range(len(seen)):
        kept = seen[dropped:]
        if current[: len(kept)] == kept:
            return current[len(kept) :]
        if _extends_last(kept, current):
            return current[len(kept) - 1 :]
    if not seen:
        return list(current)
    # History was rewritten in a way we can't align; only trust the newest utterance.
    return current[-1:] if current and current[-1] != seen[-1] else []


def _extends_last(kept: list[str], current: list[str]) -> bool:
    last = len(kept) - 1
    return (
        len(current) > last
        and current[:last] == kept[:last]
        and current[last].startswith(kept[last])
    )


class UtteranceTracker:
    """Remembers, per call, the utterances seen in the latest request."""

    def __init__(self) -> None:
        self._seen: dict[str, list[str]] = {}

    def take_new(self, call_id: str, utterances: list[str]) -> list[str]:
        fresh = new_utterances(self._seen.get(call_id, []), utterances)
        self._seen[call_id] = list(utterances)
        return fresh
