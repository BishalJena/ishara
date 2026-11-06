"""A missed proof can be recovered without inferring completion from a caller answer."""

import json
from dataclasses import replace

from app.delegate import Brain
from app.groq_client import GroqError
from tests.test_approved_context_repair import state

PROOF = "Your plumber visit to repair the leak is booked."
HEARD = PROOF + " How will they get inside?"


class MissedProof:
    def __init__(self, *, fail_review=False, add_new_goal=False):
        self.calls = []
        self.fail_review, self.add_new_goal = fail_review, add_new_goal

    async def complete_structured(self, system, user, model):
        payload = json.loads(user)
        self.calls.append((model.__name__, payload))
        if model.__name__ == "ResolutionReview":
            if self.fail_review:
                raise GroqError("synthetic unavailable")
            rows = [{"goal_id": "goal:0", "source_id": "receiver:0", "quote": PROOF}]
            if self.add_new_goal:
                rows.append({"goal_id": "goal:1", "source_id": "receiver:0", "quote": PROOF})
            return model.model_validate({"resolutions": rows})
        if len(self.calls) == 1:
            return model.model_validate(
                {
                    "resolutions": [],
                    "action": {
                        "kind": "answer_question",
                        "question_id": "receiver:0",
                        "spans": [{"source_id": "document:0", "quote": "Use the side gate"}],
                    },
                }
            )
        return model.model_validate({"resolutions": [], "action": {"kind": "wait"}})


def current():
    value = state(text="Access instructions: Use the side gate")
    value.brief = replace(value.brief, request="Arrange a plumber visit to repair the leak.")
    return value


async def test_missing_resolution_is_recovered_from_the_exact_previous_receiver_assertion():
    value, client = current(), MissedProof()
    first = await Brain(client).reply(value, HEARD)
    assert first.kind == "share" and not value.planner.completed
    closing = await Brain(client).reply(value, "Thank you.")
    assert closing.done and value.planner.completed
    assert value.planner.goals[0].evidence.text == PROOF
    assert [name for name, _ in client.calls] == ["PlannerTurn", "ResolutionReview"]


async def test_correction_prevents_older_proof_from_being_recovered():
    value, client = current(), MissedProof()
    await Brain(client).reply(value, HEARD)
    await Brain(client).reply(value, "Correction, the plumber visit is not booked.")
    closing = await Brain(client).reply(value, "Thank you.")
    assert not closing.done and not value.planner.completed
    assert all(name != "ResolutionReview" for name, _ in client.calls)


async def test_new_live_goal_cannot_borrow_a_proof_that_predates_it():
    value, client = current(), MissedProof(add_new_goal=True)
    await Brain(client).reply(value, HEARD)
    value.planner.delivered("Please book another plumber visit next week.", None)
    closing = await Brain(client).reply(value, "Thank you.")
    assert not closing.done and value.planner.goals[1].evidence is None
    assert not value.planner.completed


async def test_unavailable_review_is_bounded_to_one_attempt_per_source():
    value, client = current(), MissedProof(fail_review=True)
    await Brain(client).reply(value, HEARD)
    assert not (await Brain(client).reply(value, "Thank you.")).done
    assert not (await Brain(client).reply(value, "Thank you.")).done
    assert [name for name, _ in client.calls].count("ResolutionReview") == 1
    assert not value.planner.completed


def test_planner_input_has_one_copy_of_document_values_and_bounded_raw_history():
    from app.delegate import _steer_payload

    value = state()
    for index in range(12):
        value.observe_receiver(f"Administrative update {index}.")
    value.observe_receiver("Which medication are they taking?")
    payload = json.loads(_steer_payload(value, "Which medication are they taking?"))
    serialized = json.dumps(payload)
    assert serialized.count("Exampleton") == 1
    assert len(payload["receiver_turns"]) <= 2
    assert payload["current_receiver_turn"]["source_id"] not in {
        row["source_id"] for row in payload["receiver_turns"]
    }
    assert list(payload)[0] == "approved_sources"
    assert "receptionist_just_said" not in payload and "conversation_roles" not in payload


def test_resolution_collection_precedes_action_in_the_model_schema():
    from app.steer_planner import PlannerTurn

    assert list(PlannerTurn.model_json_schema()["properties"]) == ["resolutions", "action"]


def test_reply_metadata_does_not_imply_a_human_must_answer_routine_fees():
    from app.delegate import _steer_payload
    from tests.test_autonomous_options import state as autonomous_state

    value = autonomous_state("Book an appointment with Dr. Rao.")
    value.observe_receiver("The visit fee is ₹800. Shall we proceed?")
    payload = json.loads(_steer_payload(value, value.planner.receiver[-1].text))
    assert payload["current_receiver_turn"]["expects_reply"] is True
    assert "requires_caller_answer" not in payload["current_receiver_turn"]
    assert payload["decision_authority"]["omitted_preferences"] == "open"
    assert payload["decision_authority"]["current_terms_objection"] is None
    assert payload["goals"][0]["resolved"] is False


def test_decision_authority_keeps_an_explicit_fee_constraint_visible():
    from app.delegate import _steer_payload
    from tests.test_autonomous_options import state as autonomous_state

    value = autonomous_state("Book an appointment. Budget ₹500.")
    value.observe_receiver("The visit fee is ₹800. Shall we proceed?")
    payload = json.loads(_steer_payload(value, value.planner.receiver[-1].text))
    assert payload["decision_authority"]["current_terms_objection"] == "unapproved_price"


async def test_valid_complete_receiver_proof_wins_over_stale_accept_action():
    class StaleAction:
        async def complete_structured(self, system, user, model):
            payload = json.loads(user)
            source = payload["current_receiver_turn"]
            return model.model_validate(
                {
                    "resolutions": [
                        {
                            "goal_id": "goal:0",
                            "source_id": source["source_id"],
                            "quote": source["text"],
                        }
                    ],
                    "action": {
                        "kind": "accept_offer",
                        "goal_id": "goal:0",
                        "source_id": "receiver:stale",
                        "quote": "Monday at 9pm",
                    },
                }
            )

    value = current()
    decision = await Brain(StaleAction()).reply(value, PROOF)
    assert decision.done and decision.kind == "close"
    assert value.planner.completed and not value.planner.pending
