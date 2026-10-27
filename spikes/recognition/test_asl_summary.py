"""asl_summary: the swept rule agrees with asl_matcher.asl_decision, and the tallies, gate and
threshold suggestions behave on hand-made attempts. No model or MediaPipe needed."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

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

    def test_combined_table_has_one_column_per_run(self):
        runs = {"Mac": [attempt("yes", ("yes", 0.9), ("no", 0.05)), attempt("yes", ("mitten", 0.9), ("yes", 0.01))],
                "app": [attempt("yes", ("yes", 0.5), ("no", 0.1)), attempt("yes", ("yes", 0.7), ("no", 0.1))]}
        table = s.combined_markdown(s.combine(runs, self.rule))
        row = next(line for line in table.splitlines() if line.startswith("| yes "))
        self.assertEqual(row, "| yes | 2 | 1+0/2 fail | 1+1/2 pass |")


class Labels(unittest.TestCase):
    def test_label_is_the_file_name_before_the_attempt_number(self):
        self.assertEqual(s.label_of(Path("tomorrow_03.mov")), "tomorrow")
        self.assertEqual(s.label_of(Path("ThankYou-2.MP4")), "thankyou")
        self.assertEqual(s.label_of(Path("none_1.mov")), "none")


if __name__ == "__main__":
    unittest.main()
