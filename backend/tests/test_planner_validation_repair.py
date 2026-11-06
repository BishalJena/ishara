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
async def test_invalid_personal_answer_repair_cannot_turn_into_an_operational_choice(question):
    client = MisencodedChoice()
    reply = await Brain(client).reply(state("Order a replacement passport."), question)
    assert len(client.calls) == 2 and reply.kind != "accept"
    assert "Invalid answer spans: source_span" in client.calls[1]["validation_feedback"]
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


class StaleAfterChoice:
    def __init__(self, *, repair=True, question=False):
        self.calls, self.repair, self.question = [], repair, question

    async def complete_structured(self, system, user, model):
        payload = json.loads(user)
        self.calls.append(payload)
        current = payload["current_receiver_turn"]
        if len(self.calls) == 1:
            action = {
                "kind": "choose_option",
                "goal_id": "goal:0",
                "source_id": current["source_id"],
                "quote": current["text"],
                "option": "32-pager",
            }
            resolutions = []
        elif len(self.calls) == 2 or not self.repair:
            action = {
                "kind": "accept_offer",
                "goal_id": "goal:0",
                "source_id": "receiver:0",
                "quote": "32-pager",
            }
            resolutions = []
        else:
            action = (
                {
                    "kind": "answer_question",
                    "question_id": current["source_id"],
                    "spans": [{"source_id": "document:0", "quote": "Use the side gate"}],
                }
                if self.question
                else {"kind": "finish", "blocked": False}
            )
            resolutions = [
                {
                    "goal_id": "goal:0",
                    "source_id": current["source_id"],
                    "quote": CONFIRMATION,
                }
            ]
        return model.model_validate({"resolutions": resolutions, "action": action})


CONFIRMATION = "Your replacement passport order for the selected booklet has been registered."


async def test_stale_accept_after_choice_repairs_current_confirmation_proof():
    value, client = state("Order a replacement passport."), StaleAfterChoice()
    brain = Brain(client)
    assert (await brain.reply(value, QUESTION)).kind == "accept"
    reply = await brain.reply(value, CONFIRMATION)
    assert len(client.calls) == 3 and reply.done and value.planner.completed
    assert value.planner.goals[0].evidence.source_id == "receiver:1"
    assert not value.planner.pending


async def test_exhausted_stale_provenance_stays_quiet_without_inventing_a_caller_question():
    value, client = state("Order a replacement passport."), StaleAfterChoice(repair=False)
    brain = Brain(client)
    await brain.reply(value, QUESTION)
    reply = await brain.reply(value, CONFIRMATION)
    assert len(client.calls) == 3 and not reply.done and not reply.say
    assert reply.follow_up is None and not value.planner.pending
    assert not value.planner.completed and value.planner.evidence_review is not None


async def test_repaired_confirmation_still_answers_a_real_question_before_closing():
    from dataclasses import replace

    from app.protocol import Document

    value, client = state("Order a replacement passport."), StaleAfterChoice(question=True)
    value.brief = replace(
        value.brief,
        documents=[
            Document(name="Synthetic instructions", text="Access instructions: Use the side gate")
        ],
    )
    brain = Brain(client)
    await brain.reply(value, QUESTION)
    reply = await brain.reply(value, CONFIRMATION + " How will they get inside?")
    assert len(client.calls) == 3 and reply.kind == "share" and not reply.done
    assert "side gate" in reply.say and value.planner.completed
    assert not value.planner.pending


class InvalidAnswerScope:
    def __init__(self, *, repair=True):
        self.calls, self.repair = [], repair

    async def complete_structured(self, system, user, model):
        payload = json.loads(user)
        self.calls.append(payload)
        quotes = ["Patient name: Avery Sample", "Doctor name: Dr. Morgan Reed"]
        if len(self.calls) > 1 and self.repair:
            quotes.pop(0)
        return model.model_validate(
            {
                "resolutions": [],
                "action": {
                    "kind": "answer_question",
                    "question_id": payload["current_receiver_turn"]["source_id"],
                    "spans": [{"source_id": "document:0", "quote": quote} for quote in quotes],
                },
            }
        )


async def test_wrong_entity_selection_is_repaired_without_weakening_answer_scope():
    from tests.test_approved_context_repair import REPORT
    from tests.test_approved_context_repair import state as document_state

    value, client = document_state(text="Patient health summary\n" + REPORT), InvalidAnswerScope()
    question = "What is the doctor's name?"
    reply = await Brain(client).reply(value, question)
    assert len(client.calls) == 2 and reply.kind == "share"
    assert reply.say == "Doctor name: Dr. Morgan Reed"
    assert "Avery Sample" not in reply.say and not value.planner.pending
    feedback = client.calls[1]["validation_feedback"]
    assert "entity_scope" in feedback
    assert "Avery Sample" not in feedback and "Morgan Reed" not in feedback


async def test_failed_answer_scope_repair_is_never_partially_spoken():
    from tests.test_approved_context_repair import REPORT
    from tests.test_approved_context_repair import state as document_state

    value = document_state(text="Patient health summary\n" + REPORT)
    client = InvalidAnswerScope(repair=False)
    question = "What is the doctor's name?"
    reply = await Brain(client).reply(value, question)
    assert len(client.calls) == 2 and reply.kind != "share"
    assert "Avery Sample" not in reply.say and "Morgan Reed" not in reply.say
    assert reply.follow_up == question and value.planner.current_question == question
