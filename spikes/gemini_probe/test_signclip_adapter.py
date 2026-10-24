"""SignCLIP adapter on synthetic embeddings: no video, MediaPipe or checkpoint needed."""
import unittest
from typing import ClassVar

import numpy as np
import recognition_data as data

import signclip_adapter as sa

QUALITY = {"pose_fraction": 1.0, "hand_fraction": 1.0, "frames": 60, "landmark_ms": 500.0}


def vec(*values):
    out = np.zeros(8, dtype=np.float32)
    out[: len(values)] = values
    return data.unit(out)


def ref(ident, label, embedding, source=None, dataset="islrtc"):
    return {"id": ident, "label": label, "embedding": embedding, "sha256": ident * 4, "dataset": dataset,
            "source_id": source or f"src_{ident}", "quality": QUALITY}


REFERENCES = [ref("r1", "dog", vec(1, 0.05)), ref("r2", "dog", vec(1, -0.05), dataset="bridgeconn"),
              ref("r3", "cat", vec(0, 1, 0.05)), ref("r4", "cat", vec(0.05, 1), dataset="bridgeconn"),
              ref("r5", "horse", vec(0, 0, 1))]
WORDS = ["cat", "dog", "horse"]


class Vocabulary(unittest.TestCase):
    def test_words_are_swapped_in_and_restored(self):
        original = data.VOCABULARY
        with sa.vocabulary(WORDS):
            self.assertEqual(data.VOCABULARY, tuple(WORDS))
            data.rank({"id": "q", "sha256": "q", "source_id": "q", "embedding": vec(1)}, REFERENCES)
        self.assertEqual(data.VOCABULARY, original)
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            data.rank({"id": "q", "sha256": "q", "source_id": "q", "embedding": vec(1)}, REFERENCES)

    def test_restored_even_after_an_error(self):
        original = data.VOCABULARY
        with self.assertRaises(RuntimeError), sa.vocabulary(WORDS):
            raise RuntimeError
        self.assertEqual(data.VOCABULARY, original)


class Policy(unittest.TestCase):
    def test_only_words_with_two_sources_are_leave_one_out_queries(self):
        self.assertEqual([r["id"] for r in sa.loo_queries(REFERENCES)], ["r1", "r2", "r3", "r4"])
        same_source = [ref("a", "dog", vec(1), source="s"), ref("b", "dog", vec(1), source="s")]
        self.assertEqual(sa.loo_queries(same_source), [])

    def test_frozen_cutoff_accepts_reference_matches_without_wrong_accepts(self):
        thresholds, counts = sa.freeze_policy(REFERENCES, WORDS)
        self.assertEqual(counts["wrong_accepted"], 0)
        self.assertEqual(counts["correct_accepted"], 4)
        self.assertFalse(counts["fallback"])
        self.assertLessEqual(thresholds["similarity"], 1.0)


class Recognize(unittest.TestCase):
    policy: ClassVar[dict] = {"similarity": 0.9, "margin": 0.05}

    def test_close_match_is_accepted_far_match_is_top1_only(self):
        close = {"id": "t1", "sha256": "t1", "embedding": vec(1, 0.02), "quality": QUALITY,
                 "model_ms": 30.0, "total_ms": 600.0}
        result = sa.recognize(close, REFERENCES, self.policy, WORDS)
        self.assertEqual((result["top1"], result["accepted"], result["decision"]), ("dog", "dog", "candidate"))
        self.assertEqual([t["word"] for t in result["top"]], ["dog", "cat", "horse"])
        far = {**close, "id": "t2", "sha256": "t2", "embedding": vec(1, 1, 0.9)}
        result = sa.recognize(far, REFERENCES, self.policy, WORDS)
        self.assertIsNone(result["accepted"])
        self.assertEqual(result["decision"], "abstain")
        self.assertIn(result["top1"], ("dog", "cat"))

    def test_poor_tracking_abstains_and_failed_embeddings_are_errors(self):
        poor = {"id": "t", "sha256": "t", "embedding": vec(1), "quality": {**QUALITY, "hand_fraction": 0.0}}
        self.assertIsNone(sa.recognize(poor, REFERENCES, self.policy, WORDS)["accepted"])
        failed = {"id": "t", "sha256": "t", "error": "No tracked shoulders"}
        self.assertEqual(sa.recognize(failed, REFERENCES, self.policy, WORDS)["status"], "error")


class Separation(unittest.TestCase):
    def test_a_test_clip_equal_to_a_reference_is_refused(self):
        tests = [{"id": "t1", "sha256": "x"}]
        sa.check_separation(REFERENCES, tests)
        for clash in ({"id": "r1", "sha256": "x"}, {"id": "t1", "sha256": REFERENCES[0]["sha256"]}):
            with self.subTest(clash), self.assertRaisesRegex(ValueError, "Leakage"):
                sa.check_separation(REFERENCES, [clash])

    def test_references_from_a_test_dataset_are_refused(self):
        with self.assertRaisesRegex(ValueError, "dictionaries only"):
            sa.check_separation([*REFERENCES, ref("r9", "dog", vec(1), dataset="include")], [])


if __name__ == "__main__":
    unittest.main()
