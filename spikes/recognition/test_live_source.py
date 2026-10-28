"""Live recognizer: scripted frames, fake featurizer/embedder, synthetic bundle.

No webcam, no MediaPipe and no model: the frames are detector inputs with a frame
index as their "landmarks", so each test can check exactly which frames were matched.
"""
import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

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


def run(clips, model=None, bundle_dir=None, max_frames=256, bundle_changes=None, **options):
    lines = []
    matcher = None
    if model is not None:
        with TemporaryDirectory() as directory:
            bundle = ls.load_bundle(write_bundle(bundle_dir or directory, **(bundle_changes or {})),
                                    lines.append)
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
        self.assertAlmostEqual(results[0].match.similarity, 1.0)
        self.assertIn("rest line y=0.820", lines)

    def test_low_similarity_is_unsure(self):
        vector = 0.7 * sign_vector("doctor") + 0.714 * axis(DIM - 1)
        results, _, _ = run([Script().sign(1.0).observations()], FakeModel(vector))
        self.assertEqual([r.sign for r in results], [None])
        self.assertIn("insufficient evidence", results[0].reason)
        self.assertLess(results[0].match.similarity, THRESHOLDS["similarity"])
        self.assertEqual(results[0].match.failed_checks, ("similarity",))

    def test_close_runner_up_is_unsure(self):
        results, _, _ = run([Script().sign(1.0).observations()], FakeModel(sign_vector("hello")))
        self.assertEqual([r.sign for r in results], [None])
        self.assertGreater(results[0].match.similarity, THRESHOLDS["similarity"])
        self.assertLess(results[0].match.margin, THRESHOLDS["margin"])
        self.assertEqual(results[0].match.failed_checks, ("margin",))

    def test_poor_tracking_is_unsure_even_with_a_perfect_match(self):
        for quality, check in (({"pose_fraction": 0.59, "hand_fraction": 0.9}, "pose"),
                               ({"pose_fraction": 1.0, "hand_fraction": 0.19}, "hands")):
            with self.subTest(quality=quality):
                results, _, _ = run([Script().sign(1.0).observations()],
                                    FakeModel(sign_vector("doctor"), quality))
                self.assertEqual([r.sign for r in results], [None])
                self.assertEqual(results[0].match.failed_checks, (check,))

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


def unit_mix(**weights):
    vector = sum(weight * sign_vector(sign) for sign, weight in weights.items())
    return vector / np.linalg.norm(vector)


ALL_THRESHOLDS = {**THRESHOLDS, **data.QUALITY}


class Evidence(unittest.TestCase):
    """The extended result line: what a person needs to judge a match, beside the decision."""

    def details(self, model, **options):
        results, lines, _ = run([Script().sign(1.0).observations()], model, **options)
        self.assertEqual(len(results), 1)
        line = ls.result_json(results[0])
        return json.loads(line), line, lines

    def test_accepted_line_keeps_the_old_keys_and_adds_top3_quality_and_thresholds(self):
        details, line, _ = self.details(FakeModel(unit_mix(doctor=0.8, time=0.5, morning=0.3)))
        self.assertEqual(mb.parse_result_line(line), "doctor")
        self.assertIsNone(details["reason"])
        self.assertEqual([c["sign"] for c in details["top"]], ["doctor", "time", "morning"])
        expected = [0.8, 0.5, 0.3] / np.linalg.norm([0.8, 0.5, 0.3])
        np.testing.assert_allclose([c["similarity"] for c in details["top"]], expected, atol=1e-4)
        self.assertEqual(details["similarity"], details["top"][0]["similarity"])
        self.assertAlmostEqual(details["margin"], expected[0] - expected[1], places=4)
        self.assertEqual(details["quality"], GOOD)
        self.assertEqual(details["thresholds"], ALL_THRESHOLDS)
        self.assertEqual(details["failed_checks"], [])
        self.assertIs(details["provisional"], False)
        self.assertEqual(details["segment"], [1.8, 3.0])
        self.assertIsInstance(details["latency_ms"], float)

    def test_top_list_stops_at_three(self):
        details, _, _ = self.details(FakeModel(unit_mix(doctor=0.9, time=0.3, morning=0.2, today=0.1)))
        self.assertEqual([c["sign"] for c in details["top"]], ["doctor", "time", "morning"])

    def test_unsure_line_names_the_failed_checks_and_keeps_its_reason(self):
        details, line, _ = self.details(FakeModel(sign_vector("hello"), {"pose_fraction": 0.5,
                                                                        "hand_fraction": 0.9}))
        self.assertIsNone(mb.parse_result_line(line))
        self.assertEqual(details["failed_checks"], ["margin", "pose"])
        self.assertTrue(details["reason"].startswith("insufficient evidence (best hello 1.000"))
        self.assertEqual([c["sign"] for c in details["top"]], ["hello", "thankyou", "afternoon"])
        self.assertEqual(details["quality"], {"pose_fraction": 0.5, "hand_fraction": 0.9})

    def test_unmatchable_segment_keeps_thresholds_but_has_no_candidates(self):
        details, _, _ = self.details(FakeModel(sign_vector("doctor"), error="No tracked shoulders"))
        self.assertEqual((details["sign"], details["reason"]), (None, "No tracked shoulders"))
        self.assertEqual((details["top"], details["quality"], details["failed_checks"]), ([], None, []))
        self.assertEqual(details["thresholds"], ALL_THRESHOLDS)

    def test_without_a_bundle_there_is_no_evidence_to_show(self):
        results, _, _ = run([Script().sign(1.0).observations()])
        details = json.loads(ls.result_json(results[0]))
        self.assertEqual({k: details[k] for k in ("top", "quality", "thresholds", "failed_checks",
                                                  "provisional")},
                         {"top": [], "quality": None, "thresholds": None, "failed_checks": [],
                          "provisional": False})

    def test_a_value_exactly_at_its_cut_off_passes_like_in_the_decision(self):
        at = {"pose_fraction": 0.6, "hand_fraction": 0.2}
        self.assertEqual(ls.failed_checks(0.8, 0.1, at, ALL_THRESHOLDS), ())
        below = {"pose_fraction": 0.59, "hand_fraction": 0.19}
        self.assertEqual(ls.failed_checks(0.79, 0.09, below, ALL_THRESHOLDS),
                         ("similarity", "margin", "pose", "hands"))
        self.assertEqual(ls.failed_checks(0.9, 0.5, {}, ALL_THRESHOLDS), ("pose", "hands"))

    def test_failed_checks_are_empty_exactly_when_the_decision_accepts(self):
        with TemporaryDirectory() as directory:
            bundle = ls.load_bundle(write_bundle(directory))
        rng = np.random.default_rng(7)
        frame = [ls.Observation(0.0, Frame(0.0, True, ()), 0)]
        samples = [(sign_vector("doctor"), dict(data.QUALITY, pose_fraction=0.6, hand_fraction=0.2))]
        for _ in range(400):
            vector = sign_vector(rng.choice(data.VOCABULARY)) + rng.normal(0, 0.35, DIM)
            samples.append((vector, {"pose_fraction": rng.uniform(0.4, 1), "hand_fraction": rng.uniform(0, 0.5)}))
        outcomes = set()
        for vector, quality in samples:
            model = FakeModel(vector, quality)
            match = ls.Matcher(bundle, model.featurize, model.embed, 256)(frame)
            self.assertEqual(match.sign is None, bool(match.failed_checks), (match, quality))
            outcomes.update(match.failed_checks or ("accepted",))
        self.assertEqual(outcomes, {"accepted", "similarity", "margin", "pose", "hands"})


class Provisional(unittest.TestCase):
    def test_a_provisional_bundle_warns_loudly_and_marks_every_result(self):
        results, lines, _ = run([Script().sign(1.0).observations()], FakeModel(sign_vector("doctor")),
                                bundle_changes={"provisional": True})
        self.assertTrue(any(mb.PROVISIONAL_BANNER in line for line in lines))
        self.assertEqual([r.sign for r in results], ["doctor"])
        self.assertIs(json.loads(ls.result_json(results[0]))["provisional"], True)

    def test_flag_is_optional_and_must_be_a_boolean(self):
        for value, expected in ((False, False), (True, True)):
            with self.subTest(value=value), TemporaryDirectory() as directory:
                self.assertIs(ls.load_bundle(write_bundle(directory, provisional=value),
                                             lambda _: None).provisional, expected)
        with TemporaryDirectory() as directory:
            warnings = []
            self.assertIs(ls.load_bundle(write_bundle(directory), warnings.append).provisional, False)
            self.assertEqual(warnings, [])
            with self.assertRaises(ValueError):
                ls.load_bundle(write_bundle(directory, provisional="yes"))
            with self.assertRaises(ValueError):
                ls.load_bundle(write_bundle(directory, provisional=1))


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
        self.assertIn("#1 1.80-3.00 s  ✓ doctor  (doctor 1.00 | afternoon 0.00 | evening 0.00; "
                      "margin 1.00; 0.65 s)", lines)
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

        def show(image, overlay):
            shown.append(overlay.status)
            return len(shown) < 10

        observations = (ls.Observation(o.wall, o.frame, o.landmarks, image="img")
                        for o in Script().sign(1.0).observations())
        results, _, _ = run([observations], FakeModel(sign_vector("doctor")), show=show)
        self.assertEqual(results, [])
        self.assertEqual(shown, ["calibrating"] * 10)


class Gate:
    """A fake mac_bridge end of --handshake: the go (or stop) comes after `waits` polls."""

    def __init__(self, waits, answer=True):
        self.waits, self.answer, self.events, self.pulled = waits, answer, [], 0

    def frames(self, observations):
        """Counts the frames the recognizer has read, to see what it read while holding."""
        for observation in observations:
            self.pulled += 1
            yield observation

    def ready(self, rest_y):
        self.events.append(("ready", round(rest_y, 3), self.pulled))

    def wait(self, timeout):
        if self.waits:
            self.waits -= 1
            return None
        self.events.append(("go" if self.answer else "stop", self.pulled))
        return self.answer

    def handshake(self, playback=None):
        return ls.Handshake(self.ready, self.wait, playback)


class StartUpHandshake(unittest.TestCase):
    """mac_bridge places the call only after the ready line; nothing is recognised before its go."""

    def test_clips_say_ready_after_calibration_then_pause_until_the_go(self):
        script = Script().sign(1.0)
        gate = Gate(waits=5)
        model = FakeModel(sign_vector("doctor"))
        results, lines, _ = run([gate.frames(script.observations())], model,
                                handshake=gate.handshake(ls.PlaybackClock(Clock())))
        calibrated = round(2.0 * FPS) + 1  # the 2 s rest ends on this frame
        self.assertEqual(gate.events, [("ready", 0.82, calibrated), ("go", calibrated)],
                         "ready once calibrated, and not one clip frame read while holding")
        self.assertEqual([r.sign for r in results], ["doctor"])
        first_result = next(line for line in lines if line.startswith("#1"))
        self.assertLess(lines.index(ls.HOLD_MESSAGE), lines.index(first_result))

    def test_a_camera_keeps_running_while_holding_but_nothing_it_sees_is_a_sign(self):
        held = Script().hold(2.1).hold(1.0, UP_Y).hold(0.6)  # signs while the call connects
        script = Script().hold(2.1).hold(1.0, UP_Y).hold(0.6).sign(1.0)
        model = FakeModel(sign_vector("doctor"))
        unheld, _, _ = run([script.observations()], FakeModel(sign_vector("doctor")))
        self.assertEqual(len(unheld), 2)  # without the handshake the early sign counts

        calibrated = round(2.0 * FPS) + 1
        gate = Gate(waits=len(held.frames) - calibrated - 1)  # the go comes with the last held frame
        results, _, _ = run([gate.frames(script.observations())], model, handshake=gate.handshake(),
                            retry_calibration=True)
        self.assertEqual(gate.events, [("ready", 0.82, calibrated + 1), ("go", len(held.frames))])
        self.assertEqual([r.sign for r in results], ["doctor"])
        [matched] = model.calls
        held_frames = set(range(calibrated, len(held.frames)))
        self.assertFalse(held_frames & set(matched), "frames seen while holding never become a sign")

    def test_eof_instead_of_go_stops_without_a_result_and_skips_later_clips(self):
        gate = Gate(waits=0, answer=False)
        results, lines, source = run([gate.frames(Script().sign(1.0).observations()),
                                      gate.frames(Script().sign(1.0).observations())],
                                     FakeModel(sign_vector("doctor")), handshake=gate.handshake(ls.PlaybackClock()))
        self.assertEqual(results, [])
        self.assertEqual([event[0] for event in gate.events], ["ready", "stop"])
        self.assertIn("no call: the bridge closed the start-up handshake", lines)
        self.assertEqual(gate.pulled, round(2.0 * FPS) + 1, "the second clip was never opened")

    def test_without_a_calibration_there_is_no_ready_line(self):
        gate = Gate(waits=0)
        results, _, _ = run([gate.frames(Script().hold(2.1, body=False).observations())],
                            FakeModel(sign_vector("doctor")), handshake=gate.handshake(ls.PlaybackClock()))
        self.assertEqual((results, gate.events), ([], []))
        camera = Gate(waits=0)
        run([iter(())], FakeModel(sign_vector("doctor")), rest_y=0.82, handshake=camera.handshake())
        self.assertEqual(camera.events, [], "a camera that gives no frame is not ready")

    def test_replayed_clips_hold_once_before_the_first_clip(self):
        gate = Gate(waits=2)
        results, _, _ = run([gate.frames(Script().sign(1.0).observations()),
                             gate.frames(Script().sign(1.0).observations())],
                            FakeModel(sign_vector("time")), handshake=gate.handshake(ls.PlaybackClock()))
        self.assertEqual([r.sign for r in results], ["time", "time"])
        self.assertEqual([event[0] for event in gate.events], ["ready", "go"])

    def test_a_paused_clip_resumes_at_its_own_pace(self):
        def play(hold_s, playback):
            sleeps = []

            def sleep(seconds):
                sleeps.append(round(seconds, 6))
                wall.now += seconds

            frames = [(i * 0.5, f"f{i}") for i in range(4)]
            images = ls.playlist_images([Path("a")], True, read=lambda path: iter(frames),
                                        clock=playback, sleep=sleep)
            played = [next(images)]
            with playback.held():
                wall.now += hold_s  # the recognizer holds for the go
            played += list(images)
            return [round(t_wall - played[0][1], 6) for _, t_wall, _ in played], sleeps

        wall = Clock()
        self.assertEqual(play(5.0, ls.PlaybackClock(wall)), ([0.0, 0.5, 1.0, 1.5], [0.5, 0.5, 0.5]))

    def test_start_signal_reads_go_or_eof_from_its_stream(self):
        self.assertTrue(ls.StartSignal(io.StringIO("go\n")).wait(5))
        self.assertFalse(ls.StartSignal(io.StringIO("")).wait(5))
        self.assertFalse(ls.StartSignal(io.StringIO("stop\n")).wait(5))
        read_end, write_end = os.pipe()
        with os.fdopen(read_end) as pending, os.fdopen(write_end, "w") as bridge:
            signal = ls.StartSignal(pending)
            self.assertIsNone(signal.wait(0.05))
            bridge.write("go\n")
            bridge.flush()
            self.assertTrue(signal.wait(5))


def with_images(observations):
    return (ls.Observation(o.wall, o.frame, o.landmarks, image=o.landmarks) for o in observations)


class Preview(unittest.TestCase):
    def overlays(self, model=None, **options):
        shown = []
        script = Script().sign(1.0).hold(0.8, UP_Y).hold(0.6)

        def show(image, overlay):
            shown.append((image, overlay))
            return True

        results, _, _ = run([with_images(script.observations())], model, show=show, **options)
        return results, shown

    def test_the_latest_result_stays_on_screen_until_the_next_one(self):
        results, shown = self.overlays(FakeModel(sign_vector("doctor")))
        self.assertEqual(len(results), 2)
        self.assertEqual([image for image, _ in shown], list(range(len(shown))))  # every frame
        lasts = [overlay.last for _, overlay in shown]
        first = lasts.index(results[0])
        self.assertTrue(all(last is None for last in lasts[:first]))
        second = lasts.index(results[1])
        self.assertTrue(all(last is results[0] for last in lasts[first:second]))
        self.assertTrue(all(last is results[1] for last in lasts[second:]))
        self.assertEqual(shown[first][1].message, f"#1 doctor  {results[0].latency_s:.2f} s")
        self.assertEqual(shown[0][1].status, "calibrating")
        self.assertIn("signing", {overlay.status for _, overlay in shown})
        self.assertEqual(shown[-1][1].rest_y, 0.9 - 0.08)
        self.assertFalse(any(overlay.provisional for _, overlay in shown))

    def test_a_provisional_bundle_shows_the_banner_from_the_first_frame(self):
        _, shown = self.overlays(FakeModel(sign_vector("doctor")), bundle_changes={"provisional": True})
        self.assertTrue(all(overlay.provisional for _, overlay in shown))
        _, shown = self.overlays()
        self.assertFalse(any(overlay.provisional for _, overlay in shown))


def recognition(model=None, **options):
    results, _, _ = run([Script().sign(1.0).observations()], model, **options)
    return results[0]


class ResultPanel(unittest.TestCase):
    def test_accepted_sign_gets_a_green_label_and_the_numbers_behind_it(self):
        result = recognition(FakeModel(unit_mix(doctor=0.8, time=0.5, morning=0.3)))
        panel = ls.result_panel(result)
        self.assertEqual((panel.label, panel.accepted, panel.why), ("doctor", True, None))
        self.assertEqual([sign for sign, _ in panel.bars], ["doctor", "time", "morning"])
        self.assertAlmostEqual(panel.bars[1][1], 0.5 / np.linalg.norm([0.8, 0.5, 0.3]), places=4)
        self.assertEqual(panel.similarity_cut, 0.8)
        self.assertEqual(panel.footer, (f"margin 0.30 (min 0.10)  {result.latency_s:.2f} s",
                                        "body 1.00 (min 0.60)  hands 0.90 (min 0.20)"))

    def test_unsure_sign_shows_a_question_mark_and_why(self):
        panel = ls.result_panel(recognition(FakeModel(sign_vector("hello"))))
        self.assertEqual((panel.label, panel.accepted, panel.why), ("?", False, "low margin"))
        self.assertEqual([sign for sign, _ in panel.bars], ["hello", "thankyou", "afternoon"])

    def test_without_a_bundle_only_the_reason_and_latency_show(self):
        result = recognition()
        panel = ls.result_panel(result)
        self.assertEqual((panel.label, panel.bars, panel.similarity_cut, panel.why),
                         ("?", (), None, "no recognition bundle"))
        self.assertEqual(panel.footer, (f"{result.latency_s:.2f} s",))


class DrawOverlay(unittest.TestCase):
    """Pixel checks on a black frame: the colours carry the meaning."""
    HEIGHT, WIDTH = 720, 1280

    def draw(self, last=None, provisional=False, status="watching"):
        view = np.zeros((self.HEIGHT, self.WIDTH, 3), np.uint8)
        ls.draw_overlay(view, ls.Overlay(status, 0.82, "Ready", last, provisional))
        return view

    def count(self, region, colour):
        return int(np.all(region == colour, axis=-1).sum())

    def panel(self, view):
        return view[:400, self.WIDTH - ls.PANEL_WIDTH - 10:]

    def test_accepted_result_is_green_and_never_red(self):
        view = self.draw(recognition(FakeModel(sign_vector("doctor"))))
        self.assertGreater(self.count(self.panel(view), ls.GREEN), 500)
        self.assertEqual(self.count(view, ls.RED), 0)
        self.assertGreater(self.count(self.panel(view), ls.YELLOW), 0)  # the cut-off ticks

    def test_unsure_result_is_red_and_never_green(self):
        view = self.draw(recognition(FakeModel(sign_vector("hello"))))
        self.assertGreater(self.count(self.panel(view), ls.RED), 500)
        self.assertEqual(self.count(view, ls.GREEN), 0)
        self.assertGreater(self.count(self.panel(view), ls.GREY), 0)  # bars without a winner

    def test_bars_grow_with_similarity(self):
        view = self.draw(recognition(FakeModel(unit_mix(doctor=0.8, time=0.5, morning=0.3))))
        bars = self.panel(view)[100:, 140:141 + ls.BAR_WIDTH]  # below the label, the bar columns
        rows = [np.all(bars == colour, axis=-1).sum(axis=1).max() for colour in (ls.GREEN, ls.GREY)]
        self.assertGreater(rows[0], rows[1])
        similarities = np.array([0.8, 0.5]) / np.linalg.norm([0.8, 0.5, 0.3])
        # +1: rectangles include both ends; the 2 px cut-off tick covers part of the top bar.
        self.assertAlmostEqual(rows[0], int(ls.BAR_WIDTH * similarities[0]) + 1, delta=4)
        self.assertEqual(rows[1], int(ls.BAR_WIDTH * similarities[1]) + 1)

    def test_before_the_first_sign_there_is_no_result_box(self):
        view = self.draw()
        self.assertEqual(int(self.panel(view).sum()), 0)
        self.assertGreater(int(view[:60, :220].sum()), 0)  # the detector pill

    def test_provisional_banner_spans_the_width_and_pushes_the_box_down(self):
        view = self.draw(provisional=True)
        self.assertEqual(self.count(view[60:62], ls.RED), 2 * self.WIDTH)
        with_box = self.draw(recognition(FakeModel(sign_vector("doctor"))), provisional=True)
        self.assertEqual(self.count(with_box[60:62], ls.RED), 2 * self.WIDTH)
        self.assertEqual(self.count(self.draw()[60:62], ls.RED), 0)


class BridgeBoundary(unittest.TestCase):
    def test_vocabularies_match(self):
        # The bridge accepts the backend's whole vocabulary (template signs + ASL glosses);
        # SignCLIP enrollment bundles cover the 12 template signs, which must all be in it.
        self.assertEqual(mb.SIGNS[:len(data.VOCABULARY)], data.VOCABULARY)
        self.assertTrue(set(data.VOCABULARY) <= set(mb.SIGNS))

    def test_results_cross_to_the_bridge_as_lines(self):
        results, _, _ = run([Script().sign(1.0).hold(0.8, UP_Y).hold(0.6).observations()],
                            FakeModel(sign_vector("evening")))
        lines = [ls.result_json(r) for r in results]
        self.assertEqual([mb.parse_result_line(line) for line in lines], ["evening", "evening"])
        self.assertEqual(json.loads(lines[0])["segment"], [1.8, 3.0])


class Playlist(unittest.TestCase):
    CLIPS = (("a", ((0.0, "a0"), (0.5, "a1"), (1.0, "a2"))), ("one", ((0.0, "o0"),)), ("b", ((0.0, "b0"), (0.5, "b1"))))

    def play(self, realtime, clock):
        sleeps = []

        def sleep(seconds):
            sleeps.append(round(seconds, 6))
            clock.now += seconds

        clips = dict(self.CLIPS)
        images = list(ls.playlist_images([Path(name) for name in clips], realtime,
                                         read=lambda path: iter(clips[path.name]), clock=clock, sleep=sleep))
        return images, sleeps

    def test_clips_continue_one_clock_one_frame_after_the_last(self):
        clock = Clock()
        clock.now = 100.0
        images, sleeps = self.play(False, clock)
        self.assertEqual([(t, image) for t, _, image in images],
                         [(0.0, "a0"), (0.5, "a1"), (1.0, "a2"), (1.5, "o0"),
                          (1.5 + ls.FALLBACK_FRAME_S, "b0"), (2.0 + ls.FALLBACK_FRAME_S, "b1")])
        self.assertEqual((sleeps, {wall for _, wall, _ in images}), ([], {100.0}))

    def test_realtime_waits_for_each_frame_on_the_wall_clock(self):
        clock = Clock()
        clock.now = 100.0
        images, sleeps = self.play(True, clock)
        self.assertEqual([round(wall - 100.0, 6) for _, wall, _ in images], [round(t, 6) for t, _, _ in images])
        self.assertEqual(len(sleeps), 5)  # every frame after the first waited its turn


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

    @staticmethod
    def fake_videos(clips):
        """read_video and track stand-ins: each "image" is a scripted detector frame."""
        by_image = {}

        def read(path):
            for frame in clips[path.name]:
                by_image[id(frame)] = frame
                yield frame.t, frame

        def tracker(images, keep_image):
            for index, (t, wall, frame) in enumerate(images):
                yield ls.Observation(wall, replace(by_image[id(frame)], t=t), index)

        return read, tracker

    def run_video(self, clips, *extra, stdin=""):
        """live_source.py --video over fake clips: (result lines, stderr)."""
        read, tracker = self.fake_videos(clips)
        results = io.StringIO()
        with TemporaryDirectory() as directory:
            paths = [Path(directory, name) for name in clips]
            for path in paths:
                path.write_bytes(b"")
            with patch.object(ls, "read_video", read), patch.object(ls, "track", tracker), \
                    patch.object(ls, "result_stream", lambda: results), patch("sys.stdin", io.StringIO(stdin)), \
                    redirect_stderr(io.StringIO()) as err:
                ls.main(["--video", *map(str, paths), "--no-preview", "--fast",
                         "--bundle", str(Path(directory, "no-bundle.json")), *extra])
        return [json.loads(line) for line in results.getvalue().splitlines()], err.getvalue()

    def test_handshake_puts_the_ready_line_first_and_waits_for_go(self):
        clips = {"rest.mp4": Script().hold(2.1).frames,
                 "doctor.mp4": Script().hold(0.3).hold(1.0, UP_Y).hold(0.6).frames}
        lines, _ = self.run_video(clips, "--handshake", stdin="go\n")
        self.assertEqual(lines[0], {"event": "ready", "rest_y": 0.82})
        self.assertEqual(mb.parse_ready_line(json.dumps(lines[0]))["rest_y"], 0.82)
        self.assertEqual([line["segment"] for line in lines[1:]], [[2.2, 3.4]])
        lines, err = self.run_video(clips, "--handshake", stdin="")  # the bridge placed no call
        self.assertEqual(lines, [{"event": "ready", "rest_y": 0.82}])
        self.assertIn("no call", err)
        lines, _ = self.run_video(clips)  # without it, nothing changes
        self.assertEqual([line["segment"] for line in lines], [[2.2, 3.4]])

    def test_video_clips_play_as_one_camera_with_one_calibration(self):
        # Public per-word clips have no 2 s rest of their own: --replay-videos calibrates
        # each clip on its first 2 s and finds no sign, --video calibrates once on the rest clip.
        clips = {"rest.mp4": Script().hold(2.1).frames,
                 "doctor.mp4": Script().hold(0.3).hold(1.0, UP_Y).hold(0.6).frames}
        read, tracker = self.fake_videos(clips)
        replays = ls.replay_clips([Path(name) for name in clips], realtime=False, keep_image=False,
                                  tracker=tracker)
        with patch.object(ls, "read_video", read), redirect_stderr(io.StringIO()):
            self.assertEqual(list(ls.LiveSource(replays, None, out=lambda line: None)), [])

        [result], err = self.run_video(clips)
        self.assertEqual(result["segment"], [2.2, 3.4])  # hands up 0.3 s into the second clip
        self.assertEqual(err.count("rest line y="), 1)

    def test_video_asks_for_a_new_rest_like_the_camera(self):
        clips = {"away.mp4": Script().hold(2.1, body=False).frames, "rest.mp4": Script().hold(2.1).frames,
                 "doctor.mp4": Script().hold(0.3).hold(1.0, UP_Y).hold(0.6).frames}
        [result], err = self.run_video(clips)
        self.assertEqual(result["segment"], [4.3, 5.5])
        self.assertIn("Calibration cant_see", err)

    def test_video_needs_existing_clips(self):
        with TemporaryDirectory() as directory:
            Path(directory, "notes.txt").write_text("not a clip")
            for argv in (["--video"], ["--video", f"{directory}/notes.txt"], ["--video", f"{directory}/missing.mp4"],
                         ["--camera", "0", "--video", f"{directory}/notes.txt"]):
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
