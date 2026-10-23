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


class BolnaClient(Protocol):
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

    async def claim_reply(self, call_id: str, turn_id: str, text: str) -> bool:
        """True exactly once for an approved, unspoken turn whose text matches the
        approval. False for unknown, stale, ended or already-claimed turns."""
        ...

    async def mark_spoken(self, call_id: str, turn_id: str) -> None:
        """The custom LLM finished streaming the claimed reply to Bolna."""
        ...
