"""Start/stop detector contracts; stdlib only, no camera or model."""
import json
import unittest
from dataclasses import asdict

import detector_fixtures
from detector import (CalibrationError, Frame, Params, Segment, SignDetector, StatusChanged,
                      calibrate)

FIXTURES = sorted(detector_fixtures.FIXTURES.glob("*.json"))
REST = ((0.4, 0.9), (0.6, 0.9))
UP = ((0.45, 0.5), (0.6, 0.9))


def frame(row: dict) -> Frame:
    return Frame(row["t"], row["body"], tuple(tuple(w) for w in row["wrists"]))


def run_fixture(fixture: dict):
    params = Params(**fixture["params"])
    try:
        rest_y = calibrate([frame(row) for row in fixture["calibration"]], params)
    except CalibrationError as error:
        return error.reason, None, [], []
    detector = SignDetector(rest_y, params)
    events = [event for row in fixture["frames"] for event in detector.update(frame(row))]
    return (None, rest_y, [asdict(e) for e in events if isinstance(e, Segment)],
            [e.status for e in events if isinstance(e, StatusChanged)])


class SharedFixtures(unittest.TestCase):
    def test_every_fixture(self):
        self.assertGreaterEqual(len(FIXTURES), 20)
        for path in FIXTURES:
            fixture = json.loads(path.read_text())
            with self.subTest(path.stem):
                error, rest_y, segments, statuses = run_fixture(fixture)
                self.assertEqual(error, fixture["expected_calibration_error"])
                if fixture["expected_rest_y"] is None:
                    self.assertIsNone(rest_y)
                else:
                    self.assertAlmostEqual(rest_y, fixture["expected_rest_y"], places=9)
                self.assertEqual(statuses, fixture["expected_statuses"])
                self.assertEqual(len(segments), len(fixture["expected_segments"]))
                for got, want in zip(segments, fixture["expected_segments"]):
                    self.assertEqual((got["accepted"], got["reason"]), (want["accepted"], want["reason"]))
                    self.assertAlmostEqual(got["start"], want["start"], places=6)
                    self.assertAlmostEqual(got["end"], want["end"], places=6)

    def test_committed_fixtures_match_scenarios(self):
        self.assertEqual([p.stem for p in FIXTURES], sorted(s["name"] for s in detector_fixtures.SCENARIOS))
        for scenario in detector_fixtures.SCENARIOS:
            path = detector_fixtures.FIXTURES / f"{scenario['name']}.json"
            with self.subTest(scenario["name"]):
                self.assertEqual(path.read_text(), detector_fixtures.dump(scenario))


class DetectorContracts(unittest.TestCase):
    def test_defaults_match_shared_spec(self):
        self.assertEqual(asdict(Params()), {
            "calibration_s": 2.0, "rest_margin": 0.08, "default_rest_y": 0.80, "rest_y_min": 0.50,
            "rest_y_max": 0.95, "min_body_fraction": 0.8, "start_hold_s": 0.10, "end_rest_s": 0.40,
            "pre_roll_s": 0.20, "min_sign_s": 0.30, "max_sign_s": 4.0, "lost_body_s": 0.50})

    def test_status_emitted_once_then_only_on_change(self):
        detector = SignDetector(0.8)
        self.assertEqual(detector.update(Frame(0.0, True, REST)), [StatusChanged("watching")])
        self.assertEqual(detector.update(Frame(0.1, True, REST)), [])
        self.assertEqual(detector.update(Frame(0.2, True, UP)), [])
        self.assertEqual(detector.update(Frame(0.3, True, UP)), [StatusChanged("signing")])
        self.assertEqual(detector.update(Frame(0.4, True, UP)), [])

    def test_segment_precedes_status_in_the_same_frame(self):
        detector = SignDetector(0.8)
        for t in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5):
            detector.update(Frame(t, True, UP))
        detector.update(Frame(0.6, True, REST))
        self.assertEqual(detector.update(Frame(1.0, True, REST)),
                         [Segment(0.0, 0.6, True, None), StatusChanged("watching")])

    def test_lost_tracking_segment_precedes_cant_see(self):
        detector = SignDetector(0.8)
        for t in (0.0, 0.1, 0.2):
            detector.update(Frame(t, True, UP))
        detector.update(Frame(0.3, False, ()))
        self.assertEqual(detector.update(Frame(0.8, False, ())),
                         [Segment(0.0, 0.8, False, "lost_tracking"), StatusChanged("cant_see")])

    def test_wrist_detection_without_shoulders_never_starts_a_sign(self):
        detector = SignDetector(0.8)
        events = [e for i in range(14) for e in detector.update(Frame(i / 30, False, UP))]
        self.assertEqual(events, [StatusChanged("watching")])

    def test_time_cannot_go_backwards(self):
        detector = SignDetector(0.8)
        detector.update(Frame(1.0, True, REST))
        detector.update(Frame(1.0, True, REST))
        with self.assertRaises(ValueError):
            detector.update(Frame(0.9, True, REST))

    def test_calibration_errors_carry_reason(self):
        with self.assertRaises(CalibrationError) as caught:
            calibrate([])
        self.assertEqual(caught.exception.reason, "too_short")
        self.assertIsInstance(caught.exception, ValueError)
        hidden = [Frame(i / 10, i % 2 == 0, REST) for i in range(21)]
        with self.assertRaises(CalibrationError) as caught:
            calibrate(hidden)
        self.assertEqual(caught.exception.reason, "cant_see")

    def test_calibration_uses_custom_params(self):
        frames = [Frame(i / 10, True, REST) for i in range(11)]
        with self.assertRaises(CalibrationError):
            calibrate(frames)
        self.assertAlmostEqual(calibrate(frames, Params(calibration_s=1.0, rest_margin=0.1)), 0.8)


if __name__ == "__main__":
    unittest.main()
