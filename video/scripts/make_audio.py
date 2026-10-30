"""Voices, ring-back and score for the launch film, laid on the app recording's timeline.

    cd video && python3 scripts/make_audio.py [--voices macos|sarvam]

Reads raw/recording.json and raw/film-timeline.jsonl (scripts/record-film.sh) and writes
public/audio/*.wav and public/audio/manifest.json: one entry per spoken line, timed in
seconds from the start of raw/app.mp4. Rohan (the receptionist) is band-limited like a
phone line; Ishara's voice is clean.

macOS voices (free, default): Ishara = Lekha, Rohan = Rishi (Indian voices). Sarvam (the
product's own voice, paid per character) needs SARVAM_API_KEY and an explicit go-ahead.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
OUT = ROOT / "public" / "audio"
RATE = 48000

MACOS = {"ishara": ("Lekha", 175), "rohan": ("Rishi", 175)}
SARVAM = {"ishara": "simran", "rohan": "rahul"}


def run(*args: str) -> None:
    subprocess.run(args, check=True, capture_output=True)


def esc(expr: str) -> str:
    """Commas separate filters in a filter graph; inside an expression they must be escaped."""
    return expr.replace(",", "\\,")


def duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def speak_macos(text: str, who: str, dest: Path) -> None:
    voice, wpm = MACOS[who]
    with tempfile.TemporaryDirectory() as tmp:
        aiff = Path(tmp) / "line.aiff"
        run("say", "-v", voice, "-r", str(wpm), "-o", str(aiff), text)
        run("ffmpeg", "-y", "-v", "error", "-i", str(aiff), "-ar", str(RATE), "-ac", "1", str(dest))


def speak_sarvam(text: str, who: str, dest: Path) -> None:
    body = json.dumps({
        "text": text, "target_language_code": "en-IN", "speaker": SARVAM[who],
        "model": "bulbul:v2", "speech_sample_rate": 24000,
    }).encode()
    request = urllib.request.Request(
        "https://api.sarvam.ai/text-to-speech", data=body,
        headers={"api-subscription-key": os.environ["SARVAM_API_KEY"], "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        audio = base64.b64decode(json.load(response)["audios"][0])
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "line.wav"
        wav.write_bytes(audio)
        run("ffmpeg", "-y", "-v", "error", "-i", str(wav), "-ar", str(RATE), "-ac", "1", str(dest))


def finish(raw: Path, who: str, slot: float, dest: Path) -> float:
    """Phone-band Rohan, gently compress both, and fit the line into its slot."""
    length = duration(raw)
    tempo = min(1.25, length / slot) if slot > 0 and length > slot else 1.0
    chain = [f"atempo={tempo:.3f}"] if tempo > 1.0 else []
    if who == "rohan":
        chain += ["highpass=f=320", "lowpass=f=3300", "acompressor=threshold=-18dB:ratio=3", "volume=1.1"]
    else:
        chain += ["highpass=f=90", "acompressor=threshold=-20dB:ratio=2.5"]
    chain += ["afade=t=in:d=0.02", "areverse", "afade=t=in:d=0.04", "areverse"]
    run("ffmpeg", "-y", "-v", "error", "-i", str(raw), "-af", ",".join(chain), "-ar", str(RATE), str(dest))
    return duration(dest)


def ring(dest: Path, seconds: float) -> None:
    """Indian ring-back: 400 Hz, 25 Hz amplitude modulation, 0.4 on, 0.2 off, 0.4 on, 2 off."""
    expr = (
        "0.30*sin(2*PI*400*t)*(0.55+0.45*sin(2*PI*25*t))"
        "*(lt(mod(t,3),0.4)+between(mod(t,3),0.6,1.0))"
    )
    run("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"aevalsrc={esc(expr)}:s={RATE}:d={seconds:.2f}",
        "-af", "lowpass=f=3000,highpass=f=300", str(dest))


def score(dest: Path, seconds: float) -> None:
    """A quiet, warm pad (A major add9), slowly breathing. A placeholder for a licensed track."""
    notes = [110.0, 164.81, 220.0, 277.18, 329.63, 493.88]
    voices = "+".join(
        f"{0.06 / (i + 1) ** 0.5:.3f}*sin(2*PI*{f}*t+{i})*(0.7+0.3*sin(2*PI*{0.05 + 0.013 * i:.3f}*t))"
        for i, f in enumerate(notes)
    )
    run("ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"aevalsrc={esc(voices)}:s={RATE}:d={seconds:.1f}",
        "-af", "lowpass=f=1800,aecho=0.8:0.7:120|240:0.35|0.25,volume=1.6", str(dest))


def app_start() -> float:
    """When the app first fills the screen: the white app replaces the dark springboard."""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-t", "40", "-i", str(RAW / "app.mp4"), "-vf", "fps=4,scale=1:1,format=gray",
         "-f", "rawvideo", "-"], capture_output=True,
    ).stdout
    return next((i / 4 for i, value in enumerate(out) if value > 200), 14.0)


def lines() -> list[dict]:
    """The spoken lines, in recording seconds, from the app's own timeline."""
    start = json.loads((RAW / "recording.json").read_text())["recordingStartedAt"]
    events = [json.loads(line) for line in (RAW / "film-timeline.jsonl").read_text().splitlines() if line]
    spoken: list[dict] = []
    last_proposal: dict | None = None
    last_draft = ""
    for event in events:
        t = event["t"] - start
        kind = event["kind"]
        if kind == "caption":
            who = "rohan" if event["speaker"] == "receptionist" else "ishara"
            spoken.append({"t": t, "who": who, "text": event["text"]})
        elif kind == "proposal":
            last_proposal = event
        elif kind == "resolved" and event["outcome"] == "spoken" and last_proposal and last_proposal["origin"] == "user":
            spoken.append({"t": t, "who": "ishara", "text": last_proposal["text"]})
        elif kind == "draft":
            last_draft = event["text"]
        elif kind == "status" and event["state"] == "speaking" and last_draft:
            spoken.append({"t": t, "who": "ishara", "text": last_draft})
    return spoken


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--voices", choices=["macos", "sarvam"], default="macos")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    events = [json.loads(line) for line in (RAW / "film-timeline.jsonl").read_text().splitlines() if line]
    start = json.loads((RAW / "recording.json").read_text())["recordingStartedAt"]
    ringing = next(e["t"] - start for e in events if e["kind"] == "status" and e["state"] == "ringing")
    in_call = next(e["t"] - start for e in events if e["kind"] == "status" and e["state"] == "inCall")
    ended = next(e["t"] - start for e in events if e["kind"] == "status" and e["state"] == "ended")
    ring(OUT / "ring.wav", in_call - ringing)
    manifest = {
        "ring": {"file": "ring.wav", "t": ringing, "duration": in_call - ringing},
        "ended": ended,
        "appStart": app_start(),
        "events": [{**{k: v for k, v in e.items() if k != "t"}, "t": round(e["t"] - start, 3)} for e in events],
        "lines": [],
    }

    spoken = lines()
    speak = speak_sarvam if args.voices == "sarvam" else speak_macos
    with tempfile.TemporaryDirectory() as tmp:
        for index, line in enumerate(spoken):
            next_t = spoken[index + 1]["t"] if index + 1 < len(spoken) else ended + 1.5
            raw = Path(tmp) / f"{index}.wav"
            speak(line["text"], line["who"], raw)
            name = f"{index:02d}-{line['who']}.wav"
            length = finish(raw, line["who"], next_t - line["t"] - 0.15, OUT / name)
            manifest["lines"].append({**line, "file": name, "duration": round(length, 3)})
            print(f"{line['t']:7.2f}s {line['who']:6} {length:5.2f}s  {line['text'][:60]}")
    score(OUT / "score.wav", 260)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"{len(spoken)} lines, ring {ringing:.2f}-{in_call:.2f}s, call ended {ended:.2f}s")


if __name__ == "__main__":
    main()
