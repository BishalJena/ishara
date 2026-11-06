"""A bounded re-selection repairs encoding without inventing missing caller facts."""

import asyncio
import json

import pytest

from app.delegate import Brain
from tests.test_autonomous_options import state

QUESTION = "Do you want a 32-pager or a 64-pager?"


class MisencodedChoice:
    def __init__(self, *, correct=True, delay=0):
        self.correct, self.delay, self.calls = correct, delay, []

    async def complete_structured(self, system, user, model):
        payload = json.loads(user)
        self.calls.append(payload)
        if self.delay:
            await asyncio.sleep(self.delay)
        current = payload["current_receiver_turn"]
        if len(self.calls) > 1 and self.correct:
            action = {
                "kind": "choose_option",
                "goal_id": "goal:0",
                "source_id": current["source_id"],
                "quote": current["text"],
                "option": "32-pager",
            }
        else:
            action = {
                "kind": "answer_question",
                "question_id": current["source_id"],
                "spans": [{"source_id": "request", "quote": "I would like a 32-pager."}],
            }
        return model.model_validate({"resolutions": [], "action": action})


async def test_bad_caller_provenance_for_an_authorized_choice_gets_one_validated_reselection():
    value, client = state("Order a replacement passport."), MisencodedChoice()
    reply = await Brain(client).reply(value, QUESTION)
    assert reply.kind == "accept" and reply.say == "32-pager" and not reply.done
    assert len(client.calls) == 2 and "validation_feedback" in client.calls[1]
    assert not value.planner.pending and not value.planner.completed


async def test_failed_reselection_is_not_retried_or_spoken():
    client = MisencodedChoice(correct=False)
    reply = await Brain(client).reply(state("Order a replacement passport."), QUESTION)
    assert len(client.calls) == 2 and reply.kind != "share"
    assert "I would like a 32-pager" not in reply.say


@pytest.mark.parametrize(
    "question",
    [
        "What is the applicant's national identity number?",
        "Are you allergic to penicillin or latex?",
        "Is the patient a new or existing customer?",
    ],
)
async def test_unknown_personal_facts_never_trigger_a_preference_repair(question):
    client = MisencodedChoice()
    reply = await Brain(client).reply(state("Order a replacement passport."), question)
    assert len(client.calls) == 1 and reply.kind != "accept"
    assert reply.follow_up == question


async def test_an_explicit_budget_violation_is_not_retried():
    client = MisencodedChoice()
    reply = await Brain(client).reply(
        state("Order a replacement passport. Budget ₹800."),
        "Do you want a 32-pager or a 64-pager? The fee is ₹1,800.",
    )
    assert len(client.calls) == 1 and reply.kind != "accept"


async def test_initial_and_repair_inference_share_one_deadline(monkeypatch):
    original = asyncio.wait_for
    timeouts = []

    async def observed(awaitable, timeout):
        timeouts.append(timeout)
        return await original(awaitable, timeout)

    monkeypatch.setattr(asyncio, "wait_for", observed)
    client = MisencodedChoice(delay=0.03)
    reply = await Brain(client, timeout_s=0.05).reply(
        state("Order a replacement passport."), QUESTION
    )
    assert len(client.calls) == 2 and len(timeouts) == 2
    assert timeouts[1] < 0.025 and timeouts[1] < timeouts[0]
    assert reply.kind != "accept"


class UnnecessaryHandoff(MisencodedChoice):
    async def complete_structured(self, system, user, model):
        result = await super().complete_structured(system, user, model)
        if len(self.calls) == 1:
            return model.model_validate(
                {
                    "resolutions": [],
                    "action": {
                        "kind": "need_caller",
                        "question_id": self.calls[-1]["current_receiver_turn"]["source_id"],
                    },
                }
            )
        return result


async def test_open_operational_choice_cannot_claim_a_missing_caller_preference():
    client = UnnecessaryHandoff()
    reply = await Brain(client).reply(state("Order a replacement passport."), QUESTION)
    assert reply.kind == "accept" and reply.say == "32-pager"
    assert len(client.calls) == 2
    assert "instead of need_caller" in client.calls[1]["validation_feedback"]


@pytest.mark.parametrize(
    "question",
    [
        "Are you allergic to penicillin or latex?",
        "Is the patient a new or existing customer?",
    ],
)
async def test_genuine_personal_handoff_is_not_reselected(question):
    client = UnnecessaryHandoff()
    reply = await Brain(client).reply(state("Order a replacement passport."), question)
    assert len(client.calls) == 1 and reply.kind != "accept"
    assert reply.follow_up == question
