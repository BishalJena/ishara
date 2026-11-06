"""Routine choices use the initial request while explicit limits remain binding."""

import json

import pytest

from app.delegate import Brain, DelegateState, brief_from, build_brief
from app.protocol import BriefRequest, Profile
from app.steer_planner import ReceiverTurn, offer_objection


def state(request):
    body = BriefRequest(purpose="general", profile=Profile(name="Sample Caller"), request=request)
    return DelegateState(
        brief_from(body, build_brief(body)),
        attended=False,
        steer=True,
        opened=True,
        caller_available=False,
    )


class Choice:
    def __init__(self, option, quote=None):
        self.option, self.quote = option, quote

    async def complete_structured(self, system, user, model):
        payload = json.loads(user)
        current = payload["current_receiver_turn"]
        return model.model_validate(
            {
                "action": {
                    "kind": "choose_option",
                    "goal_id": payload["goals"][0]["goal_id"],
                    "source_id": current["source_id"],
                    "quote": self.quote or current["text"],
                    "option": self.option,
                },
                "resolutions": [],
            }
        )


@pytest.mark.parametrize(
    ("task_request", "fee", "allowed"),
    [
        ("Book an appointment.", "The consultation fee is ₹800.", True),
        ("Book an appointment.", "There is a routine consultation fee.", True),
        ("Book an appointment. Budget ₹1000.", "The consultation fee is ₹800.", True),
        ("Book an appointment. Budget ₹500.", "The consultation fee is ₹800.", False),
        ("Book an appointment with no fees.", "The consultation fee is ₹800.", False),
        ("Book an appointment. Budget ₹500.", "There is a consultation fee.", False),
    ],
)
def test_omitted_budget_is_open_but_explicit_budget_is_enforced(task_request, fee, allowed):
    assert (offer_objection(task_request, [ReceiverTurn("receiver:0", fee)]) is None) is allowed


@pytest.mark.parametrize(
    ("task_request", "offered", "option", "allowed"),
    [
        (
            "Renew my passport.",
            "Which passport booklet would you like, 32 pages or 64 pages?",
            "32 pages",
            True,
        ),
        (
            "Renew my passport with 64 pages.",
            "Which passport booklet would you like, 32 pages or 64 pages?",
            "64 pages",
            True,
        ),
        (
            "Renew my passport with 64 pages.",
            "Which passport booklet would you like, 32 pages or 64 pages?",
            "32 pages",
            False,
        ),
        ("Renew my passport.", "Is your current passport 32 pages or 64 pages?", "32 pages", False),
        (
            "Renew my passport.",
            "Which passport booklet would you like, 32 pages or 64 pages?",
            "96 pages",
            False,
        ),
        (
            "Book an appointment.",
            "Would you like Monday at 9 pm or Tuesday at 10 am?",
            "Monday at 9 pm",
            True,
        ),
        (
            "Book an appointment on Tuesday in the morning.",
            "Would you like Monday at 9 pm or Tuesday at 10 am?",
            "Monday at 9 pm",
            False,
        ),
        (
            "Book an appointment on Tuesday in the morning.",
            "Would you like Monday at 9 pm or Tuesday at 10 am?",
            "Tuesday at 10 am",
            True,
        ),
        (
            "Order a replacement passport. Budget ₹600.",
            "Choose standard ₹500 or premium ₹900 for the passport.",
            "standard ₹500",
            True,
        ),
    ],
)
async def test_ordinary_offered_options_use_context_without_caller_intervention(
    task_request, offered, option, allowed
):
    current = state(task_request)
    reply = await Brain(Choice(option)).reply(current, offered)
    assert (reply.kind == "accept") is allowed
    assert not current.planner.completed
    if allowed:
        assert reply.say == option and not reply.done and not current.planner.pending


async def test_a_fee_question_carries_the_existing_operation_without_repeating_its_name():
    current = state("Book an appointment with Dr. Rao.")
    first = await Brain(None).reply(current, "We have Monday at 9 pm. Is that okay?")
    assert first.kind == "accept" and current.planner.goals[0].accepted_offer is not None

    class Accept:
        async def complete_structured(self, system, user, model):
            payload = json.loads(user)
            turn = payload["current_receiver_turn"]
            return model.model_validate(
                {
                    "action": {
                        "kind": "accept_offer",
                        "goal_id": "goal:0",
                        "source_id": turn["source_id"],
                        "quote": turn["text"],
                    },
                    "resolutions": [],
                }
            )

    second = await Brain(Accept()).reply(current, "The clinic treatment is ₹800. Shall we proceed?")
    assert second.kind == "accept" and not second.done and second.follow_up is None
    assert not current.planner.completed


async def test_an_unambiguous_repeat_request_repeats_only_the_immediately_selected_option():
    from app.delegate import Exchange

    current = state("Renew my passport.")
    heard = "Do you want a 32-pager or a 64-pager?"
    first = await Brain(Choice("32-pager")).reply(current, heard)
    current.exchanges.append(Exchange(heard, first.say))

    class NoRequest:
        async def complete_structured(self, *_):
            raise AssertionError("A source-backed repeat needs no inference")

    repeated = await Brain(NoRequest()).reply(current, "Sorry, which one?")
    assert repeated.say == "32-pager" and repeated.kind == "share" and not repeated.done
    assert not current.planner.pending and not current.planner.completed


@pytest.mark.parametrize(
    "question",
    ["What is the applicant's national identity number?", "Does the patient have any allergies?"],
)
async def test_a_service_choice_is_never_reused_as_an_unknown_personal_fact(question):
    from app.delegate import Exchange

    current = state("Renew my passport.")
    heard = "Do you want a 32-pager or a 64-pager?"
    first = await Brain(Choice("32-pager")).reply(current, heard)
    current.exchanges.append(Exchange(heard, first.say))
    requests = []

    class Missing:
        async def complete_structured(self, system, user, model):
            payload = json.loads(user)
            requests.append(payload)
            return model.model_validate(
                {
                    "action": {
                        "kind": "need_caller",
                        "question_id": next(reversed(payload["pending_receiver_questions"])),
                    },
                    "resolutions": [],
                }
            )

    reply = await Brain(Missing()).reply(current, question)
    assert requests and reply.follow_up == question and "32-pager" not in reply.say


@pytest.mark.parametrize("price", ["₹1,800", "1,800 rupees", "₹18,000", "1,80,000 rupees"])
def test_grouped_prices_cannot_be_read_as_a_smaller_amount(price):
    assert offer_objection(
        "Book a visit. Budget ₹800.", [ReceiverTurn("r", f"The fee is {price}.")]
    )


@pytest.mark.parametrize(("limit", "allowed"), [("₹800", False), ("₹2000", True)])
async def test_selected_quote_cannot_hide_a_shared_current_offer_price(limit, allowed):
    current = state(f"Order a replacement passport. Budget {limit}.")
    heard = "A 32-pager or 64-pager costs ₹1,800."
    reply = await Brain(Choice("32-pager", quote="A 32-pager or 64-pager")).reply(current, heard)
    assert (reply.kind == "accept") is allowed


@pytest.mark.parametrize(
    ("question", "option"),
    [
        ("Are you allergic to penicillin or latex?", "penicillin"),
        ("Is the patient a new or existing customer?", "new"),
    ],
)
async def test_personal_state_questions_are_not_operational_preference_choices(question, option):
    reply = await Brain(Choice(option)).reply(state("Book an appointment."), question)
    assert reply.kind != "accept" and option not in reply.say


async def test_full_offer_price_check_still_allows_a_cheaper_selected_option():
    current = state("Order a replacement passport. Budget ₹2000.")
    heard = "We offer standard for ₹1,800 or premium for ₹2,800. Which do you want?"
    reply = await Brain(Choice("standard", quote="standard")).reply(current, heard)
    assert reply.kind == "accept" and reply.say == "standard" and not reply.done


async def test_shortened_quote_cannot_hide_a_numeric_preference_unit():
    current = state("Renew my passport with a 64-page booklet.")
    reply = await Brain(Choice("32", quote="32")).reply(
        current, "Would you like a 32-pager or a 64-pager?"
    )
    assert reply.kind != "accept"


async def test_shortened_quote_cannot_hide_a_different_operation():
    current = state("Book an appointment.")
    reply = await Brain(Choice("standard", quote="standard")).reply(
        current, "I can cancel a membership with standard or premium service. Which do you want?"
    )
    assert reply.kind != "accept"


async def test_a_later_preference_question_does_not_turn_a_personal_state_into_a_choice():
    current = state("Book an appointment.")
    reply = await Brain(Choice("penicillin")).reply(
        current, "Are you allergic to penicillin or latex? Which time would you prefer?"
    )
    assert reply.kind != "accept" and "penicillin" not in reply.say
