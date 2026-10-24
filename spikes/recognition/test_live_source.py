"""Live recognizer: scripted frames, fake featurizer/embedder, synthetic bundle.

No webcam, no MediaPipe and no model: the frames are detector inputs with a frame
index as their "landmarks", so each test can check exactly which frames were matched.
"""
import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

import live_source as ls
import mac_bridge as mb
import recognition_data as data
import retrieval
from detector import Frame

FPS = 30
DIM = len(data.VOCABULARY) + 2
REST_Y, UP_Y = 0.9, 0.3  # calibrated rest line = 0.9 - 0.08 = 0.82
THRESHOLDS = {"similarity": 0.8, "margin": 0.1}
GOOD = {"pose_fraction": 1.0, "hand_fraction": 0.9}


def axis(index):
    vector = np.zeros(DIM)
    vector[index] = 1.0
    return vector


def sign_vector(label):
    return axis(data.VOCABULARY.index(label))


def references():
    """One reference per sign on its own axis; thankyou sits close to hello (cos 0.95)."""
    rows = [{"id": f"enrol-{label}", "label": label, "embedding": sign_vector(label)}
            for label in data.VOCABULARY]
    rows[data.VOCABULARY.index("thankyou")]["embedding"] = 0.95 * axis(0) + 0.3122 * axis(1)
    return rows


def write_bundle(directory, **changes):
    document = retrieval.bundle({"encoder": "signclip", "checkpoint": "synthetic"},
                                THRESHOLDS, references())
    document.update(changes)
    path = Path(directory) / "bundle.json"
    path.write_text(json.dumps(document))
    return path


class Script:
    """Builds detector frames at FPS; the wall clock runs ahead of the clip clock by OFFSET."""
    OFFSET = 1000.0

    def __init__(self, fps=FPS):
        self.fps, self.frames = fps, []

    def hold(self, seconds, y=REST_Y, body=True):
        for _ in range(round(seconds * self.fps)):
            t = len(self.frames) / self.fps
            self.frames.append(Frame(t, body, ((0.4, y), (0.6, REST_Y)) if body else ()))
        return self

    def sign(self, seconds):
        return self.hold(2.0).hold(seconds, UP_Y).hold(0.6)

    def observations(self, clock=None):
        for index, frame in enumerate(self.frames):
            if clock is not None:
                clock.now = self.OFFSET + frame.t
            yield ls.Observation(self.OFFSET + frame.t, frame, index)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeModel:
    """Records the frames it featurized; embeds to a chosen vector after `compute_s`."""

    def __init__(self, vector, quality=GOOD, clock=None, compute_s=0.0, error=None):
        self.vector, self.quality, self.error = vector, quality, error
        self.clock, self.compute_s = clock, compute_s
        self.calls = []

    def featurize(self, observations):
        self.calls.append([o.landmarks for o in observations])
        if self.error:
            raise ValueError(self.error)
        return np.zeros((len(observations), 609), dtype=np.float32), dict(self.quality)

    def embed(self, features):
        if self.clock is not None:
            self.clock.now += self.compute_s
        return self.vector


def run(clips, model=None, bundle_dir=None, max_frames=256, **options):
    lines = []
    matcher = None
    if model is not None:
        with TemporaryDirectory() as directory:
            bundle = ls.load_bundle(write_bundle(bundle_dir or directory))
        matcher = ls.Matcher(bundle, model.featurize, model.embed, max_frames)
    source = ls.LiveSource(clips, matcher, out=lines.append, **options)
    return list(source), lines, source


class Matching(unittest.TestCase):
    def test_accepted_segment_yields_the_matching_sign_from_its_own_frames(self):
        script = Script().sign(1.0)
        model = FakeModel(sign_vector("doctor"))
        results, lines, _ = run([script.observations()], model)
        self.assertEqual([r.sign for r in results], ["doctor"])
        self.assertIsNone(results[0].reason)
        segment = results[0].segment
        self.assertTrue(segment.accepted)
        self.assertAlmostEqual(segment.start, 2.0 - 0.2)  # pre-roll before the raise
        self.assertAlmostEqual(segment.end, 3.0)  # first rest frame
        expected = [i for i, f in enumerate(script.frames)
                    if segment.start - 1e-9 <= f.t <= segment.end + 1e-9]
        self.assertEqual(model.calls, [expected])
        self.assertAlmostEqual(results[0].similarity, 1.0)
        self.assertIn("rest line y=0.820", lines)

    def test_low_similarity_is_unsure(self):
        vector = 0.7 * sign_vector("doctor") + 0.714 * axis(DIM - 1)
        results, _, _ = run([Script().sign(1.0).observations()], FakeModel(vector))
        self.assertEqual([r.sign for r in results], [None])
        self.assertIn("insufficient evidence", results[0].reason)
        self.assertLess(results[0].similarity, THRESHOLDS["similarity"])

    def test_close_runner_up_is_unsure(self):
        results, _, _ = run([Script().sign(1.0).observations()], FakeModel(sign_vector("hello")))
        self.assertEqual([r.sign for r in results], [None])
        self.assertGreater(results[0].similarity, THRESHOLDS["similarity"])
        self.assertLess(results[0].margin, THRESHOLDS["margin"])

    def test_poor_tracking_is_unsure_even_with_a_perfect_match(self):
        for quality in ({"pose_fraction": 0.59, "hand_fraction": 0.9},
                        {"pose_fraction": 1.0, "hand_fraction": 0.19}):
            with self.subTest(quality=quality):
                results, _, _ = run([Script().sign(1.0).observations()],
                                    FakeModel(sign_vector("doctor"), quality))
                self.assertEqual([r.sign for r in results], [None])

    def test_untrackable_segment_is_unsure_not_fatal(self):
        model = FakeModel(sign_vector("doctor"), error="No tracked shoulders")
        results, _, _ = run([Script().sign(1.0).observations()], model)
        self.assertEqual([(r.sign, r.reason) for r in results], [(None, "No tracked shoulders")])

    def test_more_than_256_frames_is_refused_not_truncated(self):
        script = Script(fps=80).sign(3.2)  # 0.2 s pre-roll + 3.2 s + end frame > 256 frames at 80 fps
        model = FakeModel(sign_vector("doctor"))
        results, _, _ = run([script.observations()], model)
        self.assertEqual([r.sign for r in results], [None])
        self.assertIn("> 256", results[0].reason)
        self.assertEqual(model.calls, [])

    def test_the_frame_limit_is_inclusive(self):
        script = Script(fps=80).sign(3.2)  # 273 frames from 1.8 s to 5.2 s
        for limit, expected in ((273, "doctor"), (272, None)):
            with self.subTest(limit=limit):
                results, _, _ = run([script.observations()], FakeModel(sign_vector("doctor")),
                                    max_frames=limit)
                self.assertEqual([r.sign for r in results], [expected])


class Segments(unittest.TestCase):
    def test_rejected_and_unfinished_segments_yield_nothing(self):
        script = (Script().hold(0.2, UP_Y).hold(0.6)  # too short (pre-roll clamped at the clip start)
                  .hold(4.5, UP_Y).hold(0.6)  # too long
                  .hold(0.5, UP_Y).hold(0.7, body=False).hold(0.6)  # tracking lost mid-sign
                  .hold(1.0, UP_Y))  # the clip ends mid-sign
        model = FakeModel(sign_vector("doctor"))
        results, lines, _ = run([script.observations()], model, rest_y=0.82)
        self.assertEqual(results, [])
        self.assertEqual(model.calls, [])
        for reason in ("too_short", "too_long", "lost_tracking"):
            self.assertEqual(sum(f"rejected ({reason})" in line for line in lines), 1, reason)
        self.assertTrue(any(line.startswith("unfinished") for line in lines))

    def test_two_signs_in_one_clip_give_two_results(self):
        script = Script().sign(1.0).hold(0.8, UP_Y).hold(0.6)
        results, _, _ = run([script.observations()], FakeModel(sign_vector("yes")))
        self.assertEqual([r.sign for r in results], ["yes", "yes"])


class MissingBundle(unittest.TestCase):
    def test_missing_bundle_warns_and_returns_none(self):
        warnings = []
        self.assertIsNone(ls.load_bundle(Path("/nonexistent/bundle.json"), warnings.append))
        self.assertIsNone(ls.load_bundle(None, warnings.append))
        self.assertEqual(len(warnings), 2)
        self.assertIn("/nonexistent/bundle.json", warnings[0])
        self.assertIn("nothing is guessed", warnings[0])

    def test_without_a_bundle_every_accepted_segment_is_unsure(self):
        script = Script().sign(1.0).hold(0.8, UP_Y).hold(0.6)
        results, _, _ = run([script.observations()])
        self.assertEqual([(r.sign, r.reason) for r in results], [(None, "no recognition bundle")] * 2)

    def test_a_bundle_that_breaks_the_contract_is_an_error(self):
        broken = [{"version": 2}, {"quality": {"min_pose_fraction": 0.5, "min_hand_fraction": 0.2}},
                  {"thresholds": {"similarity": float("nan"), "margin": 0.1}},
                  {"embedding_dim": DIM + 1}]
        for change in broken:
            with self.subTest(change=change), TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    ls.load_bundle(write_bundle(directory, **change))
        with TemporaryDirectory() as directory:
            document = json.loads(write_bundle(directory).read_text())
            document["references"] = document["references"][1:]
            path = Path(directory) / "short.json"
            path.write_text(json.dumps(document))
            with self.assertRaises(ValueError):
                ls.load_bundle(path)

    def test_bundle_references_keep_their_labels_and_embeddings(self):
        with TemporaryDirectory() as directory:
            bundle = ls.load_bundle(write_bundle(directory))
        self.assertEqual(bundle.thresholds, THRESHOLDS)
        self.assertEqual([r["label"] for r in bundle.references], list(data.VOCABULARY))
        np.testing.assert_allclose(bundle.references[5]["embedding"], sign_vector("doctor"))


class Latency(unittest.TestCase):
    def test_latency_runs_from_the_sign_end_to_the_result(self):
        clock = Clock()
        script = Script().sign(1.0)
        model = FakeModel(sign_vector("doctor"), clock=clock, compute_s=0.25)
        results, lines, source = run([script.observations(clock)], model, clock=clock)
        # The segment closes after 0.40 s of rest; matching then takes 0.25 s.
        self.assertAlmostEqual(results[0].latency_s, 0.40 + 0.25, places=6)
        self.assertEqual(source.latencies, [results[0].latency_s])
        self.assertTrue(any("latency 0.65 s" in line for line in lines))
        self.assertIn("within the 2 s budget", source.summary())

    def test_slow_results_are_flagged_over_budget(self):
        clock = Clock()
        model = FakeModel(sign_vector("doctor"), clock=clock, compute_s=1.7)
        _, lines, source = run([Script().sign(1.0).observations(clock)], model, clock=clock)
        self.assertTrue(any("OVER the 2 s budget" in line for line in lines))
        self.assertIn("OVER the 2 s budget", source.summary())


class Calibration(unittest.TestCase):
    def test_camera_retries_calibration_until_the_body_is_visible(self):
        script = Script().hold(2.1, body=False).sign(1.0)
        results, lines, _ = run([script.observations()], FakeModel(sign_vector("doctor")),
                                retry_calibration=True)
        self.assertEqual([r.sign for r in results], ["doctor"])
        self.assertIn("Calibration cant_see: move back so both shoulders stay in view", lines)
        self.assertIn("rest line y=0.820", lines)

    def test_replay_skips_a_clip_that_fails_calibration_and_goes_on(self):
        bad, good = Script().hold(2.1, body=False).sign(1.0), Script().sign(1.0)
        results, lines, _ = run([bad.observations(), good.observations()],
                                FakeModel(sign_vector("time")))
        self.assertEqual([r.sign for r in results], ["time"])
        self.assertEqual(sum(line.startswith("Calibration cant_see") for line in lines), 1)

    def test_given_rest_line_skips_calibration(self):
        script = Script().hold(0.3).hold(1.0, UP_Y).hold(0.6)  # no 2 s rest at the start
        results, lines, _ = run([script.observations()], FakeModel(sign_vector("today")), rest_y=0.82)
        self.assertEqual([r.sign for r in results], ["today"])
        self.assertIn("rest line y=0.820 (given)", lines)

    def test_closing_the_preview_stops_the_source(self):
        shown = []

        def show(image, status, rest_y, message):
            shown.append(status)
            return len(shown) < 10

        observations = (ls.Observation(o.wall, o.frame, o.landmarks, image="img")
                        for o in Script().sign(1.0).observations())
        results, _, _ = run([observations], FakeModel(sign_vector("doctor")), show=show)
        self.assertEqual(results, [])
        self.assertEqual(shown, ["calibrating"] * 10)


class BridgeBoundary(unittest.TestCase):
    def test_vocabularies_match(self):
        self.assertEqual(mb.SIGNS, data.VOCABULARY)

    def test_results_cross_to_the_bridge_as_lines(self):
        results, _, _ = run([Script().sign(1.0).hold(0.8, UP_Y).hold(0.6).observations()],
                            FakeModel(sign_vector("evening")))
        lines = [ls.result_json(r) for r in results]
        self.assertEqual([mb.parse_result_line(line) for line in lines], ["evening", "evening"])
        self.assertEqual(json.loads(lines[0])["segment"], [1.8, 3.0])


class CommandLine(unittest.TestCase):
    def test_noise_on_stdout_cannot_corrupt_result_lines(self):
        code = ("import os, live_source\n"
                "results = live_source.result_stream()\n"
                "print('python noise')\n"
                "os.write(1, b'native noise\\n')\n"
                "results.write('{\"sign\": null}\\n')\n")
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                              cwd=Path(__file__).parent, timeout=60, check=True)
        self.assertEqual(done.stdout, '{"sign": null}\n')
        self.assertEqual(done.stderr, "python noise\nnative noise\n")

    def test_bad_arguments_fail_before_any_camera_or_model(self):
        with TemporaryDirectory() as directory:
            Path(directory, "notes.txt").write_text("not a clip")
            for argv in (["--replay-videos", directory], ["--replay-videos", f"{directory}/missing"],
                         ["--camera", "0", "--rest-y", "1.2"],
                         ["--camera", "0", "--replay-videos", directory], []):
                with self.subTest(argv=argv), redirect_stderr(io.StringIO()), \
                        self.assertRaises(SystemExit) as raised:
                    ls.main(argv)
                self.assertEqual(raised.exception.code, 2)

    def test_replay_lists_only_videos_in_name_order(self):
        with TemporaryDirectory() as directory:
            for name in ("b.MOV", "a.mp4", "c.m4v", "notes.txt", "d.avi"):
                Path(directory, name).write_bytes(b"")
            self.assertEqual([p.name for p in ls.videos_in(Path(directory))],
                             ["a.mp4", "b.MOV", "c.m4v"])


if __name__ == "__main__":
    unittest.main()
