"""public_clips.py: clip names that asl_summary.py labels correctly, and the rest-stretch finder.
No network, ffmpeg or MediaPipe needed.

    cd spikes/asl_probe && python3 -m unittest test_public_clips
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

import public_clips as pc

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "recognition"))
from asl_summary import label_of  # noqa: E402


def frames(n: int, hand_y: float | None) -> np.ndarray:
    """n frames with only a right hand, its top point at hand_y (None: no hand)."""
    lm = np.full((n, pc.FACE + 2 * pc.HAND + pc.POSE, 3), np.nan, dtype=np.float32)
    if hand_y is not None:
        lm[:, pc.RIGHT:pc.RIGHT + pc.HAND, :] = 0.5
        lm[:, pc.RIGHT:pc.RIGHT + pc.HAND, 1] = np.linspace(hand_y, min(hand_y + 0.1, 1.0), pc.HAND)
    return lm


class Names(unittest.TestCase):
    def test_the_label_survives_any_source_or_key(self):
        cases = [("thankyou", "signasl/startasl", "thank-you-2"), ("none", "asl-signbank", "BYE-BYE-425"),
                 ("hello", "lifeprint-site", "hi.mp4"), ("wait", "signasl/youtube", "a_gp8 kUe-Q")]
        for label, source, key in cases:
            name = pc.clip_name(label, source, key)
            self.assertEqual(label_of(Path(name)), label, name)
            self.assertNotIn("/", name)
        self.assertEqual(pc.clip_name("wait", "signasl/youtube", "a_gp8 kUe-Q"), "wait_youtube-a-gp8-kUe-Q.mp4")

    def test_excluded_ids_are_names_the_prep_step_produces(self):
        for stem in pc.EXCLUDED:
            label, rest = stem.split("_", 1)
            self.assertIn(label, pc.LIFEPRINT_YT)
            self.assertTrue(rest.startswith("lifeprint-yt-"), stem)


class Rest(unittest.TestCase):
    def test_no_hand_or_a_hand_at_the_bottom_edge_is_rest(self):
        lm = np.concatenate([frames(3, None), frames(2, 0.9), frames(4, 0.4)])
        self.assertEqual(pc.resting(lm).tolist(), [True] * 5 + [False] * 4)

    def test_a_hand_at_chest_height_is_not_rest(self):
        self.assertFalse(pc.resting(frames(5, 0.6)).any(), "MORNING and PLEASE are signed at the chest")

    def test_longest_run(self):
        self.assertEqual(pc.longest_run(np.array([1, 1, 0, 1, 1, 1, 0], bool)), (3, 6))
        self.assertEqual(pc.longest_run(np.array([0, 1, 1, 1], bool)), (1, 4))
        self.assertEqual(pc.longest_run(np.zeros(4, bool)), (0, 0))


if __name__ == "__main__":
    unittest.main()
