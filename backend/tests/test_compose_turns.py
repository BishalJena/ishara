"""Evaluation turns through the production composer and voice. Groq and Sarvam are
httpx.MockTransports; nothing reaches the network."""

from __future__ import annotations

import base64
import io
import json
import wave
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from app.composer import build_composer
from app.config import Settings
from app.sarvam import SarvamTTS
from app.templates import compose_template
from scripts.compose_turns import (
    Budget,
    BudgetExceeded,
    RecordingTransport,
    Turn,
    completion_text,
    load_turns,
    run_turns,
    wav_seconds,
)

T2 = "We have 4 pm tomorrow. Does that work?"
GOOD = "No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?"
INVENTED = "No, 4 pm doesn't work. Could I come at 9 am tomorrow morning?"


def wav_bytes(seconds: float, rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\x00\x00" * int(seconds * rate))
    return buffer.getvalue()


def groq(*answers: str, seen: list[dict] | None = None) -> RecordingTransport:
    replies = iter(answers)

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": next(replies)}}]})

    return RecordingTransport(httpx.MockTransport(handler))


def sarvam(texts: list[str], seconds: float = 1.5) -> SarvamTTS:
    def handler(request: httpx.Request) -> httpx.Response:
        texts.append(json.loads(request.content)["text"])
        audio = base64.b64encode(wav_bytes(seconds)).decode()
        return httpx.Response(200, json={"audios": [audio]})

    return SarvamTTS(SecretStr("k"), transport=httpx.MockTransport(handler))


def production(recorder: RecordingTransport):
    settings = Settings(
        _env_file=None, groq_api_key=SecretStr("k"), groq_model="openai/gpt-oss-120b"
    )
    return build_composer(settings, transport=recorder)


def turn(chips: list[str], oracle: list[str] | None = None) -> Turn:
    return Turn("T3", T2, chips, oracle if oracle is not None else chips)


def caption_sent(body: dict) -> str | None:
    return json.loads(body["messages"][1]["content"])["receptionist_last_said"]


async def test_both_chip_lists_go_through_the_production_composer_and_the_draft_is_voiced(
    tmp_path: Path,
) -> None:
    seen: list[dict] = []
    recorder = groq(GOOD, INVENTED, seen=seen)
    spoken: list[str] = []
    budget = Budget(groq=5, voice=5)
    [row] = await run_turns(
        [turn(["no", "morning"], ["no", "sorry", "morning"])],
        production(recorder),
        recorder,
        sarvam(spoken, seconds=2.0),
        budget,
        tmp_path,
    )
    recognised, oracle = row["recognised"], row["oracle"]
    assert (recognised["draft"]["source"], recognised["draft"]["text"]) == ("llm", GOOD)
    assert recognised["draft"]["validator"] == []
    assert recognised["draft"]["groq_raw"] == GOOD
    # The invented 9 am is rejected by the production validator and the template is used.
    assert oracle["draft"]["source"] == "template"
    assert oracle["draft"]["groq_raw"] == INVENTED
    assert oracle["draft"]["validator"]
    assert oracle["draft"]["text"] == oracle["template"]
    assert oracle["template"] == compose_template(["no", "sorry", "morning"], "doctor_appointment")
    assert recognised["template"] == compose_template(["no", "morning"], "doctor_appointment")
    assert [caption_sent(body) for body in seen] == [T2, T2]
    assert [json.loads(b["messages"][1]["content"])["chips"] for b in seen] == [
        ["no", "morning"],
        ["no", "sorry", "morning"],
    ]
    assert spoken == [GOOD]  # only the recognised draft is what SEND would speak
    assert row["voice"]["seconds"] == 2.0
    assert row["voice"]["text"] == GOOD
    assert Path(row["voice"]["path"]) == tmp_path / "T3.wav"
    assert (tmp_path / "T3.wav").read_bytes()[:4] == b"RIFF"
    assert budget.spent == {"groq": 2, "voice": 1}


async def test_no_accepted_chip_composes_and_speaks_nothing(tmp_path: Path) -> None:
    seen: list[dict] = []
    recorder = groq(GOOD, seen=seen)
    spoken: list[str] = []
    budget = Budget(groq=5, voice=5)
    [row] = await run_turns(
        [turn([], ["no", "morning"])],
        production(recorder),
        recorder,
        sarvam(spoken),
        budget,
        tmp_path,
    )
    assert row["recognised"] == {"chips": [], "draft": None, "template": None}
    assert row["oracle"]["draft"]["text"] == GOOD
    assert row["voice"] is None
    assert spoken == []
    assert not list(tmp_path.iterdir())
    assert budget.spent == {"groq": 1, "voice": 0}


async def test_the_groq_cap_stops_the_run_before_an_extra_paid_call(tmp_path: Path) -> None:
    seen: list[dict] = []
    recorder = groq(GOOD, GOOD, seen=seen)
    with pytest.raises(BudgetExceeded, match="groq cap of 1"):
        await run_turns(
            [turn(["no", "morning"])],
            production(recorder),
            recorder,
            None,
            Budget(groq=1, voice=0),
            tmp_path,
        )
    assert len(seen) == 1


async def test_the_voice_cap_stops_before_an_extra_sarvam_call(tmp_path: Path) -> None:
    recorder = groq(GOOD, GOOD, GOOD, GOOD)
    spoken: list[str] = []
    with pytest.raises(BudgetExceeded, match="voice cap of 1"):
        await run_turns(
            [turn(["no", "morning"]), Turn("T5", None, ["yes"], ["yes"])],
            production(recorder),
            recorder,
            sarvam(spoken),
            Budget(groq=10, voice=1),
            tmp_path,
        )
    assert spoken == [GOOD]


def test_budget_counts_each_kind_up_to_its_cap() -> None:
    budget = Budget(groq=2, voice=1)
    budget.spend("groq")
    budget.spend("groq")
    budget.spend("voice")
    assert budget.spent == {"groq": 2, "voice": 1}
    with pytest.raises(BudgetExceeded):
        budget.spend("groq")
    with pytest.raises(BudgetExceeded):
        budget.spend("voice")


def test_turns_file_parsing_and_helpers() -> None:
    [parsed] = load_turns(
        {"turns": [{"turn": "T1", "receptionist": None, "chips": ["hello"], "oracle": ["hello"]}]}
    )
    assert parsed == Turn("T1", None, ["hello"], ["hello"])
    assert completion_text(b'{"choices": [{"message": {"content": "Hi."}}]}') == "Hi."
    assert completion_text(b'{"error": {"message": "x"}}') is None
    assert completion_text(b"not json") is None
    assert wav_seconds(wav_bytes(1.25)) == 1.25
    assert wav_seconds(wav_bytes(0.5, rate=22050)) == pytest.approx(0.5, abs=1e-4)
