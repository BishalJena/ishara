from __future__ import annotations

from itertools import combinations

import pytest

from app.protocol import (
    ASL_SIGNS,
    MAX_CHIPS,
    MAX_SPOKEN_CHARS,
    TEMPLATE_SIGNS,
    ComposeRequest,
    Sign,
)
from app.templates import compose_template
from app.validator import MAX_WORDS, validate

T3_CAPTION = "We have 4 pm tomorrow. Does that work?"
T5_CAPTION = "Yes, 10:30 tomorrow morning."


def check(draft: str, chips: list[Sign], caption: str | None = None) -> list[str]:
    request = ComposeRequest(
        turn_id="t1", chips=chips, purpose="doctor_appointment", last_caption=caption
    )
    return validate(draft, request)


# ---- accepted drafts ----


@pytest.mark.parametrize(
    ("chips", "caption", "draft"),
    [
        (["hello", "doctor", "tomorrow"], None, "Hello, I'd like a doctor's appointment tomorrow."),
        (
            ["no", "morning"],
            T3_CAPTION,
            "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?",
        ),
        (["yes", "thankyou"], T5_CAPTION, "Yes, 10:30 tomorrow morning works. Thank you."),
    ],
    ids=["T1", "T3", "T5"],
)
def test_plan_script_wording_is_accepted(chips: list[Sign], caption: str, draft: str) -> None:
    assert check(draft, chips, caption) == []


def test_every_template_passes_the_validator() -> None:
    chip_sets = [list(c) for n in range(1, MAX_CHIPS + 1) for c in combinations(TEMPLATE_SIGNS, n)]
    chip_sets += [[sign] for sign in ASL_SIGNS]
    chip_sets += [[core, sign] for sign in ASL_SIGNS for core in TEMPLATE_SIGNS]
    chip_sets += [[a, b] for a in ASL_SIGNS for b in ASL_SIGNS if a < b]
    chip_sets += [
        ["hello", "sick", "tomorrow"],
        ["no", "please"],
        ["yes", "thankyou", "please"],
        ["now", "please"],
        ["wait"],
        ["tomorrow", "please", "morning"],
    ]
    for chips in chip_sets:
        draft = compose_template(chips, "doctor_appointment")
        assert check(draft, chips) == [], (chips, draft)


# ---- size ----


def test_empty_or_blank_draft_is_rejected() -> None:
    assert check("", ["hello"]) == ["empty draft"]
    assert check("  \n ", ["hello"]) == ["empty draft"]


def test_character_limit_is_inclusive() -> None:
    at_limit = "Hello " + "a" * (MAX_SPOKEN_CHARS - 6)
    assert len(at_limit) == MAX_SPOKEN_CHARS
    assert check(at_limit, ["hello"]) == []
    assert check(at_limit + "a", ["hello"]) == [f"too long: {MAX_SPOKEN_CHARS + 1} characters"]


def test_word_limit_is_25() -> None:
    at_limit = "Hello" + " please" * (MAX_WORDS - 1)
    assert MAX_WORDS == 25
    assert check(at_limit, ["hello"]) == []
    assert check(at_limit + " please", ["hello"]) == ["too many words: 26"]


# ---- chip meanings ----


@pytest.mark.parametrize("sign", TEMPLATE_SIGNS)
def test_each_missing_chip_meaning_is_reported(sign: Sign) -> None:
    assert check("Please hold.", [sign]) == [f"missing meaning: {sign}"]


@pytest.mark.parametrize("sign", ASL_SIGNS)
def test_each_missing_asl_gloss_meaning_is_reported(sign: Sign) -> None:
    assert check("Alright then.", [sign]) == [f"missing meaning: {sign}"]


@pytest.mark.parametrize(
    ("sign", "draft"),
    [
        ("please", "Please."),
        ("wait", "A moment."),
        ("now", "Is today free?"),
        ("now", "Right now?"),
        ("night", "At night?"),
        ("yesterday", "Yesterday."),
        ("later", "Maybe later."),
        ("sick", "I'm feeling sick."),
        ("callonphone", "Please call me."),
        ("finish", "That's all."),
    ],
)
def test_asl_gloss_synonyms(sign: Sign, draft: str) -> None:
    assert check(draft, [sign]) == []


@pytest.mark.parametrize(
    "draft",
    ["Thank you, that works perfectly for me.", "Thanks, sounds good.", "Thank you, perfect."],
)
def test_issue_34_bare_thankyou_must_not_accept(draft: str) -> None:
    assert check(draft, ["thankyou"]) == ["adds agreement the user did not sign"]


def test_now_without_chip_is_an_invented_day() -> None:
    assert "invented day: today" in check("Hello, can you do it now?", ["hello", "can"])


def test_missing_no_in_script_turn_three() -> None:
    draft = "Sorry, 4 pm is hard. Is there anything tomorrow morning?"
    assert check(draft, ["no", "morning"], T3_CAPTION) == ["missing meaning: no"]


def test_missing_meanings_are_reported_once_per_sign() -> None:
    assert check("Please hold.", ["doctor", "doctor"]) == ["missing meaning: doctor"]


@pytest.mark.parametrize(
    ("sign", "draft"),
    [
        ("hello", "Hello."),
        ("hello", "Hi."),
        ("hello", "Hey."),
        ("thankyou", "Thank you."),
        ("thankyou", "Thanks."),
        ("yes", "Yes."),
        ("yes", "Yeah."),
        ("yes", "Yep."),
        ("yes", "Okay."),
        ("yes", "OK."),
        ("yes", "Fine."),
        ("yes", "That works."),
        ("no", "No."),
        ("no", "That is not good."),
        ("no", "That doesn't work."),
        ("no", "That doesn’t work."),
        ("no", "I cannot."),
        ("sorry", "Sorry."),
        ("sorry", "Apologies."),
        ("sorry", "I apologise."),
        ("sorry", "I apologize."),
        ("sorry", "Excuse me."),
        ("doctor", "A doctor, please."),
        ("doctor", "Any doctors?"),
        ("doctor", "The doctor's room."),
        ("doctor", "Dr, please."),
        ("time", "What time?"),
        ("time", "Any times?"),
        ("time", "Any slot?"),
        ("time", "Any slots?"),
        ("time", "When?"),
        ("today", "Is today free?"),
        ("tomorrow", "Is tomorrow free?"),
        ("morning", "In the morning?"),
        ("afternoon", "In the afternoon?"),
        ("evening", "In the evening?"),
    ],
)
def test_each_synonym_satisfies_its_sign(sign: Sign, draft: str) -> None:
    assert check(draft, [sign]) == []


@pytest.mark.parametrize(
    ("chips", "draft"),
    [
        (["today", "morning"], "Anything this morning?"),
        (["today", "evening"], "Anything tonight?"),
    ],
)
def test_combined_day_phrases_satisfy_both_signs(chips: list[Sign], draft: str) -> None:
    assert check(draft, chips) == []


def test_work_without_s_is_not_agreement() -> None:
    assert check("Does that work?", ["yes"]) == ["missing meaning: yes"]


# ---- flipped answers ----


@pytest.mark.parametrize("draft", ["Hello, no.", "Hello, I can't.", "Hello, not today."])
def test_refusal_without_no_chip_is_rejected(draft: str) -> None:
    assert "adds a refusal the user did not sign" in check(draft, ["hello", "today"])


@pytest.mark.parametrize("draft", ["Hello, yes.", "Hello, yeah.", "Hello, yep."])
def test_agreement_without_yes_chip_is_rejected(draft: str) -> None:
    assert check(draft, ["hello"]) == ["adds agreement the user did not sign"]


def test_yes_chip_with_negated_draft_is_rejected() -> None:
    assert check("Yes, that doesn't work.", ["yes"]) == ["adds a refusal the user did not sign"]


# ---- invented days and times of day ----


@pytest.mark.parametrize(
    ("phrase", "reasons"),
    [
        ("on Monday", ["invented day: monday", "invented name: Monday"]),
        ("on fridays", ["invented day: friday"]),
        ("today", ["invented day: today"]),
        ("yesterday", ["invented day: yesterday"]),
        ("next week", ["invented day: week"]),
        ("this weekend", ["invented day: weekend"]),
        ("next month", ["invented day: month"]),
        ("in march", ["invented day: march"]),
        ("in may", ["invented day: may"]),
        ("the day after tomorrow", ["invented day: day after tomorrow"]),
    ],
)
def test_invented_day_is_rejected(phrase: str, reasons: list[str]) -> None:
    draft = f"No, sorry, 4 pm doesn't work. Is there anything {phrase} in the morning?"
    assert check(draft, ["no", "morning"], T3_CAPTION) == reasons


def test_day_after_tomorrow_does_not_count_as_tomorrow() -> None:
    assert check("Anything the day after tomorrow?", ["tomorrow"]) == [
        "missing meaning: tomorrow",
        "invented day: day after tomorrow",
    ]


def test_may_as_a_verb_is_not_a_month() -> None:
    assert check("May I come in the morning?", ["morning"]) == []


def test_this_morning_implies_today() -> None:
    assert check("Anything this morning?", ["morning"]) == ["invented day: today"]


def test_tonight_implies_today_and_evening() -> None:
    assert check("Anything tonight?", ["time"]) == [
        "missing meaning: time",
        "invented day: today",
        "invented time of day: evening",
    ]


def test_invented_time_of_day_is_rejected() -> None:
    draft = "No, sorry. Is there anything in the morning or afternoon?"
    assert check(draft, ["no", "morning"]) == ["invented time of day: afternoon"]


def test_day_and_time_of_day_from_the_caption_are_allowed() -> None:
    caption = "We have Monday afternoon."
    assert check("Yes, Monday afternoon works.", ["yes"], caption) == []
    assert check("Yes, Monday afternoon works.", ["yes"]) == [
        "invented day: monday",
        "invented time of day: afternoon",
        "invented name: Monday",
    ]


# ---- invented numbers and clock times ----


@pytest.mark.parametrize(
    ("time", "invented"),
    [
        ("at 4 pm", ["4", "pm"]),
        ("at 4pm", ["4", "pm"]),
        ("at 10:30", ["10:30"]),
        ("at 10.30", ["10:30"]),
        ("at 10 a.m.", ["10", "am"]),
        ("at noon", ["noon"]),
        ("at midnight", ["midnight"]),
        ("at five", ["five"]),
        ("at twenty-five past", ["twenty", "five"]),
        ("at half past two", ["half", "two"]),
        ("at one o'clock", ["one", "o'clock"]),
        ("first", ["first"]),
    ],
)
def test_invented_number_or_time_is_rejected(time: str, invented: list[str]) -> None:
    reasons = check(f"Is there anything {time} in the morning?", ["morning"])
    assert reasons == [f"invented number or time: {token}" for token in invented]


def test_numbers_from_the_caption_are_allowed_but_others_are_not() -> None:
    draft = "No, sorry, 5 pm doesn't work. Is there anything tomorrow morning?"
    assert check(draft, ["no", "morning"], T3_CAPTION) == ["invented number or time: 5"]


def test_caption_time_matches_across_formats() -> None:
    assert check("Yes, 10:30 works.", ["yes"], "We have 10.30.") == []


def test_i_am_is_not_a_clock_time() -> None:
    assert check("Hello, I am here.", ["hello"]) == []


# ---- invented names ----


def test_invented_name_after_title_is_rejected() -> None:
    draft = "I'd like a doctor's appointment with Dr. Sharma."
    assert check(draft, ["doctor"]) == ["invented name: Sharma"]


def test_titles_and_names_mid_sentence_are_rejected() -> None:
    assert check("Hello, is Mr Shah there?", ["hello"]) == [
        "invented name: Mr",
        "invented name: Shah",
    ]


def test_name_from_the_caption_is_allowed() -> None:
    assert check("Yes, Mehta works.", ["yes"], "doctor mehta is free at that time") == []


def test_sentence_starts_and_allowlisted_words_are_not_names() -> None:
    assert check("Yes. Hello, OK, I'd like the Doctor.", ["yes", "hello", "doctor"]) == []


# ---- booking claims ----


@pytest.mark.parametrize(
    "claim", ["booked", "confirmed", "reserved", "scheduled", "all set", "is set"]
)
def test_booking_claim_is_rejected(claim: str) -> None:
    assert check(f"Yes, the appointment {claim}.", ["yes"]) == [f"booking claim: {claim}"]


def test_booking_word_said_by_receptionist_is_allowed() -> None:
    assert check("Yes, booked. Thank you.", ["yes", "thankyou"], "You're booked.") == []


def test_asking_to_book_is_not_a_claim() -> None:
    assert check("I'd like to book a doctor.", ["doctor"]) == []


# ---- meta text ----


@pytest.mark.parametrize(
    ("draft", "label"),
    [
        ('"No, sorry."', "quotes, markdown or line breaks"),
        ("“No, sorry.”", "quotes, markdown or line breaks"),
        ("**No**, sorry.", "quotes, markdown or line breaks"),
        ("# No, sorry.", "quotes, markdown or line breaks"),
        ("`No`, sorry.", "quotes, markdown or line breaks"),
        ("No, sorry.\nGoodbye.", "quotes, markdown or line breaks"),
        ("'No, sorry.'", "wrapped in quotes"),
        ("Reply: no, sorry.", "a label or colon"),
        ("- No, sorry.", "a list item"),
        ("Sure, here's my answer. No.", "commentary"),
        ("Here is the sentence. No.", "commentary"),
        ("Certainly. No.", "commentary"),
        ("No, as an AI.", "commentary"),
    ],
)
def test_meta_text_is_rejected(draft: str, label: str) -> None:
    assert f"meta text: {label}" in check(draft, ["no"])


# ---- typography the LLM may use ----


def test_curly_apostrophes_do_not_look_like_names() -> None:
    draft = "Hello, I’d like a doctor’s appointment tomorrow."
    assert check(draft, ["hello", "doctor", "tomorrow"]) == []


@pytest.mark.parametrize("apostrophe", ["’", "‘"])
def test_curly_apostrophes_cannot_hide_a_refusal(apostrophe: str) -> None:
    draft = f"Yes, that doesn{apostrophe}t work."
    assert "adds a refusal the user did not sign" in check(draft, ["yes"], T3_CAPTION)


def test_dotted_am_cannot_flip_a_heard_pm() -> None:
    reasons = check("Yes, 4 a.m. tomorrow works.", ["yes"], T3_CAPTION)
    assert reasons == ["invented number or time: am"]


def test_am_as_a_verb_at_the_start_is_not_a_time() -> None:
    assert check("Am I able to see the doctor tomorrow?", ["doctor", "tomorrow"]) == []


@pytest.mark.parametrize(
    ("draft", "reason"),
    [
        ("No, sorry. Is there anything the week after?", "invented day: week"),
        ("No, sorry. Do you have any free mornings?", "invented time of day: morning"),
        ("No, sorry. Are evenings possible?", "invented time of day: evening"),
    ],
)
def test_bare_and_plural_spans_count_as_invented_facts(draft: str, reason: str) -> None:
    assert check(draft, ["no", "sorry"]) == [reason]
