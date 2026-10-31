import asyncio
import json
import os
import time

import pytest
from pydantic import ValidationError

from app.call_presentation import CallPresenter, SummaryDraft, default_presentation
from app.groq_client import GroqError
from app.notes_archive import NotesArchive
from app.protocol import CallNotes, TranscriptEntry


def notes(*, call_id="synthetic", outcome="unclear", at=1):
    return CallNotes(
        call_id=call_id,
        mode="steer",
        ready=True,
        brief="Request: Book an appointment with Dr. Reed.\nMay share: supplied report.",
        outcome=outcome,
        summary=["You asked a question.", "They offered a time."],
        transcript=[
            TranscriptEntry(
                speaker="receptionist", text="The registration number is missing.", at=at
            )
        ],
    )


def draft(**updates):
    updates = {
        {"key_points": "detail_ids", "next_step": "next_step_id"}.get(key, key): value
        for key, value in updates.items()
    }
    return SummaryDraft.model_validate(
        {
            "title": "Booking an appointment with Dr. Reed",
            "detail_ids": [],
            "next_step_id": "none",
        }
        | updates
    )


def selection(quote, source_id="entry:0"):
    return source_id.replace("entry:", "c")


class Model:
    def __init__(self, result=None, error=None):
        self.result = result or draft()
        self.error = error
        self.calls = []
        self.closed = False

    async def complete_structured(self, system, user, schema):
        self.calls.append(json.loads(user))
        if self.error:
            raise self.error
        return self.result

    async def aclose(self):
        self.closed = True


def test_fallback_is_a_task_and_result_not_events_or_provider_narrative():
    saved = notes().model_copy(update={"bolna_summary": "The booking was definitely completed."})
    result = CallPresenter().present(saved).presentation
    assert result.title == "Booking an appointment with Dr. Reed"
    assert "before the full request was confirmed" in result.overview
    assert not result.key_points
    assert "You asked" not in result.model_dump_json()
    assert "definitely" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_generation_selects_source_clauses_and_keeps_speaker_metadata():
    client = Model(draft(key_points=[selection("registration number is missing")]))
    result = (await CallPresenter(client).generate(notes())).presentation
    assert result.overview == default_presentation(notes()).overview
    assert result.key_points == ["The registration number is missing."]
    assert client.calls[0]["sources"][0]["speaker"] == "receptionist"
    assert "bolna_summary" not in client.calls[0]


@pytest.mark.parametrize(
    "heard,quote,expected",
    [
        ("No allergies recorded.", "No allergies", ["No allergies recorded."]),
        ("No severe allergies.", "No", ["No severe allergies."]),
        ("No allergies except penicillin.", "No allergies", ["No allergies except penicillin."]),
        (
            "Allergies: Penicillin. No fever.",
            "Allergies: Penicillin. No fever.",
            ["Allergies: Penicillin.", "No fever."],
        ),
        ("Allergies: Penicillin, no fever.", "Penicillin", ["Allergies: Penicillin, no fever."]),
        ("Are you allergic to penicillin?", "penicillin", []),
    ],
)
@pytest.mark.asyncio
async def test_selected_spans_cannot_rewrite_negation_qualifiers_or_questions(
    heard, quote, expected
):
    current = notes().model_copy(
        update={"transcript": [TranscriptEntry(speaker="receptionist", text=heard, at=1)]}
    )
    result = await CallPresenter(
        Model(draft(key_points=[f"c{i}" for i in range(max(1, len(expected)))]))
    ).generate(current)
    assert result.presentation.key_points == expected


def test_summary_model_has_no_channel_for_invented_factual_prose():
    with pytest.raises(ValidationError):
        draft(key_points=[{"source_id": "c0", "text": "No allergies."}])


@pytest.mark.asyncio
async def test_wrong_source_and_invented_quote_are_discarded():
    client = Model(
        draft(
            key_points=[selection("yes", "missing"), selection("Patient number 98765.", "missing2")]
        )
    )
    result = (await CallPresenter(client).generate(notes())).presentation
    assert result == default_presentation(notes())


@pytest.mark.asyncio
async def test_agent_claim_and_unrelated_recipient_ack_cannot_confirm_booking():
    current = notes().model_copy(
        update={
            "transcript": [
                TranscriptEntry(speaker="agent", text="Your appointment is booked.", at=1),
                TranscriptEntry(speaker="receptionist", text="Okay.", at=2),
            ]
        }
    )
    result = await CallPresenter(
        Model(
            draft(
                key_points=[selection("Your appointment is booked."), selection("Okay.", "entry:1")]
            )
        )
    ).generate(current)
    assert not any("booked" in point for point in result.presentation.key_points)
    assert "before the full request was confirmed" in result.presentation.overview


@pytest.mark.asyncio
async def test_actual_result_and_recipient_instruction_are_glanceable():
    heard = (
        "Your appointment with Dr. Reed is booked for Friday at 8:30 am. Could you bring photo ID?"
    )
    current = notes(outcome="done").model_copy(
        update={"transcript": [TranscriptEntry(speaker="receptionist", text=heard, at=1)]}
    )
    result = await CallPresenter(
        Model(
            draft(
                key_points=[selection("booked for Friday")],
                next_step=selection("bring photo ID", "entry:1"),
            )
        )
    ).generate(current)
    assert result.presentation.key_points == [
        "Your appointment with Dr. Reed is booked for Friday at 8:30 am."
    ]
    assert result.presentation.next_step == "Bring photo ID."
    assert result.presentation.overview == "Your request was completed."


@pytest.mark.asyncio
async def test_unrelated_title_names_and_identifiers_are_not_accepted():
    for title in ("Booking an appointment with Dr. Invented", "Booking patient ID 98765"):
        result = await CallPresenter(Model(draft(title=title))).generate(notes())
        assert result.presentation.title == default_presentation(notes()).title


@pytest.mark.asyncio
async def test_generation_failure_finishes_with_readable_fallback():
    presenter = CallPresenter(Model(error=GroqError("unavailable")))
    saved = await presenter.generate(notes())
    assert saved.presentation.status == "ready"
    assert saved.presentation == default_presentation(notes())


@pytest.mark.asyncio
async def test_present_and_upstream_refresh_never_make_inference_requests():
    client = Model()
    presenter = CallPresenter(client)
    for _ in range(5):
        presenter.present(notes())
    assert not client.calls
    complete = asyncio.Event()
    saved = []

    def receive(result):
        saved.append(result)
        complete.set()

    presenter.schedule(notes(), receive)
    presenter.schedule(notes(), receive)
    assert presenter.present(notes()).presentation.status == "pending"
    await asyncio.wait_for(complete.wait(), 1)
    for _ in range(5):
        presenter.present(notes())
        presenter.schedule(
            notes().model_copy(update={"bolna_summary": "Late provider text"}), receive
        )
    assert len(client.calls) == len(saved) == 1
    assert presenter.present(notes()).presentation.status == "ready"
    await presenter.close()
    assert client.closed


@pytest.mark.asyncio
async def test_late_data_replaces_pending_job_without_stale_write():
    started, released = asyncio.Event(), asyncio.Event()

    class Slow(Model):
        async def complete_structured(self, system, user, schema):
            if not self.calls:
                self.calls.append(json.loads(user))
                started.set()
                await released.wait()
            return draft()

    presenter = CallPresenter(Slow())
    saved = []
    presenter.schedule(notes(), saved.append)
    await started.wait()
    updated = notes(outcome="done")
    presenter.schedule(updated, saved.append)
    released.set()
    for _ in range(10):
        await asyncio.sleep(0)
    assert len(saved) == 1 and saved[0].outcome == "done"
    assert presenter.present(updated).presentation.overview == "Your request was completed."
    await presenter.close()


def test_pending_archive_after_restart_has_ready_fallback():
    saved = notes().model_copy(
        update={"presentation": default_presentation(notes(), status="pending")}
    )
    assert CallPresenter().present(saved).presentation.status == "ready"


@pytest.mark.asyncio
async def test_ready_summary_cannot_hide_secondary_unresolved_questions():
    current = notes().model_copy(
        update={"follow_ups": ["What is the registration number?", "Which address?"]}
    )
    result = await CallPresenter(Model()).generate(current)
    assert result.presentation.next_step == "Still needed: What is the registration number?"
    assert result.presentation.key_points == ["Also unresolved: Which address?"]


def test_archive_reads_and_enrichment_preserve_expiry_and_call_chronology(tmp_path):
    archive = NotesArchive(str(tmp_path), retention_s=100)
    earlier, later = notes(call_id="earlier", at=1), notes(call_id="later", at=2)
    archive.put(earlier)
    archive.put(later)
    path = tmp_path / "earlier.json"
    original = time.time() - 90
    os.utime(path, (original, original))
    archive.put(earlier)
    archive.put(earlier.model_copy(update={"presentation": default_presentation(earlier)}))
    assert path.stat().st_mtime == original
    assert [item.call_id for item in archive.recent()] == ["later", "earlier"]
    os.utime(path, (time.time() - 101, time.time() - 101))
    assert archive.get("earlier") is None


@pytest.mark.asyncio
async def test_background_summary_retries_quota_once_and_is_bounded():
    pauses = []

    async def pause(seconds):
        pauses.append(seconds)

    class Recovering(Model):
        async def complete_structured(self, system, user, schema):
            self.calls.append(json.loads(user))
            if len(self.calls) == 1:
                raise GroqError("HTTP 429", category="http", status_code=429, retry_after_s=2)
            return draft()

    client = Recovering()
    await CallPresenter(client, sleep=pause).generate(notes())
    assert len(client.calls) == 2 and pauses == [2]
    pauses.clear()
    client = Model(error=GroqError("HTTP 429", category="http", status_code=429))
    result = await CallPresenter(client, sleep=pause).generate(notes())
    assert len(client.calls) == 2 and pauses == [20]
    assert result.presentation == default_presentation(notes())


@pytest.mark.asyncio
async def test_background_summary_waits_while_another_voice_call_is_active():
    idle = False
    complete = asyncio.Event()

    async def pause(_):
        await asyncio.sleep(0)

    client = Model()
    presenter = CallPresenter(client, sleep=pause)
    presenter.schedule(notes(), lambda _: complete.set(), when_idle=lambda: idle)
    for _ in range(3):
        await asyncio.sleep(0)
    assert not client.calls
    assert presenter.present(notes()).presentation.status == "pending"
    idle = True
    await asyncio.wait_for(complete.wait(), 1)
    assert len(client.calls) == 1
    await presenter.close()


def test_provider_schema_and_local_validation_allow_only_existing_eligible_clause_ids():
    from app.call_presentation import selection_schema, source_entries

    schema = selection_schema(source_entries(notes()))
    with pytest.raises(ValidationError):
        schema.model_validate_json(
            '{"title":"Call summary","detail_ids":["missing"],"next_step_id":"none"}', strict=True
        )
    with pytest.raises(ValidationError):
        schema.model_validate_json(
            '{"title":"Call summary","detail_ids":["c0"],"next_step_id":"c0"}', strict=True
        )
    result = schema.model_validate_json(
        '{"title":"Call summary","detail_ids":["c0"],"next_step_id":"none"}', strict=True
    )
    assert result.detail_ids[0].value == "c0"


@pytest.mark.asyncio
async def test_recent_title_describes_the_task_instead_of_only_the_doctor_name():
    result = await CallPresenter(Model(draft(title="Dr Reed"))).generate(notes())
    assert result.presentation.title == "Booking an appointment with Dr. Reed"
