"""Bolna execution status webhooks mapped to our call states.

Documented (Bolna docs, checked 23 Oct 2026):
- post-call/polling-call-status-webhooks.md: an agent-level Webhook URL receives a
  POST "as call status updates happen"; the body has the same shape as the Get
  Execution API response. There is no signature; the docs only list source IPs and an
  optional "Add headers" toggle. We therefore put a secret in the URL path.
- post-call/execution-payload.md: `id` is the execution id (the run id returned when
  the call is started) and `status` is "the status you should branch on".
- post-call/list-phone-call-status.md: statuses scheduled, queued, rescheduled,
  initiated, ringing, in-progress, call-disconnected, completed (final), balance-low,
  busy, no-answer, canceled, failed, stopped, error.
- Pre-call webhooks from tools reuse the same URL with status in-progress.

Assumed (not documented, check on the day-1 spike):
- `id` in the webhook equals the run id our BolnaClient returns from `POST /call`.
- No-answer and busy count as an ended call; failed, error and balance-low as an error.
- The payload also carries the recipient's number, so it is never logged or echoed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.protocol import CallState

_STATES = {
    "ringing": CallState.RINGING,
    "in-progress": CallState.IN_CALL,
    "call-disconnected": CallState.ENDED,
    "completed": CallState.ENDED,
    "no-answer": CallState.ENDED,
    "busy": CallState.ENDED,
    "canceled": CallState.ENDED,
    "stopped": CallState.ENDED,
    "failed": CallState.ERROR,
    "error": CallState.ERROR,
    "balance-low": CallState.ERROR,
}


class ExecutionUpdate(BaseModel):
    """The two fields we read; everything else (numbers, transcript) is ignored."""

    model_config = ConfigDict(extra="ignore")

    id: str | int
    status: str
    # Bolna's Call Summary extraction runs on every call and arrives as `summary` on the
    # final webhook (docs, 25 Oct). Kept for the notes screen; never logged.
    summary: str | None = None

    @property
    def run_id(self) -> str:
        return str(self.id)


def call_state_for(status: str) -> CallState | None:
    """Our state for a Bolna status, or None when it does not change what the app shows
    (scheduled, queued, rescheduled, initiated, unknown)."""
    return _STATES.get(status)
