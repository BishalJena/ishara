"""An unnecessary model handoff cannot hide clear approved labelled facts."""

import json

import pytest

from app.delegate import Brain
from tests.test_approved_context_repair import state


class UnneededCaller:
    def __init__(self):
        self.calls = 0

    async def complete_structured(self, system, user, model):
        self.calls += 1
        payload = json.loads(user)
        return model.model_validate(
            {
                "resolutions": [],
                "action": {
                    "kind": "need_caller",
                    "question_id": payload["current_receiver_turn"]["source_id"],
                },
            }
        )


@pytest.mark.parametrize("steer", [True, False])
@pytest.mark.parametrize("present", [True, False])
@pytest.mark.parametrize(
    ("question", "text", "expected"),
    [
        (
            "Is the patient registered? What is their patient ID?",
            "Patient ID: DEMO-20417",
            "DEMO-20417",
        ),
        ("What are the allergies?", "Allergies: Penicillin", "Penicillin"),
        ("What is their date of birth?", "Date of birth: 14 February 1993", "14 February 1993"),
        ("What is the doctor's name?", "Doctor name: Dr. Morgan Reed", "Dr. Morgan Reed"),
    ],
)
async def test_known_exact_fact_is_retrieved_before_unnecessary_handoff(
    steer, present, question, text, expected
):
    current, model = state(steer=steer, present=present, text=text), UnneededCaller()
    reply = await Brain(model).reply(current, question)
    assert reply.kind == "share" and reply.say == expected and not reply.done
    assert reply.source == "context"
    assert model.calls == 1 and not current.planner.pending
    assert "registered" not in reply.say.lower() if "ID" in question else True


@pytest.mark.parametrize(
    ("question", "text"),
    [
        ("What are the allergies?", "Patient ID: DEMO-20417"),
        ("What is the patient's home address?", "Patient ID: DEMO-20417"),
        ("What is the doctor's name?", "Patient name: Avery Sample"),
        ("What is the doctor's name?", "Previous doctor name: Dr. Historical"),
        ("What are the allergies?", "Allergies: Penicillin\nAllergies: Latex"),
        ("What is the patient's home address?", "The patient lives at an undisclosed address."),
    ],
)
async def test_unknown_conflicting_unlabelled_or_wrong_entity_facts_still_need_the_caller(
    question, text
):
    current = state(text=text)
    reply = await Brain(UnneededCaller()).reply(current, question)
    assert reply.kind != "share" and reply.follow_up == question


async def test_conflicting_same_field_across_documents_abstains():
    from dataclasses import replace

    from app.protocol import Document

    current = state(text="Allergies: Penicillin")
    current.brief = replace(
        current.brief,
        documents=current.brief.documents
        + (Document(name="Other synthetic report", text="Allergies: Latex"),),
    )
    reply = await Brain(UnneededCaller()).reply(current, "What are the allergies?")
    assert reply.kind != "share" and reply.follow_up == "What are the allergies?"


def test_retrieval_cannot_reuse_stale_single_use_caller_facts():
    from app.approved_context import retrieve_known_fields

    sources = [
        {
            "source_id": "caller:old",
            "question_id": "receiver:old",
            "label": "Patient ID",
            "text": "DEMO-20417",
        }
    ]
    assert retrieve_known_fields(sources, "What is the patient ID?", "receiver:new") is None


async def test_compound_available_fields_are_all_retrieved_exactly():
    current = state(
        text=(
            "Patient ID: DEMO-20417\nAllergies: Penicillin\n"
            "Date of birth: 14 February 1993\nMedication: Exampleton 5 mg"
        )
    )
    reply = await Brain(UnneededCaller()).reply(
        current, "Please give the patient's ID, allergies, date of birth and medication."
    )
    assert reply.kind == "share"
    for value in ("DEMO-20417", "Penicillin", "14 February 1993", "Exampleton 5 mg"):
        assert value in reply.say


async def test_explicit_budget_objection_is_not_replaced_by_a_retrieved_fee_fact():
    from dataclasses import replace

    current = state(text="Fee: ₹1,800")
    current.brief = replace(current.brief, request="Book an appointment. Budget ₹800.")
    reply = await Brain(UnneededCaller()).reply(
        current, "The fee is ₹1,800. Do you accept this fee?"
    )
    assert reply.kind != "share" and not current.answers


async def test_current_doctor_is_retrieved_without_historical_or_patient_names():
    reply = await Brain(UnneededCaller()).reply(
        state(
            text=(
                "Patient name: Avery Sample\nDoctor name: Dr. Morgan Reed\n"
                "Previous doctor name: Dr. Historical"
            )
        ),
        "What is the doctor's name?",
    )
    assert reply.kind == "share" and reply.say == "Dr. Morgan Reed"


def test_current_bound_live_reply_prevents_older_document_retrieval():
    from app.approved_context import retrieve_known_fields

    sources = [
        {"source_id": "document:0", "text": "Allergies: Penicillin"},
        {"source_id": "caller:current", "question_id": "receiver:current", "text": "Latex"},
    ]
    assert retrieve_known_fields(sources, "What are the allergies?", "receiver:current") is None


@pytest.mark.parametrize("other_label", ["Family allergies", "Maternal allergies"])
async def test_similarly_labelled_family_and_patient_facts_are_ambiguous_not_merged(other_label):
    current = state(text=f"Allergies: Penicillin\n{other_label}: None")
    reply = await Brain(UnneededCaller()).reply(current, "What are the allergies?")
    assert reply.kind != "share" and reply.follow_up == "What are the allergies?"


@pytest.mark.parametrize(
    ("text", "question"),
    [
        ("Maternal allergies: Penicillin", "What are the patient's allergies?"),
        ("Allergies: Penicillin", "What are the patient's father's allergies?"),
        ("Allergies: Penicillin", "What are the allergies and patient ID?"),
    ],
)
async def test_subject_mismatch_or_unknown_requested_field_keeps_the_real_question_pending(
    text, question
):
    current = state(text=text)
    reply = await Brain(UnneededCaller()).reply(current, question)
    assert reply.kind != "share" and reply.follow_up == question
    assert question in current.planner.pending.values()
    assert "Penicillin" not in reply.say


@pytest.mark.parametrize("failure", ["timeout", "provider"])
async def test_model_unavailability_cannot_turn_a_known_identifier_into_caller_input(failure):
    from app.groq_client import GroqError

    class Unavailable:
        async def complete_structured(self, system, user, model):
            raise TimeoutError() if failure == "timeout" else GroqError("synthetic unavailable")

    current = state(text="Patient ID: DEMO-20417")
    reply = await Brain(Unavailable()).reply(
        current, "Is the patient registered and what is their patient ID?"
    )
    assert reply.kind == "share" and reply.say == "DEMO-20417"
    assert reply.source == "context" and not reply.done and not current.planner.pending
