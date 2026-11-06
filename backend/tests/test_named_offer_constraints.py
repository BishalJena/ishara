"""Explicit named providers constrain natural and structured operation approvals."""

import json

import pytest

from app.delegate import Brain
from tests.test_autonomous_options import state
from tests.test_operation_answer_normalization import RepairedApproval


class OfferAction:
    async def complete_structured(self, system, user, model):
        payload = json.loads(user)
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


@pytest.mark.parametrize("client", [RepairedApproval, OfferAction])
@pytest.mark.parametrize(
    ("requested", "offered", "allowed"),
    [
        ("Dr. Morgan Reed", "Dr. Morgan Reed", True),
        ("Dr. Morgan Reed", "Dr. Other Doctor", False),
        ("Dr. Morgan Reed", "Dr. M. Reed", True),
        ("Dr. Morgan Reed", "Dr. Reed", True),
        ("Dr. Morgan Reed", "Dr. Jamie Reed", False),
        ("Dr. Morgan Allen Reed", "Dr. Morgan Brian Reed", False),
        ("Dr. Morgan Allen Reed", "Dr. Morgan A. Reed", True),
        ("Jordan Rivera", "Jordan Rivera", True),
        ("Jordan Rivera", "Jamie Rivera", False),
    ],
)
async def test_explicit_target_applies_to_both_model_and_normalized_approvals(
    client, requested, offered, allowed
):
    current = state(f"Book an appointment with {requested}.")
    reply = await Brain(client()).reply(
        current, f"I can book an appointment with {offered}. Shall I proceed?"
    )
    assert (reply.kind == "accept") is allowed
    assert (current.planner.goals[0].accepted_offer is not None) is allowed


@pytest.mark.parametrize("client", [RepairedApproval, OfferAction])
async def test_omitted_named_target_does_not_create_a_new_constraint(client):
    current = state("Book an appointment.")
    reply = await Brain(client()).reply(
        current, "I can book an appointment with Dr. Morgan Reed. Shall I proceed?"
    )
    assert reply.kind == "accept"


@pytest.mark.parametrize(
    ("document", "offered", "allowed"),
    [
        ("Doctor: Dr. Morgan Reed", "Dr. Morgan Reed", True),
        ("Doctor: Dr. Morgan Reed", "Dr. Other Doctor", False),
        ("Doctor: Dr. Morgan Reed\nDoctor: Dr. Other Doctor", "Dr. Morgan Reed", False),
        ("Patient name: Avery Sample", "Dr. Other Doctor", False),
    ],
)
async def test_explicit_report_provider_reference_is_bounded_by_unambiguous_labelled_target(
    document, offered, allowed
):
    from dataclasses import replace

    from app.protocol import Document

    current = state("Book an appointment with the doctor in the attached health report.")
    current.brief = replace(
        current.brief, documents=(Document(name="Synthetic report", text=document),)
    )
    reply = await Brain(OfferAction()).reply(
        current, f"I can book an appointment with {offered}. Shall I proceed?"
    )
    assert (reply.kind == "accept") is allowed
    assert (current.planner.goals[0].accepted_offer is not None) is allowed
