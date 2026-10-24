"""Compose and voice evaluation turns: recognised chips -> production composer -> Sarvam WAV.

    uv run python -m scripts.compose_turns --turns TURNS.json --out OUT.json --audio-dir DIR \
        --env-file ../.env [--max-groq 20] [--max-voice 8] [--play]

For spikes/recognition/video_eval.py: each turn carries the receptionist's last line, the
chips the recognizer accepted and the ground-truth (oracle) chips. Both chip lists go
through `app.composer.build_composer` exactly as production builds it (Groq, 1.5 s
budget, validator, template fallback) and through `TemplateComposer`; the recognised
draft, which is what the user would SEND, is synthesised with `SarvamTTS`. An empty chip
list composes nothing, as in the app. Groq's raw answer is kept by a transport wrapper
so a rejected draft can be shown next to the validator's reasons.

Paid calls are capped (--max-groq, --max-voice); the run stops before going over. Keys
come from --env-file only and are never printed. No phone call, Bolna or deploy.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import subprocess
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.composer import TemplateComposer, build_composer
from app.config import Settings
from app.ports import Composer
from app.protocol import ComposeRequest
from app.sarvam import SarvamTTS
from app.validator import validate
from scripts.sign_lab import DEFAULT_ENV_FILE, read_lab_keys

PURPOSE = "doctor_appointment"


class BudgetExceeded(Exception):
    """A paid call would go over the cap the run was started with."""


@dataclass
class Budget:
    groq: int
    voice: int
    spent: dict[str, int] = field(default_factory=lambda: {"groq": 0, "voice": 0})

    def spend(self, kind: str) -> None:
        if self.spent[kind] >= getattr(self, kind):
            raise BudgetExceeded(f"{kind} cap of {getattr(self, kind)} calls reached")
        self.spent[kind] += 1


@dataclass(frozen=True)
class Turn:
    turn: str
    receptionist: str | None
    chips: list[str]
    oracle: list[str]


def load_turns(document: dict[str, Any]) -> list[Turn]:
    return [
        Turn(t["turn"], t.get("receptionist"), list(t["chips"]), list(t["oracle"]))
        for t in document["turns"]
    ]


class RecordingTransport(httpx.AsyncBaseTransport):
    """Passes requests through and keeps each response body (Groq's raw completion)."""

    def __init__(self, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self.inner = inner or httpx.AsyncHTTPTransport()
        self.bodies: list[bytes] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self.inner.handle_async_request(request)
        body = await response.aread()
        self.bodies.append(body)
        return httpx.Response(response.status_code, headers=response.headers, content=body)


def completion_text(body: bytes) -> str | None:
    try:
        return json.loads(body)["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        return None


def wav_seconds(data: bytes) -> float:
    with wave.open(io.BytesIO(data)) as audio:
        return audio.getnframes() / audio.getframerate()


async def compose(
    composer: Composer, recorder: RecordingTransport | None, request: ComposeRequest
) -> dict[str, Any]:
    seen = len(recorder.bodies) if recorder else 0
    started = time.perf_counter()
    draft = await composer.compose(request)
    elapsed = time.perf_counter() - started
    result: dict[str, Any] = {
        "text": draft.text,
        "source": draft.source.value,
        "seconds": round(elapsed, 3),
    }
    if recorder is not None:
        bodies = recorder.bodies[seen:]
        raw = completion_text(bodies[-1]) if bodies else None
        result["groq_raw"] = raw
        # The same check GroqComposer just made, repeated only to report its reasons.
        result["validator"] = validate(raw.strip(), request) if raw is not None else None
    return result


async def run_turns(
    turns: list[Turn],
    llm: Composer,
    recorder: RecordingTransport | None,
    tts: SarvamTTS | None,
    budget: Budget,
    audio_dir: Path,
) -> list[dict[str, Any]]:
    templates = TemplateComposer()
    results = []
    for turn in turns:
        row: dict[str, Any] = {"turn": turn.turn, "receptionist": turn.receptionist}
        for variant, chips in (("recognised", turn.chips), ("oracle", turn.oracle)):
            if not chips:
                row[variant] = {"chips": [], "draft": None, "template": None}
                continue
            request = ComposeRequest(
                turn_id=f"{turn.turn}-{variant}",
                chips=chips,
                purpose=PURPOSE,
                last_caption=turn.receptionist,
            )
            if recorder is not None:
                budget.spend("groq")
            row[variant] = {
                "chips": chips,
                "draft": await compose(llm, recorder, request),
                "template": (await templates.compose(request)).text,
            }
        row["voice"] = await speak(row, tts, budget, audio_dir)
        results.append(row)
        print(f"{turn.turn}: {json.dumps(row, ensure_ascii=False)}", flush=True)
    return results


async def speak(
    row: dict[str, Any], tts: SarvamTTS | None, budget: Budget, audio_dir: Path
) -> dict[str, Any] | None:
    """The recognised draft is what SEND would speak; no draft means silence."""
    draft = row["recognised"]["draft"]
    if tts is None or draft is None:
        return None
    budget.spend("voice")
    started = time.perf_counter()
    wav = await tts.synthesize(draft["text"])
    elapsed = time.perf_counter() - started
    audio_dir.mkdir(parents=True, exist_ok=True)
    path = audio_dir / f"{row['turn']}.wav"
    path.write_bytes(wav)
    return {
        "path": str(path),
        "text": draft["text"],
        "seconds": round(wav_seconds(wav), 2),
        "tts_seconds": round(elapsed, 3),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--turns", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--audio-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--max-groq", type=int, default=20)
    parser.add_argument("--max-voice", type=int, default=8)
    parser.add_argument("--templates-only", action="store_true", help="free: no Groq, no voice")
    parser.add_argument("--play", action="store_true", help="afplay the first WAV")
    return parser


async def amain(args: argparse.Namespace) -> int:
    turns = load_turns(json.loads(args.turns.read_text()))
    budget = Budget(args.max_groq, args.max_voice)
    recorder: RecordingTransport | None = None
    tts = None
    if args.templates_only:
        llm: Composer = TemplateComposer()
    else:
        keys = read_lab_keys(args.env_file, "groq", "sarvam")
        recorder = RecordingTransport()
        settings = Settings(_env_file=None, groq_api_key=keys.groq_key, groq_model=keys.groq_model)
        llm = build_composer(settings, transport=recorder)
        tts = SarvamTTS(keys.sarvam_key) if keys.sarvam_key else None
    results = await run_turns(turns, llm, recorder, tts, budget, args.audio_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"spent": budget.spent, "turns": results}, indent=2, ensure_ascii=False) + "\n"
    )
    print(f"paid calls: {budget.spent}; results: {args.out}")
    wavs = [r["voice"]["path"] for r in results if r["voice"]]
    if args.play and wavs:
        print(f"playing {wavs[0]}: afplay exit {subprocess.run(['afplay', wavs[0]]).returncode}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(amain(build_parser().parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
