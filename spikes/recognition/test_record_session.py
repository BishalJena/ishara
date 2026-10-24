"""Guided Sign Lab recording with a scripted fake signer: no webcam, no MediaPipe."""
import hashlib
import json
import unittest
from contextlib import contextmanager
from io import StringIO
from itertools import count
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

import recognition_data as data
import record_session as rs
from detector import Frame

FPS = 30
REST_Y, UP_Y = 0.9, 0.4  # calibrated rest line = 0.9 - 0.08
_frame_numbers = count(1)  # every fake frame differs, so no two takes are the same video


class Signer:
    """Fake camera, tracker and screen in one: follows the prompts like a person would.

    plans: one entry per countdown: "sign" (sign once for 1 s), "quick" (signs right at
    GO, so the pre-roll reaches back into the countdown), "long" (never drops the
    hands), "still" (never signs), "fidget" (hands up during the countdown), "hidden"
    (shoulders out of view during the countdown), "discard" (presses X while recording),
    "manual" (signs, then presses SPACE). "quit" as the next plan presses Q at ready.
    """

    def __init__(self, plans, reviews=()):
        self.plans, self.reviews = list(plans), list(reviews)
        self.t, self.count, self.phase, self.plan, self.since = 100.0, 0, "ready", None, None
        self.log = []  # (t, active) for every tracked frame
        self.screens = []  # (phase, lines, big, frame time)

    def read(self):
        self.t += 1 / FPS
        self.count += 1
        number = next(_frame_numbers)
        image = np.zeros((24, 32, 3), np.uint8)
        image[:, :16] = number % 256
        image[:, 16:] = number // 256 % 256
        return True, image

    def clock(self):
        return self.t

    def _elapsed(self):
        return self.t - self.since if self.phase == "recording" else None

    def track(self, t, image):
        body, active, elapsed = True, False, self._elapsed()
        if self.phase == "countdown":
            body, active = self.plan != "hidden", self.plan == "fidget"
        elif elapsed is not None:
            active = (self.plan in ("sign", "manual") and 0.3 <= elapsed < 1.3
                      or self.plan == "quick" and 0 < elapsed < 1.0
                      or self.plan == "long" and elapsed >= 0.3)
        self.log.append((t, active))
        return Frame(t, body, ((0.5, UP_Y if active else REST_Y),)), None

    def show(self, tracked, phase, lines, big=None, delay_ms=1):
        if phase == "countdown" and self.phase != "countdown":
            self.plan = self.plans.pop(0)
        if phase == "recording" and self.phase != "recording":
            self.since = tracked.t
        self.phase = phase
        self.screens.append((phase, list(lines), big, tracked.t))
        if phase == "ready":
            return rs.QUIT if self.plans and self.plans[0] == "quit" else rs.SPACE
        if phase == "recording":
            if self.plan == "discard":
                return rs.DISCARD
            if self.plan == "manual" and self._elapsed() > 2.0:
                return rs.SPACE
        if phase == "review":
            return self.reviews.pop(0)
        return -1

    def messages(self, phase="ready"):
        return [lines[-1] for shown, lines, _, _ in self.screens if shown == phase]

    def times(self, phase):
        return [t for shown, _, _, t in self.screens if shown == phase]


def recorder(signer, auto_stop=True):
    return rs.Recorder(signer, signer.track, signer, auto_stop=auto_stop, clock=signer.clock)


@contextmanager
def pilot_root():
    """Clips and manifest in a temporary artifacts root, never the real artifacts/pilot."""
    validate = data.validate_records
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        with patch.object(data, "ARTIFACTS", root), patch.object(
                data, "validate_records",
                side_effect=lambda rows, verify_files=True: validate(rows, root, verify_files)):
            yield root, root / "pilot" / "dataset.json"


def session(signer, manifest, takes=3, session_id="signlab-test", **kwargs):
    out = StringIO()
    counts = rs.run_session(recorder(signer, **kwargs), manifest=manifest, signer="demo",
                            session=session_id, takes=takes, out=lambda line: print(line, file=out))
    return counts, out.getvalue()


class RecorderContracts(unittest.TestCase):
    def test_detector_mode_keeps_exactly_the_detector_cut(self):
        signer = Signer(["sign"])
        take = rs.Recorder(signer, signer.track, signer, clock=signer.clock).record(["hello"])
        times = [f.t for f in take.frames]
        first_up = next(t for t, active in signer.log if active)
        first_rest = next(t for t, active in signer.log if t > first_up and not active)
        # pre-roll 0.2 s before the hands rose, through the first frame back at rest
        expected = [t for t, _ in signer.log if first_up - 0.2 - 1e-9 <= t <= first_rest + 1e-9]
        self.assertEqual(take.cut, "detector")
        self.assertEqual(times, expected)
        self.assertEqual(len(times), 37)
        # it stopped by itself 0.4 s after the hands came down, without any key
        self.assertAlmostEqual(signer.log[-1][0] - first_rest, 0.4, delta=1.5 / FPS)
        self.assertEqual(list(dict.fromkeys(big for phase, _, big, _ in signer.screens if phase == "countdown")),
                         ["3", "2", "1"])

    def test_pre_roll_reaches_back_into_the_countdown_when_signing_at_go(self):
        signer = Signer(["quick"])
        take = recorder(signer).record(["hello"])
        first_up = next(t for t, active in signer.log if active)
        go = signer.times("countdown")[-1]
        times = [f.t for f in take.frames]
        self.assertAlmostEqual(times[0], first_up - 0.2, delta=0.5 / FPS)
        self.assertLess(times[0], go)
        self.assertEqual(times, [t for t, _ in signer.log if times[0] <= t <= times[-1]])

    def test_unusable_attempts_return_to_ready_with_the_reason(self):
        signer = Signer(["hidden", "fidget", "long", "still", "discard", "sign"])
        take = recorder(signer).record(["hello"])
        self.assertEqual(take.cut, "detector")
        messages = signer.messages()
        reasons = ["Couldn't measure the rest (cant_see)", "hands moved during the countdown",
                   "Take not usable (too long)", "No sign seen", "Discarded"]
        shown = list(dict.fromkeys(messages[1:]))  # each reason once, in order
        self.assertEqual(len(shown), len(reasons))
        for message, reason in zip(shown, reasons):
            with self.subTest(reason=reason):
                self.assertIn(reason, message)
        self.assertEqual(signer.plans, [])

    def test_no_sign_gives_up_after_the_wait(self):
        signer = Signer(["still", "sign"])
        recorder(signer).record(["hello"])
        retry = next(t for phase, lines, _, t in signer.screens
                     if phase == "ready" and "No sign seen" in lines[-1])
        waited = [t for t in signer.times("recording") if t < retry]
        self.assertAlmostEqual(waited[-1] - waited[0], rs.NO_SIGN_S, delta=2 / FPS)

    def test_manual_stop_keeps_the_whole_take_until_space(self):
        signer = Signer(["manual"])
        take = recorder(signer, auto_stop=False).record(["hello"])
        self.assertEqual(take.cut, "manual")
        self.assertEqual([f.t for f in take.frames], signer.times("recording"))
        self.assertGreater(take.frames[-1].t - take.frames[0].t, 2.0)

    def test_review_keeps_or_redoes_and_flags_weak_tracking(self):
        frames = [rs.Tracked(i / FPS, None, Frame(i / FPS, i % 2 == 0, ((0.5, 0.5),) if i < 2 else ()))
                  for i in range(10)]
        take = rs.Take(frames, "detector")
        self.assertEqual(take.quality, {"pose_fraction": 0.5, "hand_fraction": 0.2})
        for key, kept in ((rs.KEEP, True), (rs.REDO, False)):
            signer = Signer([], [key])
            with self.subTest(key=chr(key)):
                self.assertIs(recorder(signer).review(take, ["hello"]), kept)
                self.assertIn("WEAK TRACKING", signer.screens[0][1][-2])
        strong = rs.Take([rs.Tracked(f.t, None, Frame(f.t, True, ((0.5, 0.5),))) for f in frames], "detector")
        signer = Signer([], [rs.KEEP])
        recorder(signer).review(strong, ["hello"])
        self.assertNotIn("WEAK", signer.screens[0][1][-2])

    def test_quit_key_stops_from_any_phase(self):
        for key in (rs.QUIT, rs.ESCAPE):
            signer = Signer([])
            signer.show = lambda *args, key=key, **kwargs: key
            with self.subTest(key=key), self.assertRaises(rs.Quit):
                recorder(signer).record(["hello"])


class SessionContracts(unittest.TestCase):
    def test_full_session_saves_verified_takes_for_every_sign_in_plan_order(self):
        signer = Signer(["sign"] * 36, [rs.KEEP] * 36)
        with pilot_root() as (root, manifest):
            counts, out = session(signer, manifest)
            rows = data.load_dataset(manifest)
            clips = sorted(p.name for p in (root / "pilot" / "clips").iterdir())
        self.assertEqual(counts, dict.fromkeys(data.VOCABULARY, 3))
        self.assertEqual([r["label"] for r in rows], [s for s in data.VOCABULARY for _ in range(3)])
        self.assertEqual(clips, sorted(f"{r['id']}.mp4" for r in rows))
        for row in rows:
            with self.subTest(id=row["id"]):
                self.assertEqual((row["signer_id"], row["session_id"], row["split"]),
                                 ("demo", "signlab-test", "enrollment"))
                self.assertTrue(row["verified"])
                self.assertIn("guided Sign Lab session against " + rs.GUIDES[row["label"]].reference,
                              row["verification_note"])
                self.assertIn("detector cut", row["provenance"])
                self.assertEqual(row["capture"]["frames"], 37)
        for sign in ("yes", "no", "sorry"):
            self.assertIn("ISLRTC", next(r for r in rows if r["label"] == sign)["verification_note"])
        self.assertIn("INCLUDE", rows[0]["verification_note"])
        self.assertIn("export-bundle --encoder signclip --provisional", out)
        self.assertIn("sign_lab.sh", out)
        self.assertEqual(signer.reviews, [])

    def test_terminal_names_each_sign_its_reference_and_any_local_public_copy(self):
        signer = Signer(["sign"] * 12, [rs.KEEP] * 12)
        with pilot_root() as (root, manifest):
            copy = root / "clips" / "doctor" / "MVI_4471.MOV"
            copy.parent.mkdir(parents=True)
            copy.write_bytes(b"public clip")
            _, out = session(signer, manifest, takes=1)
        self.assertIn(f"Local copy: {copy}", out)
        self.assertEqual(out.count("Local copy:"), 1)
        for number, sign in enumerate(data.VOCABULARY, 1):
            with self.subTest(sign=sign):
                self.assertIn(f"[{number}/12] {sign.upper()}: {rs.GUIDES[sign].hint}\n"
                              f"  Reference: {rs.GUIDES[sign].reference}", out)
        self.assertIn(rs.FRAMING[0], out)

    def test_redo_saves_nothing_and_records_the_sign_again(self):
        signer = Signer(["sign"] * 13, [rs.REDO] + [rs.KEEP] * 12)
        with pilot_root() as (_, manifest):
            counts, out = session(signer, manifest, takes=1)
            rows = data.load_dataset(manifest)
        self.assertEqual(len(rows), 12)
        self.assertEqual(counts["hello"], 1)
        self.assertEqual([r["label"] for r in rows], list(data.VOCABULARY))
        self.assertEqual(out.count(": redo"), 1)
        self.assertIn("hello: redo", out)
        self.assertEqual((signer.plans, signer.reviews), ([], []))

    def test_resume_skips_signs_that_already_have_enough_kept_takes(self):
        with pilot_root() as (_, manifest):
            first = Signer(["sign"] * 4 + ["quit"], [rs.KEEP] * 4)
            counts, out = session(first, manifest, takes=2)
            self.assertEqual((counts["hello"], counts["thankyou"], counts["yes"]), (2, 2, 0))
            self.assertIn("resume with --session signlab-test", out)
            self.assertEqual(len(data.load_dataset(manifest)), 4)
            second = Signer(["sign"] * 20, [rs.KEEP] * 20)
            counts, out = session(second, manifest, takes=2)
            rows = data.load_dataset(manifest)
        self.assertEqual(counts, dict.fromkeys(data.VOCABULARY, 2))
        self.assertIn("hello: 2 kept already, skipping", out)
        self.assertIn("thankyou: 2 kept already, skipping", out)
        self.assertNotIn("yes: 2 kept already", out)
        self.assertEqual(second.plans, [])
        self.assertEqual(len(rows), 24)

    def test_only_verified_takes_of_this_signer_and_session_count_as_kept(self):
        base = {"signer_id": "demo", "session_id": "s1", "split": "enrollment", "label": "hello",
                "verified": True}
        rows = [base, {**base, "verified": False}, {**base, "session_id": "s2"},
                {**base, "signer_id": "other"}, {**base, "label": "no"}]
        counts = rs.kept_counts(rows, "demo", "s1")
        self.assertEqual((counts["hello"], counts["no"], counts["yes"]), (1, 1, 0))

    def test_session_id_from_another_split_is_refused_before_the_camera_is_read(self):
        signer = Signer(["sign"], [rs.KEEP])
        with pilot_root() as (root, manifest):
            clip = root / "pilot" / "old.mp4"
            clip.parent.mkdir(parents=True)
            clip.write_bytes(b"calibration clip")
            row = {"id": "old", "signer_id": "demo", "session_id": "signlab-test", "source_id": "old",
                   "split": "calibration", "label": "hello", "negative_kind": None, "verified": True,
                   "verification_note": "fixture", "provenance": "fixture", "path": "pilot/old.mp4",
                   "sha256": hashlib.sha256(b"calibration clip").hexdigest()}
            manifest.write_text(json.dumps({"version": 1, "records": [row]}))
            with self.assertRaisesRegex(ValueError, "Leakage"):
                session(signer, manifest)
        self.assertEqual(signer.count, 0)


class GuideAndCommandLine(unittest.TestCase):
    def test_every_sign_has_a_hint_and_its_plan_reference(self):
        self.assertEqual(tuple(rs.GUIDES), data.VOCABULARY)
        for sign, guide in rs.GUIDES.items():
            with self.subTest(sign=sign):
                source = "ISLRTC" if sign in ("yes", "no", "sorry") else "INCLUDE"
                self.assertEqual(guide.source, source)
                self.assertTrue(guide.reference.startswith(source + " "))
                self.assertIn(guide.entry, guide.short_reference)
                self.assertTrue(guide.hint)
        for sign in ("yes", "no"):
            self.assertIn("head movement", rs.GUIDES[sign].hint)

    def test_defaults_are_three_takes_and_one_dated_session(self):
        args = rs.build_parser().parse_args([])
        self.assertEqual((args.takes, args.signer, args.manual_stop), (3, "demo", False))
        self.assertRegex(args.session, r"^signlab-\d{8}$")

    def test_out_of_range_takes_are_refused_before_the_camera_opens(self):
        for takes in ("0", "11"):
            with self.subTest(takes=takes), patch("sys.stderr", StringIO()), \
                    patch("detect_clips.open_camera") as camera, self.assertRaises(SystemExit):
                rs.main(["--takes", takes])
            camera.assert_not_called()


if __name__ == "__main__":
    unittest.main()
