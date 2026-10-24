"""Ask Gemini 4 Argon which word each test clip signs (paid; budget-guarded).

    .venv/bin/python gemini_run.py --limit 5 --out-dir artifacts/gemini_probe/runs/pilot   # pilot
    .venv/bin/python gemini_run.py --cap-usd 10                                            # full run

Reads only manifest.json (neutral ids, paths, hashes) and candidates.json (the word
list). It never opens key/: the answer key and the provenance are for score.py.
Each request = the clip + the fixed instruction + a freshly shuffled word list, with a
JSON schema that only allows a list word or "unsure". No file name, id, URL or caption
is sent; no examples. Every response's token usage is priced and logged; a call is only
started when the money already spent plus the worst case of every call in flight stays
under the cap. Uploaded files (only for clips above the inline limit) are deleted after use.
The API key is read from the main checkout's .env into this process only and never printed.
"""
from __future__ import annotations

import argparse
import base64
import json
import random
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import prompt
from sources import ARTIFACTS

MODEL = "gemini-4-argon"
PRICE_INPUT, PRICE_OUTPUT = 2.00 / 1e6, 10.00 / 1e6  # USD per token, intro price until 30 Nov 2026
THINKING_LEVEL = "low"
VIDEO_FPS = 8.0  # Gemini samples 1 fps by default, too sparse for a 2-3 s sign
VIDEO_RESOLUTION = "high"  # 280 tokens per frame; docs call high optimal for most uses
MAX_OUTPUT_TOKENS = 8192  # thinking + answer; a hard ceiling that also bounds the worst case
INLINE_LIMIT = 15 * 1024 * 1024
ENV_FILE = Path("/Users/ansuman/Documents/ishara/.env")
MANIFEST = ARTIFACTS / "manifest.json"
CANDIDATES = ARTIFACTS / "candidates.json"
FORBIDDEN_KEYS = {"label", "word", "answer", "source_id", "url", "title", "dataset"}


def load_manifest(path: Path = MANIFEST) -> list[dict]:
    clips = json.loads(path.read_text())["clips"]
    for clip in clips:
        if set(clip) & FORBIDDEN_KEYS:
            raise ValueError(f"{clip['id']}: the Gemini manifest must hold no label or source fields")
    return clips


def load_candidates(path: Path = CANDIDATES) -> list[str]:
    return json.loads(path.read_text())["words"]


def read_key(env_file: Path = ENV_FILE, name: str = "GEMINI_API_KEY") -> str:
    """The key's value from a dotenv file; raises without echoing anything from the file."""
    for line in env_file.read_text().splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key.strip().removeprefix("export ").strip() == name:
            value = value.strip().strip('"').strip("'")
            if value:
                return value
    raise SystemExit(f"{name} is not set in {env_file}")


def cost_usd(usage: dict) -> float:
    """Input at the input price; answer and thinking tokens at the output price."""
    output = (usage.get("total_output_tokens") or 0) + (usage.get("total_thought_tokens") or 0)
    return (usage.get("total_input_tokens") or 0) * PRICE_INPUT + output * PRICE_OUTPUT


@dataclass
class Budget:
    """Spent money plus the worst case of every call in flight must stay under the cap."""
    cap_usd: float
    spent_usd: float = 0.0
    reserved_usd: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def reserve(self, worst_usd: float) -> bool:
        with self.lock:
            if self.spent_usd + self.reserved_usd + worst_usd > self.cap_usd:
                return False
            self.reserved_usd += worst_usd
            return True

    def settle(self, worst_usd: float, actual_usd: float) -> None:
        with self.lock:
            self.reserved_usd -= worst_usd
            self.spent_usd += actual_usd


def worst_case_usd(input_tokens: int) -> float:
    return input_tokens * PRICE_INPUT + MAX_OUTPUT_TOKENS * PRICE_OUTPUT


def video_part(data: bytes | None = None, uri: str | None = None) -> dict:
    part: dict[str, Any] = {"type": "video", "mime_type": "video/mp4",
                            "processing": {"type": "static", "fps": VIDEO_FPS}, "resolution": VIDEO_RESOLUTION}
    if data is not None:
        part["data"] = base64.b64encode(data).decode("ascii")
    else:
        part["uri"] = uri
    return part


def request_body(words: Sequence[str], video: dict) -> dict:
    """Everything sent for one clip. Only the video bytes, the instruction and the list."""
    return {"model": MODEL, "store": False,
            "input": [video, {"type": "text", "text": prompt.build_prompt(words)}],
            "generation_config": {"thinking_level": THINKING_LEVEL, "max_output_tokens": MAX_OUTPUT_TOKENS},
            "response_format": {"type": "text", "mime_type": "application/json",
                                "schema": prompt.response_schema(words)}}


def parse_answer(text: str | None, words: Sequence[str]) -> tuple[str, float | None]:
    """The model's word ('unsure' allowed) and confidence; 'invalid' for anything off the list."""
    try:
        answer = json.loads(text or "")
        word, confidence = answer["word"], answer.get("confidence")
    except (json.JSONDecodeError, KeyError, TypeError):
        return "invalid", None
    if word != prompt.UNSURE and word not in words:
        return "invalid", None
    return word, float(confidence) if isinstance(confidence, (int, float)) else None


def usage_dict(interaction: Any) -> dict:
    usage = getattr(interaction, "usage", None)
    if usage is None:
        return {}
    keys = ("total_input_tokens", "total_output_tokens", "total_thought_tokens", "total_cached_tokens",
            "total_tool_use_tokens", "total_tokens")
    out = {k: getattr(usage, k, None) for k in keys}
    by_modality = getattr(usage, "input_tokens_by_modality", None) or []
    out["input_by_modality"] = {str(getattr(m, "modality", "?")): getattr(m, "tokens", None) for m in by_modality}
    return out


def redact(message: str, secret: str) -> str:
    return message.replace(secret, "***") if secret else message


class GeminiProbe:
    """Runs clips through Gemini with the budget guard; `client` is a google-genai Client."""

    def __init__(self, client: Any, words: Sequence[str], budget: Budget, seed: int, secret: str = "",
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.client, self.words, self.budget, self.secret = client, list(words), budget, secret
        self.seed, self.sleep = seed, sleep
        self.input_estimate = 0
        self.lock = threading.Lock()

    def estimate_input(self, clip_seconds: float) -> int:
        """Largest input seen so far, or a generous first guess from the documented token rates."""
        with self.lock:
            guess = int(clip_seconds * VIDEO_FPS * 280 * 1.5) + 4000
            return max(self.input_estimate, guess) if self.input_estimate else guess

    def ask(self, clip: dict, root: Path = ARTIFACTS) -> dict:
        path = root / clip["path"]
        rng = random.Random(f"{self.seed}:{clip['id']}")
        words = prompt.shuffled(self.words, rng)
        data = path.read_bytes()
        worst = worst_case_usd(self.estimate_input(clip.get("duration", 5.0)))
        if not self.budget.reserve(worst):
            return {"id": clip["id"], "status": "skipped_budget"}
        uploaded, actual = None, 0.0
        try:
            if len(data) > INLINE_LIMIT:
                uploaded = self.upload(path)
                video = video_part(uri=uploaded.uri)
            else:
                video = video_part(data=data)
            body = request_body(words, video)
            started = time.perf_counter()
            interaction = self.create(body)
            latency = time.perf_counter() - started
            usage = usage_dict(interaction)
            actual = cost_usd(usage)
            with self.lock:
                self.input_estimate = max(self.input_estimate, usage.get("total_input_tokens") or 0)
            word, confidence = parse_answer(getattr(interaction, "output_text", None), words)
            return {"id": clip["id"], "sha256": clip["sha256"], "status": "ok", "word": word,
                    "confidence": confidence, "raw": (getattr(interaction, "output_text", "") or "")[:300],
                    "latency_s": round(latency, 3), "usage": usage, "cost_usd": round(actual, 6),
                    "interaction_status": str(getattr(interaction, "status", "")), "candidates_order_seed":
                    f"{self.seed}:{clip['id']}"}
        except Exception as error:  # noqa: BLE001 - an API failure is recorded per clip, never fatal
            return {"id": clip["id"], "sha256": clip["sha256"], "status": "error",
                    "error": redact(f"{type(error).__name__}: {error}", self.secret)[:500]}
        finally:
            self.budget.settle(worst, actual)
            if uploaded is not None:
                self.client.files.delete(name=uploaded.name)

    def create(self, body: dict, attempts: int = 4) -> Any:
        """Retry rate limits and server errors with backoff; anything else fails the clip."""
        for attempt in range(attempts):
            try:
                return self.client.interactions.create(**body)
            except Exception as error:  # SDK error classes differ; the status code decides
                code = getattr(error, "status_code", None) or getattr(error, "code", None)
                if attempt == attempts - 1 or code not in (429, 500, 502, 503, 504):
                    raise
                self.sleep(5 * 3 ** attempt)
        raise AssertionError("unreachable")

    def upload(self, path: Path) -> Any:
        uploaded = self.client.files.upload(file=str(path))
        while getattr(uploaded.state, "name", uploaded.state) != "ACTIVE":
            self.sleep(2)
            uploaded = self.client.files.get(name=uploaded.name)
        return uploaded


def append(path: Path, record: dict) -> None:
    with path.open("a") as stream:
        stream.write(json.dumps(record) + "\n")


def done_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return {r["id"] for r in map(json.loads, path.read_text().splitlines()) if r.get("status") == "ok"}


def spent(path: Path) -> float:
    if not path.is_file():
        return 0.0
    return sum(r.get("cost_usd", 0.0) for r in map(json.loads, path.read_text().splitlines()))


def run(out_dir: Path, cap_usd: float, limit: int | None, workers: int, seed: int,
        durations: dict[str, float]) -> int:
    from google import genai

    out_dir.mkdir(parents=True, exist_ok=True)
    predictions, cost_log = out_dir / "predictions.jsonl", out_dir / "cost_log.jsonl"
    clips = [dict(c, duration=durations.get(c["id"], 5.0)) for c in load_manifest()]
    finished = done_ids(predictions)
    todo = [c for c in clips if c["id"] not in finished][:limit]
    budget = Budget(cap_usd, spent_usd=spent(cost_log))
    secret = read_key()
    probe = GeminiProbe(genai.Client(api_key=secret), load_candidates(), budget, seed, secret)
    print(f"{len(todo)} clips to ask; spent so far ${budget.spent_usd:.4f} of ${cap_usd:.2f}", flush=True)
    lock = threading.Lock()

    def one(clip: dict) -> None:
        record = probe.ask(clip)
        with lock:
            append(predictions, record)
            if record["status"] == "ok":
                append(cost_log, {"id": record["id"], "usage": record["usage"], "cost_usd": record["cost_usd"],
                                  "cumulative_usd": round(budget.spent_usd, 6), "latency_s": record["latency_s"]})
            print(f"{record['id']}: {record['status']} {record.get('word', '')} "
                  f"{record.get('latency_s', '')}s ${record.get('cost_usd', 0):.4f} "
                  f"(total ${budget.spent_usd:.4f}) {record.get('error', '')}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, todo))
    print(f"spent ${budget.spent_usd:.4f}", flush=True)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", type=Path, default=ARTIFACTS / "runs" / "gemini")
    parser.add_argument("--cap-usd", type=float, default=10.0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261025)
    args = parser.parse_args(argv)
    durations = clip_durations()
    return run(args.out_dir, args.cap_usd, args.limit, args.workers, args.seed, durations)


def clip_durations() -> dict[str, float]:
    """Durations from the clips themselves (ffprobe), for the worst-case cost estimate."""
    from prepare import probe

    return {c["id"]: probe(ARTIFACTS / c["path"])["duration"] for c in load_manifest()}


if __name__ == "__main__":
    raise SystemExit(main())
