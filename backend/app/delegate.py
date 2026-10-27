"""Delegated calls (decision D9): the brief, the agent's "brain", and the notes.

The user signs the intent, the app builds a brief from the chips and the profile, the
user approves it once (by starting the call with its id), and the agent then pursues
only that brief. On every receptionist turn the custom-LLM endpoint asks `Brain.reply`
what to say. Attended calls may pause the receptionist ("one moment, please") and ask
the user a yes/no/wait question; unattended calls never ask and promise a callback
instead. Nothing here dials, speaks or stores secrets.

Safety: every line the brain produces goes through `check_line`, which reuses the
composer's validator pieces: no number, time, name or booking claim that neither the
brief nor the receptionist said, no agreeing to an offer (only the user's answer does
that), no meta text, at most 25 words. A rejected LLM line is
replaced by the rule-based brain's line, never spoken as is.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from app.groq_client import GroqClient, GroqError
from app.protocol import (
    MAX_CHIPS,
    AskOption,
    BriefRequest,
    BriefResponse,
    CallNotes,
    Purpose,
    Sign,
    TranscriptEntry,
)
from app.validator import (
    _AGREEMENT,
    _MONTHS,
    _WEEKDAYS,
    MAX_WORDS,
    _booking_claims,
    _invented_names,
    _invented_numbers,
    _meta_text,
    _normalise,
    temporal_facts,
)

log = logging.getLogger(__name__)

LLM_TIMEOUT_S = 2.5
ASK_TIMEOUT_S = 10.0
PAUSE_LINE = "One moment, please."
CALLBACK_LINE = "I'll need to check that and call back. Thank you."
CLOSE_LINE = "Thank you for your help. Goodbye."

PURPOSE_GOAL: dict[Purpose, str] = {"doctor_appointment": "book a doctor's appointment"}

_DAYS: dict[Sign, str] = {
    "today": "today",
    "now": "today",
    "tomorrow": "tomorrow",
    "yesterday": "yesterday",
}
_PARTS: dict[Sign, str] = {
    "morning": "in the morning",
    "afternoon": "in the afternoon",
    "evening": "in the evening",
    "night": "at night",
}
_EXTRA_FACTS: dict[Sign, str] = {
    "sick": "the caller is feeling unwell",
    "callonphone": "please call the caller back by phone",
    "later": "later is fine",
    "wait": "the caller may need a moment to answer",
    "time": "the caller is asking what times are available",
}
_PROPOSAL = re.compile(
    r"\b(\d{1,2}(:\d{2})?\s*(am|pm|a\.m\.|p\.m\.|o'clock)|\d{1,2}:\d{2}|noon|midday)\b",
    re.IGNORECASE,
)
_QUESTION = re.compile(
    r"\?\s*$|\b(does that work|is that (ok|okay|fine)|would that (work|suit))\b", re.I
)
_BOOKED = re.compile(r"\b(booked|confirmed|reserved|scheduled|all set|you're set)\b")
# Accepting an offer is the user's decision (an attended answer), never the agent's.
_COMMITMENT = re.compile(
    r"\b(i'll|we'll|i will|we will) take\b|\bbook (it|that|me|her|him|them)\b|\bplease book\b"
    r"|\bgo ahead\b|\bthat's (fine|good|great|perfect|ok|okay)\b"
)
_NO_SLOT = re.compile(
    r"\b(no (slots?|appointments?|availability)|(fully|all) booked|booked (up|out|solid)"
    r"|nothing (free|available|left)|not available|unavailable"
    r"|(can't|cannot|can not|unable to) (do|fit|offer|book|give|see|manage))\b"
)
# Details a receptionist may ask for that no brief carries (the profile has only a name,
# a callback number and a reason).
_OUT_OF_BRIEF = re.compile(
    r"\b(date of birth|birth ?date|birthday|born|dob|how old|age|insurance|policy|card"
    r"|credit|debit|bank|account|payment|pay|deposit|address|post ?code|zip|pin ?code"
    r"|e-?mail|aadhaar|social security|ssn|id number|medical (history|records?)"
    r"|allerg(y|ies)|medications?|password|otp)\b"
)
# "That isn't confirmed yet", "not booked": a booking word that denies the booking.
_NOT_BOOKED = re.compile(
    r"(\b(not|never)\b|n't\b)[^.?!]{0,20}?\b(booked|confirmed|reserved|scheduled)\b"
)


def _confirms(text: str) -> bool:
    """The receptionist says it is booked ("fully booked" and "not confirmed" are not)."""
    words = _NOT_BOOKED.sub(" ", _NO_SLOT.sub(" ", _normalise(text)))
    return _BOOKED.search(words) is not None


def _declines(text: str) -> bool:
    return _NO_SLOT.search(_normalise(text)) is not None


# ---- the brief ----


def build_brief(request: BriefRequest) -> BriefResponse:
    """Deterministic: the brief says only what the chips and the profile carry."""
    chips = list(dict.fromkeys(request.chips))[:MAX_CHIPS]
    goal = PURPOSE_GOAL[request.purpose]
    when = [_DAYS[c] for c in chips if c in _DAYS] + [_PARTS[c] for c in chips if c in _PARTS]
    constraints = []
    if when:
        constraints.append("preferred time: " + " ".join(dict.fromkeys(when)))
    constraints += [_EXTRA_FACTS[c] for c in chips if c in _EXTRA_FACTS]
    name = request.profile.name.strip()
    lines = [f"Call on behalf of {name}, who is Deaf and uses the Ishara app, to {goal}."]
    if when:
        lines.append(f"Preferred: {' '.join(dict.fromkeys(when))}.")
    if request.profile.notes:
        lines.append(f"Reason, if asked: {request.profile.notes.strip()}")
    share = [f"name ({name})"] + (["callback number"] if request.profile.callback else [])
    lines.append("May share: " + ", ".join(share) + ".")
    lines.append(
        "Will not agree to anything outside this brief; "
        "anything else comes back to you as a question."
    )
    return BriefResponse(
        brief_id=uuid.uuid4().hex, text=" ".join(lines), goal=goal, constraints=constraints
    )


@dataclass(frozen=True)
class Brief:
    text: str
    goal: str
    constraints: tuple[str, ...]
    name: str
    callback: str | None
    notes: str | None
    purpose: Purpose


def brief_from(request: BriefRequest, response: BriefResponse) -> Brief:
    return Brief(
        response.text,
        response.goal,
        tuple(response.constraints),
        request.profile.name.strip(),
        request.profile.callback,
        request.profile.notes,
        request.purpose,
    )


# ---- what the agent may say ----


def check_line(line: str, brief: Brief, transcript_text: str) -> list[str]:
    """Reasons a candidate agent line must not be spoken; empty means it may."""
    text = line.strip()
    if not text:
        return ["empty"]
    reasons: list[str] = []
    if len(text.split()) > MAX_WORDS:
        reasons.append(f"too many words: {len(text.split())}")
    known = " ".join(
        [brief.text, brief.name, brief.callback or "", brief.notes or "", transcript_text]
    )
    reasons += _invented_numbers(text, known)
    reasons += _invented_names(text, known)
    reasons += _booking_claims(_normalise(text), _normalise(transcript_text))
    reasons += [
        f"agrees for the user: {m.group(0)}"
        for pattern in (_AGREEMENT, _COMMITMENT)
        for m in pattern.finditer(_normalise(text))
    ]
    reasons += _meta_text(text)
    # A day or part of day the brief and the receptionist never mentioned.
    allowed = temporal_facts(known)
    reasons += [
        f"invented time: {f.split(':', 1)[1]}" for f in sorted(temporal_facts(text) - allowed)
    ]
    return reasons


@dataclass(frozen=True)
class Decision:
    say: str
    ask: tuple[str, tuple[AskOption, ...]] | None = None  # question and the options' spoken lines
    done: bool = False  # the brief is settled; the agent may close
    source: str = "rules"


@dataclass
class Exchange:
    receptionist: str
    agent: str


@dataclass
class DelegateState:
    brief: Brief
    attended: bool
    exchanges: list[Exchange] = field(default_factory=list)
    opened: bool = False
    pending_ask: str | None = None  # ask_id
    deciding: bool = False  # the brain is working on a receptionist turn
    answers: list[str] = field(default_factory=list)  # what the user chose, in spoken form
    outcome: str | None = None

    def transcript_text(self) -> str:
        return " ".join(x.receptionist + " " + x.agent for x in self.exchanges)


def _options_for(proposal: str) -> tuple[AskOption, ...]:
    return (
        AskOption(choice="yes", spoken=f"Yes, {proposal} works. Thank you."),
        AskOption(
            choice="no", spoken=f"No, {proposal} doesn't work, sorry. Is there another time?"
        ),
        AskOption(choice="wait", spoken="One moment, please, I'm checking."),
    )


def _proposal_in(text: str) -> str | None:
    match = _PROPOSAL.search(text)
    if not match:
        return None
    # Keep the surrounding day words if the receptionist said them ("4 pm tomorrow").
    facts = temporal_facts(text)
    day = next((f.split(":", 1)[1] for f in sorted(facts) if f.startswith("day:")), None)
    return f"{match.group(0).strip()} {day}" if day else match.group(0).strip()


# Days a receptionist can offer instead of the brief's ("today" and "now" are left out:
# "how can I help you today?" is a greeting, not an offer).
_OFFER_DAYS = frozenset(("tomorrow", "day after tomorrow", "may", *_WEEKDAYS, *_MONTHS))
_OFFERING = re.compile(r"\?|\b(how about|what about|instead|could|can|would|available|free)\b")


def _day_offer(text: str, brief: Brief) -> str | None:
    """A day the receptionist offers that the brief never asked for ("Friday instead?")."""
    if not _OFFERING.search(_normalise(text)):
        return None
    new_facts = temporal_facts(text) - temporal_facts(brief.text)
    days = [f.split(":", 1)[1] for f in new_facts if f.startswith("day:")]
    days = [d for d in days if d in _OFFER_DAYS]
    if len(days) != 1:
        return "that" if days else None
    day = days[0]
    if day == "day after tomorrow":
        return "the day after tomorrow"
    return day if day == "tomorrow" else day.capitalize()


class RuleBrain:
    """No LLM: opens with the brief, hands every proposal to the user (attended) or
    promises a callback (unattended), closes when the receptionist confirms."""

    def opening(self, state: DelegateState) -> str:
        when = next(
            (
                c[len("preferred time: ") :]
                for c in state.brief.constraints
                if c.startswith("preferred")
            ),
            None,
        )
        line = f"I'd like to {state.brief.goal} for {state.brief.name}"
        return line + (f", {when}." if when else ".")

    def decide(self, state: DelegateState, heard: str) -> Decision:
        if not state.opened:
            return Decision(self.opening(state))
        if _confirms(heard):
            return Decision(CLOSE_LINE, done=True)
        if _OUT_OF_BRIEF.search(_normalise(heard)):
            # The brief shares only the name and the callback number: never guess the rest,
            # and never answer "insurance number" with the phone number.
            return Decision(CALLBACK_LINE, done=True)
        proposal = _proposal_in(heard) or _day_offer(heard, state.brief)
        if proposal:
            if state.attended:
                return Decision(PAUSE_LINE, ask=(heard.strip(), _options_for(proposal)))
            return Decision(CALLBACK_LINE, done=True)
        if _declines(heard):
            return Decision(CALLBACK_LINE, done=True)
        if "name" in heard.lower():
            return Decision(f"The name is {state.brief.name}.")
        if state.brief.callback and re.search(
            r"\b(number|phone|call you|reach you)\b", heard, re.I
        ):
            return Decision(f"You can reach me on {state.brief.callback}.")
        if _QUESTION.search(heard):
            # A question with no concrete offer ("how can I help?"): say the request again.
            return Decision(self.opening(state))
        return Decision("Could you tell me what times are available?")


SYSTEM_PROMPT = """\
You speak on a phone call on behalf of a Deaf caller, through the Ishara app. You pursue ONE brief
and nothing else. Reply with JSON only: {"say": <one or two short sentences, at most 25 words>,
"ask_user": null or {"question": <the receptionist's proposal in plain words>,
"proposal": <the time/day offered>}, "done": true|false}.
Rules:
- Pursue only the brief. Never agree to, book, confirm or promise anything the brief does not cover.
- When the receptionist proposes a specific time or day, or asks a yes/no question about one:
  ATTENDED mode: set "say" to "One moment, please." and fill ask_user; the caller answers.
  UNATTENDED mode: say you will check and call back, and set done to true.
- Share only the facts in the brief (name, callback number, reason). Never invent symptoms, dates,
  numbers or names. If asked something the brief does not cover, say you will check and call back.
- Set done to true when the appointment is confirmed by the receptionist or you promised a callback.
- Plain spoken English, first person, no markdown, no commentary."""


def _user_message(state: DelegateState, heard: str) -> str:
    return json.dumps(
        {
            "mode": "ATTENDED" if state.attended else "UNATTENDED",
            "brief": state.brief.text,
            "conversation": [
                {"receptionist": x.receptionist, "you": x.agent} for x in state.exchanges[-6:]
            ],
            "user_answers_so_far": state.answers,
            "receptionist_just_said": heard,
        }
    )


class _LlmAsk(BaseModel):
    # SYSTEM_PROMPT also asks for a "question"; it is ignored: the user is always shown
    # the receptionist's own words, never the LLM's account of them.
    proposal: str | None = None


class _LlmTurn(BaseModel):
    """The JSON reply SYSTEM_PROMPT asks for; anything else falls back to the rules."""

    say: str = ""
    ask_user: _LlmAsk | None = None
    done: bool = False


class Brain:
    """Groq with the rule brain as the fallback; every line is checked before it is spoken."""

    def __init__(self, client: GroqClient | None, timeout_s: float = LLM_TIMEOUT_S) -> None:
        self.client = client
        self.timeout_s = timeout_s
        self.rules = RuleBrain()

    async def reply(self, state: DelegateState, heard: str) -> Decision:
        fallback = self.rules.decide(state, heard)
        if self.client is None:
            return fallback
        try:
            raw = await asyncio.wait_for(
                self.client.complete(SYSTEM_PROMPT, _user_message(state, heard)), self.timeout_s
            )
            turn = _LlmTurn.model_validate_json(raw.strip().strip("`").removeprefix("json"))
        except (TimeoutError, GroqError, ValidationError) as exc:
            log.info("delegate: LLM unavailable (%s), using rules", type(exc).__name__)
            return fallback
        transcript = state.transcript_text() + " " + heard
        if turn.ask_user is not None:
            if not state.attended:
                return Decision(CALLBACK_LINE, done=True, source="llm")
            # The agent says PAUSE_LINE whatever "say" held; what gets spoken later are the
            # options, which repeat the proposal back, so the proposal is what is checked.
            proposal = (turn.ask_user.proposal or "").strip() or _proposal_in(heard) or "that"
            reasons = check_line(proposal, state.brief, transcript)
            if reasons:
                log.info("delegate: LLM proposal rejected (%s), using rules", "; ".join(reasons))
                return fallback
            return Decision(PAUSE_LINE, ask=(heard.strip(), _options_for(proposal)), source="llm")
        reasons = check_line(turn.say, state.brief, transcript)
        if reasons:
            log.info("delegate: LLM line rejected (%s), using rules", "; ".join(reasons))
            return fallback
        return Decision(turn.say.strip(), done=turn.done, source="llm")


def build_brain(settings) -> Brain:  # noqa: ANN001  (Settings; avoids an import cycle with config)
    """Rules only without GROQ_API_KEY; otherwise Groq with the rules as fallback."""
    if getattr(settings, "groq_api_key", None) is None:
        return Brain(None)
    return Brain(GroqClient(settings.groq_api_key, settings.groq_model))


# ---- notes ----


def outcome_of(entries: list[TranscriptEntry], answers: list[str]) -> str:
    receptionist = " ".join(e.text for e in entries if e.speaker == "receptionist")
    agent = " ".join(e.text for e in entries if e.speaker == "agent")
    if not receptionist:
        return "no_answer"
    if _confirms(receptionist) or any(a.startswith("Yes") for a in answers):
        return "booked" if not any(a.startswith("No") for a in answers[-1:]) else "unclear"
    promised_callback = CALLBACK_LINE in agent
    if promised_callback and _PROPOSAL.search(receptionist):
        return "callback"  # an offer is still waiting for the user's decision
    if _declines(receptionist) or any(a.startswith("No") for a in answers):
        return "declined"
    return "callback" if promised_callback else "unclear"


def build_notes(
    call_id: str,
    brief: Brief | None,
    entries: list[TranscriptEntry],
    answers: list[str],
    bolna_summary: str | None,
    ready: bool,
) -> CallNotes:
    """Deterministic notes from the transcript: what was offered, what the user chose,
    what is still open. Every bullet quotes or paraphrases a transcript line."""
    if brief is None:
        return CallNotes(call_id=call_id, mode="live", ready=ready, transcript=entries)
    summary: list[str] = [f"Goal: {brief.goal} for {brief.name}."]
    offers = [e.text for e in entries if e.speaker == "receptionist" and _PROPOSAL.search(e.text)]
    for offer in offers[:3]:
        summary.append(f'They offered: "{offer.strip()}"')
    for answer in answers:
        summary.append(f'You answered: "{answer}"')
    confirmations = [e.text for e in entries if e.speaker == "receptionist" and _confirms(e.text)]
    for line in confirmations[:2]:
        summary.append(f'They confirmed: "{line.strip()}"')
    outcome = outcome_of(entries, answers) if ready else None
    open_questions: list[str] = []
    if ready and outcome == "callback":
        open_questions.append(
            "The agent promised to call back. Decide on the offer and call again."
        )
    if ready and outcome == "unclear":
        open_questions.append(
            "Nothing was confirmed. Read the transcript and decide the next step."
        )
    if ready and outcome == "no_answer":
        open_questions.append("Nobody answered or nothing was heard.")
    return CallNotes(
        call_id=call_id,
        mode="delegated",
        ready=ready,
        brief=brief.text,
        outcome=outcome,
        summary=summary,
        open_questions=open_questions,
        transcript=entries,
        bolna_summary=bolna_summary,
    )
