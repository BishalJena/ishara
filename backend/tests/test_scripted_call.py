"""ScriptedBolna on its own, against the stub custom LLM from test_fake_bolna (which
echoes every speak prompt, so the claim rules are tested in test_local_demo instead)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from app.bolna_agent import SILENCE_REPEAT_S
from app.markers import DISCLOSURE, GOODBYE, SILENCE_MARKER
from fakes.fake_bolna import FakeRun, asgi_client
from fakes.scripted_call import RECEPTIONIST_LINES, TALK_OVER_LINE, Pauses, ScriptedBolna
from tests.test_fake_bolna import CALL_ID, RECIPIENT, TOKEN, StubLLM

T2, T4 = RECEPTIONIST_LINES
PAUSE_S = 0.05


def _reply(turn_id: str, text: str) -> dict[str, str]:
    return {"reply_text": text, "turn_id": turn_id}


@pytest.fixture
def stub() -> StubLLM:
    return StubLLM()


@pytest.fixture
def logged() -> list[str]:
    return []


def _pauses(**pauses: float) -> Pauses:
    """No silence repeat unless a test asks for one, so no timer outlives its test."""
    return Pauses(**{"silence_s": 0, **pauses})


def _scripted(stub: StubLLM, logged: list[str], **options: object) -> ScriptedBolna:
    pauses = _pauses(ring_s=PAUSE_S, reply_s=PAUSE_S, talk_over_s=PAUSE_S)
    return ScriptedBolna(TOKEN, asgi_client(stub.app), pauses=pauses, log=logged.append, **options)


async def _start(fake: ScriptedBolna) -> str:
    return await fake.start_call(RECIPIENT, {"ishara_call_id": CALL_ID})


async def _speak(fake: ScriptedBolna, run_id: str, turn_id: str, text: str) -> None:
    await fake.send_event(run_id, "user_reply", _reply(turn_id, text))
    await fake.wait_idle()


def test_receptionist_lines_are_the_plan_script() -> None:
    assert RECEPTIONIST_LINES == (
        "We have 4 pm tomorrow. Does that work?",
        "Yes, 10:30 tomorrow morning.",
    )


def test_pauses_scale_every_field_and_refuse_negative_factors() -> None:
    assert Pauses(1, 2, 3, 4).scaled(0.5) == Pauses(0.5, 1, 1.5, 2)
    with pytest.raises(ValueError):
        Pauses().scaled(-1)


def test_silence_repeat_matches_the_real_agent() -> None:
    assert Pauses().silence_s == SILENCE_REPEAT_S


def _user_lines(run: FakeRun) -> list[str]:
    return [m["content"] for m in run.history if m["role"] == "user"]


async def _until(condition: Callable[[], bool], timeout_s: float = 2.0) -> None:
    async with asyncio.timeout(timeout_s):
        while not condition():
            await asyncio.sleep(0.01)


async def test_answer_waits_the_ring_pause_and_logs_each_status(
    stub: StubLLM, logged: list[str]
) -> None:
    fake = _scripted(stub, logged)
    fake.pauses = _pauses(ring_s=0.2)
    run_id = await _start(fake)
    await asyncio.sleep(0.1)

    assert stub.webhooks == [{"id": run_id, "status": "ringing"}]
    await fake.run_for_call(CALL_ID)
    assert [hook["status"] for hook in stub.webhooks] == ["ringing", "in-progress"]
    assert logged == [
        f"agent says: {DISCLOSURE}",
        "bolna status: ringing",
        "bolna status: in-progress",
    ]


async def test_each_spoken_reply_gets_the_next_line_after_a_pause(
    stub: StubLLM, logged: list[str]
) -> None:
    fake = _scripted(stub, logged)
    fake.pauses = _pauses(ring_s=0, reply_s=0.5)
    run_id = await _start(fake)
    run = await fake.run_for_call(CALL_ID)

    await fake.send_event(run_id, "user_reply", _reply("t1", "Hello."))
    # Poll rather than sleep a fixed time: under load the reply itself can take longer.
    async with asyncio.timeout(2):
        while run.spoken != [DISCLOSURE, "Hello."]:
            await asyncio.sleep(0.01)
    assert [m["content"] for m in run.history if m["role"] == "user"] == []

    await fake.wait_idle()
    await _speak(fake, run_id, "t3", "No.")
    await _speak(fake, run_id, "t5", "Yes. Thank you.")

    assert [m["content"] for m in run.history if m["role"] == "user"] == [T2, T4]
    assert run.spoken == [DISCLOSURE, "Hello.", "No.", "Yes. Thank you."]
    assert f"receptionist says: {T2}" in logged
    assert logged.index(f"receptionist says: {T2}") < logged.index("agent says: No.")


async def test_holding_line_and_goodbye_get_no_receptionist_line(
    stub: StubLLM, logged: list[str]
) -> None:
    fake = _scripted(stub, logged)
    run_id = await _start(fake)
    run = await fake.run_for_call(CALL_ID)

    await fake.silence(run_id)
    await fake.send_event(run_id, "end_call", {})
    await fake.wait_idle()

    assert [m["content"] for m in run.history if m["role"] == "user"] == ["[silence]"]
    assert run.spoken[-1] == GOODBYE
    assert "bolna status: completed" in logged


async def test_silence_repeat_says_the_holding_line_until_the_call_ends(
    stub: StubLLM, logged: list[str]
) -> None:
    fake = _scripted(stub, logged)
    fake.pauses = Pauses(ring_s=0, silence_s=0.1)
    run_id = await _start(fake)
    run = await fake.run_for_call(CALL_ID)

    await _until(lambda: _user_lines(run).count(SILENCE_MARKER) == 2)
    await fake.send_event(run_id, "end_call", {})
    await fake.wait_idle()
    repeats = len(stub.received)
    await asyncio.sleep(0.3)

    assert len(stub.received) == repeats, "no silence repeat after the call ended"
    assert repeats >= 2
    assert set(_user_lines(run)) == {SILENCE_MARKER}
    assert "0.1 s of silence: Bolna repeats the listen node" in logged


async def test_anything_said_restarts_the_silence_wait(stub: StubLLM, logged: list[str]) -> None:
    fake = _scripted(stub, logged)
    fake.pauses = Pauses(ring_s=0, silence_s=1.0)
    run_id = await _start(fake)
    run = await fake.run_for_call(CALL_ID)

    await asyncio.sleep(0.5)
    await fake.receptionist_says(run_id, "Hello?")
    await asyncio.sleep(0.7)  # past the first wait, inside the restarted one
    assert _user_lines(run) == ["Hello?"]

    await _until(lambda: _user_lines(run) == ["Hello?", SILENCE_MARKER])
    await fake.send_event(run_id, "end_call", {})
    await fake.wait_idle()


async def test_silence_wait_starts_only_once_the_call_is_answered(
    stub: StubLLM, logged: list[str]
) -> None:
    fake = _scripted(stub, logged)
    fake.pauses = Pauses(ring_s=0.4, silence_s=0.1)
    run_id = await _start(fake)
    run = fake.run(run_id)

    await asyncio.sleep(0.3)  # still ringing, three silence waits long
    assert _user_lines(run) == []

    await _until(lambda: "bolna status: in-progress" in logged)
    assert _user_lines(run) == []
    await _until(lambda: _user_lines(run) == [SILENCE_MARKER])
    await fake.send_event(run_id, "end_call", {})
    await fake.wait_idle()


async def test_no_silence_repeat_on_the_speak_node(stub: StubLLM, logged: list[str]) -> None:
    fake = _scripted(stub, logged, talk_over_once=True)
    fake.pauses = Pauses(ring_s=0, reply_s=0, talk_over_s=0.6, silence_s=0.1)
    run_id = await _start(fake)
    run = await fake.run_for_call(CALL_ID)

    await fake.send_event(run_id, "user_reply", _reply("t1", "Hello."))
    await _until(lambda: run.node == "speak")
    await asyncio.sleep(0.3)

    assert SILENCE_MARKER not in _user_lines(run)
    await fake.wait_idle()  # she finishes talking over the skipped SEND
    await fake.send_event(run_id, "end_call", {})
    await fake.wait_idle()


async def test_zero_silence_turns_the_repeat_off(stub: StubLLM, logged: list[str]) -> None:
    fake = _scripted(stub, logged)
    fake.pauses = Pauses(ring_s=0, silence_s=0)
    await _start(fake)
    run = await fake.run_for_call(CALL_ID)
    await asyncio.sleep(0.2)

    assert _user_lines(run) == []
    assert stub.received == []


async def test_call_ended_before_the_receptionist_answers_is_logged_not_raised(
    stub: StubLLM, logged: list[str]
) -> None:
    fake = _scripted(stub, logged)
    run_id = await _start(fake)
    await fake.run_for_call(CALL_ID)

    await fake.send_event(run_id, "user_reply", _reply("t1", "Hello."))
    await fake.send_event(run_id, "end_call", {})
    await fake.wait_idle()

    assert "the call ended before the receptionist finished" in logged
    assert not any(line.startswith("fake Bolna failed") for line in logged)


async def test_talk_over_skips_only_the_first_send_of_a_call(
    stub: StubLLM, logged: list[str]
) -> None:
    fake = _scripted(stub, logged, talk_over_once=True)
    fake.pauses = _pauses(ring_s=0, reply_s=0, talk_over_s=0.3)
    run_id = await _start(fake)
    run = await fake.run_for_call(CALL_ID)

    await fake.send_event(run_id, "user_reply", _reply("t1", "Hello."))
    await asyncio.sleep(0.1)

    assert run.spoken == [DISCLOSURE], "B24: the talked-over SEND is skipped"
    assert run.node == "speak"
    assert stub.received == []
    assert fake.receptionist_mid_speech is False, "only that one delivery is talked over"

    await fake.wait_idle()
    # She finishes talking; Bolna answers from the stale speak node. The stub echoes it,
    # the real backend refuses the claim (test_local_demo checks that).
    first = stub.received[0]["messages"]
    assert stub.blocks()[0].turn_id == "t1"
    assert first[-1] == {"role": "user", "content": TALK_OVER_LINE}

    await _speak(fake, run_id, "t1b", "Hello again.")

    assert run.spoken[-1] == "Hello again."
    assert logged.count("receptionist is talking over that SEND, so Bolna skips it (B24)") == 1


async def test_talk_over_is_off_by_default(stub: StubLLM, logged: list[str]) -> None:
    fake = _scripted(stub, logged)
    run_id = await _start(fake)
    run = await fake.run_for_call(CALL_ID)

    await _speak(fake, run_id, "t1", "Hello.")

    assert "Hello." in run.spoken
    assert TALK_OVER_LINE not in [m["content"] for m in run.history]


async def test_background_failures_are_logged(logged: list[str]) -> None:
    stub = StubLLM()
    fake = _scripted(stub, logged)
    run_id = await _start(fake)
    await fake.run_for_call(CALL_ID)
    stub.fail_status = 500

    await fake.send_event(run_id, "user_reply", _reply("t1", "Hello."))
    with pytest.raises(Exception, match="500"):
        await fake.wait_idle()

    assert any(line.startswith("fake Bolna failed: HTTPStatusError") for line in logged)
