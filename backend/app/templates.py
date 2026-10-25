"""Deterministic fallback sentences for a chip list (decision D4).

Ported in spirit from spikes/recognition/sentence.py. The output depends only on
which signs are present (duplicates and order don't matter) and the purpose. A
template never contains a day, time, number or name the chips don't carry; when
chips conflict (yes + no, today + tomorrow) both are said literally so the user
sees the conflict and removes a chip before SEND.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.protocol import SIGNS, Purpose, Sign

_DAYS: tuple[Sign, ...] = ("today", "tomorrow")
_PARTS: tuple[Sign, ...] = ("morning", "afternoon", "evening", "night")
# ASL glosses (D8) the full template logic does not model: said plainly, after the main
# sentence, in this order. None carries a day, time, number or name.
_ALIASES: dict[Sign, Sign] = {"now": "today"}
_PLAIN: dict[Sign, str] = {
    "please": "Please.",
    "wait": "A moment, please.",
    "yesterday": "Yesterday.",
    "later": "Maybe later.",
    "can": "Can you help me with that?",
    "where": "Where is it?",
    "who": "Who should I ask for?",
    "why": "Why is that?",
    "have": "Do you have that?",
    "finish": "That's all from me.",
    "callonphone": "Please call me on the phone.",
    "sick": "I'm feeling sick.",
    "hungry": "I'm hungry.",
    "drink": "I'd like a drink.",
    "water": "Some water, please.",
    "home": "At home.",
    "go": "I need to go.",
    "see": "I'd like to see them.",
    "hear": "I hear you.",
    "read": "I'll read it.",
}
_APPOINTMENT: dict[Purpose, str] = {"doctor_appointment": "a doctor's appointment"}
_DECLINE = "No, sorry, that doesn't work."  # already apologises, so a "sorry" chip adds nothing


def _either(words: Sequence[str]) -> str:
    """ "a", "a or b", "a, b or c"."""
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} or {words[-1]}"


def _when(signs: set[Sign], *, as_subject: bool) -> str | None:
    """Days and parts of day as one phrase: 'tomorrow morning', 'this afternoon',
    'in the evening' (or 'the evening' as a sentence subject)."""
    days = [d for d in _DAYS if d in signs]
    parts = [p for p in _PARTS if p in signs]
    if not days and not parts:
        return None
    if not parts:
        return _either(days)
    if not days:
        return f"{'the' if as_subject else 'in the'} {_either(parts)}"
    if days == ["today"]:
        return f"this {_either(parts)}"
    return f"{_either(days)} {_either(parts)}"


def _join_prefix(prefix: str, sentence: str) -> str:
    """'Hello' + 'Yes, that works.' -> 'Hello, yes, that works.' ('I' stays capital)."""
    if not sentence.startswith(("I ", "I'")):
        sentence = sentence[0].lower() + sentence[1:]
    return f"{prefix}, {sentence}"


def compose_template(chips: Sequence[Sign], purpose: Purpose) -> str:
    if not chips:
        raise ValueError("compose_template needs at least one chip")
    unknown = set(chips) - set(SIGNS)
    if unknown:
        raise ValueError(f"unknown signs: {sorted(unknown)}")
    signs: set[Sign] = {_ALIASES.get(c, c) for c in chips}
    appointment = _APPOINTMENT[purpose]
    when = _when(signs, as_subject=False)
    only_yes = "yes" in signs and "no" not in signs
    only_no = "no" in signs and "yes" not in signs

    request: list[str] = []
    if "doctor" in signs:
        request.append(f"I'd like {appointment}{f' {when}' if when else ''}.")
        if "time" in signs:
            request.append("What time is available?")
    elif "time" in signs:
        request.append(f"What time is available{f' {when}' if when else ''}?")
    elif when and not only_yes:  # a lone "yes" folds the day into "Yes, tomorrow works."
        request.append(f"Is there {'anything' if only_no else 'an appointment'} {when}?")

    lead: str | None = None
    prefix = [word for word in ("hello", "sorry") if word in signs]
    if only_no:
        lead = _DECLINE
        if "sorry" in prefix:
            prefix.remove("sorry")
    elif only_yes:
        if request:
            lead = "Yes."
        elif when:
            lead = f"Yes, {_when(signs, as_subject=True)} works."
        else:
            lead = "Yes, that works."
    elif "yes" in signs:
        lead = "Yes and no."

    body = ([lead] if lead else []) + request
    if prefix:
        opener = ", ".join(prefix).capitalize()
        body = [_join_prefix(opener, body[0]), *body[1:]] if body else [f"{opener}."]
    if "thankyou" in signs:
        body.append("Thank you.")
    body += [_PLAIN[sign] for sign in SIGNS if sign in signs and sign in _PLAIN]
    return " ".join(body)
