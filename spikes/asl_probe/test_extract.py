"""extract.py: regression for tracking state leaking between clips. Needs the MediaPipe venv
(spikes/recognition/.venv); skipped elsewhere. No clip is decoded: the tracker and extractor are fakes.

    cd spikes/asl_probe && ../recognition/.venv/bin/python -m unittest test_extract
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

HAVE_MEDIAPIPE = all(importlib.util.find_spec(m) for m in ("mediapipe", "cv2"))


@unittest.skipUnless(HAVE_MEDIAPIPE, "needs mediapipe and cv2")
class FreshTrackerPerClip(unittest.TestCase):
    def test_each_manifest_row_gets_its_own_tracker(self):
        import extract

        opened, used = [], {}

        @contextlib.contextmanager
        def holistic(**_):
            tracker = object()
            opened.append(tracker)
            yield tracker

        def fake_extract(video, tracker):
            used[Path(video).name] = tracker
            return {"landmarks": np.zeros((1, extract.TOTAL, 3), np.float32), "fps": 30.0, "width": 2, "height": 2}

        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps([{"id": f"c{i}", "path": f"c{i}.mp4", "label": "x"} for i in range(3)]))
            with mock.patch.object(extract.mp.solutions.holistic, "Holistic", holistic), \
                    mock.patch.object(extract, "extract", fake_extract), contextlib.redirect_stdout(io.StringIO()):
                extract.main(["--manifest", str(manifest)])
        self.assertEqual(len(opened), 3)
        self.assertEqual(len({id(t) for t in used.values()}), 3, "a clip's landmarks may not depend on the clip before it")


if __name__ == "__main__":
    unittest.main()
