"""Grounded non-field headings cannot poison an otherwise complete answer."""

import pytest

from app.approved_context import validate_answer
from app.steer_planner import AnswerSpan

TEXT = (
    "Patient health summary\nPatient name: Avery Sample\nPatient ID: DEMO-20417\n"
    "Registration status: Registered patient\nAllergies: Penicillin\nDoctor name: Dr. Morgan Reed\n"
    "Previous doctor name: Dr. Historical\n"
)
SOURCES = [{"source_id": "document:0", "text": TEXT}]


def answer(quotes, question="What is the patient ID?", sources=SOURCES):
    return validate_answer(
        sources,
        question,
        "receiver:1",
        [AnswerSpan(source_id="document:0", quote=quote) for quote in quotes],
    )


@pytest.mark.parametrize("heading", ["Patient health summary", "Patient"])
def test_inert_heading_is_removed_after_full_provenance_validation(heading):
    result, rejection = answer([heading, "Patient ID: DEMO-20417"])
    assert rejection is None and result == "Patient ID: DEMO-20417"


@pytest.mark.parametrize("heading", ["Patient health summary", "Patient"])
def test_heading_alone_cannot_become_an_answer(heading):
    result, rejection = answer([heading])
    assert result is None and rejection is not None


def test_heading_removal_cannot_hide_a_missing_requested_compound_fact():
    result, rejection = answer(
        ["Patient health summary", "Patient ID: DEMO-20417"],
        "What is the patient ID and what are the allergies?",
    )
    assert result is None and rejection == "requested_field"


def test_invented_extra_span_is_rejected_before_any_heading_normalization():
    result, rejection = answer(["Patient health summary", "Patient ID: DEMO-20417", "No allergy"])
    assert result is None and rejection == "source_span"


def test_unknown_extra_source_is_not_discarded_as_an_inert_heading():
    result, rejection = validate_answer(
        SOURCES,
        "What is the patient ID?",
        "receiver:1",
        [
            AnswerSpan(source_id="document:0", quote="Patient ID: DEMO-20417"),
            AnswerSpan(source_id="document:unknown", quote="Patient"),
        ],
    )
    assert result is None and rejection == "source_span"


@pytest.mark.parametrize(
    ("quote", "question", "category"),
    [
        ("Patient name: Avery Sample", "What is the doctor's name?", "entity_scope"),
        ("Previous doctor name: Dr. Historical", "What is the doctor's name?", "historical_field"),
    ],
)
def test_actual_wrong_entity_or_historical_fields_are_never_pruned(quote, question, category):
    result, rejection = answer(["Patient health summary", "Dr. Morgan Reed", quote], question)
    assert result is None and rejection == category


def test_stale_single_use_caller_binding_is_checked_before_heading_normalization():
    sources = SOURCES + [
        {"source_id": "caller:old", "text": "Patient", "question_id": "receiver:old"}
    ]
    result, rejection = validate_answer(
        sources,
        "What is the patient ID?",
        "receiver:1",
        [
            AnswerSpan(source_id="document:0", quote="Patient ID: DEMO-20417"),
            AnswerSpan(source_id="caller:old", quote="Patient"),
        ],
    )
    assert result is None and rejection == "question_binding"
