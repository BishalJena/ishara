"""General goals and graceful endings, with mocked inference and no telephone requests."""

import json

import pytest

from app.delegate import (
    CLARIFY_LINE,
    NEXT_STEP_LINE,
    Brain,
    DelegateState,
    Exchange,
    RuleBrain,
    brief_from,
    build_brief,
    build_notes,
)
from app.protocol import BriefRequest, Document, Profile, TranscriptEntry
from app.templates import compose_template


def state(request="Ask how to renew a passport and when it will arrive", documents=()):
    body = BriefRequest(
        purpose="general", profile=Profile(name="Riya", documents=list(documents)), request=request
    )
    result = DelegateState(brief_from(body, build_brief(body)), attended=False, steer=True)
    result.opened = True
    return result


class Planner:
    def __init__(self, **reply):
        self.reply = reply
        self.calls = []

    async def complete_structured(self, system, user, response_model):
        self.calls.append(json.loads(user))
        reply = dict(self.reply)
        kind = reply.pop("action")
        resolutions = reply.pop("resolutions", [])
        if kind == "finish":
            reply.setdefault("blocked", False)
        if kind in {"answer_question", "need_caller"}:
            pending = self.calls[-1]["pending_receiver_questions"]
            reply.setdefault("question_id", next(reversed(pending), "receiver:0"))
        if kind == "answer_question":
            reply["spans"] = [{"source_id": reply.pop("source_id"), "quote": reply.pop("quote")}]
        return response_model.model_validate(
            {
                "action": {"kind": kind, **reply},
                "resolutions": resolutions,
            }
        )


def test_typed_goal_replaces_legacy_appointment_metadata():
    body = BriefRequest(
        purpose="doctor_appointment",
        profile=Profile(name="Riya"),
        request="Ask a plumber to repair a leaking pipe",
    )
    brief = build_brief(body)
    assert brief.goal == body.request
    assert "doctor" not in brief.text and "appointment" not in brief.text


def test_general_signed_day_does_not_invent_an_appointment():
    line = compose_template(["tomorrow", "please"], "general")
    assert "tomorrow" in line.lower() and "appointment" not in line


def test_delivery_information_is_not_an_appointment_offer_or_a_personal_detail_question():
    reply = RuleBrain().decide(
        state(), "The delivery time is 4 pm and the address is on your letter"
    )
    assert reply.kind not in {"accept", "defer", "time"}


async def test_general_planner_can_finish_after_the_goal_is_answered():
    heard = "We will send your passport in about a month"
    planner = Planner(
        action="finish",
        resolutions=[{"goal_id": "goal:0", "source_id": "receiver:0", "quote": heard}],
    )
    reply = await Brain(planner).reply(state("Ask when the passport will arrive"), heard)
    assert reply.done and not reply.callback and reply.source == "llm"
    assert planner.calls[0]["caller_goal"] == "Ask when the passport will arrive"


async def test_anything_else_does_not_discard_an_unanswered_part_of_the_request():
    planner = Planner(action="ask_operator", question="What documents do I need to bring?")
    reply = await Brain(planner).reply(
        state("Ask about the renewal fee and required documents"),
        "The fee is listed on the form. Anything else you would like to know?",
    )
    assert not reply.done and reply.say == "What documents do I need to bring?"


async def test_completion_requires_operator_evidence_not_an_invented_resolution():
    planner = Planner(
        action="finish",
        resolutions=[
            {"goal_id": "goal:0", "source_id": "receiver:0", "quote": "Your passport has been sent"}
        ],
    )
    reply = await Brain(planner).reply(state(), "Please hold while I check")
    assert not reply.done


async def test_plumber_goal_and_live_user_updates_reach_the_planner():
    current = state("Ask a plumber about repairing the leaking pipe")
    current.answers.append("Please ask whether they can come tomorrow.")
    planner = Planner(
        action="ask_operator", question="Do you offer visits tomorrow to look at the pipe?"
    )
    reply = await Brain(planner).reply(current, "I can help with the pipe")
    assert reply.source == "llm"
    assert "plumber" in planner.calls[0]["caller_goal"]
    assert planner.calls[0]["user_answers_so_far"] == current.answers


async def test_a_repeated_question_falls_back_without_asking_it_again():
    current = state()
    current.exchanges.append(Exchange("Let me look at that", NEXT_STEP_LINE))
    reply = await Brain(Planner(action="ask_operator", question=NEXT_STEP_LINE)).reply(
        current, "It will be sent in a month"
    )
    assert reply.say == CLARIFY_LINE and reply.say != NEXT_STEP_LINE and not reply.done


async def test_a_document_detail_can_be_quoted_for_an_unanticipated_question():
    current = state(
        documents=(Document(name="Application", text="Category: Renewal\nReference: SAMPLE-24"),)
    )
    planner = Planner(action="answer_question", source_id="document:0", quote="Renewal")
    reply = await Brain(planner).reply(current, "Which category is printed on the application?")
    assert reply.say == "Renewal" and reply.kind == "share"
    assert next(s for s in planner.calls[0]["approved_sources"] if s["source_id"] == "document:0")[
        "text"
    ].startswith("Category:")


async def test_a_document_value_that_was_not_supplied_is_rejected():
    current = state(documents=(Document(name="Application", text="Category: Renewal"),))
    reply = await Brain(
        Planner(action="answer_question", source_id="document:0", quote="Replacement")
    ).reply(current, "Which category is printed on the application?")
    assert reply.kind == "defer" and "Replacement" not in reply.say


def test_generic_fallback_has_a_bounded_recovery_instead_of_an_endless_question_loop():
    current = state()
    rules = RuleBrain()
    replies = []
    for _ in range(5):
        reply = rules.decide(current, "It is being processed")
        replies.append(reply)
        current.exchanges.append(Exchange("It is being processed", reply.say))
        if reply.done:
            break
    assert sum(x.say == NEXT_STEP_LINE for x in replies) == 1
    assert replies[-1].done and replies[-1].callback


def test_general_notes_do_not_label_a_passport_confirmation_as_an_appointment():
    current = state()
    entries = [TranscriptEntry(speaker="receptionist", text="Your renewal is confirmed", at=1)]
    notes = build_notes(
        "fixture",
        current.brief,
        entries,
        [],
        None,
        True,
        promised_callback=False,
        mode="steer",
        goal_completed=True,
    )
    assert notes.outcome == "done"


@pytest.mark.parametrize(
    "heard",
    ["okay goodbye", "is there anything else you would like to know", "that's all thank you bye"],
)
def test_rule_fallback_recognizes_the_operator_ending_a_general_conversation(heard):
    assert RuleBrain().decide(state(), heard).done


async def test_an_appointment_confirmation_can_leave_another_requested_question_open():
    planner = Planner(action="ask_operator", question="What should I bring with me?")
    reply = await Brain(planner).reply(
        state("Book an appointment and ask what to bring"), "Your appointment is confirmed"
    )
    assert not reply.done and reply.say == "What should I bring with me?"


async def test_document_quotes_keep_the_original_source_case_and_punctuation():
    current = state(documents=(Document(name="Application", text="Category: RE-NEWAL"),))
    planner = Planner(action="answer_question", source_id="document:0", quote="renewal")
    reply = await Brain(planner).reply(current, "Which category is printed on the application?")
    assert reply.say == "RE-NEWAL"


def test_a_delivered_signed_reply_is_part_of_the_agent_context():
    import contextlib

    from tests.test_delegate import AUTH
    from tests.test_steer import build_steer_flow, every, start_steer

    with contextlib.ExitStack() as stack:
        flow = build_steer_flow(stack)
        call_id = start_steer(flow, request="Ask about a passport renewal")
        with flow.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
            flow.receive(ws)
            flow.live(call_id)
            flow.speak_last(call_id)
            every(flow, ws)
            ws.send_json(
                {
                    "type": "approve",
                    "turn_id": "signed-fixture",
                    "text": "Please ask about delivery.",
                }
            )
            flow.drain_until(ws, "status")
            assert flow.speak_last(call_id) == "Please ask about delivery."
            session = flow.manager._sessions[call_id]
            assert session.purpose == "general", "Old clients get the general steer path too"
            assert "Please ask about delivery." in session.delegate.answers


def test_a_general_brief_requires_a_nonempty_user_goal():
    with pytest.raises(ValueError):
        BriefRequest(purpose="general", profile=Profile(name="Riya"))
    with pytest.raises(ValueError):
        BriefRequest(purpose="general", request="   ", profile=Profile(name="Riya"))
