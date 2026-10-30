"""Steer calls (CallMode "steer"): the agent runs the call from a typed request, the
present user may step in by typing or signing, and nothing is agreed, shared or
invented outside the request.

Driven like test_delegate.py: the rule brain, the real CallManager, the real custom-LLM
endpoint and the app WebSocket, with the fake Bolna recording what would be spoken.
"""

from __future__ import annotations

import contextlib
from functools import partial

import pytest

from app.calls import FILLER_GAP_S, CallManager, steer_window_s
from app.delegate import (
    ANOTHER_TIME_LINE,
    CALLBACK_LINE,
    CLOSE_LINE,
    DEFER_LINE,
    FILLERS,
    TIMES_LINE,
    Brief,
    DelegateState,
    RuleBrain,
    build_brief,
)
from app.main import create_app
from app.protocol import BriefRequest, Detail, Profile, StartCallRequest
from app.validator import tidy, validate_polish
from tests.conftest import make_settings
from tests.test_calls import CLINIC, PHARMACY, FakeBolna, FakeComposer
from tests.test_delegate import AUTH, Flow

REQUEST = "Book a check-up next week, mornings only. Tuesday or Wednesday is fine."
PROFILE = {
    "name": "Bishal Jena",
    "details": [{"label": "Date of birth", "value": "12 March 1998"}],
}


def steer_brief(request: str | None = REQUEST, details: list[Detail] | None = None) -> Brief:
    profile = Profile(name="Bishal Jena", details=details or [])
    body = BriefRequest(purpose="doctor_appointment", profile=profile, request=request)
    response = build_brief(body)
    from app.delegate import brief_from

    return brief_from(body, response)


def steer_state(brief: Brief | None = None, opened: bool = True) -> DelegateState:
    state = DelegateState(brief or steer_brief(), attended=False, steer=True)
    state.opened = opened
    return state


# ---- protocol ----


def test_start_call_needs_exactly_one_recipient() -> None:
    with pytest.raises(ValueError):
        StartCallRequest(purpose="doctor_appointment")
    with pytest.raises(ValueError):
        StartCallRequest(purpose="doctor_appointment", contact_id="clinic", phone_number=CLINIC)
    assert StartCallRequest(purpose="doctor_appointment", phone_number=CLINIC).contact_id is None


# ---- the brief from a typed request ----


def test_brief_carries_the_request_and_its_times() -> None:
    brief = steer_brief()
    assert "Request: " + REQUEST in brief.text
    assert brief.constraints == ("preferred time: on Tuesday or Wednesday in the morning",)
    assert brief.days == {"tuesday", "wednesday"}
    assert brief.parts == {"morning"}
    assert "Date of birth" not in brief.text  # no details given here


def test_brief_lists_approved_details_by_label_only() -> None:
    brief = steer_brief(details=[Detail(label="Date of birth", value="12 March 1998")])
    assert "May share: name (Bishal Jena), Date of birth." in brief.text
    assert "12 March" not in brief.text


def test_request_without_times_pins_nothing() -> None:
    brief = steer_brief("Ask whether they take walk-ins.")
    assert brief.constraints == ()
    assert brief.days == frozenset() and brief.parts == frozenset()


# ---- the rule brain in steer mode ----


def test_accepts_an_offer_that_fits_the_request() -> None:
    decision = RuleBrain().decide(steer_state(), "We have Wednesday at 10:30. Does that work?")
    assert decision.kind == "accept"
    assert decision.say == "Yes, 10:30 wednesday works. Thank you."
    assert not decision.done  # the receptionist still has to confirm


def test_declines_an_offer_outside_the_request_with_the_preference() -> None:
    decision = RuleBrain().decide(steer_state(), "We have Wednesday at 4 pm. Does that work?")
    assert decision.kind == "decline"
    assert decision.say == (
        "No, 4 pm wednesday doesn't work, sorry. "
        "Is there anything on Tuesday or Wednesday in the morning?"
    )


def test_declines_a_day_the_request_did_not_allow() -> None:
    decision = RuleBrain().decide(steer_state(), "How about Friday at 9 am?")
    assert decision.kind == "decline"
    assert decision.say.startswith("No, 9 am friday doesn't work")


def test_a_request_without_times_accepts_any_offer() -> None:
    state = steer_state(steer_brief("Book a check-up, please."))
    decision = RuleBrain().decide(state, "We have Friday at 4 pm. Does that work?")
    assert decision.kind == "accept"


def test_shares_an_approved_detail_and_nothing_else() -> None:
    state = steer_state(steer_brief(details=[Detail(label="Date of birth", value="12 March 1998")]))
    brain = RuleBrain()
    assert (
        brain.decide(state, "Can I get his date of birth?").say == "Date of birth is 12 March 1998."
    )
    assert brain.decide(state, "And his DOB?").kind == "share"
    deferred = brain.decide(state, "And his insurance number, please?")
    assert deferred.kind == "defer"
    assert deferred.say == DEFER_LINE
    assert deferred.follow_up == "And his insurance number, please?"
    assert not deferred.done  # the call goes on


def test_an_open_when_question_answers_with_the_request_or_asks_for_times() -> None:
    brain = RuleBrain()
    answered = brain.decide(steer_state(), "What day would you like?")
    assert answered.kind == "time"
    assert answered.say.startswith("On Tuesday or Wednesday in the morning, please.")
    assert (
        brain.decide(steer_state(steer_brief("Book a check-up.")), "When suits you?").say
        == TIMES_LINE
    )


def test_a_fitting_day_without_a_time_asks_for_the_times() -> None:
    decision = RuleBrain().decide(steer_state(), "Could you do Tuesday?")
    assert decision.kind == "time"
    assert decision.say == f"Tuesday works. {TIMES_LINE}"


def test_no_slots_asks_once_for_another_time_then_promises_a_callback() -> None:
    state = steer_state()
    brain = RuleBrain()
    assert brain.decide(state, "We're fully booked that week.").say == ANOTHER_TIME_LINE
    second = brain.decide(state, "Nothing free at all, sorry.")
    assert second.say == CALLBACK_LINE and second.done


def test_confirmation_closes() -> None:
    decision = RuleBrain().decide(steer_state(), "That's booked for you.")
    assert decision.say == CLOSE_LINE and decision.done and decision.kind == "close"


def test_fillers_never_repeat_back_to_back() -> None:
    state = steer_state()
    said = [state.next_filler() for _ in range(12)]
    assert all(a != b for a, b in zip(said, said[1:], strict=False))
    assert set(said) <= set(FILLERS)


# ---- polishing typed lines ----


def test_tidy_capitalises_and_punctuates() -> None:
    assert tidy("  can we   do 11 instead ") == "Can we do 11 instead."
    assert tidy("thanks!") == "Thanks!"


def test_polish_may_reuse_the_users_and_receptionists_facts_but_add_none() -> None:
    caption = "We have Tuesday at 4 pm."
    assert (
        validate_polish("Could we make it 11 instead, please?", "can we do 11 instead", caption)
        == []
    )
    assert (
        validate_polish("Could we do Tuesday at 11 instead?", "can we do 11 instead", caption) == []
    )
    assert "invented day: friday" in validate_polish(
        "Could we do Friday at 11 instead?", "can we do 11 instead", caption
    )
    assert "invented number or time: 12" in validate_polish("Make it 12.", "can we do 11", caption)
    assert validate_polish("Yes, that works.", "what time is it", caption) == [
        "adds agreement the user did not type"
    ]


# ---- the whole call through the manager ----


def build_steer_flow(stack: contextlib.ExitStack, **manager_options) -> Flow:
    settings = make_settings(allowed_recipients=f"clinic={CLINIC},pharmacy={PHARMACY}")
    bolna, composer = FakeBolna(), FakeComposer()
    options = {
        "delivery_timeout_s": 10.0,
        "end_after_done_s": 60.0,
        "steer_window": lambda _text: 0.3,
        "user_preview_s": 0.2,
        "filler_gap_s": FILLER_GAP_S,
    }
    options.update(manager_options)
    manager = CallManager(settings, composer, bolna, **options)

    def in_flight_text(run_id: str) -> str | None:
        session = manager._sessions[manager._call_by_run[run_id]]
        return session.in_flight.approved_text if session.in_flight is not None else None

    bolna.in_flight_text = in_flight_text
    app = create_app(settings, composer=composer, bolna=bolna, ledger=manager)
    client = stack.enter_context(__import__("fastapi.testclient").testclient.TestClient(app))
    return Flow(client, manager, bolna)


@pytest.fixture
def steer():
    with contextlib.ExitStack() as stack:
        yield partial(build_steer_flow, stack)


def start_steer(f: Flow, *, recipient: dict | None = None, request: str = REQUEST) -> str:
    body = {"purpose": "doctor_appointment", "profile": PROFILE, "request": request}
    response = f.client.post("/briefs", json=body, headers=AUTH)
    assert response.status_code == 200, response.text
    brief_id = response.json()["brief_id"]
    start = {
        **(recipient or {"contact_id": "clinic"}),
        "purpose": "doctor_appointment",
        "mode": "steer",
        "brief_id": brief_id,
    }
    response = f.client.post("/calls", json=start, headers=AUTH)
    assert response.status_code == 200, response.text
    assert response.json()["mode"] == "steer"
    return response.json()["call_id"]


def test_a_pasted_number_dials_only_when_it_is_allowlisted(steer) -> None:
    f = steer()
    start_steer(f, recipient={"phone_number": PHARMACY})
    assert f.bolna.started[-1][0] == PHARMACY
    body = {"phone_number": "+919999999999", "purpose": "doctor_appointment"}
    response = f.client.post("/calls", json=body, headers=AUTH)
    assert response.status_code == 403
    assert "9999" not in response.text
    assert len(f.bolna.started) == 1


def test_away_user_hears_nothing_the_agent_speaks_at_once(steer) -> None:
    f = steer()
    call_id = start_steer(f)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        assert f.receive(ws)["type"] == "status"
        f.live(call_id)
        f.drain_until(ws, "caption")  # disclosure
        assert f.speak_last(call_id).startswith(
            "I'd like to book a doctor's appointment for Bishal Jena"
        )
        # No presence message: the app is not in front, so the line is spoken straight away.
        said = f.listen_turn(call_id, "We have Wednesday at 10:30. Does that work?")
        assert said == "Yes, 10:30 wednesday works. Thank you."
        kinds = [m["type"] for m in every(f, ws)]
        assert "proposal" not in kinds


def test_present_user_sees_the_proposal_and_it_is_spoken_when_the_window_runs_out(steer) -> None:
    f = steer()
    call_id = start_steer(f)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        assert f.receive(ws)["type"] == "status"
        f.live(call_id)
        f.speak_last(call_id)
        ws.send_json({"type": "presence", "present": True})
        said = f.listen_turn(call_id, "We have Wednesday at 10:30. Does that work?")
        assert said == "Yes, 10:30 wednesday works. Thank you."
        messages = every(f, ws)
        proposal = next(m for m in messages if m["type"] == "proposal")
        assert proposal["text"] == said and proposal["origin"] == "agent"
        assert proposal["window_s"] == 0.3
        resolved = next(m for m in messages if m["type"] == "proposal_resolved")
        assert resolved["turn_id"] == proposal["turn_id"] and resolved["outcome"] == "spoken"
        agent_lines = [
            m["text"] for m in messages if m["type"] == "caption" and m["speaker"] == "agent"
        ]
        assert said in agent_lines


def test_holding_drops_the_line_and_covers_until_the_user_speaks(steer) -> None:
    f = steer(steer_window=lambda _text: 2.0)
    call_id = start_steer(f)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        assert f.receive(ws)["type"] == "status"
        f.live(call_id)
        f.speak_last(call_id)
        ws.send_json({"type": "presence", "present": True})

        # The listen request blocks for the window; hold it from another thread.
        import threading

        heard = "We have Wednesday at 4 pm. Does that work?"
        result: list[str] = []
        worker = threading.Thread(target=lambda: result.append(f.listen_turn(call_id, heard)))
        worker.start()
        proposal = f.drain_until(ws, "proposal")
        assert proposal["text"].startswith("No, 4 pm wednesday doesn't work")
        ws.send_json({"type": "hold", "turn_id": proposal["turn_id"], "composing": True})
        worker.join(timeout=5)
        assert result and result[0] in FILLERS  # the receptionist hears a cover line
        assert f.drain_until(ws, "proposal_resolved")["outcome"] == "held"

        # While the user types, more receptionist words get at most quiet or a filler.
        assert f.listen_turn(call_id, "Hello? Are you there?") == ""  # within the gap

        ws.send_json({"type": "say", "text": "can we do 11 instead"})
        preview = f.drain_until(ws, "proposal")
        assert preview["origin"] == "user" and preview["text"] == "Can we do 11 instead."
        assert f.drain_until(ws, "proposal_resolved")["outcome"] == "spoken"
        assert f.bolna.injected[-1] == "Can we do 11 instead."
        assert f.speak_last(call_id) == "Can we do 11 instead."

    f.finish()
    notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
    assert notes["mode"] == "steer"
    assert notes["stepped_in"] == 1
    assert 'You answered: "Can we do 11 instead."' in notes["summary"]


def test_backing_out_of_composing_speaks_the_held_line_after_all(steer) -> None:
    f = steer(steer_window=lambda _text: 2.0)
    call_id = start_steer(f)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        assert f.receive(ws)["type"] == "status"
        f.live(call_id)
        f.speak_last(call_id)
        ws.send_json({"type": "presence", "present": True})
        import threading

        result: list[str] = []
        worker = threading.Thread(
            target=lambda: result.append(f.listen_turn(call_id, "How about Friday at 9 am?"))
        )
        worker.start()
        proposal = f.drain_until(ws, "proposal")
        ws.send_json({"type": "hold", "turn_id": proposal["turn_id"], "composing": True})
        worker.join(timeout=5)
        ws.send_json({"type": "hold", "turn_id": proposal["turn_id"], "composing": False})
        f.drain_until(ws, "status")  # speaking
        assert f.bolna.injected[-1] == proposal["text"]
        assert f.speak_last(call_id) == proposal["text"]


def test_looking_away_mid_window_speaks_the_line(steer) -> None:
    f = steer(steer_window=lambda _text: 2.0)
    call_id = start_steer(f)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        assert f.receive(ws)["type"] == "status"
        f.live(call_id)
        f.speak_last(call_id)
        ws.send_json({"type": "presence", "present": True})
        import threading

        result: list[str] = []
        worker = threading.Thread(
            target=lambda: result.append(f.listen_turn(call_id, "We have Wednesday at 10:30."))
        )
        worker.start()
        f.drain_until(ws, "proposal")
        ws.send_json({"type": "presence", "present": False})
        worker.join(timeout=5)
        assert result == ["Yes, 10:30 wednesday works. Thank you."]
        assert f.drain_until(ws, "proposal_resolved")["outcome"] == "spoken"


def test_something_not_provided_is_deferred_and_noted(steer) -> None:
    f = steer()
    call_id = start_steer(f)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        assert f.receive(ws)["type"] == "status"
        f.live(call_id)
        f.speak_last(call_id)
        assert (
            f.listen_turn(call_id, "Can I get his date of birth?")
            == "Date of birth is 12 March 1998."
        )
        assert f.listen_turn(call_id, "And his insurance number?") == DEFER_LINE
        follow_up = f.drain_until(ws, "follow_up")
        assert follow_up["text"] == "And his insurance number?"
    f.finish()
    notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
    assert notes["follow_ups"] == ["And his insurance number?"]
    assert any("insurance" in q for q in notes["open_questions"])


def test_the_window_grows_with_the_words_to_read() -> None:
    assert steer_window_s("Yes.") == 3.75
    assert steer_window_s(" ".join(["word"] * 40)) == 8.0


def every(f: Flow, ws, timeout: float = 0.3) -> list[dict]:
    messages: list[dict] = []
    with contextlib.suppress(Exception):
        while True:
            messages.append(f.receive(ws, timeout=timeout))
    return messages
