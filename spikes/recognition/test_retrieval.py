"""Data leakage and abstention contracts; no model downloads or inference."""
import json
import unittest
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
from itertools import count
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

import recognition_data as data
import retrieval
from retrieval import calibrate_policy, calibration_report, rank_records, score


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


def pilot_row(split, label, looks_like, similarity, negative_kind=None):
    ident = f"p{next(_query_ids)}"
    return {"id": ident, "signer_id": "demo", "session_id": split, "source_id": ident,
            "sha256": ident, "split": split, "label": label, "negative_kind": negative_kind,
            "verified": True, "fixture": {"looks_like": looks_like, "similarity": similarity}}


def pilot_records():
    """A manifest that meets the PLAN minimum, with synthetic embeddings per clip."""
    rows = [pilot_row(split, label, label, similarity)
            for split, copies, similarity in (("enrollment", 3, 1.0), ("calibration", 5, 0.95))
            for label in DEMO_SIGNS for _ in range(copies)]
    return rows + [pilot_row("calibration", None, "hello", 0.3, data.NEGATIVES[i % 4])
                   for i in range(20)]


class FakeEncoder:
    """Stands in for a loaded model: embeds each clip from its fixture, no inference."""
    contract = {"encoder": "signclip", "checkpoint": "synthetic", "input": "synthetic:v1"}

    def __init__(self, name):
        self.name = name

    def extract(self, row, fresh=False):
        fixture = row["fixture"]
        return {**row, "embedding": data.unit(toward(fixture["looks_like"], fixture["similarity"])),
                "quality": {"pose_fraction": 1, "hand_fraction": 1}}


@contextmanager
def fake_pilot(records, root, contract=FakeEncoder.contract):
    encoder = type("Encoder", (FakeEncoder,), {"contract": contract})
    with ExitStack() as stack:
        stack.enter_context(patch.object(data, "load_dataset", lambda manifest: records))
        stack.enter_context(patch.object(retrieval, "Encoder", encoder))
        stack.enter_context(patch.object(retrieval, "EVIDENCE", root / "retrieval"))
        stack.enter_context(patch.object(retrieval, "REPORTS", root / "evidence"))
        yield stack.enter_context(redirect_stdout(StringIO()))


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

    def test_report_lists_per_sign_counts_and_denominators(self):
        time = [attempt("time", 0.9) for _ in range(3)] + [attempt("time", 0.7) for _ in range(2)]
        policy, result = calibrate_policy(
            calibration_rows({"time": time}, [attempt(None, 0.8, "hello")]))
        report = calibration_report("signclip", policy, result, "f" * 64)
        for line in ("# Calibration report: signclip",
                     f"- Similarity cut-off: {policy['similarity']:.7f}",
                     f"- Margin over the runner-up: {policy['margin']:.7f}",
                     "- Tracking quality: pose >= 0.6, hands >= 0.2",
                     "- Wrong accepts: 0 of 60 sign attempts",
                     "- Negative accepts: 0 of 21 negative clips",
                     f"- Enrollment/calibration fingerprint: `{'f' * 64}`",
                     "| time | 3 | 5 | 60% | 0 |", "| hello | 5 | 5 | 100% | 0 |"):
            with self.subTest(line=line):
                self.assertIn(line + "\n", report)
        self.assertEqual(sum(row.startswith("| ") for row in report.splitlines()), 13)

    def test_report_shows_wrong_and_negative_accepts_of_a_loose_cut_off(self):
        yes = [attempt("yes", 0.9) for _ in range(5)] + [attempt("yes", 0.85, looks_like="no")]
        rows = calibration_rows({"yes": yes}, [attempt(None, 0.85, "hello")])
        loose = {"similarity": 0.8, "margin": 0.0}
        report = calibration_report("slgcn", loose, score(rows, loose), "0" * 64)
        self.assertIn("| yes | 5 | 6 | 83% | 1 |\n", report)
        self.assertIn("- Wrong accepts: 1 of 61 sign attempts\n", report)
        self.assertIn("- Negative accepts: 1 of 21 negative clips\n", report)

    def test_calibrate_command_freezes_policy_and_writes_the_report(self):
        with TemporaryDirectory() as temporary, fake_pilot(pilot_records(), Path(temporary)) as out:
            root = Path(temporary)
            self.assertEqual(retrieval.pilot("calibrate", "signclip", None, False), 0)
            policy = (root / "retrieval" / "policy-signclip.json").read_text()
            report = (root / "evidence" / "calibration-signclip.md").read_text()
        self.assertIn('"data_fingerprint"', policy)
        self.assertIn("| evening | 5 | 5 | 100% | 0 |", report)
        self.assertIn("- Negative accepts: 0 of 20 negative clips", report)
        self.assertIn(report, out.getvalue())


class BundleContracts(unittest.TestCase):
    """The iPhone reads this exact layout; P3 later swaps in iOS-extracted references."""

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root, self.records = Path(temporary.name), pilot_records()
        with fake_pilot(self.records, self.root):
            self.assertEqual(retrieval.pilot("calibrate", "signclip", None, False), 0)
        self.policy = json.loads((self.root / "retrieval" / "policy-signclip.json").read_text())
        self.destination = self.root / "evidence" / "recognition-bundle-signclip.json"

    def export(self, records=None, contract=FakeEncoder.contract):
        with fake_pilot(records or self.records, self.root, contract):
            return retrieval.export_bundle("signclip", None)

    def test_bundle_has_the_agreed_format(self):
        self.assertEqual(self.export(), 0)
        bundle = json.loads(self.destination.read_text())
        self.assertEqual(list(bundle), ["version", "encoder", "embedding_dim", "thresholds",
                                        "quality", "references"])
        self.assertEqual(bundle["version"], 1)
        self.assertEqual(json.loads(bundle["encoder"]), FakeEncoder.contract)
        self.assertEqual(bundle["thresholds"], self.policy["thresholds"])
        self.assertEqual(bundle["quality"], {"min_pose_fraction": 0.6, "min_hand_fraction": 0.2})
        enrollment = [r for r in self.records if r["split"] == "enrollment"]
        self.assertEqual([r["id"] for r in bundle["references"]], [r["id"] for r in enrollment])
        self.assertEqual([r["label"] for r in bundle["references"]],
                         [r["label"] for r in enrollment])
        self.assertEqual({r["label"] for r in bundle["references"]}, set(DEMO_SIGNS))
        self.assertEqual(bundle["embedding_dim"], DIM)
        for reference in bundle["references"]:
            self.assertEqual(list(reference), ["id", "label", "embedding"])
            self.assertEqual(len(reference["embedding"]), DIM)
            np.testing.assert_allclose(reference["embedding"], toward(reference["label"], 1.0),
                                       atol=1e-6)

    def test_bundle_quality_follows_the_shared_constant(self):
        with patch.dict(data.QUALITY, min_hand_fraction=0.3):
            self.export()
        self.assertEqual(json.loads(self.destination.read_text())["quality"]["min_hand_fraction"], 0.3)

    def test_changed_enrollment_or_calibration_data_is_refused(self):
        for split in ("enrollment", "calibration"):
            records = [dict(r) for r in self.records]
            next(r for r in records if r["split"] == split)["verification_note"] = "re-reviewed"
            with self.subTest(split=split), self.assertRaisesRegex(ValueError, "changed since"):
                self.export(records)
        self.assertFalse(self.destination.exists())

    def test_different_encoder_contract_is_refused(self):
        with self.assertRaisesRegex(ValueError, "different encoder contract"):
            self.export(contract={**FakeEncoder.contract, "checkpoint": "other"})
        self.assertFalse(self.destination.exists())

    def test_missing_policy_is_refused(self):
        (self.root / "retrieval" / "policy-signclip.json").unlink()
        with self.assertRaisesRegex(ValueError, "before exporting a bundle"):
            self.export()

    def test_mixed_dimensions_or_missing_signs_cannot_be_bundled(self):
        references = [{"id": f"r{i}", "label": label, "embedding": np.eye(DIM)[i]}
                      for i, label in enumerate(DEMO_SIGNS)]
        thresholds = {"similarity": 0.5, "margin": 0.1}
        self.assertEqual(retrieval.bundle({}, thresholds, references)["embedding_dim"], DIM)
        with self.assertRaisesRegex(ValueError, "one dimension"):
            retrieval.bundle({}, thresholds, references + [
                {"id": "x", "label": "hello", "embedding": np.ones(DIM + 1)}])
        with self.assertRaisesRegex(ValueError, "every sign"):
            retrieval.bundle({}, thresholds, references[:-1])


def loo_rows(signs=None):
    """Enrollment-like attempts (no negatives) ranked against the synthetic references."""
    signs = signs or {}
    queries = [a for label in DEMO_SIGNS
               for a in signs.get(label, [attempt(label, s) for s in (0.95, 0.9, 0.85)])]
    return rank_records(queries, REFERENCES)


def ranked(label, concept, similarity, margin):
    return {"label": label, "quality": {"pose_fraction": 1, "hand_fraction": 1},
            "ranking": [{"concept": concept, "similarity": similarity}], "margin": margin}


def enrollment_records(sims=(0.95, 0.9, 0.85)):
    return [pilot_row("enrollment", label, label, s) for label in DEMO_SIGNS for s in sims]


class ProvisionalBundleContracts(unittest.TestCase):
    """Sign Lab try mode: enrollment-only cut-offs that are never mistaken for calibration."""

    def test_clean_takes_are_all_accepted_at_the_weakest_observed_match(self):
        rows = loo_rows()
        thresholds, counts = retrieval.provisional_policy(rows)
        self.assertEqual(thresholds, {"similarity": min(r["ranking"][0]["similarity"] for r in rows),
                                      "margin": min(r["margin"] for r in rows)})
        self.assertEqual((counts["queries"], counts["correct_accepted"], counts["wrong_accepted"],
                          counts["abstentions"], counts["fallback"]), (36, 36, 0, 0, False))
        stricter = {**thresholds, "similarity": thresholds["similarity"] + 1e-6}
        self.assertEqual(sum(c["correct_accepted"] for c in score(rows, stricter)["per_concept"].values()), 24)

    def test_a_confused_take_is_left_out_by_the_most_permissive_clean_cut_off(self):
        yes = [attempt("yes", 0.9) for _ in range(4)] + [attempt("yes", 0.8),
                                                         attempt("yes", 0.85, looks_like="no")]
        rows = loo_rows({label: [attempt(label, 0.95) for _ in range(3)] for label in DEMO_SIGNS}
                        | {"yes": yes})
        loosest = {"similarity": 0.8 - 1e-6, "margin": 0.0}
        self.assertEqual(score(rows, loosest)["per_concept"]["yes"]["wrong_accepted"], 1)
        thresholds, counts = retrieval.provisional_policy(rows)
        self.assertEqual((counts["correct_accepted"], counts["wrong_accepted"], counts["fallback"]),
                         (37, 0, False))
        self.assertEqual(counts["per_concept"]["yes"],
                         {"total": 6, "correct_accepted": 4, "wrong_accepted": 0, "abstentions": 2})
        self.assertAlmostEqual(min(thresholds.values()), 0.8, places=6)

    def test_signs_that_all_look_alike_fall_back_to_the_documented_default(self):
        rows = loo_rows({label: [attempt(label, 0.99, "hello") for _ in range(3)] for label in DEMO_SIGNS})
        thresholds, counts = retrieval.provisional_policy(rows)
        self.assertEqual(thresholds, retrieval.PROVISIONAL_FALLBACK)
        self.assertIsNot(thresholds, retrieval.PROVISIONAL_FALLBACK)
        self.assertTrue(counts["fallback"])
        self.assertEqual((counts["correct_accepted"], counts["wrong_accepted"]), (3, 33))
        banner = retrieval.provisional_banner(thresholds, counts, Path("bundle.json"))
        self.assertIn("FALLBACK", banner)
        self.assertIn("wrong accepts 33", banner)

    def test_cut_off_never_drops_below_the_weakest_correct_match(self):
        # (0.7, 0.5) would also accept only the hello take, but no correct take was seen at 0.7.
        rows = [ranked("hello", "hello", 0.9, 0.5), ranked("yes", "hello", 0.7, 0.3)]
        thresholds, counts = retrieval.provisional_policy(rows)
        self.assertEqual(thresholds, {"similarity": 0.9, "margin": 0.5})
        self.assertEqual((counts["correct_accepted"], counts["wrong_accepted"]), (1, 0))

    def test_a_cut_off_that_accepts_nothing_is_never_chosen(self):
        # Each correct take is dominated by a wrong one, but (0.95, 0.9) would accept nothing.
        rows = [ranked("hello", "hello", 0.95, 0.30), ranked("yes", "yes", 0.50, 0.90),
                ranked("no", "hello", 0.96, 0.35), ranked("sorry", "yes", 0.55, 0.95)]
        self.assertEqual(score(rows, {"similarity": 0.95, "margin": 0.9})["negative_false_accepts"], 0)
        thresholds, counts = retrieval.provisional_policy(rows)
        self.assertTrue(counts["fallback"])
        self.assertEqual(thresholds, retrieval.PROVISIONAL_FALLBACK)

    def test_leave_one_out_never_matches_a_take_to_itself(self):
        references = []
        for label in DEMO_SIGNS:
            for suffix, similarity in (("a", 1.0), ("b", 0.8)):
                ident = f"{label}-{suffix}"
                references.append({"id": ident, "sha256": ident, "source_id": ident, "label": label,
                                   "quality": {"pose_fraction": 1, "hand_fraction": 1},
                                   "embedding": data.unit(toward(label, similarity))})
        rows = retrieval.leave_one_out(references)
        self.assertEqual(len(rows), 24)
        for row in rows:
            other = row["id"][:-1] + ("b" if row["id"].endswith("a") else "a")
            with self.subTest(id=row["id"]):
                self.assertEqual(row["ranking"][0]["reference_id"], other)
                self.assertAlmostEqual(row["ranking"][0]["similarity"], 0.8, places=6)
                self.assertNotIn("embedding", row)

    def test_leave_one_out_needs_two_takes_of_every_sign(self):
        references = [{"id": f"{label}{i}", "sha256": f"{label}{i}", "source_id": f"{label}{i}",
                       "label": label, "embedding": toward(label, 0.9)}
                      for label in DEMO_SIGNS for i in range(2)]
        retrieval.leave_one_out(references)
        with self.assertRaisesRegex(ValueError, r"2 takes of every sign; short: time \(1\)$"):
            retrieval.leave_one_out(references[:-1])
        with self.assertRaisesRegex(ValueError, "could not be embedded"):
            retrieval.leave_one_out(references + [{**references[0], "id": "x", "error": "no hands"}])

    def export(self, records, root):
        with fake_pilot(records, root) as out:
            status = retrieval.export_provisional_bundle("signclip", None)
        return status, out.getvalue()

    def test_try_bundle_is_marked_provisional_and_kept_apart_from_calibration(self):
        import live_source

        records = enrollment_records()
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            status, out = self.export(records, root)
            path = root / "evidence" / "recognition-bundle-signclip-provisional.json"
            document = json.loads(path.read_text())
            loaded = live_source.load_bundle(path)
            self.assertFalse((root / "evidence" / "recognition-bundle-signclip.json").exists())
            self.assertFalse((root / "retrieval" / "policy-signclip.json").exists())
        self.assertEqual(status, 0)
        self.assertEqual(list(document), ["version", "provisional", "encoder", "embedding_dim", "thresholds",
                                          "quality", "references", "leave_one_out"])
        self.assertIs(document["provisional"], True)
        self.assertEqual(document["version"], 1)
        self.assertEqual(json.loads(document["encoder"]), FakeEncoder.contract)
        self.assertEqual(document["quality"], data.QUALITY)
        self.assertEqual([r["id"] for r in document["references"]], [r["id"] for r in records])
        loo = document["leave_one_out"]
        self.assertEqual((loo["queries"], loo["correct_accepted"], loo["wrong_accepted"], loo["fallback"]),
                         (36, 36, 0, False))
        self.assertIn("same-session references, no negatives", loo["method"])
        self.assertEqual(loaded.thresholds, document["thresholds"])
        self.assertIn(retrieval.PROVISIONAL_BANNER, out)
        self.assertIn("accepted 36 of 36, wrong accepts 0, abstained 0", out)
        self.assertNotIn("FALLBACK", out)

    def test_only_verified_enrollment_takes_are_used(self):
        records = enrollment_records() + [pilot_row("calibration", label, label, 0.9) for label in DEMO_SIGNS]
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.export(records, root)
            document = json.loads((root / "evidence" / "recognition-bundle-signclip-provisional.json").read_text())
            self.assertEqual(len(document["references"]), 36)
            self.assertEqual(document["leave_one_out"]["queries"], 36)
            unverified = enrollment_records()
            unverified[5]["verified"] = False
            with self.assertRaisesRegex(ValueError, "1 enrollment takes are unverified"):
                self.export(unverified, Path(temporary) / "second")
            self.assertFalse((Path(temporary) / "second").exists())

    def test_provisional_cut_offs_are_refused_for_evaluate_and_calibrated_export(self):
        records = pilot_records()
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with fake_pilot(records, root):
                self.assertEqual(retrieval.pilot("calibrate", "signclip", None, False), 0)
            policy_path = root / "retrieval" / "policy-signclip.json"
            retrieval.frozen_policy(policy_path, records, "evaluating test")  # calibrated: accepted
            policy = json.loads(policy_path.read_text())
            policy_path.write_text(json.dumps({**policy, "provisional": True}))
            with self.assertRaisesRegex(ValueError, "PROVISIONAL .* cannot be used for evaluating test"):
                retrieval.frozen_policy(policy_path, records, "evaluating test")
            with fake_pilot(records, root), self.assertRaisesRegex(ValueError, "PROVISIONAL"):
                retrieval.export_bundle("signclip", None)
            self.assertFalse((root / "evidence" / "recognition-bundle-signclip.json").exists())

    def test_provisional_flag_selects_the_try_export_and_only_for_export_bundle(self):
        with patch.object(retrieval, "export_provisional_bundle", return_value=0) as provisional, \
                patch.object(retrieval, "export_bundle", return_value=0) as calibrated:
            retrieval.main(["export-bundle", "--encoder", "signclip", "--provisional"])
            provisional.assert_called_once_with("signclip", data.DATASET)
            calibrated.assert_not_called()
            retrieval.main(["export-bundle", "--encoder", "signclip"])
            calibrated.assert_called_once_with("signclip", data.DATASET)
        for command in ("calibrate", "evaluate", "status", "replay"):
            with self.subTest(command=command), redirect_stderr(StringIO()) as stderr, \
                    self.assertRaises(SystemExit):
                retrieval.main([command, "--provisional"])
            self.assertIn("--provisional only applies to export-bundle", stderr.getvalue())


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

    def test_take_is_verified_only_with_an_explicit_confirmation_note(self):
        from pilot_capture import save_take

        validate = data.validate_records
        metadata = {k: v for k, v in record().items()
                    if k in {"signer_id", "session_id", "split", "label", "negative_kind", "provenance"}}
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "dataset.json"
            with patch.object(data, "ARTIFACTS", root), patch.object(
                data, "validate_records",
                side_effect=lambda rows, verify_files=True: validate(rows, root, verify_files)
            ):
                for shade, note, verified in ((10, "", False), (90, "   ", False),
                                              (170, "  checked against INCLUDE  ", True)):
                    frames = [np.full((48, 64, 3), shade + i, np.uint8) for i in range(6)]
                    row = save_take(frames, [i / 25 for i in range(6)], metadata, manifest,
                                    verification_note=note)
                    with self.subTest(note=note):
                        self.assertIs(row["verified"], verified)
                        self.assertEqual(row["verification_note"], note.strip())
                self.assertEqual([r["verified"] for r in data.load_dataset(manifest)],
                                 [False, False, True])


if __name__ == "__main__":
    unittest.main()
