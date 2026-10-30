"""Delegated calls (decision D9): the brief, the agent's "brain", and the notes.

The user signs the intent, the app builds a brief from the chips and the profile, the
user approves it once (by starting the call with its id), and the agent then pursues
only that brief. On every receptionist turn the custom-LLM endpoint asks `Brain.reply`
what to say. Attended calls may pause the receptionist ("one moment, please") and ask
the user: yes/no/wait about an offered time, or a time word about an open "when?"
question. Unattended calls never ask: they promise a callback, or answer an open "when?"
from the brief's preferred time. Nothing here dials, speaks or stores secrets.

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
from dataclasses import dataclass, field, replace
from typing import Literal

from pydantic import BaseModel, ValidationError, model_validator

from app.groq_client import GroqClient, GroqError
from app.protocol import (
    MAX_CHIPS,
    AskChoice,
    AskOption,
    BriefRequest,
    BriefResponse,
    CallMode,
    CallNotes,
    Detail,
    Document,
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
from app.validator import (
    _PARTS as PART_WORDS,
)

log = logging.getLogger(__name__)

LLM_TIMEOUT_S = 2.5
ASK_TIMEOUT_S = 10.0
PAUSE_LINE = "One moment, please."
CALLBACK_LINE = "I'll need to check that and call back. Thank you."
CLOSE_LINE = "Thank you for your help. Goodbye."
WAIT_LINE = "One moment, please, I'm checking."
# Steer calls (CallMode "steer").
DEFER_LINE = "I don't have that with me. Could I send it to you afterwards?"
TIMES_LINE = "What times do you have available?"
ANOTHER_TIME_LINE = "I see. What is the nearest time you do have?"
# Said to the receptionist while the user is typing or signing a reply. Rotated so the
# same line is never said twice in a row; none carries a fact.
FILLERS = (
    "One moment, please.",
    "Just a second, let me check.",
    "Bear with me a moment.",
    "Let me confirm that.",
    "One moment, I'm checking.",
)
# Days a typed request can pin an appointment to. Spans ("next week") only narrow it.
_PIN_DAYS = frozenset(("today", "tomorrow", "day after tomorrow", *_WEEKDAYS))
# The time words the user can sign (or tap) to answer an open "when?" question, in the
# card's order, with what each says. NOW reads as "today", like it does in the brief.
# The model has no number signs, so no clock time is ever signed.
TIME_ANSWERS: dict[AskChoice, str] = {
    "tomorrow": "tomorrow",
    "morning": "in the morning",
    "now": "today, as soon as possible",
}

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
# The receptionist asks *when* without offering a time ("what time would you like?",
# "morning or afternoon?"). Matched on normalised text: the live transcriber writes
# lowercase with no punctuation. "When did ...?" asks about the past, not a booking.
_OPEN_TIME = re.compile(
    r"\b(what|which) (time|day|date)s?\b"
    r"|\bwhen (would|do|can|could|will) (you|she|he|they|we)\b"
    r"|\bwhen (works|suits|is (good|best|convenient)|are you (free|available))\b"
    r"|\bmornings? or (afternoons?|evenings?)\b|\b(afternoons?|evenings?) or mornings?\b"
    r"|\bprefer(red)? (a )?(time|day)\b|\b(time|day) in mind\b|\bparticular (time|day)\b"
)
_BOOKED = re.compile(r"\b(booked|confirmed|reserved|scheduled|all set|you're set)\b")
# Accepting an offer is the user's decision (an attended answer), never the agent's.
_COMMITMENT = re.compile(
    r"\b(i'll|we'll|i will|we will) take\b|\bbook (it|that|me|her|him|them)\b|\bplease book\b"
    r"|\bgo ahead\b|\bthat's (fine|good|great|perfect|ok|okay)\b"
)
# A refusal ("cant": the live transcriber drops apostrophes).
_NO_SLOT = re.compile(
    r"\b(no (slots?|appointments?|availability)|(fully|all) booked|booked (up|out|solid)"
    r"|nothing (free|available|left)|not available|unavailable"
    r"|(can't|cant|cannot|can not|unable to) (do|fit|offer|book|give|see|manage))\b"
)
# Where one part of a reply ends and the next begins: "we can't do 4 pm, but 5 pm works".
_CLAUSE_BREAK = re.compile(r"[.,;!?]|\b(?:but|however|though|although|instead|whereas)\b")
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


def _typed_when(request_text: str) -> str | None:
    """The days and parts of day a typed request names, as the agent says them, e.g.
    "on Tuesday or Wednesday in the morning"; None when it names none."""
    facts = temporal_facts(request_text)
    days = [d for d in _WEEKDAYS if f"day:{d}" in facts]
    relative = [d for d in ("today", "tomorrow", "day after tomorrow") if f"day:{d}" in facts]
    pieces: list[str] = []
    if days:
        pieces.append("on " + " or ".join(d.capitalize() for d in days))
    if relative:
        pieces.append(
            " or ".join("the day after tomorrow" if d.startswith("day") else d for d in relative)
        )
    parts = [p for p in PART_WORDS if f"part:{p}" in facts]
    if parts:
        pieces.append("in the " + " or ".join(parts) if parts != ["night"] else "at night")
    return " ".join(pieces) if pieces else None


def build_brief(request: BriefRequest) -> BriefResponse:
    """Deterministic: the brief says only what the chips, the typed request and the
    profile carry."""
    chips = list(dict.fromkeys(request.chips))[:MAX_CHIPS]
    goal = PURPOSE_GOAL[request.purpose]
    when = [_DAYS[c] for c in chips if c in _DAYS] + [_PARTS[c] for c in chips if c in _PARTS]
    typed = _typed_when(request.request) if request.request else None
    if typed and not when:
        when = [typed]
    constraints = []
    if when:
        constraints.append("preferred time: " + " ".join(dict.fromkeys(when)))
    constraints += [_EXTRA_FACTS[c] for c in chips if c in _EXTRA_FACTS]
    name = request.profile.name.strip()
    lines = [f"Call on behalf of {name}, who is Deaf and uses the Ishara app, to {goal}."]
    if request.request:
        text = request.request.strip()
        lines.append(f"Request: {text}{'' if text.endswith(('.', '!', '?')) else '.'}")
    if when:
        lines.append(f"Preferred: {' '.join(dict.fromkeys(when))}.")
    if request.profile.notes:
        reason = request.profile.notes.strip()
        lines.append(f"Reason, if asked: {reason}{'' if reason.endswith(('.', '!', '?')) else '.'}")
    share = [f"name ({name})"] + (["callback number"] if request.profile.callback else [])
    share += [d.label.strip() for d in request.profile.details]
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
    request: str | None = None
    details: tuple[Detail, ...] = ()
    documents: tuple[Document, ...] = ()

    @property
    def days(self) -> frozenset[str]:
        """Days the typed request pins the appointment to; empty means any day."""
        if not self.request:
            return frozenset()
        return (
            frozenset(
                f.split(":", 1)[1] for f in temporal_facts(self.request) if f.startswith("day:")
            )
            & _PIN_DAYS
        )

    @property
    def parts(self) -> frozenset[str]:
        """Parts of day the typed request allows; empty means any time."""
        if not self.request:
            return frozenset()
        return frozenset(
            f.split(":", 1)[1] for f in temporal_facts(self.request) if f.startswith("part:")
        )


def brief_from(request: BriefRequest, response: BriefResponse) -> Brief:
    return Brief(
        response.text,
        response.goal,
        tuple(response.constraints),
        request.profile.name.strip(),
        request.profile.callback,
        request.profile.notes,
        request.purpose,
        request.request.strip() if request.request else None,
        tuple(request.profile.details),
        tuple(request.profile.documents),
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
        + [f"{d.label} {d.value}" for d in brief.details]
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


# What a steer decision did, so the brain knows which lines are rule-bound (every
# commitment, share or deferral) and which the LLM may reword ("other").
DecisionKind = Literal["other", "open", "close", "share", "defer", "accept", "decline", "time"]


@dataclass(frozen=True)
class Decision:
    say: str
    ask: tuple[str, tuple[AskOption, ...]] | None = None  # question and the options' spoken lines
    done: bool = False  # the brief is settled; the agent may close
    callback: bool = False  # the line promises to call back (it also settles the brief)
    source: str = "rules"
    kind: DecisionKind = "other"
    follow_up: str | None = None  # steer: what was asked for and deferred


@dataclass
class Exchange:
    receptionist: str
    agent: str


@dataclass
class DelegateState:
    brief: Brief
    attended: bool
    # Steer calls: the agent decides every turn by the brief, the user may step in.
    steer: bool = False
    exchanges: list[Exchange] = field(default_factory=list)
    opened: bool = False
    pending_ask: str | None = None  # ask_id
    deciding: bool = False  # the brain is working on a receptionist turn
    answers: list[str] = field(default_factory=list)  # what the user chose, in spoken form
    # How the brief settled; set once, and nothing new is said or asked after it.
    outcome: Literal["done", "callback"] | None = None
    # Steer bookkeeping.
    follow_ups: list[str] = field(default_factory=list)
    stepped_in: int = 0
    composing: bool = False  # the user is typing or signing; the agent only fills
    fillers_said: int = 0
    last_filler: str | None = None
    last_filler_at: float | None = None  # manager clock
    held_text: str | None = None  # an agent line the user held; spoken if they back out
    asked_for_another_time: bool = False

    def transcript_text(self) -> str:
        # The user's spoken answers are part of the call too ("In the morning, please."),
        # so later lines may repeat what the user chose.
        said = [x.receptionist + " " + x.agent for x in self.exchanges]
        return " ".join(said + self.answers)

    @property
    def mode(self) -> CallMode:
        return "steer" if self.steer else "delegated"

    def next_filler(self) -> str:
        """The next cover line, never the one just said."""
        candidates = [f for f in FILLERS if f != self.last_filler]
        line = candidates[self.fillers_said % len(candidates)]
        self.fillers_said += 1
        self.last_filler = line
        return line


def _options_for(proposal: str) -> tuple[AskOption, ...]:
    return (
        AskOption(choice="yes", spoken=f"Yes, {proposal} works. Thank you."),
        AskOption(
            choice="no", spoken=f"No, {proposal} doesn't work, sorry. Is there another time?"
        ),
        AskOption(choice="wait", spoken=WAIT_LINE),
    )


def _time_line(when: str) -> str:
    """The answer to an open "when?": the time, then a nudge towards a concrete offer
    (which goes to the user as yes/no), so the receptionist doesn't ask "when?" again."""
    return f"{when[0].upper()}{when[1:]}, please. What times are available?"


TIME_OPTIONS: tuple[AskOption, ...] = (
    *(AskOption(choice=choice, spoken=_time_line(when)) for choice, when in TIME_ANSWERS.items()),
    AskOption(choice="wait", spoken=WAIT_LINE),
)


def _asks_when(text: str) -> bool:
    return _OPEN_TIME.search(_normalise(text)) is not None


def _preferred_time(brief: Brief) -> str | None:
    """The brief's "preferred time: ..." constraint, e.g. "tomorrow in the morning"."""
    prefix = "preferred time: "
    return next((c[len(prefix) :] for c in brief.constraints if c.startswith(prefix)), None)


def _clock_times(text: str) -> dict[str, str]:
    """Distinct clock times in `text`, keyed without spaces ("4pm"), as said ("4 pm")."""
    times: dict[str, str] = {}
    for match in _PROPOSAL.finditer(_normalise(text)):
        times.setdefault(re.sub(r"\s+", "", match.group(0)), match.group(0).strip())
    return times


@dataclass(frozen=True)
class _TimesHeard:
    """The clock times in a receptionist's turn, split by the clauses that refuse."""

    said: frozenset[str]  # every time mentioned (keys)
    offered: dict[str, str]  # times in clauses that refuse nothing
    unsure: bool  # one refusing clause names several times: which one it refuses is unclear
    offering_text: str  # the clauses that refuse nothing

    @property
    def single(self) -> str | None:
        """The one time on offer; None when there are none or several to choose from."""
        if self.unsure or len(self.offered) != 1:
            return None
        return next(iter(self.offered.values()))


def _times_heard(text: str) -> _TimesHeard:
    said: set[str] = set()
    offered: dict[str, str] = {}
    unsure = False
    offering: list[str] = []
    for clause in _CLAUSE_BREAK.split(_normalise(text)):
        times = _clock_times(clause)
        said |= times.keys()
        if _NO_SLOT.search(clause):
            unsure = unsure or len(times) > 1
            continue
        offering.append(clause)
        for key, time_said in times.items():
            offered.setdefault(key, time_said)
    return _TimesHeard(frozenset(said), offered, unsure, " ".join(offering))


def _proposal_in(text: str) -> str | None:
    """The clock time the receptionist offers ("4 pm tomorrow"). Never one she refuses
    ("can't do 4 pm, but 5 pm works" offers 5 pm); "that" when she offers several, so the
    agent never picks one for the user; None when she offers none."""
    heard = _times_heard(text)
    if heard.single is None:
        return "that" if heard.offered or heard.unsure else None
    # Keep the day words of the offer if the receptionist said them ("4 pm tomorrow").
    facts = temporal_facts(heard.offering_text)
    day = next((f.split(":", 1)[1] for f in sorted(facts) if f.startswith("day:")), None)
    return f"{heard.single} {day}" if day else heard.single


def _not_on_offer(proposal: str, heard: str) -> list[str]:
    """Reasons an LLM proposal names a time from `heard` that is not the one on offer: a
    refused time, or one of several."""
    times = _times_heard(heard)
    single = re.sub(r"\s+", "", times.single) if times.single else None
    return [
        f"not the time on offer: {time_said}"
        for key, time_said in _clock_times(proposal).items()
        if key in times.said and key != single
    ]


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


# ---- steer: fitting an offer to the typed request ----

_CLOCK = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?")
# Label words that name the same detail in the receptionist's mouth.
_DETAIL_SYNONYMS: dict[str, tuple[str, ...]] = {
    "birth": ("dob", "born", "birthday", "birth"),
    "insurance": ("insurance", "policy", "insurer"),
    "address": ("address", "live", "postcode", "pin code", "zip"),
    "email": ("email", "e-mail", "mail"),
    "phone": ("phone", "number", "reach you", "call you back"),
    "age": ("age", "how old"),
}
_DETAIL_STOP_WORDS = frozenset(("the", "of", "and", "number", "his", "her", "their", "my"))


def _part_of(clock: str) -> str | None:
    """The part of day a clock time falls in ("4 pm" -> afternoon; "10:30" with no am/pm
    reads as a working hour: 1-6 as afternoon or evening, 7-11 as morning)."""
    match = _CLOCK.match(clock.strip())
    if match is None:
        return None
    hour, meridiem = int(match.group(1)), match.group(3)
    if (meridiem == "pm" and hour != 12) or (meridiem is None and 1 <= hour <= 6):
        hour += 12
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


def _offer_fits(heard: str, brief: Brief, clock: str | None) -> bool:
    """Whether the time on offer is one the typed request allows: its day is one of the
    request's pinned days (or the request pins none) and its part of day is one of the
    request's parts (or it names none). A day the receptionist never said is no bar."""
    facts = temporal_facts(heard)
    offer_days = {f.split(":", 1)[1] for f in facts if f.startswith("day:")} & _PIN_DAYS
    if brief.days and offer_days and not (offer_days & brief.days):
        return False
    offer_parts = {f.split(":", 1)[1] for f in facts if f.startswith("part:")}
    if clock and (part := _part_of(clock)):
        offer_parts = {part}
    return not (brief.parts and offer_parts and not (offer_parts & brief.parts))


def _preferred_phrase(brief: Brief) -> str:
    """ "on Tuesday or Wednesday in the morning" for the decline line; "" when the
    request pins nothing."""
    when = _preferred_time(brief)
    return f" {when}" if when else ""


def _shareable(heard: str, details: tuple[Detail, ...]) -> Detail | None:
    """The approved detail the receptionist is asking for, matched on its label's words
    and their common synonyms; None when nothing approved fits."""
    text = _normalise(heard)
    words = set(re.findall(r"[a-z]+", text))
    for detail in details:
        label_words = {w for w in re.findall(r"[a-z]+", detail.label.lower()) if len(w) >= 3}
        label_words -= _DETAIL_STOP_WORDS
        if label_words & words:
            return detail
        for key, synonyms in _DETAIL_SYNONYMS.items():
            if key in detail.label.lower() and any(s in text for s in synonyms):
                return detail
    return None


class RuleBrain:
    """No LLM: opens with the brief, hands every proposal to the user (attended) or
    promises a callback (unattended), closes when the receptionist confirms."""

    def decide_steer(self, state: DelegateState, heard: str) -> Decision:
        """Steer calls: every commitment is decided here, by the typed request. Accept an
        offer only when it fits, decline with the request's preference otherwise, share
        only approved details, defer anything else as a follow-up. Never asks the user."""
        brief = state.brief
        if not state.opened:
            return Decision(self.opening(state), kind="open")
        if _confirms(heard):
            return Decision(CLOSE_LINE, done=True, kind="close")
        if (detail := _shareable(heard, brief.details)) is not None:
            return Decision(f"{detail.label.strip()} is {detail.value.strip()}.", kind="share")
        if brief.callback and re.search(r"\b(number|phone|call you|reach you)\b", heard, re.I):
            return Decision(f"You can reach me on {brief.callback}.", kind="share")
        if _OUT_OF_BRIEF.search(_normalise(heard)):
            return Decision(DEFER_LINE, kind="defer", follow_up=heard.strip())
        times = _times_heard(heard)
        if times.single is not None:
            proposal = _proposal_in(heard) or times.single
            if _offer_fits(times.offering_text, brief, times.single):
                return Decision(f"Yes, {proposal} works. Thank you.", kind="accept")
            return Decision(
                f"No, {proposal} doesn't work, sorry. Is there anything{_preferred_phrase(brief)}?",
                kind="decline",
            )
        if times.offered or times.unsure:
            # Several times at once: pick none; let the request's preference narrow it.
            preferred = _preferred_phrase(brief)
            if preferred:
                return Decision(f"Which of those would be{preferred}?", kind="time")
            return Decision("Yes, the earliest of those works. Thank you.", kind="accept")
        if _asks_when(heard):
            when = _preferred_time(brief)
            return Decision(_time_line(when) if when else TIMES_LINE, kind="time")
        heard_days = {
            f.split(":", 1)[1] for f in temporal_facts(heard) if f.startswith("day:")
        } & _PIN_DAYS
        if heard_days and _OFFERING.search(_normalise(heard)):
            # A day on offer with no clock time: fine when the request allows it, then
            # ask for the times; otherwise decline with the request's preference.
            fits = not brief.days or bool(heard_days & brief.days)
            day = min(heard_days, key=lambda d: (d not in brief.days, d))
            spoken = "the day after tomorrow" if day == "day after tomorrow" else day
            spoken = (
                spoken
                if spoken in ("today", "tomorrow", "the day after tomorrow")
                else spoken.capitalize()
            )
            if fits and len(heard_days) == 1:
                return Decision(f"{spoken[0].upper()}{spoken[1:]} works. {TIMES_LINE}", kind="time")
            if fits:
                return Decision(f"Which of those would be{_preferred_phrase(brief)}?", kind="time")
            return Decision(
                f"No, {spoken} doesn't work, sorry. Is there anything{_preferred_phrase(brief)}?",
                kind="decline",
            )
        if _declines(heard):
            if state.asked_for_another_time:
                return Decision(CALLBACK_LINE, done=True, callback=True, kind="close")
            state.asked_for_another_time = True
            return Decision(ANOTHER_TIME_LINE, kind="time")
        if "name" in heard.lower():
            return Decision(f"The name is {brief.name}.", kind="share")
        if _QUESTION.search(heard):
            return Decision(self.opening(state), kind="other")
        return Decision(TIMES_LINE, kind="other")

    def opening(self, state: DelegateState) -> str:
        when = _preferred_time(state.brief)
        line = f"I'd like to {state.brief.goal} for {state.brief.name}"
        return line + (f", {when}." if when else ".")

    def open_time(self, state: DelegateState, heard: str) -> Decision:
        """An open "when?" with no time on offer. Attended: the user picks a time word.
        Unattended: the brief's preferred time, said once; otherwise a callback."""
        if state.attended:
            return Decision(PAUSE_LINE, ask=(heard.strip(), TIME_OPTIONS))
        when = _preferred_time(state.brief)
        if when is None:
            return Decision(CALLBACK_LINE, done=True, callback=True)
        line = _time_line(when)
        if any(x.agent == line for x in state.exchanges):
            # Asked again after hearing it: the brief has nothing more to add.
            return Decision(CALLBACK_LINE, done=True, callback=True)
        return Decision(line)

    def decide(self, state: DelegateState, heard: str) -> Decision:
        if state.steer:
            return self.decide_steer(state, heard)
        if not state.opened:
            return Decision(self.opening(state))
        if _confirms(heard):
            return Decision(CLOSE_LINE, done=True)
        if _OUT_OF_BRIEF.search(_normalise(heard)):
            # The brief shares only the name and the callback number: never guess the rest,
            # and never answer "insurance number" with the phone number.
            return Decision(CALLBACK_LINE, done=True, callback=True)
        # A clock time is a concrete offer even inside a "when?" question; a day offer
        # is not: "what time tomorrow?" asks for a time.
        proposal = _proposal_in(heard)
        if not proposal and _asks_when(heard):
            return self.open_time(state, heard)
        proposal = proposal or _day_offer(heard, state.brief)
        if proposal:
            if state.attended:
                return Decision(PAUSE_LINE, ask=(heard.strip(), _options_for(proposal)))
            return Decision(CALLBACK_LINE, done=True, callback=True)
        if _declines(heard):
            return Decision(CALLBACK_LINE, done=True, callback=True)
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
"ask_user": null or {"kind": "offer", "question": <the receptionist's proposal in plain words>,
"proposal": <the one time/day offered now; never a time the receptionist says they can't do;
if they offer more than one time, use "that">} or {"kind": "time"}, "done": true|false}.
Rules:
- Pursue only the brief. Never agree to, book, confirm or promise anything the brief does not cover.
- When the receptionist proposes a specific time or day, or asks a yes/no question about one:
  ATTENDED mode: set "say" to "One moment, please." and set ask_user to the "offer" form; the
  caller answers.
  UNATTENDED mode: say you will check and call back, and set done to true.
- When the receptionist asks an open question about when (what time, which day, morning or
  afternoon) without offering a specific time: set "say" to "One moment, please." and ask_user
  to {"kind": "time"}, in both modes. Never pick a time yourself.
- Share only the facts in the brief (name, callback number, reason). Never invent symptoms, dates,
  numbers or names. If asked something the brief does not cover, say you will check and call back.
- Set done to true when the appointment is confirmed by the receptionist or you promised a callback.
- Plain spoken English, first person, no markdown, no commentary."""


STEER_PROMPT = """\
You speak on a phone call on behalf of a Deaf caller, through the Ishara app. You pursue ONE brief
and nothing else. Reply with JSON only: {"say": <one or two short sentences, at most 25 words>,
"ask_user": null, "done": false}.
Rules:
- Pursue only the brief. Never agree to, book, confirm or promise anything, and never pick or
  suggest a time: another part of the system answers offers and questions about times.
- Share only the facts in the brief. Never invent symptoms, dates, numbers or names.
- If asked something the brief does not cover, say you don't have it with you and will send it
  afterwards.
- Plain spoken English, first person, no markdown, no commentary."""


def _user_message(state: DelegateState, heard: str) -> str:
    return json.dumps(
        {
            "mode": "STEER" if state.steer else "ATTENDED" if state.attended else "UNATTENDED",
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
    kind: Literal["offer", "time"] = "offer"
    proposal: str | None = None

    @model_validator(mode="after")
    def _time_has_no_proposal(self) -> _LlmAsk:
        if self.kind == "time" and (self.proposal or "").strip():
            raise ValueError("an open time question offers no time")
        return self


class _LlmTurn(BaseModel):
    """The JSON reply SYSTEM_PROMPT asks for; anything else falls back to the rules."""

    say: str = ""
    ask_user: _LlmAsk | None = None
    done: bool = False


LOOKUP_PROMPT = """\
You help a phone assistant answer a question from the person on the other end of a call, using
only documents the caller attached (a card, letter or bill, as plain text). Reply with JSON only:
{"label": "<one to three plain words naming what was asked, e.g. Policy number>",
 "value": "<the answer copied EXACTLY as it appears in a document>"}
or {"label": null, "value": null} if the documents do not contain it.
Never guess, complete, reformat or combine values. If several documents have it, use the first.
"""


class _Lookup(BaseModel):
    label: str | None = None
    value: str | None = None


def _normalised_text(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def verified_lookup(found: _Lookup, documents: tuple[Document, ...]) -> Detail | None:
    """The looked-up fact as a detail, only if its value appears verbatim (ignoring case,
    spaces and punctuation) in one of the documents. This is what stops an invented answer."""
    if not found.label or not found.value:
        return None
    label, value = found.label.strip(), found.value.strip()
    if not (1 <= len(label.split()) <= 3 and 1 <= len(value) <= 80):
        return None
    needle = _normalised_text(value)
    if not needle or not any(needle in _normalised_text(d.text) for d in documents):
        return None
    return Detail(label=label[:1].upper() + label[1:], value=value)


class Brain:
    """Groq with the rule brain as the fallback; every line is checked before it is spoken."""

    def __init__(self, client: GroqClient | None, timeout_s: float = LLM_TIMEOUT_S) -> None:
        self.client = client
        self.timeout_s = timeout_s
        self.rules = RuleBrain()

    async def lookup(self, brief: Brief, heard: str) -> Decision | None:
        """Steer: the receptionist asked for something the brief doesn't hold. Find it in
        the attached documents; share it only when it is there word for word."""
        if self.client is None or not brief.documents:
            return None
        docs = "\n\n".join(f"### {d.name}\n{d.text[:6000]}" for d in brief.documents)
        try:
            raw = await asyncio.wait_for(
                self.client.complete(
                    LOOKUP_PROMPT, f"They asked: {heard.strip()}\n\nDocuments:\n{docs}"
                ),
                self.timeout_s,
            )
            found = _Lookup.model_validate_json(raw.strip().strip("`").removeprefix("json"))
        except (TimeoutError, GroqError, ValidationError) as exc:
            log.info("steer: lookup unavailable (%s), deferring", type(exc).__name__)
            return None
        detail = verified_lookup(found, brief.documents)
        if detail is None:
            log.info("steer: lookup found nothing verbatim, deferring")
            return None
        return Decision(f"{detail.label} is {detail.value}.", source="llm", kind="share")

    async def reply(self, state: DelegateState, heard: str) -> Decision:
        fallback = self.rules.decide(state, heard)
        if self.client is None:
            return fallback
        if state.steer:
            # Every commitment, share, deferral and time answer is rule-bound; the LLM
            # may only phrase the conversational turns, and never asks the user. The one
            # exception: a deferral may become a share if the answer is in a document.
            if fallback.kind == "defer":
                return await self.lookup(state.brief, heard) or fallback
            if fallback.kind != "other":
                return fallback
            try:
                raw = await asyncio.wait_for(
                    self.client.complete(STEER_PROMPT, _user_message(state, heard)),
                    self.timeout_s,
                )
                turn = _LlmTurn.model_validate_json(raw.strip().strip("`").removeprefix("json"))
            except (TimeoutError, GroqError, ValidationError) as exc:
                log.info("steer: LLM unavailable (%s), using rules", type(exc).__name__)
                return fallback
            if turn.ask_user is not None or turn.done:
                return fallback
            reasons = check_line(turn.say, state.brief, state.transcript_text() + " " + heard)
            if reasons:
                log.info("steer: LLM line rejected (%s), using rules", "; ".join(reasons))
                return fallback
            return Decision(turn.say.strip(), source="llm", kind="other")
        try:
            raw = await asyncio.wait_for(
                self.client.complete(SYSTEM_PROMPT, _user_message(state, heard)), self.timeout_s
            )
            turn = _LlmTurn.model_validate_json(raw.strip().strip("`").removeprefix("json"))
        except (TimeoutError, GroqError, ValidationError) as exc:
            log.info("delegate: LLM unavailable (%s), using rules", type(exc).__name__)
            return fallback
        transcript = state.transcript_text() + " " + heard
        if turn.ask_user is not None and turn.ask_user.kind == "time":
            if _proposal_in(heard):
                # A clock time was offered: that is a yes/no question for the user.
                log.info("delegate: LLM time ask over a concrete offer, using rules")
                return fallback
            # The lines are fixed (the time words' sentences or the brief's time).
            return replace(self.rules.open_time(state, heard), source="llm")
        if turn.ask_user is not None:
            if not state.attended:
                return Decision(CALLBACK_LINE, done=True, callback=True, source="llm")
            # The agent says PAUSE_LINE whatever "say" held; what gets spoken later are the
            # options, which repeat the proposal back, so the proposal is what is checked.
            proposal = (turn.ask_user.proposal or "").strip() or _proposal_in(heard) or "that"
            reasons = check_line(proposal, state.brief, transcript)
            reasons += _not_on_offer(proposal, heard)
            if reasons:
                log.info("delegate: LLM proposal rejected (%s), using rules", "; ".join(reasons))
                return fallback
            return Decision(PAUSE_LINE, ask=(heard.strip(), _options_for(proposal)), source="llm")
        reasons = check_line(turn.say, state.brief, transcript)
        if reasons:
            log.info("delegate: LLM line rejected (%s), using rules", "; ".join(reasons))
            return fallback
        # SYSTEM_PROMPT: done means confirmed by the receptionist or a promised callback.
        callback = turn.done and not _confirms(heard)
        return Decision(turn.say.strip(), done=turn.done, callback=callback, source="llm")


def build_brain(settings) -> Brain:  # noqa: ANN001  (Settings; avoids an import cycle with config)
    """Rules only without GROQ_API_KEY; otherwise Groq with the rules as fallback."""
    if getattr(settings, "groq_api_key", None) is None:
        return Brain(None)
    return Brain(GroqClient(settings.groq_api_key, settings.groq_model))


# ---- notes ----


def outcome_of(entries: list[TranscriptEntry], answers: list[str], promised_callback: bool) -> str:
    receptionist = " ".join(e.text for e in entries if e.speaker == "receptionist")
    if not receptionist:
        return "no_answer"
    if _confirms(receptionist) or any(a.startswith("Yes") for a in answers):
        return "booked" if not any(a.startswith("No") for a in answers[-1:]) else "unclear"
    if promised_callback and _PROPOSAL.search(_normalise(receptionist)):
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
    *,
    promised_callback: bool,
    mode: CallMode = "delegated",
    follow_ups: list[str] | None = None,
    stepped_in: int = 0,
) -> CallNotes:
    """Deterministic notes from the transcript: what was offered, what the user chose,
    what is still open. Every bullet quotes or paraphrases a transcript line."""
    if brief is None:
        return CallNotes(call_id=call_id, mode="live", ready=ready, transcript=entries)
    summary: list[str] = [f"Goal: {brief.goal} for {brief.name}."]
    offers = [
        e.text
        for e in entries
        if e.speaker == "receptionist" and _PROPOSAL.search(_normalise(e.text))
    ]
    for offer in offers[:3]:
        summary.append(f'They offered: "{offer.strip()}"')
    for answer in answers:
        summary.append(f'You answered: "{answer}"')
    confirmations = [e.text for e in entries if e.speaker == "receptionist" and _confirms(e.text)]
    for line in confirmations[:2]:
        summary.append(f'They confirmed: "{line.strip()}"')
    outcome = outcome_of(entries, answers, promised_callback) if ready else None
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
    for asked in follow_ups or []:
        open_questions.append(f'They asked for something you didn\'t give: "{asked}"')
    return CallNotes(
        call_id=call_id,
        mode=mode,
        ready=ready,
        brief=brief.text,
        outcome=outcome,
        summary=summary,
        open_questions=open_questions,
        transcript=entries,
        bolna_summary=bolna_summary,
        follow_ups=list(follow_ups or []),
        stepped_in=stepped_in,
    )
