"""Synthetic document relay regressions. No account, patient or telephone records."""

import json

import pytest

from app.delegate import Brain, DelegateState, brief_from, build_brief
from app.protocol import BriefRequest, Document, Profile

REPORT = """Patient name: Avery Sample
Patient ID: DEMO-20417
Date of birth: 14 February 1993
Allergies: Penicillin
Medication: Exampleton 5 mg each morning
Last visit: 12 August 2026 BP 138/88
Doctor name: Dr. Morgan Reed
Registration status: Registered patient
"""


def state(*, steer=True, present=False, text=REPORT):
    request = BriefRequest(
        purpose="general",
        profile=Profile(name="Avery Sample", documents=[Document(name="Synthetic report", text=text)]),
        request="Book a routine appointment with Dr. Morgan Reed using my report.",
    )
    return DelegateState(
        brief_from(request, build_brief(request)), attended=False, steer=steer,
        opened=True, caller_available=present,
    )


class Selected:
    def __init__(self, quotes=(), kind="answer_question", source="document:0"):
        self.quotes, self.kind, self.source = quotes, kind, source
        self.payloads = []

    async def complete_structured(self, system, user, model):
        payload = json.loads(user)
        self.payloads.append(payload)
        pending = payload["pending_receiver_questions"]
        action = {"kind": self.kind}
        if "spans" in model.model_json_schema()["$defs"]["AnswerQuestion"]["properties"]:
            if self.kind in {"answer_question", "need_caller"}:
                action["question_id"] = next(reversed(pending), "receiver:0")
            if self.kind == "answer_question":
                action["spans"] = [{"source_id": self.source, "quote": quote} for quote in self.quotes]
        elif self.kind == "answer_question":
            action.update(source_id=self.source, quote=self.quotes[0])
        return model.model_validate({"action": action, "resolutions": []})


@pytest.mark.parametrize("steer", [True, False], ids=["steer", "delegated"])
@pytest.mark.parametrize("present", [True, False], ids=["present", "absent"])
@pytest.mark.parametrize(("question", "quotes"), [
    ("Do they have any allergy?", ["Penicillin"]),
    ("What is the patient ID?", ["DEMO-20417"]),
    ("What is their date of birth?", ["14 February 1993"]),
    ("Which medication are they taking?", ["Exampleton 5 mg each morning"]),
    ("What is the doctor's name?", ["Dr. Morgan Reed"]),
    ("Can you tell me if they had any allergy or what was the blood pressure at their last checkup?",
     ["Allergies: Penicillin", "Last visit: 12 August 2026 BP 138/88"]),
    ("Are they a registered patient, and what is their registration number?",
     ["Registration status: Registered patient", "Patient ID: DEMO-20417"]),
])
async def test_supplied_document_facts_answer_without_live_intervention(steer, present, question, quotes):
    current = state(steer=steer, present=present)
    reply = await Brain(Selected(quotes)).reply(current, question)
    assert reply.kind == "share" and not reply.done and reply.follow_up is None
    assert all(quote in reply.say for quote in quotes)
    assert not current.planner.pending


@pytest.mark.parametrize("kind", ["wait", "need_caller"])
@pytest.mark.parametrize("heard", ["Okay.", "Right.", "One moment, I'm checking."])
async def test_neutral_acknowledgement_cannot_become_a_missing_caller_fact(kind, heard):
    current = state()
    reply = await Brain(Selected(kind=kind)).reply(current, heard)
    assert not reply.done and reply.follow_up is None
    assert not current.planner.pending


async def test_doctor_question_rejects_patient_profile_name():
    reply = await Brain(Selected(["Avery Sample"], source="name")).reply(state(), "What is the doctor's name?")
    assert "Avery Sample" not in reply.say


async def test_compound_answer_cannot_silently_drop_the_second_requested_field():
    question = "What are the allergies and patient ID?"
    reply = await Brain(Selected(["Penicillin"])).reply(state(present=True), question)
    assert reply.kind == "defer" and reply.follow_up == question


async def test_split_label_and_value_document_is_supported():
    reply = await Brain(Selected(["Penicillin"])).reply(
        state(text="Allergies:\nPenicillin\nPatient ID:\nDEMO-20417"), "Any allergies?"
    )
    assert reply.kind == "share" and reply.say == "Penicillin"


async def test_multiple_source_spans_are_not_limited_to_eighty_characters():
    value = "A documented nonurgent scheduling preference supplied by the caller in a longer descriptive sentence."
    reply = await Brain(Selected([value])).reply(
        state(text=f"Scheduling preference: {value}"), "What is the scheduling preference?"
    )
    assert reply.kind == "share" and reply.say == value
