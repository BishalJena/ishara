"""Receiver questions and honest closure, using only synthetic inference."""

import json

import pytest

from app.delegate import Brain, DelegateState, Exchange, brief_from, build_brief
from app.protocol import BriefRequest, Profile


class Inference:
    def __init__(self, **reply):
        self.reply = reply

    async def complete(self, system, user):
        return json.dumps(self.reply)


def state(request):
    body = BriefRequest(purpose="general", profile=Profile(name="Test Caller"), request=request)
    return DelegateState(
        brief_from(body, build_brief(body)), attended=False, steer=True, opened=True
    )


@pytest.mark.parametrize(
    ("goal", "question", "invented"),
    [
        (
            "Ask about replacing a lost passport.",
            "How did they lose it?",
            "It was lost while travelling.",
        ),
        (
            "Ask a plumber about repairing a pipe.",
            "How did the pipe get damaged?",
            "It broke during renovations.",
        ),
    ],
)
async def test_unknown_receiver_fact_requests_caller_input(goal, question, invented):
    reply = await Brain(Inference(say=invented, done=False)).reply(state(goal), question)
    assert reply.follow_up == question
    assert reply.say != invented and not reply.done


async def test_unknown_receiver_question_without_inference_stays_open():
    question = "When did they get their old passport"
    reply = await Brain(None).reply(state("Ask about replacing a lost passport."), question)
    assert reply.follow_up == question and not reply.done


async def test_a_fee_question_cannot_be_agreed_by_inference():
    question = "The fee is fifty dollars. Do you accept the charge?"
    reply = await Brain(Inference(say="I accept the charge.", done=False)).reply(
        state("Ask about repairing a pipe."), question
    )
    assert reply.follow_up == question
    assert "accept the charge" not in reply.say.lower()


async def test_tentative_operator_words_do_not_prove_external_work_completed():
    reply = await Brain(
        Inference(say="I have logged the request.", done=True, completion_evidence="we can log in")
    ).reply(state("Register a replacement passport request."), "Okay then, we can log in")
    assert not reply.done
    assert "I have logged" not in reply.say


async def test_old_confirmation_cannot_override_current_correction():
    current = state("Register a replacement passport request.")
    current.exchanges.append(Exchange("Your request has been logged.", "Thank you."))
    reply = await Brain(
        Inference(say="Thank you.", done=True, completion_evidence="Your request has been logged.")
    ).reply(current, "Correction, the request has not been logged.")
    assert not reply.done


class StructuredInference:
    def __init__(self, action, **fields):
        resolutions = fields.pop("resolutions", [])
        if action == "finish":
            fields.setdefault("blocked", False)
        self.fields = {"action": {"kind": action, **fields}, "resolutions": resolutions}

    async def complete_structured(self, system, user, response_model):
        fields = json.loads(json.dumps(self.fields))
        action = fields["action"]
        if action["kind"] in {"answer_question", "need_caller"}:
            pending = json.loads(user)["pending_receiver_questions"]
            action.setdefault("question_id", next(reversed(pending), "receiver:0"))
        if action["kind"] == "answer_question":
            action["spans"] = [{"source_id": action.pop("source_id"), "quote": action.pop("quote")}]
        return response_model.model_validate(fields)


async def test_an_old_yes_cannot_authorize_an_identically_worded_new_question():
    current = state("Ask about inspecting a pipe.")
    question = "Do you want to proceed?"
    current.observe_receiver(question)
    current.caller_question_by_turn["first-send"] = current.planner.current_question_turn
    current.delivered_caller_reply("first-send", "Yes, please.")
    current.observe_receiver("The inspection charge is 40 credits.")
    current.observe_receiver(question)
    brain = Brain(
        StructuredInference("answer_question", source_id="caller:0", quote="Yes, please.")
    )
    decision = await brain.reply(current, question)
    assert decision.follow_up == question
    assert decision.say != "Yes, please."
    assert current.planner.current_question_turn.source_id == "receiver:2"


async def test_an_unapproved_operation_cannot_be_requested_as_an_information_question():
    question = "Could you process the replacement with the expedited service?"
    current = state("Ask what documents are needed for a replacement passport.")
    decision = await Brain(StructuredInference("ask_operator", question=question)).reply(
        current, "The standard service takes longer."
    )
    assert decision.say != question and not decision.done


async def test_a_document_quote_must_match_the_requested_field():
    from dataclasses import replace

    from app.protocol import Document

    current = state("Ask about replacing my passport.")
    current.brief = replace(
        current.brief, documents=(Document(name="Form", text="Category: renewal\nCause: lost"),)
    )
    question = "Which category is printed on the form?"
    decision = await Brain(
        StructuredInference("answer_question", source_id="document:0", quote="lost")
    ).reply(current, question)
    assert decision.say == "renewal" and decision.source == "context"
    assert decision.follow_up is None and not current.planner.pending


def test_bounded_caller_source_ids_are_never_reused():
    from app.steer_planner import MAX_CALLER_REPLIES, PlannerMemory

    memory = PlannerMemory()
    for number in range(MAX_CALLER_REPLIES + 4):
        memory.delivered(str(number), None)
    assert len(memory.replies) == MAX_CALLER_REPLIES
    assert len({reply.source_id for reply in memory.replies}) == MAX_CALLER_REPLIES
    assert memory.replies[-1].source_id == f"caller:{MAX_CALLER_REPLIES + 3}"


@pytest.mark.parametrize(
    "goal_request",
    [
        "I'd like to order a replacement passport after losing it abroad",
        "Please call the clinic to book an appointment.",
        "I need you to cancel my membership.",
    ],
)
def test_natural_operation_requests_require_external_action_evidence(goal_request):
    from app.steer_planner import PlannerMemory

    memory = PlannerMemory()
    memory.initialize(goal_request)
    assert memory.goals[0].kind == "external_action"


@pytest.mark.parametrize(
    "goal_request",
    ["Ask how to order a replacement passport", "Do you offer weekend visits?"],
)
def test_information_requests_remain_information_goals(goal_request):
    from app.steer_planner import PlannerMemory

    memory = PlannerMemory()
    memory.initialize(goal_request)
    assert memory.goals[0].kind == "information"


def manager_session(brain=None):
    from app.calls import CallManager
    from app.composer import TemplateComposer
    from app.protocol import CallState
    from app.sessions import CallSession
    from tests.conftest import make_settings
    from tests.test_calls import FakeBolna

    manager = CallManager(
        make_settings(),
        TemplateComposer(),
        FakeBolna(),
        brain=brain,
        cover_first_s=100,
        steer_window=lambda _: 0.0,
    )
    session = CallSession(
        "synthetic-call",
        "general",
        run_id="synthetic-run",
        mode="steer",
        delegate=state("Ask about a replacement passport."),
        line=CallState.IN_CALL,
        present=True,
    )
    manager._sessions[session.call_id] = session
    return manager, session


async def test_signed_send_keeps_the_question_captured_before_composing():
    from app.protocol import ApproveMessage, HoldMessage

    manager, session = manager_session()
    first = "When did you lose the passport?"
    second = "Do you want to proceed?"
    await manager.record_caption(session.call_id, first)
    original = session.delegate.planner.current_question_turn
    await manager._on_hold(session, HoldMessage(turn_id="none", composing=True))
    await manager.record_caption(session.call_id, second)
    await manager._on_approve(session, ApproveMessage(turn_id="signed", text="Yesterday."))
    assert session.delegate.caller_question_by_turn["signed"] == original
    await manager.claim_in_flight(session.call_id)
    await manager.mark_spoken(session.call_id, "signed")
    assert first not in session.delegate.planner.pending.values()
    assert second in session.delegate.planner.pending.values()
    assert session.delegate.planner.replies[-1].question_id == original.source_id


async def test_new_caption_during_publication_cannot_speak_or_commit_a_stale_decision():
    from app.delegate import DEFER_LINE

    stale = "What documents are needed?"
    manager, session = manager_session(Brain(StructuredInference("ask_operator", question=stale)))
    later = "When did you lose the passport?"

    class CaptionDuringPublish:
        injected = False

        async def send(self, message):
            if getattr(message, "speaker", None) == "agent" and not self.injected:
                self.injected = True
                await manager.record_caption(session.call_id, later)

    manager._links[session.call_id] = CaptionDuringPublish()
    await manager.record_caption(session.call_id, "The standard service is available.")
    spoken = await manager.delegate_reply(session.call_id, "The standard service is available.")
    assert spoken == DEFER_LINE
    assert session.delegate.planner.current_question == later
    assert stale not in [entry.text for entry in session.transcript]
    assert session.delegate.exchanges[-1].receptionist == later
    assert session.delegate.outcome is None


@pytest.mark.parametrize(
    "negative", ["We do not open on weekends.", "Actually, we do not open on weekends."]
)
async def test_negative_information_answer_preserves_an_unrelated_resolved_goal(negative):
    current = state("Ask what the membership fee is and whether the library opens on weekends")
    fee = "The membership fee is 20 credits."
    first = StructuredInference(
        "ask_operator",
        question="Do you open on weekends?",
        resolutions=[{"goal_id": "goal:0", "source_id": "receiver:0", "quote": fee}],
    )
    assert not (await Brain(first).reply(current, fee)).done
    assert current.planner.goals[0].evidence is not None
    second = StructuredInference(
        "finish",
        resolutions=[
            {
                "goal_id": "goal:1",
                "source_id": "receiver:1",
                "quote": negative,
            }
        ],
    )
    reply = await Brain(second).reply(current, negative)
    assert current.planner.goals[0].evidence is not None
    assert current.planner.completed and reply.done


def test_a_real_correction_revokes_previous_external_action_evidence():
    from app.steer_planner import ReceiverTurn

    current = state("Register a replacement passport request.")
    current.planner.initialize(current.brief.request)
    current.planner.goals[0].evidence = ReceiverTurn(
        "receiver:0", "Your replacement passport request has been registered."
    )
    current.observe_receiver("Correction, the replacement request has not been registered.")
    assert current.planner.goals[0].evidence is None
    assert not current.planner.completed


@pytest.mark.parametrize(
    "question",
    [
        "Tell me how you lost the passport.",
        "Please tell me your old passport issue date.",
        "What caused the pipe damage? Please hold while I check your account.",
    ],
)
@pytest.mark.parametrize("planner", [None, "wait"])
async def test_substantive_receiver_question_survives_floor_and_hold_words(question, planner):
    current = state("Ask about replacing my passport.")
    client = StructuredInference(planner) if planner else None
    decision = await Brain(client).reply(current, question)
    assert decision.follow_up == question and not decision.done
    assert question in current.planner.pending.values()


async def test_unknown_operation_word_cannot_be_completed_by_a_capability_statement():
    current = state("I need a plumber to fix the pipe.")
    heard = "We can help with the pipe."
    client = StructuredInference(
        "finish", resolutions=[{"goal_id": "goal:0", "source_id": "receiver:0", "quote": heard}]
    )
    decision = await Brain(client).reply(current, heard)
    assert current.planner.goals[0].kind == "external_action"
    assert not current.planner.completed and not decision.done


async def test_outside_terms_wait_for_send_then_actual_receiver_completion():
    from app.delegate import DEFER_LINE
    from app.protocol import ApproveMessage, HoldMessage

    manager, session = manager_session(Brain(StructuredInference("need_caller")))
    session.delegate = state("Register a replacement passport request.")
    offer = "The registration fee is 40 credits. Do you accept the charge?"
    await manager.record_caption(session.call_id, offer)
    assert await manager.delegate_reply(session.call_id, offer) == DEFER_LINE
    assert session.delegate.planner.current_question == offer
    assert session.delegate.follow_ups == [offer]
    await manager._on_hold(session, HoldMessage(turn_id="none", composing=True))
    await manager._on_approve(session, ApproveMessage(turn_id="explicit-send", text="Yes, please."))
    await manager.claim_in_flight(session.call_id)
    await manager.mark_spoken(session.call_id, "explicit-send")
    assert not session.delegate.planner.pending
    assert session.delegate.follow_ups == []
    assert not session.delegate.planner.completed
    completed = "Your replacement passport request has been registered."
    manager._brain = Brain(
        StructuredInference(
            "finish",
            resolutions=[{"goal_id": "goal:0", "source_id": "receiver:1", "quote": completed}],
        )
    )
    await manager.record_caption(session.call_id, completed)
    await manager.delegate_reply(session.call_id, completed)
    assert session.delegate.planner.completed and session.delegate.outcome == "done"
    for task in manager._tasks:
        task.cancel()


@pytest.mark.parametrize(
    "correction", ["Actually, that was wrong.", "Correction: disregard my previous answer."]
)
async def test_unscoped_correction_revokes_proof_before_another_question_can_close(correction):
    from app.steer_planner import ReceiverTurn

    current = state("Ask what the membership fee is.")
    current.planner.initialize(current.brief.request)
    current.planner.goals[0].evidence = ReceiverTurn(
        "receiver:0", "The membership fee is 20 credits."
    )
    assert current.planner.completed
    reply = await Brain(
        StructuredInference("ask_operator", question="What is the membership fee?")
    ).reply(current, correction)
    assert current.planner.goals[0].evidence is None
    assert not current.planner.completed and not reply.done


async def test_late_unscoped_correction_cannot_leave_stale_done_notes():
    from app.protocol import CallState
    from app.steer_planner import ReceiverTurn

    manager, session = manager_session()
    session.delegate = state("Ask what the membership fee is.")
    session.delegate.planner.initialize(session.delegate.brief.request)
    session.delegate.planner.goals[0].evidence = ReceiverTurn(
        "receiver:0", "The membership fee is 20 credits."
    )
    session.delegate.outcome = "done"
    await manager.record_caption(session.call_id, "Actually, that was wrong.")
    session.advance(CallState.ENDED)
    assert manager._notes_for(session).outcome == "unclear"


@pytest.mark.parametrize(
    ("goal_request", "offer", "accepted"),
    [
        (
            "Register a replacement passport request.",
            "I can register the replacement passport request.",
            True,
        ),
        (
            "Register a replacement passport request.",
            "Do you want me to register the replacement passport request?",
            True,
        ),
        ("Cancel my gym membership.", "I can register you for a replacement passport.", False),
        ("Register a replacement passport request.", "I can register a library membership.", False),
        (
            "Register a replacement passport request.",
            "I can register the expedited replacement passport request.",
            False,
        ),
        (
            "Cancel my membership. My previous fee was 50 credits.",
            "The cancellation fee is 40 credits. Shall I proceed?",
            True,
        ),
        (
            "Cancel my membership. Do not pay a fee of 50 credits.",
            "The cancellation fee is 40 credits. Shall I proceed?",
            True,
        ),
        (
            "Cancel my membership with a budget up to 50 credits.",
            "The cancellation fee is 40 credits. Shall I proceed?",
            True,
        ),
        (
            "Cancel my membership for no more than 50 credits.",
            "The cancellation fee is 40 credits. Shall I proceed?",
            True,
        ),
        (
            "Cancel my membership with a budget up to 50 credits.",
            "The cancellation fee is 60 credits. Shall I proceed?",
            False,
        ),
        (
            "Cancel my membership with a budget up to 50 credits and a maximum of 100 credits.",
            "The cancellation fee is 80 credits. Shall I proceed?",
            False,
        ),
    ],
)
async def test_unattended_offers_respect_operation_target_and_positive_spending_authorization(
    goal_request, offer, accepted
):
    current = state(goal_request)
    current.caller_available = False
    client = StructuredInference(
        "accept_offer", goal_id="goal:0", source_id="receiver:0", quote=offer
    )
    decision = await Brain(client).reply(current, offer)
    assert (decision.kind == "accept") is accepted
    assert not current.planner.completed
    if accepted:
        assert not decision.done and current.planner.goals[0].accepted_offer is not None
    else:
        assert decision.done and decision.follow_up == offer
