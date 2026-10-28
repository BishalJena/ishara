"""fetch_clips writes a clip only after a complete read; stdlib only, no network."""
import http.client
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest import mock

import fetch_clips

MEMBER = "Greetings/48. Hello/MVI_0029.MOV"
PAYLOAD = bytes(range(256)) * 1024  # 256 KiB, read in several chunks


def make_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr(MEMBER, PAYLOAD)
    return buf.getvalue()


BLOB = make_zip()
DATA_START = BLOB.index(PAYLOAD)
CUT = DATA_START + len(PAYLOAD) // 2


class FlakyRemote(io.BytesIO):
    """Zip bytes whose member read dies halfway with IncompleteRead while `drops` remain."""

    def __init__(self, network: NS):
        super().__init__(BLOB)
        self.network = network

    def read(self, n=-1):
        pos = self.tell()
        end = len(BLOB) if n is None or n < 0 else pos + n
        if self.network.drops and pos < DATA_START + len(PAYLOAD) and end > CUT:
            if pos < CUT:
                return super().read(CUT - pos)
            self.network.drops -= 1
            raise http.client.IncompleteRead(b"", DATA_START + len(PAYLOAD) - pos)
        return super().read(n)


class FetchClipsTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        artifacts = Path(tmp.name)
        self.clips = artifacts / "clips"
        self.dest = self.clips / "hello" / "MVI_0029.MOV"
        self.network = NS(drops=0)
        for patcher in [
            mock.patch.object(fetch_clips, "ARTIFACTS", artifacts),
            mock.patch.object(fetch_clips, "CLIPS", self.clips),
            mock.patch.object(
                fetch_clips, "zip_index", lambda: {"Greetings_1of2.zip": ("https://zenodo.invalid/z", len(BLOB))}
            ),
            mock.patch.object(fetch_clips, "RemoteFile", lambda url, size: FlakyRemote(self.network)),
            mock.patch("sys.stdout", io.StringIO()),
        ]:
            patcher.start()
            self.addCleanup(patcher.stop)

    def files(self) -> list[Path]:
        return sorted(p for p in self.clips.rglob("*") if p.is_file())

    def test_interrupted_read_leaves_no_clip_and_no_temp_file(self):
        self.network.drops = 1
        with self.assertRaises(http.client.IncompleteRead):
            fetch_clips.fetch([MEMBER])
        self.assertEqual(self.files(), [])

    def test_rerun_after_interrupted_read_fetches_the_clip(self):
        self.network.drops = 1
        with self.assertRaises(http.client.IncompleteRead):
            fetch_clips.fetch([MEMBER])
        self.assertEqual(fetch_clips.fetch([MEMBER]), [self.dest])
        self.assertEqual(self.dest.read_bytes(), PAYLOAD)
        self.assertEqual(self.files(), [self.dest])

    def test_empty_or_short_existing_clip_is_fetched_again(self):
        for stale in (b"", PAYLOAD[: len(PAYLOAD) // 2]):
            with self.subTest(size=len(stale)):
                self.dest.parent.mkdir(parents=True, exist_ok=True)
                self.dest.write_bytes(stale)
                self.assertEqual(fetch_clips.fetch([MEMBER]), [self.dest])
                self.assertEqual(self.dest.read_bytes(), PAYLOAD)

    def test_complete_existing_clip_is_not_fetched_again(self):
        self.dest.parent.mkdir(parents=True, exist_ok=True)
        kept = b"k" * len(PAYLOAD)
        self.dest.write_bytes(kept)
        self.assertEqual(fetch_clips.fetch([MEMBER]), [self.dest])
        self.assertEqual(self.dest.read_bytes(), kept)

    def test_short_member_stream_is_rejected(self):
        info = zipfile.ZipInfo(MEMBER)
        info.file_size = len(PAYLOAD)
        archive = NS(open=lambda _: io.BytesIO(PAYLOAD[:-1]))
        with self.assertRaisesRegex(OSError, "short read"):
            fetch_clips._extract(archive, info, self.dest)
        self.assertEqual(self.files(), [])


if __name__ == "__main__":
    unittest.main()
