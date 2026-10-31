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
        profile=Profile(
            name="Avery Sample", documents=[Document(name="Synthetic report", text=text)]
        ),
        request="Book a routine appointment with Dr. Morgan Reed using my report.",
    )
    return DelegateState(
        brief_from(request, build_brief(request)),
        attended=False,
        steer=steer,
        opened=True,
        caller_available=present,
    )


class Selected:
    def __init__(self, quotes=(), kind="answer_question", source="document:0", resolutions=()):
        self.quotes, self.kind, self.source = quotes, kind, source
        self.resolutions = list(resolutions)
        self.payloads = []

    async def complete_structured(self, system, user, model):
        payload = json.loads(user)
        self.payloads.append(payload)
        pending = payload["pending_receiver_questions"]
        action = {"kind": self.kind}
        if self.kind in {"answer_question", "need_caller"}:
            action["question_id"] = next(reversed(pending), "receiver:0")
        if self.kind == "answer_question":
            action["spans"] = [{"source_id": self.source, "quote": quote} for quote in self.quotes]
        return model.model_validate({"action": action, "resolutions": self.resolutions})


@pytest.mark.parametrize("steer", [True, False], ids=["steer", "delegated"])
@pytest.mark.parametrize("present", [True, False], ids=["present", "absent"])
@pytest.mark.parametrize(
    ("question", "quotes"),
    [
        ("Do they have any allergy?", ["Penicillin"]),
        ("What is the patient ID?", ["DEMO-20417"]),
        ("What is their date of birth?", ["14 February 1993"]),
        ("Which medication are they taking?", ["Exampleton 5 mg each morning"]),
        ("What is the doctor's name?", ["Dr. Morgan Reed"]),
        (
            "Can you tell me if they had any allergy or what was the blood pressure "
            "at their last checkup?",
            ["Allergies: Penicillin", "Last visit: 12 August 2026 BP 138/88"],
        ),
        (
            "Are they a registered patient, and what is their registration number?",
            ["Registration status: Registered patient", "Patient ID: DEMO-20417"],
        ),
    ],
)
async def test_supplied_document_facts_answer_without_live_intervention(
    steer, present, question, quotes
):
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
    reply = await Brain(Selected(["Avery Sample"], source="name")).reply(
        state(), "What is the doctor's name?"
    )
    assert "Avery Sample" not in reply.say


async def test_compound_answer_cannot_silently_drop_the_second_requested_field():
    question = "What are the allergies and patient ID?"
    reply = await Brain(Selected(["Penicillin"])).reply(state(present=True), question)
    assert reply.kind == "share" and reply.source == "context"
    assert "Penicillin" in reply.say and "DEMO-20417" in reply.say


async def test_split_label_and_value_document_is_supported():
    reply = await Brain(Selected(["Penicillin"])).reply(
        state(text="Allergies:\nPenicillin\nPatient ID:\nDEMO-20417"), "Any allergies?"
    )
    assert reply.kind == "share" and reply.say == "Penicillin"


async def test_multiple_source_spans_are_not_limited_to_eighty_characters():
    value = (
        "A documented nonurgent scheduling preference supplied by the caller "
        "in a longer descriptive sentence."
    )
    reply = await Brain(Selected([value])).reply(
        state(text=f"Scheduling preference: {value}"), "What is the scheduling preference?"
    )
    assert reply.kind == "share" and reply.say == value


async def test_current_request_is_not_overridden_by_a_historical_document_field():
    current = state(text="Previous doctor name: Dr. Historical\nPatient name: Avery Sample")
    reply = await Brain(Selected(["Dr. Morgan Reed"], source="request")).reply(
        current, "What is the doctor's name?"
    )
    assert reply.kind == "share" and reply.say == "Dr. Morgan Reed"


async def test_patient_and_doctor_names_can_be_answered_together():
    reply = await Brain(
        Selected(["Patient name: Avery Sample", "Doctor name: Dr. Morgan Reed"])
    ).reply(state(), "What is the patient's name and the doctor's name?")
    assert reply.kind == "share" and "Avery Sample" in reply.say and "Morgan Reed" in reply.say


async def test_free_prose_remains_available_beside_labelled_rows():
    current = state(
        text=(
            "Patient ID: DEMO-20417\nInstructions: Bring identification.\n"
            "The patient prefers a home visit."
        )
    )
    reply = await Brain(Selected(["The patient prefers a home visit."])).reply(
        current, "Does the patient prefer a home visit?"
    )
    assert reply.kind == "share" and reply.say == "The patient prefers a home visit."


@pytest.mark.parametrize("mode", ["steer", "delegated"])
def test_an_accepted_offer_never_becomes_completed_notes_without_receiver_confirmation(mode):
    from app.delegate import build_notes
    from app.protocol import TranscriptEntry

    current = state(steer=mode == "steer")
    notes = build_notes(
        "synthetic-call",
        current.brief,
        [
            TranscriptEntry(
                speaker="receptionist", text="I can book an appointment. Shall I proceed?", at=1
            ),
            TranscriptEntry(speaker="agent", text="Yes, please proceed.", at=2),
        ],
        ["Yes, please proceed."],
        None,
        True,
        promised_callback=False,
        mode=mode,
        goal_completed=False,
    )
    assert notes.outcome == "unclear"


@pytest.mark.parametrize("steer", [True, False])
async def test_four_requested_facts_are_shared_in_one_natural_turn_without_completing_the_goal(
    steer,
):
    quotes = [
        "Patient ID: DEMO-20417",
        "Allergies: Penicillin",
        "Date of birth: 14 February 1993",
        "Medication: Exampleton 5 mg each morning",
    ]
    current = state(steer=steer)
    reply = await Brain(Selected(quotes)).reply(
        current, "What are the patient ID, allergies, date of birth, and medication?"
    )
    assert reply.kind == "share" and not reply.done and reply.follow_up is None
    assert all(quote in reply.say for quote in quotes)
    assert not current.planner.completed


async def test_a_question_followed_by_a_hold_is_answered_instead_of_suppressed():
    inference = Selected(["Allergies: Penicillin"])
    reply = await Brain(inference).reply(state(), "What are the allergies? Please hold.")
    assert reply.kind == "share" and inference.payloads


async def test_new_context_keeps_attended_legacy_time_choices_explicit():
    current = state(steer=False, present=True)
    current.attended = True
    inference = Selected(["Allergies: Penicillin"])
    reply = await Brain(inference).reply(current, "We have 10 am tomorrow. Does that work?")
    assert reply.ask is not None and not inference.payloads and not reply.done


async def test_a_legacy_unattended_brief_still_answers_supplied_document_facts():
    request = BriefRequest(
        purpose="doctor_appointment",
        profile=Profile(
            name="Avery Sample", documents=[Document(name="Synthetic report", text=REPORT)]
        ),
    )
    current = DelegateState(brief_from(request, build_brief(request)), attended=False, opened=True)
    reply = await Brain(Selected(["DEMO-20417"])).reply(current, "What is the patient ID?")
    assert reply.kind == "share" and not reply.done and reply.say == "DEMO-20417"


async def test_completion_with_a_final_receiver_question_keeps_the_question_open_until_answered():
    from dataclasses import replace

    current = state(text="Access instructions: Use the side gate")
    current.brief = replace(current.brief, request="Arrange a plumber visit to repair the leak.")
    proof = "Your plumber visit to repair the leak is booked."
    heard = proof + " What access instructions should the plumber follow?"
    inference = Selected(
        ["Access instructions: Use the side gate"],
        resolutions=[
            {
                "goal_id": "goal:0",
                "source_id": "receiver:0",
                "quote": proof,
            }
        ],
    )
    reply = await Brain(inference).reply(current, heard)
    assert reply.kind == "share" and not reply.done and "side gate" in reply.say
    assert current.planner.completed
    assert current.planner.goals[0].evidence.text == proof
    closing = await Brain(inference).reply(current, "Thank you.")
    assert closing.done and closing.kind == "close"


async def test_relevant_source_spans_are_not_rejected_by_a_redundant_word_limit():
    labels = ["Access", "Timing", "Preference", "Instructions"]
    value = " ".join(["supplied"] * 23)
    quotes = [f"{label}: {value}" for label in labels]
    current = state(text="\n".join(quotes))
    reply = await Brain(Selected(quotes)).reply(
        current, "What are access, timing, preference and instructions?"
    )
    assert len(reply.say.split()) > 80 and reply.kind == "share" and not reply.done


@pytest.mark.parametrize(
    "closing", ["Anything else?", "Is there anything else you would like to know?"]
)
async def test_a_pure_closing_invitation_never_becomes_a_missing_caller_fact(closing):
    from app.steer_planner import ReceiverTurn

    current = state()
    current.planner.initialize(current.brief.request)
    current.planner.goals[0].evidence = ReceiverTurn("receiver:proof", "The request is confirmed.")

    class Finish:
        async def complete_structured(self, system, user, model):
            return model.model_validate(
                {"action": {"kind": "finish", "blocked": False}, "resolutions": []}
            )

    reply = await Brain(Finish()).reply(current, closing)
    assert reply.done and reply.follow_up is None and not current.planner.pending


async def test_a_closing_invitation_does_not_hide_a_substantive_fact_question():
    current = state()
    reply = await Brain(Selected(["Allergies: Penicillin"])).reply(
        current, "Is there anything else you need? What are the patient's allergies?"
    )
    assert reply.kind == "share" and not reply.done and "Penicillin" in reply.say


async def test_a_named_service_person_does_not_also_require_the_callers_name():
    reply = await Brain(Selected(["Jordan"])).reply(
        state(text="Plumber name: Jordan"), "What is the plumber's name?"
    )
    assert reply.kind == "share" and reply.say == "Jordan"


async def test_two_named_service_people_remain_independent_required_facts():
    document = "Plumber name: Jordan\nElectrician name: Taylor"
    question = "What are the plumber's name and the electrician's name?"
    complete = await Brain(Selected(["Jordan", "Taylor"])).reply(state(text=document), question)
    partial = await Brain(Selected(["Jordan"])).reply(state(text=document), question)
    assert complete.kind == "share" and "Jordan" in complete.say and "Taylor" in complete.say
    assert partial.kind == "share" and partial.source == "context"
    assert "Jordan" in partial.say and "Taylor" in partial.say


async def test_explicit_caller_and_service_names_cannot_silently_drop_the_caller():
    question = "What are the patient's name and the plumber's name?"
    reply = await Brain(Selected(["Jordan"])).reply(
        state(text="Patient name: Avery Sample\nPlumber name: Jordan"), question
    )
    assert reply.kind == "share" and reply.source == "context"
    assert "Avery Sample" in reply.say and "Jordan" in reply.say


async def test_an_unknown_service_person_cannot_borrow_the_profile_name():
    reply = await Brain(Selected(["Avery Sample"], source="name")).reply(
        state(text="Category: Ordinary"), "What is the plumber's name?"
    )
    assert "Avery Sample" not in reply.say


async def test_semantic_arrangement_confirmation_does_not_require_a_completed_verb_template():
    from dataclasses import replace

    current = state()
    current.brief = replace(current.brief, request="Arrange a plumber visit to repair the leak.")
    heard = "I'll come Monday at 9 pm. You're all set."

    class Confirm:
        async def complete_structured(self, system, user, model):
            payload = json.loads(user)
            return model.model_validate(
                {
                    "resolutions": [
                        {
                            "goal_id": "goal:0",
                            "source_id": payload["current_receiver_turn"]["source_id"],
                            "quote": heard,
                        }
                    ],
                    "action": {"kind": "finish", "blocked": False},
                }
            )

    reply = await Brain(Confirm()).reply(current, heard)
    assert reply.done and current.planner.completed
    assert current.planner.goals[0].evidence.text == heard
    assert "repaired" not in current.planner.goals[0].evidence.text


@pytest.mark.parametrize(
    ("task_request", "question", "answer"),
    [
        ("Ask what the membership fee is.", "What is the membership fee?", "₹800"),
        ("Ask when the plumber can visit.", "When can you come?", "Monday"),
        ("Ask whether the library opens on Sundays.", "Do you open on Sundays?", "Yes"),
    ],
)
async def test_short_receiver_answers_use_dialogue_context_without_becoming_caller_facts(
    task_request, question, answer
):
    from dataclasses import replace

    from app.delegate import Exchange

    current = state()
    current.brief = replace(current.brief, request=task_request)
    current.exchanges.append(Exchange("I can help.", question))
    seen = []

    class Answered:
        async def complete_structured(self, system, user, model):
            payload = json.loads(user)
            seen.append(payload)
            return model.model_validate(
                {
                    "resolutions": [
                        {
                            "goal_id": "goal:0",
                            "source_id": payload["current_receiver_turn"]["source_id"],
                            "quote": answer,
                        }
                    ],
                    "action": {"kind": "finish", "blocked": False},
                }
            )

    reply = await Brain(Answered()).reply(current, answer)
    assert reply.done and current.planner.completed
    assert seen[0]["last_agent_lines"][-1] == question
    assert question not in [source["text"] for source in seen[0]["approved_sources"]]
