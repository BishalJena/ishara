"""Interfaces between backend modules, so each can be built and tested with fakes.

| Port        | Implemented by                 | Used by                        |
|-------------|--------------------------------|--------------------------------|
| Composer    | app/composer.py                | app/calls.py (session layer)   |
| BolnaClient | app/bolna_client.py            | app/calls.py                   |
| CallLedger  | app/calls.py (session layer)   | app/custom_llm.py              |
"""

from __future__ import annotations

from typing import Protocol

from app.protocol import ComposeRequest, Draft


class Composer(Protocol):
    async def compose(self, request: ComposeRequest) -> Draft:
        """Return a validated LLM draft or the template fallback. Never raises for
        provider failures; falls back to the template instead."""
        ...


class BolnaError(Exception):
    """Every BolnaClient failure (network, HTTP status, bad response, missing agent id).

    The message names only the operation and the HTTP status: Bolna's error bodies can
    hold account identifiers, and the API key must never reach a message or log.
    """

    def __init__(self, status_code: int | None, operation: str, reason: str = "failed") -> None:
        self.status_code = status_code
        self.operation = operation
        status = f"HTTP {status_code}" if status_code is not None else "no response"
        super().__init__(f"Bolna {operation} {reason} ({status})")


class BolnaClient(Protocol):
    """Implementations raise BolnaError, and only BolnaError, when Bolna can't be used;
    the session layer turns it into 502 / not_delivered / end_failed."""

    async def start_call(self, recipient: str, user_data: dict[str, str]) -> str:
        """Ask Bolna to dial `recipient` (already allowlisted). Returns the run id."""
        ...

    async def send_event(self, run_id: str, event: str, properties: dict[str, str]) -> None:
        """POST /v1/call/{run_id}/events. A 202 means published, not spoken."""
        ...


class CallLedger(Protocol):
    async def record_caption(self, call_id: str, text: str) -> None:
        """A new receptionist utterance from Bolna's transcript."""
        ...

    async def record_agent_line(self, call_id: str, text: str) -> None:
        """A fixed line the voice says without a SEND (e.g. the holding line). Shown to
        the app as an agent caption; never touches turns, approvals or the composer's
        last caption."""
        ...

    async def claim_reply(self, call_id: str, turn_id: str, text: str) -> bool:
        """True exactly once for an approved, unspoken turn whose text matches the
        approval. False for unknown, stale, ended or already-claimed turns."""
        ...

    async def mark_spoken(self, call_id: str, turn_id: str) -> None:
        """The custom LLM finished streaming the claimed reply to Bolna."""
        ...
