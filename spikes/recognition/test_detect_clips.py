"""Clip CLI boundaries with fake MediaPipe results; stdlib only, no camera or model."""
import unittest
from types import SimpleNamespace as NS

from detect_clips import ARTIFACTS, ROOT, calibration_window, clip_name, clips_dir, detect, to_frame, within
from detector import CalibrationError, Frame, Params, Segment, State

REST, UP = ((0.4, 0.9), (0.6, 0.9)), ((0.45, 0.5), (0.6, 0.9))
BOTH_UP = ((0.45, 0.5), (0.55, 0.5))


def pose(left=0.9, right=0.9):
    landmarks = [NS(x=0.5, y=0.5, visibility=0.0) for _ in range(33)]
    landmarks[11], landmarks[12] = NS(x=0.6, y=0.3, visibility=left), NS(x=0.4, y=0.3, visibility=right)
    return NS(landmark=landmarks)


def hand(x, y):
    return NS(landmark=[NS(x=x, y=y)] + [NS(x=0.99, y=0.01) for _ in range(20)])


def result(pose_landmarks=None, left=None, right=None):
    return NS(pose_landmarks=pose_landmarks, left_hand_landmarks=left, right_hand_landmarks=right)


def frames(*runs, t0=0.0):
    out = []
    for wrists, count in runs:
        out += [Frame(round(t0 + (len(out) + i) / 30, 4), True, wrists) for i in range(count)]
    return out


class FrameMapping(unittest.TestCase):
    def test_body_needs_both_shoulders_visible(self):
        self.assertTrue(to_frame(1.5, result(pose(0.5, 0.5))).body)
        self.assertFalse(to_frame(1.5, result(pose(0.49, 0.9))).body)
        self.assertFalse(to_frame(1.5, result(pose(0.9, 0.49))).body)
        self.assertFalse(to_frame(1.5, result()).body)

    def test_wrists_are_hand_landmark_zero_left_then_right(self):
        frame = to_frame(2.0, result(pose(), hand(0.3, 0.7), hand(0.6, 0.4)))
        self.assertEqual(frame, Frame(2.0, True, ((0.3, 0.7), (0.6, 0.4))))
        self.assertEqual(to_frame(0, result(None, None, hand(0.6, 0.4))).wrists, ((0.6, 0.4),))
        self.assertEqual(to_frame(0, result(pose())).wrists, ())

    def test_wrists_kept_without_body_and_clamped_to_image(self):
        frame = to_frame(0.0, result(None, hand(-0.1, 1.2), hand(1.3, -0.2)))
        self.assertEqual(frame, Frame(0.0, False, ((0.0, 1.0), (1.0, 0.0))))


class ClipOutput(unittest.TestCase):
    def test_clips_only_under_artifacts(self):
        self.assertEqual(clips_dir(ARTIFACTS / "detector"), (ARTIFACTS / "detector").resolve())
        for outside in (ROOT / "clips", ARTIFACTS / ".." / "clips", "/tmp/clips"):
            with self.subTest(outside), self.assertRaises(ValueError):
                clips_dir(outside)

    def test_cut_includes_both_boundary_frames(self):
        segment = Segment(1.0, 2.0, True, None)
        self.assertEqual([within(t, segment) for t in (0.9667, 1.0, 2.0, 2.0333)], [False, True, True, False])

    def test_clip_name_records_verdict(self):
        self.assertEqual(clip_name("take", 3, Segment(0, 1, False, "too_long")), "take-03-too_long.mp4")
        self.assertEqual(clip_name("take", 1, Segment(0, 1, True, None)), "take-01-accepted.mp4")


class SavedClipDetection(unittest.TestCase):
    def test_calibrates_on_leading_rest_only(self):
        clip = frames((REST, 61), (BOTH_UP, 100), (REST, 30))  # all frames: median 0.5
        self.assertEqual(len(calibration_window(clip, Params())), 61)
        rest_y, segments, state = detect(clip, Params())
        self.assertAlmostEqual(rest_y, 0.82)
        self.assertEqual(segments, [Segment(clip[61].t - 0.2, clip[161].t, True, None)])
        self.assertIs(state, State.WATCHING)

    def test_short_take_needs_explicit_rest_line(self):
        take = frames((REST, 6), (UP, 20), (REST, 15))
        with self.assertRaises(CalibrationError):
            detect(take, Params())
        rest_y, segments, _ = detect(take, Params(), rest_y=0.8)
        self.assertEqual(rest_y, 0.8)
        self.assertEqual(segments, [Segment(0.0, take[26].t, True, None)])

    def test_reports_sign_unfinished_at_end_of_clip(self):
        _, segments, state = detect(frames((REST, 6), (UP, 20), (REST, 5)), Params(), rest_y=0.8)
        self.assertEqual((segments, state), ([], State.SIGNING))


if __name__ == "__main__":
    unittest.main()
