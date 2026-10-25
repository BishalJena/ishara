from __future__ import annotations

import re
from itertools import combinations

import pytest

from app.protocol import ASL_SIGNS, MAX_SPOKEN_CHARS, TEMPLATE_SIGNS, Sign
from app.templates import compose_template

PURPOSE = "doctor_appointment"
# Every combination of the twelve template signs; the ASL glosses are appended plainly and
# are covered one at a time and paired with each template sign.
ALL_CHIP_SETS = [
    list(c) for n in range(1, len(TEMPLATE_SIGNS) + 1) for c in combinations(TEMPLATE_SIGNS, n)
]
ASL_CHIP_SETS = [[sign] for sign in ASL_SIGNS] + [
    [core, sign] for sign in ASL_SIGNS for core in TEMPLATE_SIGNS
]


def t(*chips: Sign) -> str:
    return compose_template(list(chips), PURPOSE)


@pytest.mark.parametrize(
    ("chips", "expected"),
    [
        (["hello", "doctor", "tomorrow"], "Hello, I'd like a doctor's appointment tomorrow."),
        (["no", "morning"], "No, sorry, that doesn't work. Is there anything in the morning?"),
        (["yes", "thankyou"], "Yes, that works. Thank you."),
    ],
    ids=["T1", "T3", "T5"],
)
def test_script_turns(chips: list[Sign], expected: str) -> None:
    assert compose_template(chips, PURPOSE) == expected


@pytest.mark.parametrize(
    ("sign", "expected"),
    [
        ("hello", "Hello."),
        ("thankyou", "Thank you."),
        ("yes", "Yes, that works."),
        ("no", "No, sorry, that doesn't work."),
        ("sorry", "Sorry."),
        ("doctor", "I'd like a doctor's appointment."),
        ("today", "Is there an appointment today?"),
        ("tomorrow", "Is there an appointment tomorrow?"),
        ("morning", "Is there an appointment in the morning?"),
        ("afternoon", "Is there an appointment in the afternoon?"),
        ("evening", "Is there an appointment in the evening?"),
        ("time", "What time is available?"),
    ],
)
def test_every_sign_alone(sign: Sign, expected: str) -> None:
    assert t(sign) == expected


@pytest.mark.parametrize(
    ("chips", "expected"),
    [
        (["yes", "tomorrow", "morning"], "Yes, tomorrow morning works."),
        (["yes", "evening"], "Yes, the evening works."),
        (["today", "morning", "afternoon"], "Is there an appointment this morning or afternoon?"),
        (["doctor", "today", "evening"], "I'd like a doctor's appointment this evening."),
        (["time", "tomorrow"], "What time is available tomorrow?"),
        (
            ["doctor", "time", "tomorrow"],
            "I'd like a doctor's appointment tomorrow. What time is available?",
        ),
        (["yes", "doctor"], "Yes. I'd like a doctor's appointment."),
        (["no", "time"], "No, sorry, that doesn't work. What time is available?"),
        (["hello", "yes"], "Hello, yes, that works."),
        (["hello", "sorry"], "Hello, sorry."),
        (["sorry", "yes"], "Sorry, yes, that works."),
        (["sorry", "doctor"], "Sorry, I'd like a doctor's appointment."),
        (["thankyou", "hello"], "Hello. Thank you."),
    ],
)
def test_combinations(chips: list[Sign], expected: str) -> None:
    assert compose_template(chips, PURPOSE) == expected


def test_sorry_with_no_is_not_said_twice() -> None:
    assert t("sorry", "no") == t("no")
    assert t("sorry", "no").count("sorry") == 1


def test_conflicting_days_are_both_said_never_one_picked() -> None:
    text = t("today", "tomorrow", "morning")
    assert "today" in text and "tomorrow" in text


def test_conflicting_answers_are_both_said() -> None:
    assert t("yes", "no") == "Yes and no."
    assert t("yes", "no", "morning") == "Yes and no. Is there an appointment in the morning?"


def test_duplicates_and_order_do_not_change_the_sentence() -> None:
    assert t("no", "no", "morning", "no") == t("no", "morning")
    assert t("tomorrow", "doctor", "hello") == t("hello", "doctor", "tomorrow")


def test_thank_you_always_comes_last() -> None:
    expected = "No, sorry, that doesn't work. Is there anything in the morning? Thank you."
    assert t("thankyou", "no", "morning") == expected


def test_every_chip_set_gives_a_short_clean_sentence() -> None:
    for chips in ALL_CHIP_SETS:
        text = compose_template(chips, PURPOSE)
        assert not re.search(r"\d", text), chips
        assert len(text.split()) <= 25, chips
        assert len(text) <= MAX_SPOKEN_CHARS, chips
        assert text[0].isupper() and text[-1] in ".?", chips
        assert "  " not in text, chips


def test_empty_chips_fail_fast() -> None:
    with pytest.raises(ValueError):
        compose_template([], PURPOSE)


def test_unknown_sign_fails_fast() -> None:
    with pytest.raises(ValueError, match="unknown"):
        compose_template(["hello", "pizza"], PURPOSE)


def test_unknown_purpose_fails_fast() -> None:
    with pytest.raises(KeyError):
        compose_template(["hello"], "taxi")
