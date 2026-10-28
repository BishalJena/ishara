"""Decision D9, version B: an open time question goes to the attended user.

When the receptionist asks *when* ("What time would you like?", "Morning or afternoon?")
without offering a time, the attended agent says "One moment, please." and the app asks
the user, who signs or taps one of the time words; the agent then says that word's fixed
sentence. Unattended calls answer from the brief's preferred time, or promise a callback.
Nothing here dials or reaches Groq.
"""

from __future__ import annotations

import contextlib
import json
from functools import partial

import pytest

from app.delegate import (
    CALLBACK_LINE,
    PAUSE_LINE,
    SYSTEM_PROMPT,
    Brain,
    Decision,
    DelegateState,
    Exchange,
    RuleBrain,
    brief_from,
    build_brief,
    build_notes,
)
from app.markers import EVENT_END_CALL
from app.protocol import BriefRequest, TranscriptEntry
from tests.test_delegate import AUTH, PROFILE, build_flow, make_brief
from tests.test_delegate_attacks import FakeGroq, llm, opened_call, quiet, wait_for

WAIT_LINE = "One moment, please, I'm checking."
# The time words the recognizer can chip, in the card's order, with the exact sentence
# the agent says for each.
TIME_SENTENCES = {
    "tomorrow": "Tomorrow, please. What times are available?",
    "morning": "In the morning, please. What times are available?",
    "now": "Today, as soon as possible, please. What times are available?",
}
TIME_CHOICES = [*TIME_SENTENCES, "wait"]

OPEN_QUESTIONS = [
    "What time would you like?",
    "When would you like to come in?",
    "Morning or afternoon?",
    "Do you prefer mornings or afternoons?",
    "Which day works for you?",
    "What day works best?",
    "When can she come in?",
    "And what time tomorrow?",
    "Sure. Do you have a preferred time?",
    # The live transcriber: lowercase, no punctuation.
    "what time would you like to come in",
    "when would you like to come in",
    "morning or afternoon",
]

LIVE_QUESTION = "what time would you like to come in"


def state(attended: bool = True, chips: tuple[str, ...] = ("tomorrow", "morning")) -> DelegateState:
    """An opened call whose brief carries these time chips (the default: tomorrow morning)."""
    request = BriefRequest(purpose="doctor_appointment", chips=list(chips), profile=PROFILE)
    delegate = DelegateState(brief_from(request, build_brief(request)), attended=attended)
    delegate.opened = True
    return delegate


def options_of(decision: Decision) -> dict[str, str]:
    assert decision.ask is not None, decision
    return {o.choice: o.spoken for o in decision.ask[1]}


# ---- the rule brain ----


@pytest.mark.parametrize("heard", OPEN_QUESTIONS)
def test_an_open_time_question_asks_the_attended_user_for_a_time_word(heard: str) -> None:
    decision = RuleBrain().decide(state(), heard)
    assert decision.say == PAUSE_LINE
    assert decision.ask is not None and decision.ask[0] == heard.strip()
    assert list(options_of(decision)) == TIME_CHOICES
    assert options_of(decision) == {**TIME_SENTENCES, "wait": WAIT_LINE}
    assert not decision.done and not decision.callback


@pytest.mark.parametrize(
    ("heard", "yes_line"),
    [
        # A concrete time wins over the open question around it.
        (
            "what time would you like we have four pm tomorrow",
            "Yes, 4 pm tomorrow works. Thank you.",
        ),
        ("We have 4 pm tomorrow. Does that work?", "Yes, 4 pm tomorrow works. Thank you."),
        ("Would Monday or Tuesday suit?", "Yes, that works. Thank you."),
        ("Could you come on Friday instead?", "Yes, Friday works. Thank you."),
    ],
)
def test_a_concrete_offer_still_gets_yes_no_wait(heard: str, yes_line: str) -> None:
    decision = RuleBrain().decide(state(), heard)
    assert list(options_of(decision)) == ["yes", "no", "wait"]
    assert options_of(decision)["yes"] == yes_line


@pytest.mark.parametrize(
    "heard",
    [
        "How can I help you today?",
        "When did the cough start?",
        "Sorry, what was that?",
    ],
)
def test_questions_that_are_not_about_when_ask_nothing(heard: str) -> None:
    assert RuleBrain().decide(state(), heard).ask is None


@pytest.mark.parametrize(
    ("chips", "line"),
    [
        (("tomorrow", "morning"), "Tomorrow in the morning, please. What times are available?"),
        (("tomorrow",), "Tomorrow, please. What times are available?"),
        (("now",), "Today, please. What times are available?"),
    ],
)
def test_unattended_answers_an_open_question_from_the_brief(chips, line) -> None:
    decision = RuleBrain().decide(state(attended=False, chips=chips), LIVE_QUESTION)
    assert decision == Decision(line)


def test_unattended_without_a_preferred_time_promises_a_callback() -> None:
    decision = RuleBrain().decide(state(attended=False, chips=()), LIVE_QUESTION)
    assert decision == Decision(CALLBACK_LINE, done=True, callback=True)


def test_unattended_never_repeats_the_brief_time_in_a_loop() -> None:
    delegate = state(attended=False, chips=("tomorrow",))
    first = RuleBrain().decide(delegate, LIVE_QUESTION)
    delegate.exchanges.append(Exchange(LIVE_QUESTION, first.say))
    again = RuleBrain().decide(delegate, "sorry what time would you like")
    assert again == Decision(CALLBACK_LINE, done=True, callback=True)


def test_no_time_sentence_reads_as_a_yes_or_a_no_in_the_notes() -> None:
    # outcome_of reads "Yes..." as accepted and "No..." as declined.
    for sentence in TIME_SENTENCES.values():
        assert not sentence.startswith(("Yes", "No"))


# ---- the LLM brain ----


async def test_an_llm_time_ask_gives_the_time_options() -> None:
    raw = llm(PAUSE_LINE, {"kind": "time"})
    decision = await Brain(FakeGroq(raw)).reply(state(), LIVE_QUESTION)
    assert decision.source == "llm" and decision.say == PAUSE_LINE
    assert decision.ask is not None and decision.ask[0] == LIVE_QUESTION
    assert options_of(decision) == {**TIME_SENTENCES, "wait": WAIT_LINE}


async def test_an_llm_time_ask_over_a_concrete_offer_uses_the_rule_yes_no() -> None:
    raw = llm(PAUSE_LINE, {"kind": "time"})
    decision = await Brain(FakeGroq(raw)).reply(state(), "we have four pm tomorrow does that work")
    assert decision.source == "rules"
    assert options_of(decision)["yes"] == "Yes, 4 pm tomorrow works. Thank you."


@pytest.mark.parametrize(
    "ask",
    [
        {"kind": "time", "proposal": "4 pm tomorrow"},  # a time ask carries no proposal
        {"kind": "date"},
        {"kind": None},
    ],
)
async def test_a_malformed_llm_time_ask_falls_back_to_the_rules(ask: dict) -> None:
    decision = await Brain(FakeGroq(llm(PAUSE_LINE, ask))).reply(state(), LIVE_QUESTION)
    assert decision.source == "rules"
    assert options_of(decision) == {**TIME_SENTENCES, "wait": WAIT_LINE}


async def test_an_llm_offer_ask_still_reads_the_proposal() -> None:
    raw = llm(PAUSE_LINE, {"kind": "offer", "proposal": "4 pm tomorrow"})
    decision = await Brain(FakeGroq(raw)).reply(state(), "We have 4 pm tomorrow. Does that work?")
    assert decision.source == "llm"
    assert options_of(decision)["yes"] == "Yes, 4 pm tomorrow works. Thank you."


async def test_an_unattended_llm_time_ask_answers_from_the_brief() -> None:
    raw = llm(PAUSE_LINE, {"kind": "time"})
    decision = await Brain(FakeGroq(raw)).reply(state(attended=False), LIVE_QUESTION)
    assert decision.ask is None and decision.source == "llm"
    assert decision.say == "Tomorrow in the morning, please. What times are available?"
    assert not decision.done


async def test_an_unattended_llm_time_ask_without_a_preference_promises_a_callback() -> None:
    raw = llm(PAUSE_LINE, {"kind": "time"})
    decision = await Brain(FakeGroq(raw)).reply(state(attended=False, chips=()), LIVE_QUESTION)
    assert decision.say == CALLBACK_LINE and decision.done and decision.callback


def test_the_prompt_tells_the_llm_how_to_hand_over_an_open_question() -> None:
    assert '"kind": "time"' in SYSTEM_PROMPT


async def test_the_users_answer_counts_as_a_known_fact_for_later_llm_lines() -> None:
    delegate = state(chips=())
    delegate.answers.append(TIME_SENTENCES["morning"])
    line = "Could you tell me which mornings are free?"
    decision = await Brain(FakeGroq(llm(line))).reply(delegate, "Let me look at the diary.")
    assert decision.source == "llm" and decision.say == line
    # Nobody said "evening": still rejected.
    evening = "Could you tell me which evenings are free?"
    decision = await Brain(FakeGroq(llm(evening))).reply(delegate, "Let me look at the diary.")
    assert decision.source == "rules"


# ---- notes ----


def test_a_time_answer_is_listed_and_settles_nothing() -> None:
    brief = make_brief().brief
    entries = [
        TranscriptEntry(speaker="receptionist", text=LIVE_QUESTION, at=1.0),
        TranscriptEntry(speaker="agent", text=TIME_SENTENCES["tomorrow"], at=2.0),
    ]
    notes = build_notes(
        "c1", brief, entries, [TIME_SENTENCES["tomorrow"]], None, True, promised_callback=False
    )
    assert f'You answered: "{TIME_SENTENCES["tomorrow"]}"' in notes.summary
    assert notes.outcome == "unclear"


# ---- through the backend ----


@pytest.fixture
def flow():
    with contextlib.ExitStack() as stack:
        yield partial(build_flow, stack)


@pytest.mark.parametrize("choice", list(TIME_SENTENCES))
def test_each_time_word_speaks_exactly_its_sentence_once(flow, choice: str) -> None:
    f = flow()
    call_id = f.start(f.brief(), attended=True)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        f.live(call_id)
        f.speak_last(call_id)  # Bolna says the opening
        assert f.listen_turn(call_id, LIVE_QUESTION) == PAUSE_LINE
        ask = f.drain_until(ws, "ask")
        assert ask["question"] == LIVE_QUESTION
        assert [o["choice"] for o in ask["options"]] == TIME_CHOICES
        assert ask["fallback"] == CALLBACK_LINE

        ws.send_json({"type": "answer", "ask_id": ask["ask_id"], "choice": choice})
        resolved = f.drain_until(ws, "ask_resolved")
        assert resolved == {
            "type": "ask_resolved",
            "ask_id": ask["ask_id"],
            "spoken": TIME_SENTENCES[choice],
            "source": "user",
        }
        assert f.speak_last(call_id) == TIME_SENTENCES[choice]
        # Single use: a second answer speaks nothing.
        ws.send_json({"type": "answer", "ask_id": ask["ask_id"], "choice": choice})
        assert f.drain_until(ws, "error")["code"] == "unknown_ask"
    assert f.bolna.injected.count(TIME_SENTENCES[choice]) == 1
    # A time answer settles nothing: the call goes on.
    delegate = f.manager._sessions[call_id].delegate
    assert delegate.outcome is None and delegate.answers == [TIME_SENTENCES[choice]]


def test_open_question_then_offer_then_yes_is_booked(flow) -> None:
    f = flow()
    call_id = f.start(f.brief(), attended=True)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        f.live(call_id)
        f.speak_last(call_id)
        f.listen_turn(call_id, LIVE_QUESTION)
        ask = f.drain_until(ws, "ask")
        ws.send_json({"type": "answer", "ask_id": ask["ask_id"], "choice": "tomorrow"})
        f.drain_until(ws, "ask_resolved")
        assert f.speak_last(call_id) == TIME_SENTENCES["tomorrow"]

        assert f.listen_turn(call_id, "we have four pm tomorrow does that work") == PAUSE_LINE
        offer = f.drain_until(ws, "ask")
        assert [o["choice"] for o in offer["options"]] == ["yes", "no", "wait"]
        ws.send_json({"type": "answer", "ask_id": offer["ask_id"], "choice": "yes"})
        assert f.drain_until(ws, "ask_resolved")["spoken"] == "Yes, 4 pm tomorrow works. Thank you."
        f.speak_last(call_id)
    f.finish()
    response = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
    assert response["outcome"] == "booked"
    assert response["summary"][1:] == [
        'They offered: "we have four pm tomorrow does that work"',
        f'You answered: "{TIME_SENTENCES["tomorrow"]}"',
        'You answered: "Yes, 4 pm tomorrow works. Thank you."',
    ]


def test_wait_on_an_open_question_holds_and_keeps_the_time_options(flow) -> None:
    f = flow(ask_timeout_s=2.0)
    call_id = f.start(f.brief(), attended=True)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        f.live(call_id)
        f.speak_last(call_id)
        f.listen_turn(call_id, LIVE_QUESTION)
        ask = f.drain_until(ws, "ask")
        ws.send_json({"type": "answer", "ask_id": ask["ask_id"], "choice": "wait"})
        wait_for(lambda: len(f.bolna.replies()) == 2)
        assert f.speak_last(call_id) == WAIT_LINE
        assert "ask_resolved" not in [m["type"] for m in quiet(f, ws, 0.2)]
        ws.send_json({"type": "answer", "ask_id": ask["ask_id"], "choice": "morning"})
        assert f.drain_until(ws, "ask_resolved")["spoken"] == TIME_SENTENCES["morning"]


def test_an_unanswered_open_question_times_out_to_a_callback(flow) -> None:
    f = flow(ask_timeout_s=0.2, end_after_done_s=0.05)
    call_id = f.start(f.brief(), attended=True)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        f.live(call_id)
        f.speak_last(call_id)
        f.listen_turn(call_id, LIVE_QUESTION)
        f.drain_until(ws, "ask")
        resolved = f.drain_until(ws, "ask_resolved")
        assert resolved["source"] == "timeout" and resolved["spoken"] == CALLBACK_LINE
    wait_for(lambda: any(e == EVENT_END_CALL for _, e, _ in f.bolna.events))
    f.finish()
    notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
    assert notes["outcome"] == "callback"


@pytest.mark.parametrize(
    ("heard", "wrong"),
    [
        (LIVE_QUESTION, "yes"),  # yes answers no open question
        ("We have 4 pm tomorrow. Does that work?", "tomorrow"),  # nor a time word an offer
    ],
)
def test_a_choice_the_ask_does_not_offer_is_refused_and_speaks_nothing(flow, heard, wrong) -> None:
    f = flow()
    call_id = f.start(f.brief(), attended=True)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        f.live(call_id)
        f.speak_last(call_id)
        f.listen_turn(call_id, heard)
        ask = f.drain_until(ws, "ask")
        ws.send_json({"type": "answer", "ask_id": ask["ask_id"], "choice": wrong})
        assert f.drain_until(ws, "error")["code"] == "bad_choice"
    assert len(f.bolna.injected) == 1  # only the opening


def test_a_socket_that_reconnects_gets_the_open_time_question(flow) -> None:
    f = flow()
    call_id = f.start(f.brief(), attended=True)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        f.live(call_id)
        f.speak_last(call_id)
        f.listen_turn(call_id, LIVE_QUESTION)
        ask = f.drain_until(ws, "ask")
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        again = f.drain_until(ws, "ask")
        assert again["ask_id"] == ask["ask_id"] and again["options"] == ask["options"]
        ws.send_json({"type": "answer", "ask_id": ask["ask_id"], "choice": "now"})
        assert f.drain_until(ws, "ask_resolved")["spoken"] == TIME_SENTENCES["now"]


def test_unattended_open_question_says_the_brief_time_and_asks_nothing(flow) -> None:
    f = flow()
    with contextlib.ExitStack() as stack:
        call_id = opened_call(f, attended=False, chips=["tomorrow"])
        ws = stack.enter_context(f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH))
        assert f.listen_turn(call_id, LIVE_QUESTION) == TIME_SENTENCES["tomorrow"]
        assert "ask" not in [m["type"] for m in quiet(f, ws)]


def test_the_llm_brain_end_to_end_hands_the_open_question_over(flow) -> None:
    groq = FakeGroq(json.dumps({"say": PAUSE_LINE, "ask_user": {"kind": "time"}, "done": False}))
    f = flow(brain=Brain(groq, timeout_s=1.0))
    call_id = f.start(f.brief(), attended=True)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        f.live(call_id)
        f.speak_last(call_id)
        assert f.listen_turn(call_id, LIVE_QUESTION) == PAUSE_LINE
        ask = f.drain_until(ws, "ask")
        assert [o["choice"] for o in ask["options"]] == TIME_CHOICES
        ws.send_json({"type": "answer", "ask_id": ask["ask_id"], "choice": "tomorrow"})
        assert f.drain_until(ws, "ask_resolved")["spoken"] == TIME_SENTENCES["tomorrow"]
