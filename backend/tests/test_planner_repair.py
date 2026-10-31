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
    return DelegateState(brief_from(body, build_brief(body)), attended=False, steer=True, opened=True)


@pytest.mark.parametrize(
    ("goal", "question", "invented"),
    [
        ("Ask about replacing a lost passport.", "How did they lose it?", "It was lost while travelling."),
        ("Ask a plumber about repairing a pipe.", "How did the pipe get damaged?", "It broke during renovations."),
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
