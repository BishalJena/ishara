"""Attended Call for me (D9, version B) end to end through FakeBolna's graph runtime.

The receptionist asks an open time question, the user answers with a time word, the
receptionist offers a concrete time, the user says yes and the call is booked. FakeBolna
asks the custom LLM exactly like live Bolna (listen prompt per utterance, speak prompt
plus the event notice after each user_reply), so this covers the real speak path.
"""

from __future__ import annotations

from collections.abc import Callable

from app.delegate import PAUSE_LINE
from app.markers import DISCLOSURE, GOODBYE
from tests.e2e.test_demo_script import AUTH, CONTACT, RING_S, Harness, make_harness

__all__ = ["make_harness"]  # the fixture this module uses

PROFILE = {"name": "Riya", "callback": "the number ending 4321"}
QUESTION = "what time would you like to come in"
OFFER = "we have four pm tomorrow does that work"
TOMORROW = "Tomorrow, please. What times are available?"
YES = "Yes, 4 pm tomorrow works. Thank you."


def start_attended(harness: Harness) -> str:
    brief = harness.client.post(
        "/briefs",
        json={"purpose": "doctor_appointment", "chips": ["tomorrow"], "profile": PROFILE},
        headers=AUTH,
    )
    assert brief.status_code == 200, brief.text
    body = {
        "contact_id": CONTACT,
        "purpose": "doctor_appointment",
        "mode": "delegated",
        "brief_id": brief.json()["brief_id"],
        "attended": True,
    }
    response = harness.client.post("/calls", json=body, headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()["call_id"]


def test_open_question_signed_time_then_offer_yes_is_booked(
    make_harness: Callable[..., Harness],
) -> None:
    harness = make_harness()
    harness.fake.ring_s = RING_S
    call_id = start_attended(harness)
    opening = "I'd like to book a doctor's appointment for Riya, tomorrow."

    with harness.socket(call_id) as app:
        app.expect("status", state="in_call")
        run = harness.run_for(call_id)
        harness.idle()
        assert run.spoken == [DISCLOSURE, opening]

        assert harness.says(run, QUESTION) == PAUSE_LINE
        ask = app.expect("ask", question=QUESTION)
        assert [o["choice"] for o in ask["options"]] == ["tomorrow", "morning", "now", "wait"]
        assert run.spoken[-1] == PAUSE_LINE, "nothing is said for the user before they choose"

        app.send({"type": "answer", "ask_id": ask["ask_id"], "choice": "tomorrow"})
        app.expect("ask_resolved", spoken=TOMORROW, source="user")
        harness.idle()
        assert run.spoken[-1] == TOMORROW

        assert harness.says(run, OFFER) == PAUSE_LINE
        offer = app.expect("ask", question=OFFER)
        app.send({"type": "answer", "ask_id": offer["ask_id"], "choice": "yes"})
        app.expect("ask_resolved", spoken=YES, source="user")
        harness.idle()

        # The user's yes settled the brief: the agent adds nothing before hanging up.
        assert harness.says(run, "great you're booked for four pm tomorrow") == ""
        app.send({"type": "end"})
        app.expect("status", state="ended")
        harness.idle()

    assert run.spoken == [DISCLOSURE, opening, PAUSE_LINE, TOMORROW, PAUSE_LINE, YES, GOODBYE]
    notes = harness.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
    assert notes["outcome"] == "booked"
    assert f'You answered: "{TOMORROW}"' in notes["summary"]
    assert f'You answered: "{YES}"' in notes["summary"]
