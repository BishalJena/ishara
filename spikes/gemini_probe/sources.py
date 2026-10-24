"""Index and fetch the public ISL word videos used by the probe (local only, never committed).

    .venv/bin/python sources.py index        # INCLUDE zip listings + ISLRTC mirror file list
    .venv/bin/python sources.py bridgeconn   # stream the Bridgeconn shards, keep wanted words
    .venv/bin/python sources.py fetch --spec artifacts/gemini_probe/spec.json

Sources (all research-permitted; credited in docs/experiments/gemini-video-probe.md):
- INCLUDE (AI4Bharat, CC-BY-4.0), Zenodo 4010759: category zips read by HTTP range requests.
- ISLRTC Indian Sign Language Dictionary via the re-encoded Hugging Face mirror
  silentone0725/Indian_Sign_Language_Data.gov_Rencoded (research use with acknowledgement).
- Bridgeconn ISL Bible (ISLV) Dictionary, bridgeconn/sign-dictionary-isl (CC-BY-SA-4.0).
Everything lands under spikes/recognition/artifacts/gemini_probe/ (gitignored).
"""
from __future__ import annotations

import argparse
import http.client
import json
import re
import struct
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile
import zlib
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECOGNITION = HERE.parent / "recognition"
# fetch_clips (stdlib-only INCLUDE range reader) is shared with the recognition spike.
sys.path.insert(0, str(RECOGNITION))
import fetch_clips

ARTIFACTS = RECOGNITION / "artifacts" / "gemini_probe"
INDEX = ARTIFACTS / "index"
RAW = ARTIFACTS / "raw"
ISLRTC_TREE = "https://huggingface.co/api/datasets/silentone0725/Indian_Sign_Language_Data.gov_Rencoded/tree/main"
ISLRTC_FILE = "https://huggingface.co/datasets/silentone0725/Indian_Sign_Language_Data.gov_Rencoded/resolve/main/"
BRIDGECONN_SHARD = "https://huggingface.co/datasets/bridgeconn/sign-dictionary-isl/resolve/main/shard_{:05d}-train.tar"
BRIDGECONN_SHARDS = 5
VARIANT = re.compile(r"_?\(sign_?\d+\)$", re.IGNORECASE)
COPY = re.compile(r"\s\(\d+\)$")  # 'Adult (1)': a duplicate upload, same entry


def word_key(name: str) -> str:
    """Comparable word: 'Thank_You_(Sign_2)' and '55. Thank you' both become 'thank you'.

    Word boundaries are kept, so 'B_Ed' (the degree) never matches INCLUDE's 'bed'.
    """
    name = COPY.sub("", VARIANT.sub("", COPY.sub("", name.strip())))
    name = re.sub(r"^\d+\.\s*", "", name).replace("_", " ").lower()
    return " ".join("".join(c for c in name if c.isalpha() or c == " ").split())


def include_index() -> dict[str, list[list[str]]]:
    """word -> [[zip, member], ...] over every INCLUDE category zip (central directories only)."""
    words: dict[str, list[list[str]]] = {}
    for key, (url, size) in sorted(fetch_clips.zip_index().items()):
        print(f"listing {key}", flush=True)
        for name in zipfile.ZipFile(fetch_clips.RemoteFile(url, size)).namelist():
            parts = name.lstrip("./").split("/")
            if len(parts) == 3 and parts[2] and not parts[2].startswith("."):
                words.setdefault(word_key(parts[1]), []).append([key, "/".join(parts)])
    return words


def islrtc_index() -> dict[str, list[str]]:
    """word -> mirror paths (main entry and 'Sign 2/3' variants)."""
    top = json.load(urllib.request.urlopen(ISLRTC_TREE))
    words: dict[str, list[str]] = {}
    for folder in (d["path"] for d in top if d["type"] == "directory"):
        url: str | None = f"{ISLRTC_TREE}/{urllib.parse.quote(folder)}"
        while url:
            response = urllib.request.urlopen(url)
            for item in json.load(response):
                if item["type"] == "file" and item["path"].endswith(".mp4"):
                    stem = item["path"].rsplit("/", 1)[-1][:-4]
                    words.setdefault(word_key(stem), []).append(item["path"])
            link = response.headers.get("Link", "")
            url = link.split("<")[1].split(">")[0] if 'rel="next"' in link else None
    return words


def index() -> int:
    INDEX.mkdir(parents=True, exist_ok=True)
    (INDEX / "include.json").write_text(json.dumps(include_index(), indent=1, sort_keys=True))
    (INDEX / "islrtc.json").write_text(json.dumps(islrtc_index(), indent=1, sort_keys=True))
    print(f"indexes -> {INDEX}")
    return 0


def bridgeconn_glosses(meta: dict) -> list[str]:
    """The English gloss sits in transcript.text, e.g. 'help (2)' for a second sign."""
    text = (meta.get("transcript") or {}).get("text")
    return [text] if isinstance(text, str) and text.strip() else []


def stream_samples(url: str) -> Iterable[tuple[str, dict[str, bytes]]]:
    """(key, {extension: bytes}) per webdataset sample, reading the tar as one stream."""
    current, members = None, {}
    with urllib.request.urlopen(url) as response, tarfile.open(fileobj=response, mode="r|") as tar:
        for member in tar:
            if not member.isfile():
                continue
            key, _, extension = member.name.partition(".")
            if key != current and current is not None:
                yield current, members
                members = {}
            current = key
            if extension in ("json", "mp4"):
                members[extension] = tar.extractfile(member).read()
    if current is not None:
        yield current, members


def bridgeconn(wanted: set[str]) -> int:
    """Keep every sample's metadata, and the video of samples whose gloss is a wanted word."""
    out = RAW / "bridgeconn"
    out.mkdir(parents=True, exist_ok=True)
    catalogue = []
    for shard in range(1, BRIDGECONN_SHARDS + 1):
        url = BRIDGECONN_SHARD.format(shard)
        print(f"streaming shard {shard}", flush=True)
        for key, members in stream_samples(url):
            meta = json.loads(members.get("json", b"{}"))
            words = sorted({word_key(g) for g in bridgeconn_glosses(meta)})
            row = {"key": key, "shard": shard, "glosses": bridgeconn_glosses(meta), "words": words,
                   "filename": meta.get("filename"), "duration_sec": meta.get("duration_sec")}
            if wanted & set(words) and "mp4" in members:
                path = out / f"{shard}_{key}.mp4"
                path.write_bytes(members["mp4"])
                row["file"] = str(path.relative_to(ARTIFACTS))
            catalogue.append(row)
    (INDEX / "bridgeconn.json").write_text(json.dumps(catalogue, indent=1))
    print(f"{len(catalogue)} samples, {sum('file' in r for r in catalogue)} videos kept")
    return 0


def download(url: str, destination: Path) -> None:
    """Write to a temporary name first, so a network error never leaves a truncated clip."""
    if destination.is_file() and destination.stat().st_size > 0:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(url) as response:
        partial.write_bytes(response.read())
    partial.rename(destination)


def member_bytes(url: str, info: zipfile.ZipInfo) -> bytes:
    """One member's data in two range requests (local header, then the whole body).

    Zenodo serves ~0.35 MB/s per connection, so the 1 MB readahead of RemoteFile is too
    slow for hundreds of clips; whole-member requests run in parallel instead.
    """
    header = fetch_clips.RemoteFile(url, info.header_offset + 30)._fetch(info.header_offset, info.header_offset + 30)
    name_length, extra_length = struct.unpack("<HH", header[26:30])
    start = info.header_offset + 30 + name_length + extra_length
    body = fetch_clips.RemoteFile(url, start + info.compress_size)._fetch(start, start + info.compress_size)
    if info.compress_type == zipfile.ZIP_STORED:
        return body
    if info.compress_type == zipfile.ZIP_DEFLATED:
        return zlib.decompressobj(-15).decompress(body)
    raise ValueError(f"Unsupported compression {info.compress_type} for {info.filename}")


def fetch_include(members: list[list[str]], workers: int = 12) -> None:
    """Range-read the wanted INCLUDE members, several at a time."""
    index_ = fetch_clips.zip_index()
    by_zip: dict[str, list[str]] = {}
    for key, member in members:
        if not include_path(member).is_file():
            by_zip.setdefault(key, []).append(member)
    jobs = []
    for key, wanted in sorted(by_zip.items()):
        url, size = index_[key]
        archive = zipfile.ZipFile(fetch_clips.RemoteFile(url, size))
        names = {n.lstrip("./"): n for n in archive.namelist()}
        jobs += [(url, archive.getinfo(names[m]), m) for m in wanted]

    def one(job: tuple[str, zipfile.ZipInfo, str]) -> None:
        url, info, member = job
        for attempt in range(3):  # Zenodo drops long range reads now and then (IncompleteRead)
            try:
                data = member_bytes(url, info)
                break
            except (OSError, http.client.HTTPException) as error:
                print(f"  retry {member}: {type(error).__name__}", flush=True)
                if attempt == 2:
                    raise
        if len(data) != info.file_size or zlib.crc32(data) != info.CRC:
            raise ValueError(f"Corrupt download of {member}")
        destination = include_path(member)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(".part")
        partial.write_bytes(data)
        partial.rename(destination)
        print(f"  {member}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, jobs))


def include_path(member: str) -> Path:
    category, folder, filename = member.split("/")
    return RAW / "include" / category / folder / filename


def fetch(spec_path: Path) -> int:
    spec = json.loads(spec_path.read_text())
    for source in spec["sources"]:
        if source.get("islrtc_path"):
            download(ISLRTC_FILE + urllib.parse.quote(source["islrtc_path"]), ARTIFACTS / source["file"])
    fetch_include([s["include_member"] for s in spec["sources"] if "include_member" in s])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["index", "bridgeconn", "fetch"])
    parser.add_argument("--words", type=Path, help="JSON list of wanted word keys (bridgeconn)")
    parser.add_argument("--spec", type=Path, default=ARTIFACTS / "spec.json")
    args = parser.parse_args(argv)
    if args.command == "index":
        return index()
    if args.command == "bridgeconn":
        return bridgeconn(set(json.loads(args.words.read_text())))
    return fetch(args.spec)


if __name__ == "__main__":
    raise SystemExit(main())
