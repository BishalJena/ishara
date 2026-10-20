"""Pull individual INCLUDE test clips out of the Zenodo zips via HTTP range requests.

The dataset (CC-BY-4.0, https://zenodo.org/records/4010759) is published as
~1 GB category zips. We only need a handful of clips, so this reads each zip's
central directory remotely and downloads just the requested members.

Usage:
    .venv/bin/python fetch_clips.py                 # default demo-vocabulary test clips
    .venv/bin/python fetch_clips.py "Greetings/48. Hello/MVI_0029.MOV" ...
Clips land in artifacts/clips/<label>/<uid>.MOV (gitignored).
"""

from __future__ import annotations

import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

RECORD = "https://zenodo.org/api/records/4010759"
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
CLIPS = ARTIFACTS / "clips"

DEFAULT_CLIPS = [
    "Days_and_Time/73. Today/MVI_4616.MOV",
    "Days_and_Time/74. Tomorrow/MVI_5477.MOV",
    "Greetings/48. Hello/MVI_0029.MOV",
    "Greetings/48. Hello/MVI_9914.MOV",
    "Greetings/55. Thank you/MVI_9948.MOV",
    "Greetings/55. Thank you/MVI_0111.MOV",
    "Jobs/87. Doctor/MVI_4471.MOV",
    "Jobs/87. Doctor/MVI_8875.MOV",
    "Places/30. Hospital/MVI_3481.MOV",
    "Places/30. Hospital/MVI_3639.MOV",
    "Places/36. Location/MVI_3341.MOV",
    "Places/36. Location/MVI_3342.MOV",
]


class RemoteFile(io.RawIOBase):
    """Seekable read-only file over HTTP range requests with a simple readahead cache."""

    def __init__(self, url: str, size: int, chunk: int = 1 << 20):
        self.url, self.size, self.chunk, self.pos = url, size, chunk, 0
        self.cache_start, self.cache = 0, b""

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence]
        self.pos = max(0, base + offset)
        return self.pos

    def _fetch(self, start: int, end: int) -> bytes:
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={start}-{end - 1}"})
        with urllib.request.urlopen(req) as resp:
            if resp.status != 206:
                raise IOError(f"range request not honoured (HTTP {resp.status})")
            return resp.read()

    def read(self, n=-1):
        if n < 0:
            n = self.size - self.pos
        end = min(self.pos + n, self.size)
        if end <= self.pos:
            return b""
        if not (self.cache_start <= self.pos and end <= self.cache_start + len(self.cache)):
            fetch_end = min(max(end, self.pos + self.chunk), self.size)
            self.cache_start, self.cache = self.pos, self._fetch(self.pos, fetch_end)
        off = self.pos - self.cache_start
        data = self.cache[off : off + (end - self.pos)]
        self.pos += len(data)
        return data

    def readinto(self, b):
        data = self.read(len(b))
        b[: len(data)] = data
        return len(data)


def zip_index() -> dict[str, tuple[str, int]]:
    with urllib.request.urlopen(RECORD) as resp:
        files = json.load(resp)["files"]
    return {f["key"]: (f["links"]["self"], f["size"]) for f in files if f["key"].endswith(".zip")}


def fetch(wanted: list[str]) -> list[Path]:
    index = zip_index()
    by_category: dict[str, list[str]] = {}
    for member in wanted:
        by_category.setdefault(member.split("/")[0], []).append(member)

    out = []
    for category, members in by_category.items():
        pending = set(members)
        parts = sorted(k for k in index if k.startswith(category + "_"))
        for key in parts:
            if not pending:
                break
            url, size = index[key]
            print(f"indexing {key} ({size / 1e6:.0f} MB remote)")
            zf = zipfile.ZipFile(RemoteFile(url, size))
            names = {n.lstrip("./"): n for n in zf.namelist()}
            for member in sorted(pending):
                if member not in names:
                    continue
                dest = _dest(member)
                if not dest.is_file():
                    info = zf.getinfo(names[member])
                    print(f"  {member} -> {dest.relative_to(ARTIFACTS)} ({info.file_size / 1e6:.1f} MB)")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as src, dest.open("wb") as dst:
                        dst.write(src.read())
                pending.discard(member)
                out.append(dest)
        for member in pending:
            print(f"  NOT FOUND in any {category} zip: {member}", file=sys.stderr)
    return out


def _dest(member: str) -> Path:
    _, folder, filename = member.split("/")
    label = "".join(c for c in folder if c.isalpha()).lower()
    return CLIPS / label / filename


if __name__ == "__main__":
    fetch(sys.argv[1:] or DEFAULT_CLIPS)
