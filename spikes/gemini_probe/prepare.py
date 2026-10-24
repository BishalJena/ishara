"""Cut neutral, silent, text-free clips from the local spec and write label-free manifests.

    .venv/bin/python prepare.py            # after sources.py fetch

Outputs under spikes/recognition/artifacts/gemini_probe/ (gitignored):
  clips/<id>.mp4          every clip, re-encoded; ids are random hex, nothing about the sign
  manifest.json           TEST clips only: id, path, sha256, in a shuffled order (no labels)
  candidates.json         the closed word list (every word that has a test clip), sorted
  references.json         SignCLIP reference clips with their labels (never given to Gemini)
  key/answer_key.json     test id -> word; read only by score.py
  key/provenance.json     test id -> source, dataset, url; read only by score.py and the leak checks
  ocr.json                burned-in text audit per test clip (found, blurred, dropped)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

import ocr
from sources import ARTIFACTS, RECOGNITION

# The same leak rule as the earlier public-video probe.
sys.path.insert(0, str(RECOGNITION))
from video_eval import assert_no_leakage

CLIPS = ARTIFACTS / "clips"
MANIFEST = ARTIFACTS / "manifest.json"
CANDIDATES = ARTIFACTS / "candidates.json"
REFERENCES = ARTIFACTS / "references.json"
KEY_DIR = ARTIFACTS / "key"
ANSWER_KEY = KEY_DIR / "answer_key.json"
PROVENANCE = KEY_DIR / "provenance.json"
OCR_REPORT = ARTIFACTS / "ocr.json"
FPS = 25
MAX_SECONDS = 10.0  # SignCLIP takes at most 256 frames; 10 s at 25 fps is 250
ENCODE_ARGS = ("-map", "0:v:0", "-an", "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1",
               "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
               "-fflags", "+bitexact", "-flags:v", "+bitexact",
               "-movflags", "+faststart")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def neutral_ids(count: int, seed: int) -> list[str]:
    """Distinct random hex ids: neither the id nor its order says anything about the sign."""
    rng = random.Random(seed)
    ids: set[str] = set()
    while len(ids) < count:
        ids.add(f"c_{rng.getrandbits(48):012x}")
    return sorted(ids, key=lambda _: rng.random())


def cut_command(source: Path, destination: Path, start: float | None = None, end: float | None = None,
                crop: str | None = None) -> list[str]:
    """Silent (-an), no subtitles/data/chapters/metadata, 25 fps, at most 720 p, bit-exact headers."""
    filters = ([f"crop={crop}"] if crop else []) + ["scale=-2:'min(720,ih)'", f"fps={FPS}"]
    span = (["-ss", f"{start:.3f}"] if start is not None else []) + (["-to", f"{end:.3f}"] if end is not None else [])
    return ["ffmpeg", "-v", "error", "-y", *span, "-i", str(source), "-vf", ",".join(filters),
            *ENCODE_ARGS, str(destination)]


def probe(path: Path) -> dict:
    """Streams and tags of an encoded clip, to prove nothing but silent video is inside."""
    output = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "stream=codec_type:stream_tags:format=duration:format_tags", "-of", "json", str(path)],
                            check=True, capture_output=True, text=True).stdout
    document = json.loads(output)
    return {"streams": [s["codec_type"] for s in document.get("streams", [])],
            "stream_tags": [s.get("tags", {}) for s in document.get("streams", [])],
            "format_tags": document.get("format", {}).get("tags", {}),
            "duration": float(document.get("format", {}).get("duration", 0))}


def check_probe(info: dict) -> None:
    """One video stream; only container boilerplate tags, and the muxer's generic stream tags."""
    allowed = {"major_brand", "minor_version", "compatible_brands", "language", "vendor_id"}
    generic = {"handler_name": "VideoHandler", "encoder": "Lavc libx264"}
    tags = {**info["format_tags"], **{k: v for t in info["stream_tags"] for k, v in t.items()}}
    unexpected = {k: v for k, v in tags.items() if k not in allowed and generic.get(k) != v}
    if info["streams"] != ["video"] or unexpected:
        raise ValueError(f"Clip is not bare silent video: {info}")


def assert_disjoint(references: Sequence[dict], tests: Sequence[dict]) -> None:
    """No shared id, clip hash, source video, signer group, dataset, url or raw-file hash."""
    assert_no_leakage(references, tests)  # id, sha256, source_id, signer_id
    for key in ("dataset", "url", "raw_sha256"):
        shared = {r[key] for r in references} & {t[key] for t in tests}
        if shared:
            raise ValueError(f"Leakage: test and reference clips share {key} {sorted(shared)[:5]}")


def prepare(spec_path: Path, seed: int) -> int:
    spec = json.loads(spec_path.read_text())
    sources = {s["source_id"]: s for s in spec["sources"]}
    CLIPS.mkdir(parents=True, exist_ok=True)
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    raw_hashes: dict[str, str] = {}
    rows, skipped = [], []
    for clip_id, cut in zip(neutral_ids(len(spec["clips"]), seed), spec["clips"], strict=True):
        source = sources[cut["source_id"]]
        raw = ARTIFACTS / source["file"]
        raw_hashes.setdefault(source["file"], sha256(raw))
        destination = CLIPS / f"{clip_id}.mp4"
        subprocess.run(cut_command(raw, destination, cut.get("start"), cut.get("end"), cut.get("crop")), check=True)
        info = probe(destination)
        check_probe(info)
        if info["duration"] > MAX_SECONDS:
            skipped.append({"source_id": source["source_id"], "split": cut["split"],
                            "reason": f"{info['duration']:.1f} s > {MAX_SECONDS} s"})
            destination.unlink()
            continue
        rows.append({"id": clip_id, "path": str(destination.relative_to(ARTIFACTS)), "label": cut["label"],
                     "split": cut["split"], "set": cut["set"], "source_id": source["source_id"],
                     "signer_id": source["signer_id"], "dataset": source["dataset"], "url": source["url"],
                     "raw_sha256": raw_hashes[source["file"]], "duration": round(info["duration"], 3)})
        print(f"{clip_id} {cut['split']}", flush=True)
    audit = {}
    for row in (r for r in rows if r["split"] == "test"):
        audit[row["id"]] = ocr.clean(ARTIFACTS / row["path"], ENCODE_ARGS, FPS)
        check_probe(probe(ARTIFACTS / row["path"]))
        print(f"ocr {row['id']}: {audit[row['id']]['action']}", flush=True)
    for row in rows:
        row["sha256"] = sha256(ARTIFACTS / row["path"])
    tests = [r for r in rows if r["split"] == "test" and not audit[r["id"]]["action"].startswith("drop")]
    references = [r for r in rows if r["split"] == "reference"]
    assert_disjoint(references, tests)
    random.Random(seed + 1).shuffle(tests)
    write(MANIFEST, {"version": 1, "clips": [{k: r[k] for k in ("id", "path", "sha256")} for r in tests]})
    write(CANDIDATES, {"words": sorted({r["label"] for r in tests})})
    write(REFERENCES, {"version": 1, "references": [
        {k: r[k] for k in ("id", "path", "sha256", "label", "source_id", "signer_id", "dataset", "url",
                           "raw_sha256", "duration")} for r in references]})
    write(ANSWER_KEY, {"answers": {r["id"]: r["label"] for r in sorted(tests, key=lambda r: r["id"])}})
    write(PROVENANCE, {"tests": {r["id"]: {k: r[k] for k in ("source_id", "signer_id", "dataset", "set", "url",
                                                              "raw_sha256", "duration")}
                                 for r in sorted(tests, key=lambda r: r["id"])},
                       "skipped": skipped})
    write(OCR_REPORT, {"clips": audit})
    dropped = sum(a["action"].startswith("drop") for a in audit.values())
    print(f"{len(tests)} test clips ({dropped} dropped for text), {len(references)} references, "
          f"{len(skipped)} skipped as too long")
    return 0


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=1, sort_keys=False) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec", type=Path, default=ARTIFACTS / "spec.json")
    parser.add_argument("--seed", type=int, default=20261025)
    args = parser.parse_args(argv)
    return prepare(args.spec, args.seed)


if __name__ == "__main__":
    raise SystemExit(main())
