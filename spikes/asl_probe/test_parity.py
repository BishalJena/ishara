"""parity.py's part swap: which landmark part (face, hands, pose, frame count) makes the app path
decide differently from the Mac path. Fake models stand in for the TFLite; no MediaPipe needed.

    cd spikes/asl_probe && python3 -m unittest test_parity
"""
from __future__ import annotations

import unittest

import numpy as np

import parity as p

FRAMES = 6


def clip(fill: float = 0.5) -> np.ndarray:
    return np.full((FRAMES, p.POINTS, 3), fill, dtype=np.float32)


def decide_by_right_hand(lm: np.ndarray) -> str:
    """A model that only looks at whether the right hand was tracked in most frames."""
    seen = ~np.isnan(lm[:, p.PARTS["right_hand"], 0]).any(axis=1)
    return "chip:yes" if seen.mean() > 0.5 else "abstain"


class PartSwap(unittest.TestCase):
    def test_swapping_the_part_the_model_reads_reproduces_the_mac_decision(self):
        mac, app = clip(), clip()
        mac[:, p.PARTS["left_hand"]] = app[:, p.PARTS["left_hand"]] = np.nan  # a one-handed sign
        app[:, p.PARTS["right_hand"]] = np.nan  # the app's landmarker lost the right hand
        app[:, p.PARTS["face"]] += 0.1  # and differs on the face, which the model ignores
        report = p.attribute(mac, app, decide_by_right_hand)
        self.assertEqual(report["mac"], "chip:yes")
        self.assertEqual(report["app"], "abstain")
        self.assertEqual(report["explained_by"], ["right_hand"])
        self.assertEqual(report["swaps"]["face"], "abstain")

    def test_mirrored_hands_are_named_as_handedness(self):
        mac, app = clip(), clip()
        mac[:, p.PARTS["left_hand"]] = np.nan
        app[:, p.PARTS["right_hand"]] = np.nan  # the same hand, reported on the other side
        report = p.attribute(mac, app, decide_by_right_hand)
        self.assertIn("handedness", report["explained_by"])

    def test_different_frame_counts_are_aligned_and_reported(self):
        mac, app = clip(), clip()[:-2]
        report = p.attribute(mac, app, decide_by_right_hand)
        self.assertEqual(report["frames"], [FRAMES, FRAMES - 2])
        self.assertEqual(report["explained_by"], [], "same decision: nothing to explain")

    def test_both_hands_together_when_no_single_part_explains_it(self):
        def needs_both_hands(lm: np.ndarray) -> str:
            hands = [(~np.isnan(lm[:, p.PARTS[h], 0]).any(axis=1)).mean() > 0.5 for h in ("left_hand", "right_hand")]
            return "chip:yes" if all(hands) else "abstain"
        mac, app = clip(), clip()
        app[:, p.PARTS["left_hand"]] = np.nan
        app[:, p.PARTS["right_hand"]] = np.nan
        report = p.attribute(mac, app, needs_both_hands)
        self.assertEqual(report["swaps"]["left_hand"], "abstain")
        self.assertEqual(report["swaps"]["right_hand"], "abstain")
        self.assertEqual(report["explained_by"], ["hands"])

    def test_a_frame_count_difference_is_named(self):
        def needs_six_frames(lm: np.ndarray) -> str:
            return "chip:yes" if len(lm) >= FRAMES else "abstain"
        report = p.attribute(clip(), clip()[:-1], needs_six_frames)
        self.assertEqual((report["mac"], report["app"]), ("chip:yes", "abstain"))
        self.assertEqual(report["explained_by"], ["frames"])

    def test_nothing_named_when_no_swap_reproduces_it(self):
        def needs_face_and_pose(lm: np.ndarray) -> str:
            ok = [np.allclose(lm[:, p.PARTS[part]], 0.5) for part in ("face", "pose")]
            return "chip:yes" if all(ok) else "abstain"
        mac, app = clip(), clip()
        app[:, p.PARTS["face"]] += 0.1
        app[:, p.PARTS["pose"]] += 0.1
        report = p.attribute(mac, app, needs_face_and_pose)
        self.assertEqual(report["app"], "abstain")
        self.assertEqual(report["explained_by"], [])


if __name__ == "__main__":
    unittest.main()
