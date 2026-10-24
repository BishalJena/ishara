"""video_eval contracts on synthetic data: neutral manifests, leakage, scoring maths.

No video, MediaPipe or model: the replay itself is live_source's, covered by test_live_source.
"""
import unittest

import recognition_data as data
import video_eval as ve

H = "a" * 64


def clip(ident="clip_001", split="test", **changes):
    row = {"id": ident, "path": f"video_eval/clips/{ident}.mp4", "sha256": H, "source_id": "src_01",
           "signer_id": "signer-a", "split": split, "set": "A"}
    return {**row, **changes}


def manifest(*clips):
    return {"version": 1, "clips": list(clips)}


class Manifest(unittest.TestCase):
    def test_a_neutral_label_free_manifest_parses(self):
        clips = ve.parse_manifest(manifest(clip(), clip("clip_002", split="reference")))
        self.assertEqual([(c.id, c.split) for c in clips], [("clip_001", "test"), ("clip_002", "reference")])

    def test_a_label_in_the_manifest_is_refused(self):
        with self.assertRaisesRegex(ValueError, "labels belong in labels.json"):
            ve.parse_manifest(manifest(clip(label="hello")))

    def test_a_clip_named_after_its_sign_is_refused(self):
        for changes in ({"id": "hello_01", "path": "video_eval/clips/hello_01.mp4"},
                        {"path": "video_eval/clips/hello.mp4"}):
            with self.subTest(changes), self.assertRaisesRegex(ValueError, "neutral"):
                ve.parse_manifest(manifest(clip(**changes)))

    def test_unknown_split_duplicate_id_and_version_are_refused(self):
        with self.assertRaisesRegex(ValueError, "unknown split"):
            ve.parse_manifest(manifest(clip(split="calibration")))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            ve.parse_manifest(manifest(clip(), clip()))
        with self.assertRaisesRegex(ValueError, "version"):
            ve.parse_manifest({"version": 2, "clips": []})

    def test_labels_must_cover_exactly_the_manifest_with_vocabulary_signs(self):
        clips = ve.parse_manifest(manifest(clip(), clip("clip_002")))
        self.assertEqual(ve.parse_labels({"labels": {"clip_001": "hello", "clip_002": "time"}}, clips),
                         {"clip_001": "hello", "clip_002": "time"})
        with self.assertRaisesRegex(ValueError, "without a label: clip_002"):
            ve.parse_labels({"labels": {"clip_001": "hello"}}, clips)
        with self.assertRaisesRegex(ValueError, "not in the manifest: clip_003"):
            ve.parse_labels({"labels": {"clip_001": "hello", "clip_002": "yes", "clip_003": "no"}}, clips)
        with self.assertRaisesRegex(ValueError, "outside the 12-sign vocabulary: clip_002"):
            ve.parse_labels({"labels": {"clip_001": "hello", "clip_002": "hospital"}}, clips)


class Leakage(unittest.TestCase):
    REFERENCE = {"id": "clip_010", "sha256": "r" * 64, "source_id": "src_10", "signer_id": "islrtc-01"}

    def test_disjoint_sets_pass(self):
        ve.assert_no_leakage([self.REFERENCE], [clip()])

    def test_any_shared_id_hash_source_or_signer_is_leakage(self):
        for key in ("id", "sha256", "source_id", "signer_id"):
            with self.subTest(key), self.assertRaisesRegex(ValueError, f"share {key}"):
                ve.assert_no_leakage([self.REFERENCE], [clip(**{key: self.REFERENCE[key]})])

    def test_records_feed_the_pilot_split_checks(self):
        """A test clip from a reference's source video fails recognition_data's own leakage check."""
        clips = ve.parse_manifest(manifest(clip("clip_001", split="reference", sha256="b" * 64),
                                           clip("clip_002", sha256="c" * 64)))
        rows = ve.records(clips, {"clip_001": "hello", "clip_002": "hello"}, {"src_01": "title"})
        self.assertEqual([r["split"] for r in rows], ["enrollment", "test"])
        with self.assertRaisesRegex(ValueError, "Leakage"):
            data.validate_records(rows, verify_files=False)


class Preparing(unittest.TestCase):
    def test_cut_is_silent_untitled_and_padded_with_rest(self):
        command = ve.cut_command("in.mp4", 1.5, 4.25, "clip_001.mp4")
        for flag in ("-an", "-sn", "-dn"):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("-map_metadata") + 1], "-1")
        self.assertEqual(command[command.index("-map") + 1], "0:v:0")
        self.assertEqual(command[command.index("-ss") + 1], "1.500")
        self.assertEqual(command[command.index("-to") + 1], "4.250")
        filters = command[command.index("-vf") + 1]
        self.assertIn("start_mode=clone:start_duration=2.0", filters)
        self.assertIn("stop_mode=clone:stop_duration=1.0", filters)
        self.assertNotIn("crop", filters)
        cropped = ve.cut_command("in.mp4", 0, 1, "o.mp4", crop="10:10:0:0")
        self.assertTrue(cropped[cropped.index("-vf") + 1].startswith("crop=10:10:0:0,"))

    def test_neutral_ids_are_shuffled_reproducibly_and_complete(self):
        ids = ve.neutral_ids(30, seed=7)
        self.assertEqual(sorted(ids), [f"clip_{i:03d}" for i in range(1, 31)])
        self.assertNotEqual(ids, sorted(ids))
        self.assertEqual(ids, ve.neutral_ids(30, seed=7))
        self.assertNotEqual(ids, ve.neutral_ids(30, seed=8))


def result(ident, *shown, latency=500.0, top=None):
    recognitions = [{"sign": None if s == ve.UNSURE else s, "latency_ms": latency,
                     "top": [{"sign": top or s, "similarity": 0.9}]} for s in shown]
    return {"id": ident, "set": "A", "shown": list(shown), "recognitions": recognitions}


class Scoring(unittest.TestCase):
    def test_outcomes(self):
        self.assertEqual(ve.clip_outcome(["hello"], "hello"), "correct")
        self.assertEqual(ve.clip_outcome(["?", "hello"], "hello"), "correct")
        self.assertEqual(ve.clip_outcome(["hello", "hello"], "hello"), "repeated")
        self.assertEqual(ve.clip_outcome(["hello", "doctor"], "hello"), "wrong")
        self.assertEqual(ve.clip_outcome(["doctor"], "hello"), "wrong")
        self.assertEqual(ve.clip_outcome(["?"], "hello"), "unsure")
        self.assertEqual(ve.clip_outcome([], "hello"), "missed")

    def test_nearest_rank_percentile(self):
        values = [float(v) for v in range(1, 11)]
        self.assertEqual(ve.percentile(values, 50), 5.0)
        self.assertEqual(ve.percentile(values, 95), 10.0)
        self.assertEqual(ve.percentile(values, 90), 9.0)
        self.assertEqual(ve.percentile([3.0, 1.0, 2.0], 50), 2.0)
        self.assertEqual(ve.percentile([7.0], 95), 7.0)
        self.assertIsNone(ve.percentile([], 50))

    def test_score_counts_per_sign_confusions_and_latency(self):
        labels = {"clip_001": "hello", "clip_002": "hello", "clip_003": "doctor", "clip_004": "time",
                  "clip_005": "yes"}
        rows = [result("clip_001", "hello", latency=400), result("clip_002", "doctor", latency=600),
                result("clip_003", "?", latency=800, top="doctor"),
                result("clip_004", "?", "time", latency=1000, top="time"),
                result("clip_005")]
        summary = ve.score(rows, labels)
        self.assertEqual(summary["per_sign"]["hello"], {"clips": 2, "correct": 1, "wrong": 1})
        self.assertEqual(summary["per_sign"]["doctor"], {"clips": 1, "unsure": 1})
        self.assertEqual(summary["per_sign"]["yes"], {"clips": 1, "missed": 1})
        self.assertNotIn("no", summary["per_sign"])
        self.assertEqual(summary["total"]["clips"], 5)
        self.assertAlmostEqual(summary["accuracy"], 2 / 5)
        self.assertEqual(summary["confusion"], [{"truth": "hello", "accepted": "doctor", "count": 1}])
        self.assertEqual(summary["top1"], {"segments": 5, "top1_right": 4})
        self.assertEqual(summary["latency_ms"]["count"], 5)
        self.assertEqual(summary["latency_ms"]["p50"], 800)
        self.assertEqual(summary["latency_ms"]["p95"], 1000)
        self.assertAlmostEqual(summary["latency_ms"]["mean"], 760)

    def test_table_lists_every_counted_sign_and_the_total(self):
        labels = {"clip_001": "hello", "clip_002": "doctor"}
        text = ve.table(ve.score([result("clip_001", "hello"), result("clip_002", "hello")], labels))
        self.assertIn("| hello | 1 | 1 | 0 | 0 | 0 | 0 |", text)
        self.assertIn("| doctor | 1 | 0 | 1 | 0 | 0 | 0 |", text)
        self.assertIn("| **all** | **2** | **1** | **1** | **0** | **0** | **0** |", text)


if __name__ == "__main__":
    unittest.main()
