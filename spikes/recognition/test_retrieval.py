"""Data leakage and abstention contracts; no model downloads or inference."""
import unittest
from contextlib import redirect_stderr
from io import StringIO
from itertools import count
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import recognition_data as data
from retrieval import calibrate_policy, rank_records, score


def record(ident="a", split="enrollment"):
    return {"id": ident, "signer_id": "demo", "session_id": ident,
            "source_id": ident, "split": split, "label": "hello",
            "negative_kind": None, "verified": True,
            "verification_note": "Fixture only", "provenance": "synthetic test fixture",
            "sha256": ("a" if ident == "a" else "b") * 64, "path": f"pilot/{ident}.mp4"}


DEMO_SIGNS = ("hello", "thankyou", "yes", "no", "sorry", "doctor",
              "today", "tomorrow", "morning", "afternoon", "evening", "time")


def development_rows():
    """Exactly the PLAN minimum: 3 enrollment and 5 calibration per sign, 20 negatives."""
    rows = [{"split": split, "label": label, "negative_kind": None, "signer_id": "demo",
             "verified": True}
            for split, count in (("enrollment", 3), ("calibration", 5))
            for label in DEMO_SIGNS for _ in range(count)]
    return rows + [{"split": "calibration", "label": None, "signer_id": "demo",
                    "negative_kind": data.NEGATIVES[i % 4], "verified": True} for i in range(20)]


DIM = len(DEMO_SIGNS) + 1  # the last axis belongs to no reference
REFERENCES = [{"id": f"ref-{label}", "sha256": f"ref-{label}", "source_id": f"ref-{label}",
               "label": label, "embedding": np.eye(DIM)[i]} for i, label in enumerate(DEMO_SIGNS)]
_query_ids = count()


def toward(label, similarity):
    """Unit embedding with cosine `similarity` to one reference and 0 to all others."""
    return (similarity * np.eye(DIM)[DEMO_SIGNS.index(label)]
            + np.sqrt(1 - similarity ** 2) * np.eye(DIM)[-1])


def attempt(label, similarity, looks_like=None):
    ident = f"q{next(_query_ids)}"
    return {"id": ident, "sha256": ident, "source_id": ident, "label": label,
            "quality": {"pose_fraction": 1, "hand_fraction": 1},
            "embedding": toward(looks_like or label, similarity)}


def calibration_rows(signs=None, extra=(), negatives=20):
    """5 clear attempts per sign and faint negatives, ranked against synthetic references."""
    signs = signs or {}
    queries = [a for label in DEMO_SIGNS
               for a in signs.get(label, [attempt(label, 0.95) for _ in range(5)])]
    queries += [attempt(None, 0.3, "hello") for _ in range(negatives)] + list(extra)
    return rank_records(queries, REFERENCES)


class DatasetContracts(unittest.TestCase):
    def test_sessions_and_sources_cannot_cross_splits(self):
        for field in ("session_id", "source_id", "sha256"):
            a, b = record(), record("b", "test")
            b[field] = a[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                data.validate_records([a, b], verify_files=False)

    def test_duplicate_cannot_pad_enrollment_count(self):
        a, b = record(), record("b")
        b["sha256"] = a["sha256"]
        with self.assertRaises(ValueError):
            data.validate_records([a, b], verify_files=False)

    def test_path_escape_and_unsubstantiated_verification_fail(self):
        for change in ({"path": "../outside.mp4"}, {"verification_note": ""},
                       {"verified": "yes"}, {"negative_kind": "idle"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                data.validate_records([{**record(), **change}], verify_files=False)

    def test_absent_data_cannot_pass_a_pilot(self):
        result = data.readiness([], final=True)
        self.assertFalse(result["ready"])
        self.assertIn("No fresh pilot recordings", result["issues"])

    def test_vocabulary_is_the_twelve_demo_signs_in_order(self):
        self.assertEqual(data.VOCABULARY, DEMO_SIGNS)

    def test_hospital_is_no_longer_a_supported_label(self):
        with self.assertRaisesRegex(ValueError, "target concept"):
            data.validate_records([{**record(), "label": "hospital"}], verify_files=False)
        data.validate_records([{**record(), "label": "evening"}], verify_files=False)

    def test_readiness_requires_every_one_of_the_twelve_signs(self):
        self.assertTrue(data.readiness(development_rows())["ready"])
        for label in DEMO_SIGNS:
            for split, minimum in (("enrollment", 3), ("calibration", 5)):
                rows = development_rows()
                rows.remove(next(r for r in rows if r["split"] == split and r["label"] == label))
                result = data.readiness(rows)
                with self.subTest(label=label, split=split):
                    self.assertFalse(result["ready"])
                    self.assertEqual(result["issues"],
                                     [f"{split}: need {minimum} verified examples of {label}"])
        rows = development_rows()
        rows.remove(next(r for r in rows if r["label"] is None))
        self.assertEqual(data.readiness(rows)["issues"], ["calibration: need 20 negative clips"])


class RetrievalContracts(unittest.TestCase):
    def test_query_truth_cannot_change_ranking_and_self_match_is_excluded(self):
        query = {**record(), "embedding": np.array([1.0, 0.0])}
        duplicate = {**query, "id": "duplicate", "label": "doctor"}
        genuine = {**record("b"), "label": "tomorrow", "embedding": np.array([0.9, 0.1])}
        result = data.rank(query, [query, duplicate, genuine])
        modified = {**query, "label": "morning"}
        self.assertEqual(result, data.rank(modified, [query, duplicate, genuine]))
        self.assertEqual([r["concept"] for r in result["ranking"]], ["tomorrow"])

    def test_uncalibrated_lookup_never_accepts_even_an_exact_match(self):
        result = {"ranking": [{"concept": "hello", "similarity": 1.0}], "margin": 1.0}
        decision = data.decision(result, {"pose_fraction": 1, "hand_fraction": 1})
        self.assertEqual(decision["status"], "abstain")
        self.assertIsNone(decision["concept"])

    def test_missing_tracking_cannot_be_overridden_by_similarity(self):
        result = {"ranking": [{"concept": "hello", "similarity": 1.0}], "margin": 1.0}
        decision = data.decision(result, {}, {"similarity": 0.8, "margin": 0.1})
        self.assertEqual(decision["status"], "abstain")

    def test_tracking_quality_boundaries_come_from_the_shared_constant(self):
        result = {"ranking": [{"concept": "hello", "similarity": 1.0}], "margin": 1.0}
        policy = {"similarity": 0.8, "margin": 0.1}
        self.assertEqual(data.QUALITY, {"min_pose_fraction": 0.6, "min_hand_fraction": 0.2})
        for quality, status in (({"pose_fraction": 0.6, "hand_fraction": 0.2}, "candidate"),
                                ({"pose_fraction": 0.59, "hand_fraction": 1}, "abstain"),
                                ({"pose_fraction": 1, "hand_fraction": 0.19}, "abstain")):
            with self.subTest(quality=quality):
                self.assertEqual(data.decision(result, quality, policy)["status"], status)
        with patch.dict(data.QUALITY, min_pose_fraction=0.7):
            self.assertEqual(data.decision(result, {"pose_fraction": 0.65, "hand_fraction": 1},
                                           policy)["status"], "abstain")

    def test_nonfinite_thresholds_and_quality_cannot_accept(self):
        result = {"ranking": [{"concept": "hello", "similarity": 1.0}], "margin": 1.0}
        with self.assertRaises(ValueError):
            data.decision(result, {"pose_fraction": 1, "hand_fraction": 1},
                          {"similarity": float("nan"), "margin": 0})
        decision = data.decision(result, {"pose_fraction": float("nan"), "hand_fraction": 1},
                                 {"similarity": 0.8, "margin": 0.1})
        self.assertEqual(decision["status"], "abstain")

    def test_invalid_embeddings_fail_instead_of_producing_arbitrary_labels(self):
        for vector in ([0, 0], [np.nan, 1], [np.inf, 0], [[1, 0]]):
            with self.subTest(vector=vector), self.assertRaises(ValueError):
                data.unit(vector)

    def test_wrong_supported_accept_and_negative_accept_are_distinct(self):
        base = {"quality": {"pose_fraction": 1, "hand_fraction": 1},
                "ranking": [{"concept": "hello", "similarity": 0.99}], "margin": 0.2}
        result = score([{**base, "label": "doctor"}, {**base, "label": None}],
                       {"similarity": 0.8, "margin": 0.1})
        self.assertEqual(result["per_concept"]["doctor"]["wrong_accepted"], 1)
        self.assertEqual(result["negative_false_accepts"], 1)
        self.assertEqual(result["per_concept"]["doctor"]["correct_accepted"], 0)


class CalibrationContracts(unittest.TestCase):
    """PLAN R2b: >=60% per sign, 0 wrong accepts, 0 negative accepts, never reject-all."""

    def test_clean_session_accepts_every_attempt_and_no_negative(self):
        policy, result = calibrate_policy(calibration_rows())
        self.assertGreater(max(policy["similarity"], policy["margin"]), 0.3)
        for label, counts in result["per_concept"].items():
            with self.subTest(label=label):
                self.assertEqual((counts["correct_accepted"], counts["total"]), (5, 5))
        self.assertEqual((result["negative_false_accepts"], result["negative_count"]), (0, 20))

    def test_sixty_percent_per_sign_is_the_exact_boundary(self):
        # A negative at 0.8 forces the cut-off above 0.8, so only the 0.9 attempts survive.
        for total, kept in ((5, 3), (20, 12)):
            for strong, passes in ((kept, True), (kept - 1, False)):
                time = ([attempt("time", 0.9) for _ in range(strong)]
                        + [attempt("time", 0.7) for _ in range(total - strong)])
                rows = calibration_rows({"time": time}, [attempt(None, 0.8, "hello")])
                with self.subTest(total=total, strong=strong):
                    if passes:
                        _, result = calibrate_policy(rows)
                        counts = result["per_concept"]["time"]
                        self.assertEqual((counts["correct_accepted"], counts["total"]), (kept, total))
                        self.assertEqual(result["negative_false_accepts"], 0)
                    else:
                        with self.assertRaisesRegex(ValueError, "60%"):
                            calibrate_policy(rows)

    def test_one_wrong_accept_disqualifies_a_threshold(self):
        yes = [attempt("yes", 0.9) for _ in range(4)] + [attempt("yes", 0.8)]
        confused = attempt("yes", 0.85, looks_like="no")
        _, clean = calibrate_policy(calibration_rows({"yes": yes}))
        self.assertEqual(clean["per_concept"]["yes"]["correct_accepted"], 5)
        rows = calibration_rows({"yes": yes + [confused]})
        loose = score(rows, {"similarity": 0.8, "margin": 0.0})
        self.assertEqual(loose["per_concept"]["yes"]["wrong_accepted"], 1)
        _, result = calibrate_policy(rows)
        self.assertEqual(sum(c["wrong_accepted"] for c in result["per_concept"].values()), 0)
        self.assertEqual(result["per_concept"]["yes"]["correct_accepted"], 4)

    def test_one_negative_accept_disqualifies_a_threshold(self):
        yes = [attempt("yes", 0.9) for _ in range(4)] + [attempt("yes", 0.8)]
        rows = calibration_rows({"yes": yes}, [attempt(None, 0.85, "hello")])
        self.assertEqual(score(rows, {"similarity": 0.8, "margin": 0.0})["negative_false_accepts"], 1)
        _, result = calibrate_policy(rows)
        self.assertEqual(result["negative_false_accepts"], 0)
        self.assertEqual(result["per_concept"]["yes"]["correct_accepted"], 4)

    def test_reject_all_is_not_successful_calibration(self):
        # Every sign looks like hello, so only a reject-everything cut-off has 0 wrong accepts.
        signs = {label: [attempt(label, 0.99, "hello") for _ in range(5)] for label in DEMO_SIGNS}
        with self.assertRaisesRegex(ValueError, "60%"):
            calibrate_policy(calibration_rows(signs))

    def test_missing_negatives_block_calibration(self):
        for negatives in (0, 19):
            with self.subTest(negatives=negatives), self.assertRaisesRegex(
                    ValueError, f"needs 20 negative clips; found {negatives}"):
                calibrate_policy(calibration_rows(negatives=negatives))

    def test_every_sign_needs_calibration_attempts(self):
        with self.assertRaisesRegex(ValueError, "missing evening$"):
            calibrate_policy(calibration_rows({"evening": []}))


class CaptureContracts(unittest.TestCase):
    def parse(self, concept):
        from pilot_capture import build_parser

        return build_parser().parse_args(
            ["capture", "--signer", "demo", "--session", "s1", "--split", "enrollment",
             "--concept", concept])

    def test_capture_parser_accepts_demo_signs_and_rejects_hospital(self):
        for concept in DEMO_SIGNS + data.NEGATIVES:
            with self.subTest(concept=concept):
                self.assertEqual(self.parse(concept).concept, concept)
        with redirect_stderr(StringIO()) as stderr, self.assertRaises(SystemExit):
            self.parse("hospital")
        self.assertIn("invalid choice: 'hospital'", stderr.getvalue())
    def test_video_roundtrip_stays_unverified_and_does_not_change_on_bad_timestamp(self):
        import cv2
        from pilot_capture import save_take, verify

        validate = data.validate_records
        frames = [np.full((48, 64, 3), i * 20, np.uint8) for i in range(8)]
        metadata = {k: v for k, v in record().items()
                    if k in {"signer_id", "session_id", "split", "label", "negative_kind", "provenance"}}
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "dataset.json"
            with patch.object(data, "ARTIFACTS", root), patch.object(
                data, "validate_records",
                side_effect=lambda rows, verify_files=True: validate(rows, root, verify_files)
            ):
                row = save_take(frames, [i / 25 for i in range(8)], metadata, manifest)
                self.assertFalse(row["verified"])
                self.assertAlmostEqual(row["capture"]["fps"], 25)
                self.assertEqual(data.load_dataset(manifest)[0]["sha256"], row["sha256"])
                video = cv2.VideoCapture(str(root / row["path"]))
                try:
                    self.assertEqual(int(video.get(cv2.CAP_PROP_FRAME_COUNT)), 8)
                    self.assertAlmostEqual(video.get(cv2.CAP_PROP_FPS), 25, places=2)
                    self.assertTrue(video.read()[0])
                finally:
                    video.release()
                original = manifest.read_bytes()
                with self.assertRaises(ValueError):
                    save_take(frames, [0] * 8, metadata, manifest)
                with self.assertRaisesRegex(ValueError, "review"):
                    verify(SimpleNamespace(manifest=manifest, id=row["id"], note="Not actually reviewed"))
                self.assertEqual(manifest.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
