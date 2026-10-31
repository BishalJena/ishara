"""A whole approved operation can naturally answer a clear permission question."""

import json

import pytest

from app.delegate import Brain
from tests.test_autonomous_options import state


class WholeRequest:
    async def complete_structured(self, system, user, model):
        payload = json.loads(user)
        source = next(row for row in payload["approved_sources"] if row["source_id"] == "request")
        return model.model_validate(
            {
                "resolutions": [],
                "action": {
                    "kind": "answer_question",
                    "question_id": payload["current_receiver_turn"]["source_id"],
                    "spans": [{"source_id": "request", "quote": source["text"]}],
                },
            }
        )


class RepairedApproval(WholeRequest):
    def __init__(self):
        self.calls = []

    async def complete_structured(self, system, user, model):
        payload = json.loads(user)
        self.calls.append(payload)
        if len(self.calls) == 1:
            return await super().complete_structured(system, user, model)
        current = payload["current_receiver_turn"]
        return model.model_validate(
            {
                "resolutions": [],
                "action": {
                    "kind": "accept_offer",
                    "goal_id": "goal:0",
                    "source_id": current["source_id"],
                    "quote": current["text"],
                },
            }
        )


@pytest.mark.parametrize(
    ("goal", "heard"),
    [
        (
            "Book an appointment with the doctor in the attached health report.",
            "I can book an appointment with Dr. Morgan Reed. Shall I proceed?",
        ),
        (
            "Arrange a plumber visit to repair the leak.",
            "We can arrange the plumber visit. Can we go ahead?",
        ),
    ],
)
async def test_whole_affirmative_goal_becomes_guarded_current_offer_acceptance(goal, heard):
    current = state(goal)
    if "report" in goal:
        from dataclasses import replace

        from app.protocol import Document

        current.brief = replace(
            current.brief,
            documents=(Document(name="Synthetic report", text="Doctor: Dr. Morgan Reed"),),
        )
    client = RepairedApproval()
    reply = await Brain(client).reply(current, heard)
    assert reply.kind == "accept" and not reply.done and reply.source == "llm"
    assert len(client.calls) == 2 and "Wrong action kind" in client.calls[1]["validation_feedback"]
    assert current.planner.goals[0].accepted_offer.source_id == "receiver:0"
    assert current.planner.goals[0].accepted_offer.text == heard
    assert not current.planner.completed and not current.planner.pending


@pytest.mark.parametrize(
    ("goal", "heard"),
    [
        (
            "Book an appointment. Budget ₹800.",
            "I can book an appointment for ₹1,800. Shall I proceed?",
        ),
        ("Book an appointment at 10 am.", "I can book an appointment at 9 pm. Shall I proceed?"),
        (
            "Order a standard replacement passport.",
            "I can order a premium passport upgrade. Shall I proceed?",
        ),
    ],
)
async def test_natural_operation_restatement_cannot_bypass_offer_constraints(goal, heard):
    current = state(goal)
    reply = await Brain(WholeRequest()).reply(current, heard)
    assert reply.kind != "accept" and current.planner.goals[0].accepted_offer is None
    assert reply.follow_up is not None or reply.kind == "decline"


@pytest.mark.parametrize(
    "goal",
    [
        "Book only after I approve.",
        "Do not book until I review.",
        "Book an appointment if I approve it.",
        "Book an appointment pending my consent.",
    ],
)
async def test_negative_or_conditional_request_never_becomes_permission(goal):
    current = state(goal)
    reply = await Brain(WholeRequest()).reply(
        current, "I can book an appointment. Shall I proceed?"
    )
    assert reply.kind != "accept"
    assert current.planner.goals[0].accepted_offer is None


async def test_an_operation_quote_cannot_swallow_a_simultaneous_unknown_fact_question():
    current = state("Book an appointment.")
    heard = "I can book an appointment. Shall I proceed? What are the allergies?"
    reply = await Brain(WholeRequest()).reply(current, heard)
    assert reply.kind != "accept" and current.planner.goals[0].accepted_offer is None
    assert current.planner.pending and "allergies" in reply.follow_up


async def test_an_older_unknown_question_prevents_normalizing_new_permission():
    current = state("Book an appointment.")
    current.observe_receiver("What are the allergies?")
    reply = await Brain(WholeRequest()).reply(
        current, "I can book an appointment. Shall I proceed?"
    )
    assert reply.kind != "accept" and current.planner.goals[0].accepted_offer is None
    assert "receiver:0" in current.planner.pending


async def test_alternative_offers_are_not_treated_as_whole_goal_permission():
    current = state("Book an appointment.")
    reply = await Brain(WholeRequest()).reply(
        current, "I can book Monday or Tuesday. Shall I proceed?"
    )
    assert reply.kind != "accept" and current.planner.goals[0].accepted_offer is None


async def test_an_information_request_is_not_normalized_as_operation_approval():
    current = state("Ask what the appointment fee is.")
    reply = await Brain(WholeRequest()).reply(current, "I can tell you the fee. Shall I proceed?")
    assert reply.kind != "accept" and current.planner.goals[0].accepted_offer is None


async def test_exhausted_wrong_action_kind_never_automatically_becomes_consent():
    current = state("Book an appointment.")
    reply = await Brain(WholeRequest()).reply(
        current, "I can book an appointment. Shall I proceed?"
    )
    assert reply.kind != "accept" and current.planner.goals[0].accepted_offer is None
    assert reply.say != "Book an appointment." and reply.follow_up is not None
