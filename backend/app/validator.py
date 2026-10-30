"""Checks an LLM draft against the chips and the receptionist's last words.

PLAN §4: reject a draft that misses a chip's meaning, adds a day, time, number or
name that neither the user signed nor the receptionist said, or runs past 25
words. `validate` returns the reasons; an empty list means the draft may be shown.
Only LLM drafts go through it at runtime. Template sentences meet every other rule
(tests/test_template_properties.py) but are exempt from the 25-word limit (issue #62):
they are deterministic, the user reads them before SEND, and with many plain-phrase
signs they run longer.
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
    # ASL glosses (D8). "now" is temporal (today); "night" and "yesterday" are facts below.
    "please": re.compile(r"\bplease\b"),
    "wait": re.compile(r"\b(wait|hold on|hold|one moment|a moment|moment|minute)\b"),
    "later": re.compile(r"\b(later|afterwards|another time)\b"),
    "can": re.compile(r"\b(can|could|able)\b"),
    "where": re.compile(r"\b(where|address|location)\b"),
    "who": re.compile(r"\b(who|whom)\b"),
    "why": re.compile(r"\b(why|reason)\b"),
    "have": re.compile(r"\b(have|has|had|got)\b"),
    "finish": re.compile(r"\b(finish|finished|done|complete|completed|that's all)\b"),
    "callonphone": re.compile(r"\b(call|phone|ring)\b"),
    "sick": re.compile(r"\b(sick|unwell|ill|not feeling well|not well)\b"),
    "hungry": re.compile(r"\b(hungry|eat|food)\b"),
    "drink": re.compile(r"\b(drink|drinks)\b"),
    "water": re.compile(r"\bwater\b"),
    "home": re.compile(r"\b(home|house)\b"),
    "go": re.compile(r"\b(go|going|leave|come)\b"),
    "see": re.compile(r"\b(see|visit|meet)\b"),
    "hear": re.compile(r"\b(hear|heard|hearing)\b"),
    "read": re.compile(r"\b(read|reading)\b"),
}
# Polarity words that flip the user's answer; they need the matching chip. Agreement also
# covers "that works", "sounds good", "perfect" (issue #34: a bare thankyou must not accept).
_REFUSAL = _MEANINGS["no"]
_AGREEMENT = re.compile(
    r"\b(yes|yeah|yep|sure|perfect|perfectly|agreed)\b"
    r"|\b(that|this|it|which) (works|is fine|is good|is great|is perfect|suits me|sounds good)\b"
    r"|\bworks (perfectly |well )?for me\b|\bsounds (good|great|perfect)\b"
)

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
    rows += [("(?:right )?now", ("day:today",))]
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
    "now": "day:today",
    "tomorrow": "day:tomorrow",
    "yesterday": "day:yesterday",
    "morning": "part:morning",
    "afternoon": "part:afternoon",
    "evening": "part:evening",
    "night": "part:night",
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


_HOUR_WORDS = {
    word: str(hour)
    for hour, word in enumerate(
        ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")
        + ("eleven", "twelve"),
        start=1,
    )
}
_MINUTE_WORDS = {"fifteen": "15", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50"}
_MINUTE_WORDS |= {"forty five": "45", "forty-five": "45"}
_HOUR = "|".join(_HOUR_WORDS)
_MINUTE = "|".join(sorted(_MINUTE_WORDS, key=len, reverse=True))
_WORD_CLOCK = re.compile(rf"\b({_HOUR})[ -]({_MINUTE})\b")
_WORD_HOUR_AM_PM = re.compile(rf"\b({_HOUR})(?= ?[ap]m\b)")


def _normalise(text: str) -> str:
    """Lower case, straight apostrophes, 'a.m.' -> 'am', '10.30' -> '10:30', and clock
    times in words as digits ('four pm' -> '4 pm', 'ten thirty' -> '10:30'), because the
    call transcriber writes spoken times in words."""
    text = text.lower().replace("’", "'").replace("‘", "'")
    text = re.sub(r"\b([ap])\.m\.?", r"\1m", text)
    text = _WORD_CLOCK.sub(lambda m: f"{_HOUR_WORDS[m[1]]}:{_MINUTE_WORDS[m[2]]}", text)
    text = _WORD_HOUR_AM_PM.sub(lambda m: _HOUR_WORDS[m[1]], text)
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


def validate_polish(candidate: str, typed: str, last_caption: str | None) -> list[str]:
    """Reasons a polished rewording of `typed` must not be spoken: it may reuse the
    user's own facts and the receptionist's last words, but add none of its own, flip
    no answer, claim no booking and carry no meta text."""
    text = candidate.strip()
    if not text:
        return ["empty"]
    reasons: list[str] = []
    if len(text) > MAX_SPOKEN_CHARS:
        reasons.append(f"too long: {len(text)} characters")
    if len(text.split()) > MAX_WORDS:
        reasons.append(f"too many words: {len(text.split())}")
    known = f"{typed} {last_caption or ''}"
    normalised, typed_normalised = _normalise(text), _normalise(typed)
    if _REFUSAL.search(normalised) and not _REFUSAL.search(typed_normalised):
        reasons.append("adds a refusal the user did not type")
    if _AGREEMENT.search(normalised) and not _AGREEMENT.search(typed_normalised):
        reasons.append("adds agreement the user did not type")
    for fact in sorted(temporal_facts(text) - temporal_facts(known)):
        kind, value = fact.split(":", 1)
        reasons.append(f"invented {'day' if kind == 'day' else 'time of day'}: {value}")
    reasons += _invented_numbers(text, known)
    reasons += _invented_names(text, known)
    reasons += _booking_claims(normalised, _normalise(known))
    reasons += _meta_text(text)
    return reasons


def tidy(typed: str) -> str:
    """The typed line as spoken when no LLM polishes it: trimmed, one space between
    words, a capital to start and a full stop to end."""
    text = " ".join(typed.split())
    if not text:
        return text
    text = text[0].upper() + text[1:]
    return text if text.endswith((".", "!", "?")) else text + "."


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
