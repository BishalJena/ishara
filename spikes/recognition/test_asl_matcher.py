"""The open-set decision rule and the version-2 ASL bundle (no model, no MediaPipe needed)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import asl_matcher as am  # noqa: E402
from vocabulary import ASL_SIGNS, REHEARSED, SIGNS, TEMPLATE_SIGNS  # noqa: E402

BUNDLE = am.load_asl_bundle()
GOOD = {"pose_fraction": 1.0, "hand_fraction": 0.9}


def probs(**mass: float) -> np.ndarray:
    """A probability vector with the given glosses' mass; the rest spread evenly."""
    p = np.zeros(len(BUNDLE.glosses))
    for gloss, value in mass.items():
        p[BUNDLE.glosses.index(gloss)] = value
    rest = 1.0 - p.sum()
    assert rest >= -1e-9, mass
    zeros = p == 0
    p[zeros] = rest / zeros.sum()
    return p


class BundleTests(unittest.TestCase):
    def test_fixture_is_consistent(self) -> None:
        self.assertEqual(len(BUNDLE.glosses), 250)
        self.assertTrue(BUNDLE.provisional)
        self.assertTrue(BUNDLE.vocabulary <= set(BUNDLE.glosses))
        self.assertTrue(BUNDLE.vocabulary <= set(SIGNS), BUNDLE.vocabulary - set(SIGNS))
        for word in REHEARSED:
            self.assertIn(word, BUNDLE.vocabulary)
        self.assertLessEqual(BUNDLE.thresholds["pick_one_p"], BUNDLE.thresholds["p"])

    def test_vocabulary_module_matches_backend(self) -> None:
        backend = Path(__file__).resolve().parents[2] / "backend" / "app" / "protocol.py"
        source = backend.read_text()
        for sign in SIGNS:
            self.assertIn(f'"{sign}"', source, f"{sign} missing from backend protocol")
        self.assertEqual(len(set(TEMPLATE_SIGNS) & set(ASL_SIGNS)), 0)

    def test_rejects_vocabulary_outside_the_model(self) -> None:
        document = json.loads(am.DEFAULT_ASL_BUNDLE.read_text())
        document["vocabulary"].append("doctor")  # not one of the 250
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(document, handle)
        with self.assertRaises(ValueError):
            am.load_asl_bundle(Path(handle.name))

    def test_rejects_other_bundle_kinds(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"version": 1, "encoder": "signclip"}, handle)
        with self.assertRaises(ValueError):
            am.load_asl_bundle(Path(handle.name))


class DecisionTests(unittest.TestCase):
    def test_confident_vocabulary_word_is_a_chip(self) -> None:
        verdict = am.asl_decision(probs(tomorrow=0.72, yourself=0.1), GOOD, BUNDLE)
        self.assertEqual((verdict["status"], verdict["sign"]), ("chip", "tomorrow"))
        self.assertAlmostEqual(verdict["p"], 0.72)
        self.assertEqual(verdict["top"][0][0], "tomorrow")

    def test_grey_zone_is_pick_one_not_a_chip(self) -> None:
        verdict = am.asl_decision(probs(tomorrow=0.45, yourself=0.3), GOOD, BUNDLE)
        self.assertEqual(verdict["status"], "pick_one")
        self.assertIsNone(verdict["sign"])
        self.assertEqual(verdict["candidate"], "tomorrow")

    def test_confident_but_small_margin_is_pick_one(self) -> None:
        verdict = am.asl_decision(probs(no=0.5, yes=0.45), GOOD, BUNDLE)
        self.assertEqual(verdict["status"], "pick_one")

    def test_confident_non_vocabulary_word_is_unsure_never_a_chip(self) -> None:
        # The ISLRTC "no" read as ASL "bye" at 0.88; the 240 other classes are the reject bucket.
        verdict = am.asl_decision(probs(bye=0.88), GOOD, BUNDLE)
        self.assertEqual(verdict["status"], "abstain")
        self.assertIsNone(verdict["candidate"])
        self.assertIn("not in vocabulary", verdict["reason"])

    def test_restricting_to_the_vocabulary_first_would_have_been_wrong(self) -> None:
        # ISL "evening" clips: flat output, the best vocabulary word at p 0.01. Must be "?".
        p = probs(vacuum=0.12, pool=0.1, no=0.01)
        verdict = am.asl_decision(p, GOOD, BUNDLE)
        self.assertEqual(verdict["status"], "abstain")
        self.assertIsNone(verdict["sign"])

    def test_flat_output_is_unsure(self) -> None:
        verdict = am.asl_decision(np.full(250, 1 / 250), GOOD, BUNDLE)
        self.assertEqual(verdict["status"], "abstain")

    def test_poor_tracking_abstains_even_when_confident(self) -> None:
        verdict = am.asl_decision(probs(hello=0.95), {"pose_fraction": 0.3, "hand_fraction": 0.9}, BUNDLE)
        self.assertEqual(verdict["status"], "abstain")
        self.assertIn("pose", verdict["reason"])
        verdict = am.asl_decision(probs(hello=0.95), {"pose_fraction": 1.0, "hand_fraction": 0.1}, BUNDLE)
        self.assertIn("hands", verdict["reason"])

    def test_per_word_cutoff_overrides_the_global_one(self) -> None:
        tuned = am.AslBundle(BUNDLE.glosses, BUNDLE.vocabulary, BUNDLE.thresholds, {"tomorrow": 0.45},
                             BUNDLE.quality, True, BUNDLE.model_sha256)
        self.assertEqual(am.asl_decision(probs(tomorrow=0.5, another=0.1), GOOD, tuned)["status"], "chip")
        self.assertEqual(am.asl_decision(probs(morning=0.5, another=0.1), GOOD, tuned)["status"], "pick_one")

    def test_invalid_vectors_abstain(self) -> None:
        self.assertEqual(am.asl_decision(np.zeros(10), GOOD, BUNDLE)["status"], "abstain")
        bad = probs(hello=0.9)
        bad[0] = np.nan
        self.assertEqual(am.asl_decision(bad, GOOD, BUNDLE)["reason"], "invalid evidence")

    def test_softmax(self) -> None:
        p = am.softmax(np.array([2.0, 0.0, -1.0]))
        self.assertAlmostEqual(float(p.sum()), 1.0)
        self.assertEqual(int(p.argmax()), 0)


if __name__ == "__main__":
    unittest.main()
