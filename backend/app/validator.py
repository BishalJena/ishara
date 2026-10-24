"""Checks an LLM draft against the chips and the receptionist's last words.

PLAN §4: reject a draft that misses a chip's meaning, adds a day, time, number or
name that neither the user signed nor the receptionist said, or runs past 25
words. `validate` returns the reasons; an empty list means the draft may be shown.
Facts copied from the receptionist's caption are allowed. Known blind spots: a
name at the very start of a sentence or written in lower case is not detected.
"""

from __future__ import annotations

import re

from app.protocol import MAX_SPOKEN_CHARS, ComposeRequest, Sign

MAX_WORDS = 25

# How each non-temporal sign may be expressed. Temporal signs are checked as facts.
_MEANINGS: dict[Sign, re.Pattern[str]] = {
    "hello": re.compile(r"\b(hello|hi|hey)\b"),
    "thankyou": re.compile(r"\bthanks?\b"),
    "yes": re.compile(r"\b(yes|yeah|yep|okay|ok|fine|works)\b"),
    "no": re.compile(r"\b(no|not|cannot)\b|n't\b"),
    "sorry": re.compile(r"\b(sorry|apologies|apologi[sz]e|excuse me)\b"),
    "doctor": re.compile(r"\b(doctor|doctors|doctor's|dr)\b"),
    "time": re.compile(r"\b(time|times|slot|slots|when)\b"),
}
# Polarity words that flip the user's answer; they need the matching chip.
_REFUSAL = _MEANINGS["no"]
_AGREEMENT = re.compile(r"\b(yes|yeah|yep)\b")

_PARTS = ("morning", "afternoon", "evening", "night")
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_MONTHS = ("january", "february", "march", "april", "june", "july", "august") + (
    "september",
    "october",
    "november",
    "december",
)
# "may" is usually the verb, so only count it as a month after a preposition or before a number.
_MAY_MONTH = r"(?:(?<=in )|(?<=of )|(?<=on )|(?<=by )|(?<=until ))may\b|\bmay(?= \d)"
_SPANS = ("weekend", "week", "fortnight", "month", "year")


def _temporal_table() -> list[tuple[re.Pattern[str], frozenset[str]]]:
    """Phrase -> fact keys, longest phrases first; each match is consumed once."""
    rows: list[tuple[str, tuple[str, ...]]] = [("day after tomorrow", ("day:day after tomorrow",))]
    rows += [(f"this {part}", ("day:today", f"part:{part}")) for part in _PARTS]
    rows += [("tonight", ("day:today", "part:evening"))]
    rows += [(day, (f"day:{day}",)) for day in ("today", "tomorrow", "yesterday")]
    rows += [(f"{day}s?", (f"day:{day}",)) for day in _WEEKDAYS]
    rows += [(month, (f"day:{month}",)) for month in _MONTHS]
    rows += [(f"(?:next|this|last|coming) {span}", (f"day:{span}",)) for span in _SPANS]
    rows += [(f"{span}s?", (f"day:{span}",)) for span in _SPANS]
    rows += [(f"{part}s?", (f"part:{part}",)) for part in _PARTS]
    table = [(re.compile(rf"\b{phrase}\b"), frozenset(keys)) for phrase, keys in rows]
    table.append((re.compile(_MAY_MONTH), frozenset({"day:may"})))
    return table


_TEMPORAL = _temporal_table()
_SIGN_FACTS: dict[Sign, str] = {
    "today": "day:today",
    "tomorrow": "day:tomorrow",
    "morning": "part:morning",
    "afternoon": "part:afternoon",
    "evening": "part:evening",
}

_NUMBER_WORDS = frozenset(
    ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")
    + ("eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen")
    + ("eighteen", "nineteen", "twenty", "thirty", "forty", "fifty", "sixty", "hundred")
    + ("thousand", "dozen", "half", "quarter", "noon", "midday", "midnight", "o'clock", "pm")
    + ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth")
    + ("tenth", "eleventh", "twelfth", "twentieth", "thirtieth")
)

# Capitalised words that are not names; matched in lower case.
_NOT_NAMES = frozenset({"i", "i'd", "i'm", "i'll", "i've", "ok", "okay", "doctor", "dr"})
_TITLES = frozenset({"dr", "mr", "mrs", "ms", "prof"})

_BOOKING = re.compile(
    r"\b(booked|confirmed|reserved|scheduled|all set|is set|you're set|we're set|i'm set)\b"
)
_META = (
    (re.compile(r"[\"“”`*#_\[\]{}<>|~•\n]"), "quotes, markdown or line breaks"),
    (re.compile(r"^['‘]|['’]$"), "wrapped in quotes"),
    (re.compile(r"(?<!\d):|:(?!\d)"), "a label or colon"),
    (re.compile(r"^\s*-"), "a list item"),
    (
        re.compile(
            r"\b(here's|here is|certainly|draft|sentence|rephrased?|reword(ed)?|rewrite|"
            r"translation|chips?|the user|the signer|the caller|as an ai)\b",
            re.IGNORECASE,
        ),
        "commentary",
    ),
)


def _normalise(text: str) -> str:
    """Lower case, straight apostrophes, 'a.m.' -> 'am', '10.30' -> '10:30'."""
    text = text.lower().replace("’", "'").replace("‘", "'")
    text = re.sub(r"\b([ap])\.m\.?", r"\1m", text)
    return re.sub(r"(\d)\.(\d)", r"\1:\2", text)


def temporal_facts(text: str) -> set[str]:
    """Day and part-of-day facts mentioned in `text`, e.g. {'day:tomorrow', 'part:morning'}."""
    remaining = _normalise(text)
    facts: set[str] = set()
    for pattern, keys in _TEMPORAL:
        if pattern.search(remaining):
            facts |= keys
            remaining = pattern.sub(" ", remaining)
    return facts


def _number_tokens(text: str) -> list[str]:
    found: list[str] = []
    previous_is_number = False
    for token in re.findall(r"\d+(?::\d+)?|[a-z']+", _normalise(text)):
        # "am" is only a time after a number ("10 am"); otherwise it's "I am".
        previous_is_number = (
            token[0].isdigit() or token in _NUMBER_WORDS or (token == "am" and previous_is_number)
        )
        if previous_is_number:
            found.append(token)
    return found


def _missing_meanings(text: str, request: ComposeRequest, facts: set[str]) -> list[str]:
    reasons = []
    for sign in dict.fromkeys(request.chips):
        fact = _SIGN_FACTS.get(sign)
        ok = fact in facts if fact else _MEANINGS[sign].search(text)
        if not ok:
            reasons.append(f"missing meaning: {sign}")
    return reasons


def _flipped_answer(text: str, request: ComposeRequest) -> list[str]:
    reasons = []
    if "no" not in request.chips and _REFUSAL.search(text):
        reasons.append("adds a refusal the user did not sign")
    if "yes" not in request.chips and _AGREEMENT.search(text):
        reasons.append("adds agreement the user did not sign")
    return reasons


def _invented_temporal(facts: set[str], request: ComposeRequest, caption: str) -> list[str]:
    allowed = {_SIGN_FACTS[s] for s in request.chips if s in _SIGN_FACTS} | temporal_facts(caption)
    labels = {"day": "invented day", "part": "invented time of day"}
    reasons = []
    for fact in sorted(facts - allowed):
        kind, value = fact.split(":", 1)
        reasons.append(f"{labels[kind]}: {value}")
    return reasons


def _invented_numbers(draft: str, caption: str) -> list[str]:
    heard = set(_number_tokens(caption))
    invented = dict.fromkeys(t for t in _number_tokens(draft) if t not in heard)
    return [f"invented number or time: {token}" for token in invented]


def _invented_names(draft: str, caption: str) -> list[str]:
    heard = set(re.findall(r"[a-z][a-z']*", _normalise(caption)))
    reasons = []
    sentence_start, previous = True, ""
    for match in re.finditer(r"[.!?]|[A-Za-z][A-Za-z'’]*", draft):
        token = match.group(0)
        if token in ".!?":
            sentence_start = previous not in _TITLES
            continue
        word = token.lower().replace("’", "'")
        is_name = token[0].isupper() and not sentence_start and word not in _NOT_NAMES
        if is_name and word not in heard:
            reasons.append(f"invented name: {token}")
        sentence_start, previous = False, word
    return reasons


def _booking_claims(text: str, caption: str) -> list[str]:
    return [
        f"booking claim: {claim}"
        for claim in dict.fromkeys(m.group(0) for m in _BOOKING.finditer(text))
        if claim not in caption
    ]


def _meta_text(draft: str) -> list[str]:
    return [f"meta text: {label}" for pattern, label in _META if pattern.search(draft)]


def validate(draft_text: str, request: ComposeRequest) -> list[str]:
    """Reasons to reject `draft_text` for `request`; empty means it may be shown."""
    draft = draft_text.strip()
    if not draft:
        return ["empty draft"]
    reasons: list[str] = []
    if len(draft) > MAX_SPOKEN_CHARS:
        reasons.append(f"too long: {len(draft)} characters")
    words = len(draft.split())
    if words > MAX_WORDS:
        reasons.append(f"too many words: {words}")
    text, caption = _normalise(draft), request.last_caption or ""
    facts = temporal_facts(draft)
    reasons += _missing_meanings(text, request, facts)
    reasons += _flipped_answer(text, request)
    reasons += _invented_temporal(facts, request, caption)
    reasons += _invented_numbers(draft, caption)
    reasons += _invented_names(draft, caption)
    reasons += _booking_claims(text, _normalise(caption))
    reasons += _meta_text(draft)
    return reasons
