"""Decision D9: briefs, the delegated agent's lines, asks and answers, notes.

The brain here is the rule brain (no Groq), driven through the real CallManager, the
real custom-LLM endpoint and the app WebSocket, with the fake Bolna recording what
would have been spoken. Nothing dials.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from functools import partial

import anyio
import pytest
from fastapi.testclient import TestClient

from app.bolna_agent import SPEAK_PROMPT
from app.calls import CallManager
from app.delegate import (
    CALLBACK_LINE,
    PAUSE_LINE,
    Brain,
    Brief,
    Decision,
    DelegateState,
    RuleBrain,
    build_brief,
    build_notes,
    check_line,
)
from app.main import create_app
from app.markers import (
    DISCLOSURE,
    EVENT_END_CALL,
    EVENT_USER_REPLY,
    USER_DATA_CALL_ID,
    render_marker_block,
)
from app.protocol import BriefRequest, Profile, TranscriptEntry
from fakes.fake_bolna import EVENT_NOTICE, bolna_render
from tests.conftest import APP_TOKEN, CUSTOM_LLM_TOKEN, WEBHOOK_SECRET, make_settings
from tests.test_calls import CLINIC, FakeBolna, FakeComposer

AUTH = {"Authorization": f"Bearer {APP_TOKEN}"}
LLM_AUTH = {"Authorization": f"Bearer {CUSTOM_LLM_TOKEN}"}
PROFILE = {"name": "Asha Rao", "callback": "the number ending 4321", "notes": "a persistent cough"}


def brief_request(**overrides) -> dict:
    body = {"purpose": "doctor_appointment", "chips": ["tomorrow", "morning"], "profile": PROFILE}
    body.update(overrides)
    return body


# ---- pure parts ----


def test_brief_says_only_what_the_chips_and_profile_carry() -> None:
    response = build_brief(BriefRequest(**brief_request()))
    assert response.goal == "book a doctor's appointment"
    assert response.constraints == ["preferred time: tomorrow in the morning"]
    assert "Asha Rao" in response.text and "tomorrow in the morning" in response.text
    assert "cough" in response.text and "callback number" in response.text
    assert "Will not agree to anything outside this brief" in response.text
    for word in ("Monday", "10", "Dr"):
        assert word not in response.text


def test_brief_without_time_or_notes_still_reads_well() -> None:
    response = build_brief(
        BriefRequest(purpose="doctor_appointment", chips=[], profile=Profile(name="Ravi"))
    )
    assert response.constraints == []
    assert response.text.startswith("Call on behalf of Ravi")
    assert "Preferred" not in response.text and "Reason" not in response.text


def make_brief(attended: bool = True) -> DelegateState:
    request = BriefRequest(**brief_request())
    response = build_brief(request)
    brief = Brief(
        response.text,
        response.goal,
        tuple(response.constraints),
        "Asha Rao",
        PROFILE["callback"],
        PROFILE["notes"],
        "doctor_appointment",
    )
    return DelegateState(brief, attended=attended)


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        ("We can do Thursday at 4 pm.", "invented"),  # day and time nobody said
        ("Your appointment is booked.", "booking claim"),
        ("Here's the sentence: I'd like an appointment.", "meta text"),
        ("Dr Mehta will see you.", "invented name"),
        ("", "empty"),
    ],
)
def test_check_line_rejects_what_the_brief_never_said(line: str, reason: str) -> None:
    state = make_brief()
    reasons = check_line(line, state.brief, "")
    assert reasons and any(reason in r for r in reasons), reasons


def test_check_line_allows_the_receptionists_own_facts() -> None:
    state = make_brief()
    heard = "We have 10:30 tomorrow morning with Dr Mehta."
    assert check_line("So 10:30 tomorrow morning with Dr Mehta?", state.brief, heard) == []
    # Accepting the offer is the user's answer, never the agent's own line.
    assert check_line("Yes, 10:30 tomorrow morning with Dr Mehta works.", state.brief, heard) == [
        "agrees for the user: yes"
    ]
    assert (
        check_line(
            "I'd like to book a doctor's appointment for Asha Rao, tomorrow morning.",
            state.brief,
            "",
        )
        == []
    )


def test_rule_brain_opens_with_the_brief_then_hands_proposals_to_the_user() -> None:
    state = make_brief(attended=True)
    opening = RuleBrain().decide(state, "Hello, City Clinic.")
    assert (
        opening.say
        == "I'd like to book a doctor's appointment for Asha Rao, tomorrow in the morning."
    )
    state.opened = True
    offer = RuleBrain().decide(state, "We have 4 pm tomorrow. Does that work?")
    assert offer.say == PAUSE_LINE and offer.ask is not None
    question, options = offer.ask
    assert question == "We have 4 pm tomorrow. Does that work?"
    assert [o.choice for o in options] == ["yes", "no", "wait"]
    assert options[0].spoken == "Yes, 4 pm tomorrow works. Thank you."
    assert options[1].spoken.startswith("No, 4 pm tomorrow doesn't work")


# The live transcriber writes spoken times in words; the first real Call for me
# (28 Oct) repeated its opening because "four pm" was never seen as an offer.
@pytest.mark.parametrize(
    ("heard", "proposal"),
    [
        ("we have four pm tomorrow does that work", "4 pm tomorrow"),
        ("yes at ten thirty tomorrow morning does that work", "10:30 tomorrow"),
        ("how about nine a.m. tomorrow", "9 am tomorrow"),
    ],
)
def test_rule_brain_hands_a_time_said_in_words_to_the_user(heard: str, proposal: str) -> None:
    state = make_brief(attended=True)
    state.opened = True
    offer = RuleBrain().decide(state, heard)
    assert offer.say == PAUSE_LINE and offer.ask is not None
    assert offer.ask[1][0].spoken == f"Yes, {proposal} works. Thank you."


def test_check_line_accepts_a_proposal_the_receptionist_said_in_words() -> None:
    state = make_brief()
    assert check_line("4 pm tomorrow", state.brief, "we have four pm tomorrow") == []
    assert check_line("5 pm tomorrow", state.brief, "we have four pm tomorrow") != []


def test_notes_list_an_offer_said_in_words() -> None:
    state = make_brief(attended=False)
    entries = [
        TranscriptEntry(speaker="receptionist", text="we have four pm tomorrow", at=1.0),
        TranscriptEntry(speaker="agent", text=CALLBACK_LINE, at=2.0),
    ]
    notes = build_notes("c1", state.brief, entries, [], None, True, promised_callback=True)
    assert 'They offered: "we have four pm tomorrow"' in notes.summary
    assert notes.outcome == "callback"


def test_rule_brain_unattended_never_asks_and_promises_a_callback() -> None:
    state = make_brief(attended=False)
    state.opened = True
    offer = RuleBrain().decide(state, "We have 4 pm tomorrow. Does that work?")
    assert offer == Decision(CALLBACK_LINE, done=True, callback=True)


def test_rule_brain_shares_only_profile_facts() -> None:
    state = make_brief()
    state.opened = True
    assert RuleBrain().decide(state, "What is the patient's name?").say == "The name is Asha Rao."
    assert "ending 4321" in RuleBrain().decide(state, "Which number can we call you on?").say
    assert RuleBrain().decide(state, "Your appointment is booked, see you then.") == Decision(
        "Thank you for your help. Goodbye.", done=True
    )


def test_notes_quote_the_transcript_and_name_the_outcome() -> None:
    state = make_brief()
    entries = [
        TranscriptEntry(
            speaker="receptionist", text="We have 4 pm tomorrow. Does that work?", at=1.0
        ),
        TranscriptEntry(speaker="agent", text="Yes, 4 pm tomorrow works. Thank you.", at=2.0),
        TranscriptEntry(speaker="receptionist", text="Booked for 4 pm tomorrow.", at=3.0),
    ]
    notes = build_notes(
        "c1",
        state.brief,
        entries,
        ["Yes, 4 pm tomorrow works. Thank you."],
        None,
        True,
        promised_callback=False,
    )
    assert notes.outcome == "booked"
    assert notes.summary[0].startswith("Goal: book a doctor's appointment for Asha Rao")
    assert any(s.startswith("They offered:") for s in notes.summary)
    assert any(s.startswith("You answered:") for s in notes.summary)
    assert any(s.startswith("They confirmed:") for s in notes.summary)
    assert notes.open_questions == []
    unfinished = build_notes("c1", state.brief, entries, [], None, False, promised_callback=False)
    assert unfinished.ready is False and unfinished.outcome is None


def test_notes_for_a_callback_leave_an_open_question() -> None:
    state = make_brief(attended=False)
    entries = [
        TranscriptEntry(speaker="receptionist", text="Only Thursday 4 pm is free.", at=1.0),
        TranscriptEntry(speaker="agent", text=CALLBACK_LINE, at=2.0),
    ]
    notes = build_notes(
        "c1", state.brief, entries, [], "Caller to call back.", True, promised_callback=True
    )
    assert notes.outcome == "callback"
    assert notes.open_questions and "call again" in notes.open_questions[0]
    assert notes.bolna_summary == "Caller to call back."


# ---- through the backend ----


@dataclass
class Flow:
    client: TestClient
    manager: CallManager
    bolna: FakeBolna

    def brief(self, **overrides) -> str:
        response = self.client.post("/briefs", json=brief_request(**overrides), headers=AUTH)
        assert response.status_code == 200, response.text
        return response.json()["brief_id"]

    def start(self, brief_id: str | None, attended: bool) -> str:
        body = {
            "contact_id": "clinic",
            "purpose": "doctor_appointment",
            "mode": "delegated",
            "brief_id": brief_id,
            "attended": attended,
        }
        response = self.client.post("/calls", json=body, headers=AUTH)
        assert response.status_code == 200, response.text
        assert response.json()["mode"] == "delegated"
        return response.json()["call_id"]

    def live(self, call_id: str) -> None:
        payload = {
            "id": f"run-{len(self.bolna.started)}",
            "status": "in-progress",
            "telephony_data": {"to_number": CLINIC},
        }
        assert self.client.post(f"/bolna/webhook/{WEBHOOK_SECRET}", json=payload).status_code == 204

    def finish(self, summary: str | None = None) -> None:
        payload = {
            "id": f"run-{len(self.bolna.started)}",
            "status": "completed",
            "summary": summary,
        }
        assert self.client.post(f"/bolna/webhook/{WEBHOOK_SECRET}", json=payload).status_code == 204

    def listen_turn(self, call_id: str, heard: str) -> str:
        """Bolna's listen-node request after the receptionist said `heard`; returns what the
        custom LLM told Bolna to say."""
        body = {
            "model": "ishara-relay",
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": render_marker_block("listen").replace("{{ishara_call_id}}", call_id),
                },
                {"role": "user", "content": heard},
            ],
        }
        response = self.client.post("/v1/chat/completions", json=body, headers=LLM_AUTH)
        assert response.status_code == 200, response.text
        return response.json()["choices"][0]["message"]["content"]

    def speak_last(self, call_id: str) -> str:
        """Bolna's speak-node request after the latest user_reply event (a SEND or a
        delegated line), as live Bolna sends it: only the call id is filled in, plus its
        event notice. Returns what the custom LLM told Bolna to say."""
        prompt = bolna_render(SPEAK_PROMPT, {USER_DATA_CALL_ID: call_id})
        notice = EVENT_NOTICE.format(event=EVENT_USER_REPLY)
        body = {
            "model": "ishara-relay",
            "stream": False,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "system", "content": notice},
            ],
        }
        response = self.client.post("/v1/chat/completions", json=body, headers=LLM_AUTH)
        assert response.status_code == 200, response.text
        return response.json()["choices"][0]["message"]["content"]

    def receive(self, ws, timeout: float = 2.0) -> dict:
        async def next_message() -> dict:
            with anyio.fail_after(timeout):
                return await ws._send_rx.receive()

        message = ws.portal.call(next_message)
        ws._raise_on_close(message)
        return json.loads(message["text"])

    def drain_until(self, ws, kind: str) -> dict:
        for _ in range(12):
            message = self.receive(ws)
            if message["type"] == kind:
                return message
        raise AssertionError(f"no {kind} message")


def build_flow(
    stack: contextlib.ExitStack,
    ask_timeout_s: float = 5.0,
    end_after_done_s: float = 60.0,
    brain: Brain | None = None,
    allowed_recipients: str = f"clinic={CLINIC}",
    delivery_timeout_s: float = 10.0,
) -> Flow:
    settings = make_settings(allowed_recipients=allowed_recipients)
    bolna, composer = FakeBolna(), FakeComposer()
    manager = CallManager(
        settings,
        composer,
        bolna,
        delivery_timeout_s=delivery_timeout_s,
        ask_timeout_s=ask_timeout_s,
        end_after_done_s=end_after_done_s,
        brain=brain,
    )

    def in_flight_text(run_id: str) -> str | None:
        session = manager._sessions[manager._call_by_run[run_id]]
        return session.in_flight.approved_text if session.in_flight is not None else None

    bolna.in_flight_text = in_flight_text
    app = create_app(settings, composer=composer, bolna=bolna, ledger=manager)
    client = stack.enter_context(TestClient(app))
    return Flow(client, manager, bolna)


@pytest.fixture
def flow():
    with contextlib.ExitStack() as stack:
        yield partial(build_flow, stack)


def test_delegated_call_needs_an_existing_brief(flow) -> None:
    f = flow()
    body = {
        "contact_id": "clinic",
        "purpose": "doctor_appointment",
        "mode": "delegated",
        "brief_id": "nope",
        "attended": False,
    }
    assert f.client.post("/calls", json=body, headers=AUTH).status_code == 404
    assert f.bolna.started == []


def test_attended_call_speaks_the_brief_then_asks_the_user_and_speaks_the_answer(flow) -> None:
    f = flow()
    call_id = f.start(f.brief(), attended=True)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        assert f.receive(ws)["type"] == "status"
        f.live(call_id)
        f.drain_until(ws, "caption")  # the disclosure

        # The opening is already on its way to the speak node, so the listen node waits.
        assert f.listen_turn(call_id, "Hello, City Clinic, how can I help?") == ""
        assert f.drain_until(ws, "caption")["text"] == "Hello, City Clinic, how can I help?"
        opening = "I'd like to book a doctor's appointment for Asha Rao, tomorrow in the morning."
        assert f.speak_last(call_id) == opening
        assert f.bolna.replies()[0]["turn_id"] == "delegate-open"
        said_first = f.drain_until(ws, "caption")
        assert said_first["speaker"] == "agent" and said_first["text"] == opening

        said = f.listen_turn(call_id, "Sorry, what was that?")
        assert said == opening
        assert f.drain_until(ws, "caption")["text"] == "Sorry, what was that?"
        agent = f.drain_until(ws, "caption")
        assert agent["speaker"] == "agent" and agent["text"] == said

        said = f.listen_turn(call_id, "We have 4 pm tomorrow. Does that work?")
        assert said == PAUSE_LINE
        ask = f.drain_until(ws, "ask")
        assert ask["question"] == "We have 4 pm tomorrow. Does that work?"
        assert [o["choice"] for o in ask["options"]] == ["yes", "no", "wait"]
        assert ask["fallback"] == CALLBACK_LINE

        ws.send_json({"type": "answer", "ask_id": ask["ask_id"], "choice": "yes"})
        resolved = f.drain_until(ws, "ask_resolved")
        assert resolved["source"] == "user"
        assert resolved["spoken"] == "Yes, 4 pm tomorrow works. Thank you."
        # The answer went to Bolna through the verbatim speak node, exactly like a SEND.
        assert f.bolna.injected[-1] == "Yes, 4 pm tomorrow works. Thank you."
        assert f.bolna.replies()[-1]["turn_id"].startswith("ask-")
        assert f.speak_last(call_id) == "Yes, 4 pm tomorrow works. Thank you."

    f.finish(summary="Appointment agreed for 4 pm tomorrow.")
    notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
    assert notes["ready"] is True and notes["mode"] == "delegated"
    assert notes["outcome"] == "booked"
    assert notes["bolna_summary"] == "Appointment agreed for 4 pm tomorrow."
    speakers = [(e["speaker"], e["text"]) for e in notes["transcript"]]
    assert ("receptionist", "We have 4 pm tomorrow. Does that work?") in speakers
    assert ("agent", PAUSE_LINE) in speakers


OPENING = "I'd like to book a doctor's appointment for Asha Rao, tomorrow in the morning."


def agent_captions(messages: list[dict]) -> list[str]:
    return [m["text"] for m in messages if m["type"] == "caption" and m["speaker"] == "agent"]


def every_message(f: Flow, ws, timeout: float = 0.3) -> list[dict]:
    """Every message the app gets until it has been quiet for `timeout` seconds."""
    seen: list[dict] = []
    with contextlib.suppress(TimeoutError):
        while True:
            seen.append(f.receive(ws, timeout=timeout))
    return seen


# Issue #59: the app got only `spoken {turn_id: "delegate-open"}` for the opening, never
# its words, so the user saw the disclosure and then the receptionist's reply.
def test_the_opening_shows_as_an_agent_caption_once_bolna_has_said_it(flow) -> None:
    f = flow()
    call_id = f.start(f.brief(), attended=True)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        assert f.receive(ws)["type"] == "status"
        f.live(call_id)
        before = every_message(f, ws)
        # Injected into the speak node but not said yet: nothing about it on screen.
        assert agent_captions(before) == [DISCLOSURE]
        assert f.speak_last(call_id) == OPENING
        after = every_message(f, ws)
        assert agent_captions(after) == [OPENING]
        caption = next(m for m in after if m["type"] == "caption")
        spoken = next(m for m in after if m["type"] == "spoken")
        assert spoken["turn_id"] == "delegate-open"
        assert after.index(caption) < after.index(spoken)
        assert caption["at"] > 0


def test_an_opening_bolna_never_says_never_shows_as_said(flow) -> None:
    f = flow(delivery_timeout_s=0.1)
    call_id = f.start(f.brief(), attended=True)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        assert f.receive(ws)["type"] == "status"
        f.live(call_id)
        seen = every_message(f, ws)
        assert {"type": "not_delivered", "turn_id": "delegate-open"}.items() <= next(
            m for m in seen if m["type"] == "not_delivered"
        ).items()
        # The speak node asks too late: the turn has expired, nothing is said or shown.
        assert f.speak_last(call_id) == ""
        seen += every_message(f, ws)
    assert agent_captions(seen) == [DISCLOSURE]


def test_settled_call_says_and_asks_nothing_new_before_hanging_up(flow) -> None:
    f = flow()
    call_id = f.start(f.brief(), attended=True)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        assert f.receive(ws)["type"] == "status"
        f.live(call_id)
        f.speak_last(call_id)  # Bolna says the opening
        f.listen_turn(call_id, "We have 4 pm tomorrow. Does that work?")
        ask = f.drain_until(ws, "ask")
        ws.send_json({"type": "answer", "ask_id": ask["ask_id"], "choice": "yes"})
        f.drain_until(ws, "ask_resolved")

        # Found by the local demo: the receptionist then offers another time.
        assert f.listen_turn(call_id, "Yes, 10:30 tomorrow morning.") == ""
        kinds = []
        with contextlib.suppress(Exception):
            for _ in range(6):
                kinds.append(f.receive(ws, timeout=0.3)["type"])
        assert "ask" not in kinds


def test_unattended_call_never_asks_and_hangs_up_after_the_callback_line(flow) -> None:
    f = flow(end_after_done_s=0.05)
    call_id = f.start(f.brief(), attended=False)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        assert f.receive(ws)["type"] == "status"
        f.live(call_id)
        f.speak_last(call_id)  # Bolna says the opening
        said = f.listen_turn(call_id, "We only have Thursday at 4 pm. Does that work?")
        assert said == CALLBACK_LINE
        # No ask reaches the app; the call ends on its own shortly after.
        kinds = []
        with contextlib.suppress(Exception):
            for _ in range(10):
                kinds.append(f.receive(ws, timeout=1.0)["type"])
        assert "ask" not in kinds
        assert any(e == EVENT_END_CALL for _, e, _ in f.bolna.events)
    notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
    assert notes["outcome"] == "callback"
    assert notes["open_questions"]


def test_unanswered_ask_times_out_to_the_callback_line(flow) -> None:
    f = flow(ask_timeout_s=0.2)
    call_id = f.start(f.brief(), attended=True)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        assert f.receive(ws)["type"] == "status"
        f.live(call_id)
        f.speak_last(call_id)  # Bolna says the opening
        f.listen_turn(call_id, "We have 4 pm tomorrow, does that work?")
        f.drain_until(ws, "ask")
        resolved = f.drain_until(ws, "ask_resolved")
        assert resolved["source"] == "timeout" and resolved["spoken"] == CALLBACK_LINE
        assert f.bolna.injected[-1] == CALLBACK_LINE


def test_answering_an_unknown_ask_is_an_error_and_speaks_nothing(flow) -> None:
    f = flow()
    call_id = f.start(f.brief(), attended=True)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        assert f.receive(ws)["type"] == "status"
        f.live(call_id)
        ws.send_json({"type": "answer", "ask_id": "stale", "choice": "yes"})
        message = f.drain_until(ws, "error")
        assert message["code"] == "unknown_ask"
    # Only the agent's own opening went out; nothing from the stale answer.
    assert [r["turn_id"] for r in f.bolna.replies()] == ["delegate-open"]


def test_live_calls_are_untouched_by_the_delegate_path(flow) -> None:
    f = flow()
    response = f.client.post(
        "/calls", json={"contact_id": "clinic", "purpose": "doctor_appointment"}, headers=AUTH
    )
    call_id = response.json()["call_id"]
    f.live(call_id)
    assert f.listen_turn(call_id, "Hello, City Clinic.") == ""
    notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
    assert notes["mode"] == "live" and notes["brief"] is None
    assert [e["speaker"] for e in notes["transcript"]][-1] == "receptionist"


def test_notes_need_the_app_token_and_a_known_call(flow) -> None:
    f = flow()
    assert f.client.get("/calls/nope/notes", headers=AUTH).status_code == 404
    assert f.client.get("/calls/nope/notes").status_code in (401, 403)


def test_user_reply_events_carry_only_the_turn(flow) -> None:
    f = flow()
    call_id = f.start(f.brief(), attended=True)
    with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
        f.receive(ws)
        f.live(call_id)
        f.speak_last(call_id)  # Bolna says the opening
        f.listen_turn(call_id, "Is 4 pm tomorrow ok?")
        ask = f.drain_until(ws, "ask")
        ws.send_json({"type": "answer", "ask_id": ask["ask_id"], "choice": "no"})
        f.drain_until(ws, "ask_resolved")
    for _, event, props in f.bolna.events:
        if event == EVENT_USER_REPLY:
            assert set(props) == {"turn_id"}
            assert CLINIC not in json.dumps(props)
