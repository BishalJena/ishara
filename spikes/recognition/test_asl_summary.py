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


class Labels(unittest.TestCase):
    def test_label_is_the_file_name_before_the_attempt_number(self):
        self.assertEqual(s.label_of(Path("tomorrow_03.mov")), "tomorrow")
        self.assertEqual(s.label_of(Path("ThankYou-2.MP4")), "thankyou")
        self.assertEqual(s.label_of(Path("none_1.mov")), "none")


if __name__ == "__main__":
    unittest.main()
