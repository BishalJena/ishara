"""asl_summary: the swept rule agrees with asl_matcher.asl_decision, and the tallies, gate and
threshold suggestions behave on hand-made attempts. No model or MediaPipe needed."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import asl_summary as s
from asl_matcher import asl_decision, load_asl_bundle

GOOD = {"pose_fraction": 1.0, "hand_fraction": 1.0}


def attempt(word: str, *top: tuple[str, float], quality=GOOD) -> s.Attempt:
    return s.Attempt(word, tuple(top), dict(quality))


class RuleMatchesTheMatcher(unittest.TestCase):
    def test_same_decision_as_asl_decision_on_random_vectors(self):
        bundle = load_asl_bundle()
        rule = s.Rule.from_bundle(json.loads(s.DEFAULT_BUNDLE.read_text()))
        rng = np.random.default_rng(7)
        vocab_index = [bundle.glosses.index(g) for g in sorted(bundle.vocabulary)]
        for i in range(400):
            z = rng.normal(0, 1, len(bundle.glosses))
            z[vocab_index[i % len(vocab_index)]] += rng.uniform(0, 7)
            p = np.exp(z - z.max())
            p /= p.sum()
            q = {"pose_fraction": float(rng.choice([1.0, 0.3])), "hand_fraction": float(rng.choice([1.0, 0.1]))}
            expected = asl_decision(p, q, bundle)
            order = np.argsort(-p)
            got = rule.decide(s.Attempt("x", tuple((bundle.glosses[j], float(p[j])) for j in order[:3]), q))
            want = (expected["status"], expected["sign"] or expected["candidate"])
            self.assertEqual(got, want, f"vector {i}")


class Tally(unittest.TestCase):
    rule = s.Rule(frozenset({"yes", "no", "tomorrow"}), p=0.6, margin=0.3, pick_one_p=0.35)

    def test_counts_chips_one_taps_unsure_and_wrong(self):
        rows = s.tally([
            attempt("yes", ("yes", 0.9), ("no", 0.05)),
            attempt("yes", ("yes", 0.5), ("no", 0.2)),
            attempt("yes", ("mitten", 0.95), ("yes", 0.01)),
            attempt("no", ("yes", 0.8), ("no", 0.1)),
            attempt("none", ("tomorrow", 0.7), ("no", 0.1)),
        ], self.rule)
        self.assertEqual((rows["yes"]["chip"], rows["yes"]["pick_one"], rows["yes"]["unsure"]), (1, 1, 1))
        self.assertEqual(rows["no"]["wrong_chip"], 1)
        verdict = s.gate(rows)
        self.assertTrue(verdict["words"]["yes"])
        self.assertFalse(verdict["words"]["no"])
        self.assertEqual((verdict["wrong_auto_accepts"], verdict["negative_auto_accepts"]), (1, 1))
        self.assertFalse(verdict["passes"])

    def test_poor_tracking_never_counts(self):
        rows = s.tally([attempt("yes", ("yes", 0.99), ("no", 0.0), quality={"pose_fraction": 0.2, "hand_fraction": 1})],
                       self.rule)
        self.assertEqual(rows["yes"]["unsure"], 1)


class Suggest(unittest.TestCase):
    rule = s.Rule(frozenset({"yes", "tomorrow"}), p=0.6, margin=0.3, pick_one_p=0.35)

    def test_raises_the_cut_off_above_a_confident_wrong_chip(self):
        attempts = [attempt("yes", ("yes", 0.9), ("no", 0.05)),
                    attempt("no", ("yes", 0.72), ("no", 0.1))]
        self.assertEqual(s.suggest(attempts, self.rule)["p"], 0.75)

    def test_per_word_cut_off_adds_right_chips_only(self):
        attempts = [attempt("tomorrow", ("tomorrow", 0.5), ("later", 0.1)),
                    attempt("tomorrow", ("tomorrow", 0.55), ("later", 0.1)),
                    attempt("yes", ("yes", 0.9), ("no", 0.05))]
        suggestion = s.suggest(attempts, self.rule)
        self.assertEqual(suggestion["p"], 0.6, "no mistakes is no reason to lower the global cut-off")
        self.assertEqual(suggestion["per_word"], {"tomorrow": 0.5}, "the highest that still takes both")
        attempts.append(attempt("no", ("yes", 0.5), ("no", 0.1)))
        suggestion = s.suggest(attempts, self.rule)
        self.assertEqual(suggestion["p"], 0.6)
        self.assertEqual(suggestion["per_word"], {"tomorrow": 0.5}, "yes may not go down to 0.5: that is wrong once")

    def test_written_bundle_is_frozen_and_loads(self):
        document = json.loads(s.DEFAULT_BUNDLE.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frozen.json"
            s.write_bundle(document, {"p": 0.55, "per_word": {"tomorrow": 0.45}}, True, "test", path)
            frozen = load_asl_bundle(path)
        self.assertFalse(frozen.provisional)
        self.assertEqual(frozen.thresholds["p"], 0.55)
        self.assertEqual(frozen.per_word, {"tomorrow": 0.45})


class CandidateBundle(unittest.TestCase):
    def test_candidate_keeps_the_provisional_flag(self):
        document = json.loads(s.DEFAULT_BUNDLE.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "candidate.json"
            s.write_bundle(document, {"p": 0.65, "per_word": {"tomorrow": 0.5}}, True, "test", path, provisional=True)
            candidate = load_asl_bundle(path)
            text = json.loads(path.read_text())["calibration"]
        self.assertTrue(candidate.provisional, "a candidate from public clips must not unlock the shipped banner")
        self.assertEqual(candidate.thresholds["p"], 0.65)
        self.assertEqual(candidate.per_word, {"tomorrow": 0.5})
        self.assertTrue(text.startswith("candidate"), text)


class Combine(unittest.TestCase):
    """Several runs of the same clips (Mac / app path, landscape / portrait) judged together."""
    rule = s.Rule(frozenset({"yes", "tomorrow"}), p=0.6, margin=0.3, pick_one_p=0.35)

    def test_attempts_survive_the_json_round_trip(self):
        attempts = [s.Attempt("yes", (("yes", 0.9), ("no", 0.05)), dict(GOOD), "yes_1.mp4"),
                    s.Attempt("none", (("tomorrow", 0.4), ("later", 0.2)), {"pose_fraction": 0.5, "hand_fraction": 0.1},
                              "none_1.mp4", 0.4)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run.json"
            path.write_text(json.dumps({"source": "Mac path", "attempts": s.attempts_json(attempts)}))
            name, loaded = s.from_json(path)
        self.assertEqual(name, "Mac path")
        self.assertEqual(loaded, attempts)

    def test_suggestion_is_fitted_on_every_run_at_once(self):
        mac = [attempt("yes", ("yes", 0.9), ("no", 0.05)), attempt("tomorrow", ("tomorrow", 0.5), ("later", 0.1))]
        app = [attempt("yes", ("yes", 0.9), ("no", 0.05)), attempt("none", ("tomorrow", 0.5), ("later", 0.1))]
        self.assertEqual(s.suggest(mac, self.rule)["per_word"], {"tomorrow": 0.5}, "the Mac run alone allows it")
        report = s.combine({"Mac": mac, "app": app}, self.rule)
        self.assertEqual(report["suggestion"]["per_word"], {}, "the app run has a negative at 0.5: no per-word cut-off")
        self.assertEqual(report["suggestion"]["p"], 0.6)

    def test_a_wrong_chip_in_any_run_fails_the_combined_gate(self):
        clean = [attempt("yes", ("yes", 0.9), ("no", 0.05))]
        dirty = [attempt("yes", ("yes", 0.9), ("no", 0.05)), attempt("none", ("yes", 0.8), ("no", 0.1))]
        report = s.combine({"Mac": clean, "app": dirty}, self.rule)
        self.assertTrue(report["runs"]["Mac"]["gate"]["passes"])
        self.assertFalse(report["runs"]["app"]["gate"]["passes"])
        self.assertFalse(report["passes"])
        self.assertTrue(s.combine({"Mac": clean, "app": clean}, self.rule)["passes"])

    def test_totals_give_accept_and_false_chip_counts_per_run(self):
        run = [attempt("yes", ("yes", 0.9), ("no", 0.05)), attempt("yes", ("yes", 0.5), ("no", 0.1)),
               attempt("no", ("yes", 0.8), ("no", 0.1)), attempt("tomorrow", ("later", 0.9), ("no", 0.05)),
               attempt("none", ("tomorrow", 0.7), ("later", 0.1)), attempt("none", ("tomorrow", 0.4), ("later", 0.1)),
               attempt("none", ("mitten", 0.9), ("later", 0.01))]
        report = s.combine({"Mac": run}, self.rule)
        self.assertEqual(report["runs"]["Mac"]["totals"],
                         {"signs": 4, "chip": 1, "pick_one": 1, "wrong_chip": 1, "wrong_pick": 0,
                          "negatives": 3, "negative_chip": 1, "negative_pick": 1})
        row = next(line for line in s.combined_markdown(report).splitlines() if line.startswith("| all signs "))
        self.assertEqual(row, "| all signs | 4 | 1 chips (25%) + 1 one-tap, 1 wrong chips (25%) |")

    def test_combined_table_has_one_column_per_run(self):
        runs = {"Mac": [attempt("yes", ("yes", 0.9), ("no", 0.05)), attempt("yes", ("mitten", 0.9), ("yes", 0.01))],
                "app": [attempt("yes", ("yes", 0.5), ("no", 0.1)), attempt("yes", ("yes", 0.7), ("no", 0.1))]}
        table = s.combined_markdown(s.combine(runs, self.rule))
        row = next(line for line in table.splitlines() if line.startswith("| yes "))
        self.assertEqual(row, "| yes | 2 | 1+0/2 fail | 1+1/2 pass |")


class VocabularyWhatIf(unittest.TestCase):
    """--vocabulary: the same runs judged as if the bundle chipped only these glosses."""

    def run_main(self, tmp: Path, *extra: str) -> dict:
        yes_as_can = [s.Attempt("yes", (("can", 0.7), ("yes", 0.2)), dict(GOOD), "yes_1.mp4"),
                      s.Attempt("yes", (("yes", 0.9), ("no", 0.05)), dict(GOOD), "yes_2.mp4")]
        run = tmp / "run.json"
        run.write_text(json.dumps({"source": "Mac", "attempts": s.attempts_json(yes_as_can)}))
        out = tmp / "combined.json"
        with contextlib.redirect_stdout(io.StringIO()):
            s.main(["--combine", str(run), "--json", str(out), *extra])
        return json.loads(out.read_text())

    def test_a_gloss_left_out_of_the_vocabulary_can_no_longer_chip(self):
        with tempfile.TemporaryDirectory() as tmp:
            wide = self.run_main(Path(tmp), "--vocabulary", "yes,no,thankyou,can")
            narrowed = self.run_main(Path(tmp), "--vocabulary", "yes,no,thankyou")
        self.assertEqual(wide["runs"]["Mac"]["rows"]["yes"]["wrong_chip"], 1, "can is in the wide vocabulary")
        self.assertEqual(narrowed["runs"]["Mac"]["rows"]["yes"]["wrong_chip"], 0)
        self.assertEqual(narrowed["runs"]["Mac"]["rows"]["yes"]["chip"], 1)

    def test_the_candidate_bundle_carries_the_narrowed_vocabulary(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "candidate.json"
            self.run_main(Path(tmp), "--vocabulary", "yes,no", "--write-bundle", str(bundle), "--provisional")
            self.assertEqual(load_asl_bundle(bundle).vocabulary, frozenset({"yes", "no"}))

    def test_a_gloss_the_model_lacks_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(SystemExit) as refused:
            self.run_main(Path(tmp), "--vocabulary", "yes,doctor")
        self.assertIn("doctor", str(refused.exception))


class MacLandmarks(unittest.TestCase):
    """Regression: legacy Holistic in video mode carries its tracking from one clip into the next,
    so one tracker shared over a folder made each clip's score depend on the clip sorted before it
    (tomorrow 0.80 alone, 0.37 after its neighbour). Every clip must get a tracker of its own."""

    def test_every_clip_gets_a_fresh_tracker(self):
        opened: list[object] = []
        seen: dict[str, object] = {}

        @contextlib.contextmanager
        def holistic():
            tracker = object()
            opened.append(tracker)
            yield tracker

        def extract(clip, tracker):
            seen[Path(clip).name] = tracker
            return {"landmarks": np.zeros((2, 543, 3))}

        clips = [Path(name) for name in ("hello_1.mp4", "hello_2.mp4", "none_1.mp4")]
        with mock.patch.dict(sys.modules, {"extract": types.SimpleNamespace(extract=extract)}), \
                mock.patch("detect_clips.holistic", holistic):
            out = list(s.mac_landmarks(clips))
        self.assertEqual([c for c, _ in out], clips)
        self.assertEqual(len(opened), 3)
        self.assertEqual(len({id(t) for t in seen.values()}), 3, "no two clips may share a tracker")
        self.assertEqual(out[0][1].dtype, np.float32)


class Labels(unittest.TestCase):
    def test_label_is_the_file_name_before_the_attempt_number(self):
        self.assertEqual(s.label_of(Path("tomorrow_03.mov")), "tomorrow")
        self.assertEqual(s.label_of(Path("ThankYou-2.MP4")), "thankyou")
        self.assertEqual(s.label_of(Path("none_1.mov")), "none")


if __name__ == "__main__":
    unittest.main()
