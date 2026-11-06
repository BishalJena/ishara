from __future__ import annotations

import os
import time

from fastapi.testclient import TestClient

from app.calls import CallManager
from app.composer import TemplateComposer
from app.main import create_app
from app.notes_archive import NotesArchive
from app.protocol import CallNotes, CallState, TranscriptEntry
from tests.conftest import APP_TOKEN, make_settings
from tests.test_calls import FakeBolna

AUTH = {"Authorization": "Bearer " + APP_TOKEN}


def test_archive_survives_a_new_manager_and_is_private_and_bounded(tmp_path):
    settings = make_settings(call_notes_dir=str(tmp_path / "notes"))
    manager = CallManager(settings, TemplateComposer(), FakeBolna())
    notes = CallNotes(
        call_id="finished",
        mode="steer",
        ready=True,
        summary=["A recorded outcome"],
        transcript=[TranscriptEntry(speaker="agent", text="Thank you.", at=1)],
    )
    manager._archive.put(notes)
    restarted = CallManager(settings, TemplateComposer(), FakeBolna())
    recovered = restarted.notes("finished")
    assert recovered.model_dump(exclude={"presentation"}) == notes.model_dump(
        exclude={"presentation"}
    )
    assert recovered.presentation.status == "ready"
    assert restarted.recent_notes() == [recovered]
    path = tmp_path / "notes/finished.json"
    assert path.stat().st_mode & 0o777 == 0o600
    assert restarted.notes("../outside") is None
    os.utime(path, (time.time() - 90000, time.time() - 90000))
    assert restarted.notes("finished") is None


def test_live_notes_are_never_archived(tmp_path):
    archive = NotesArchive(str(tmp_path))
    archive.put(CallNotes(call_id="live", mode="steer", ready=False))
    assert archive.get("live") is None


def test_lost_start_response_is_recovered_by_unique_brief_without_redial():
    settings = make_settings()
    bolna = FakeBolna()
    manager = CallManager(settings, TemplateComposer(), bolna)
    with TestClient(create_app(settings, ledger=manager)) as client:
        brief = client.post(
            "/briefs",
            headers=AUTH,
            json={
                "purpose": "doctor_appointment",
                "chips": [],
                "profile": {"name": "Riya"},
                "request": "Book a check-up tomorrow.",
            },
        ).json()["brief_id"]
        call = client.post(
            "/calls",
            headers=AUTH,
            json={
                "contact_id": "clinic",
                "purpose": "doctor_appointment",
                "mode": "steer",
                "brief_id": brief,
            },
        ).json()
        recovered = client.get(f"/briefs/{brief}/call", headers=AUTH)
        assert recovered.status_code == 200 and recovered.json() == call
        assert len(bolna.started) == 1
        assert client.get(f"/briefs/{brief}/call").status_code == 401
        assert client.get("/briefs/unknown/call", headers=AUTH).status_code == 404


def test_history_is_opt_in_and_replays_only_the_spoken_transcript(tmp_path):
    settings = make_settings(call_notes_dir=str(tmp_path))
    manager = CallManager(settings, TemplateComposer(), FakeBolna())
    with TestClient(create_app(settings, ledger=manager)) as client:
        call = client.post(
            "/calls", headers=AUTH, json={"contact_id": "clinic", "purpose": "doctor_appointment"}
        ).json()["call_id"]
        manager._sessions[call].transcript.append(
            TranscriptEntry(speaker="receptionist", text="A line before attachment", at=1)
        )
        with client.websocket_connect(f"/calls/{call}/ws?history=1", headers=AUTH) as ws:
            assert ws.receive_json() == {
                "type": "history",
                "entries": [
                    {"speaker": "receptionist", "text": "A line before attachment", "at": 1.0}
                ],
            }
            assert ws.receive_json()["type"] == "status"
        manager._sessions[call].advance(CallState.ENDED)
        manager._mark_finished(manager._sessions[call])
        notes = client.get(f"/calls/{call}/notes", headers=AUTH).json()
        assert notes["ready"]
        assert client.get("/calls/recent", headers=AUTH).json()["calls"][0]["call_id"] == call
        assert client.get("/calls/recent").status_code == 401


def test_live_caption_and_replayed_history_have_the_same_identity():
    settings = make_settings()
    manager = CallManager(settings, TemplateComposer(), FakeBolna())
    with TestClient(create_app(settings, ledger=manager)) as client:
        call = client.post(
            "/calls", headers=AUTH, json={"contact_id": "clinic", "purpose": "doctor_appointment"}
        ).json()["call_id"]
        with client.websocket_connect(f"/calls/{call}/ws", headers=AUTH) as ws:
            assert ws.receive_json()["type"] == "status"
            client.portal.call(manager.record_caption, call, "A recorded question")
            frame = ws.receive_json()
            for _ in range(3):
                if frame.get("text") == "A recorded question":
                    break
                frame = ws.receive_json()
            assert frame["type"] == "caption" and frame["text"] == "A recorded question"
            transcript = client.get(f"/calls/{call}/notes", headers=AUTH).json()["transcript"]
            canonical = next(entry for entry in transcript if entry["text"] == frame["text"])
            assert frame["at"] == canonical["at"]
            assert frame["text"] == canonical["text"]


def test_a_busy_typed_reply_is_reported_instead_of_silently_dropped():
    import asyncio

    from app.protocol import BriefRequest, Profile, SayMessage, StartCallRequest

    class Capture:
        def __init__(self):
            self.frames = []

        async def send(self, message):
            self.frames.append(message)

    async def scenario():
        bolna = FakeBolna()
        manager = CallManager(make_settings(), TemplateComposer(), bolna)
        brief = await manager.create_brief(
            BriefRequest(
                purpose="doctor_appointment",
                chips=[],
                profile=Profile(name="Riya"),
                request="Book a check-up.",
            )
        )
        call = await manager.start_call(
            StartCallRequest(
                contact_id="clinic",
                purpose="doctor_appointment",
                mode="steer",
                brief_id=brief.brief_id,
            )
        )
        session = manager._sessions[call.call_id]
        session.advance(CallState.IN_CALL)
        session.approve("already-speaking", "The current line")
        session.claim()
        capture = Capture()
        manager._links[call.call_id] = capture
        await manager._on_say(session, SayMessage(text="Please wait."))
        assert capture.frames[-1].code == "reply_not_sent"
        assert session.in_flight.approved_text == "The current line"
        assert not bolna.events

    asyncio.run(scenario())
