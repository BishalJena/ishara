"""Scorer on synthetic predictions: outcomes, intervals, subsets, confusions, same-file check."""
import unittest

import score as sc

H = "a" * 64


class Intervals(unittest.TestCase):
    def test_wilson_matches_known_values(self):
        self.assertEqual(sc.wilson(0, 10), [0.0, 0.278])
        self.assertEqual(sc.wilson(5, 10), [0.237, 0.763])
        self.assertEqual(sc.wilson(10, 10), [0.722, 1.0])
        self.assertEqual(sc.wilson(81, 263), [0.255, 0.366])
        self.assertIsNone(sc.wilson(0, 0))

    def test_percentile_is_nearest_rank(self):
        self.assertEqual(sc.percentile([5, 1, 3, 2, 4], 50), 3)
        self.assertEqual(sc.percentile([1, 2, 3, 4], 95), 4)
        self.assertEqual(sc.percentile(list(range(1, 101)), 95), 95)
        self.assertIsNone(sc.percentile([], 50))


class Outcomes(unittest.TestCase):
    def test_gemini(self):
        ok = {"status": "ok"}
        self.assertEqual(sc.gemini_outcome({**ok, "word": "time"}, "time"), "correct")
        self.assertEqual(sc.gemini_outcome({**ok, "word": "today"}, "time"), "wrong")
        self.assertEqual(sc.gemini_outcome({**ok, "word": "unsure"}, "time"), "unsure")
        self.assertEqual(sc.gemini_outcome({**ok, "word": "invalid"}, "time"), "error")
        self.assertEqual(sc.gemini_outcome({"status": "error"}, "time"), "error")
        self.assertEqual(sc.gemini_outcome(None, "time"), "error")

    def test_gemini_confidence_cut_turns_low_answers_into_unsure(self):
        record = {"status": "ok", "word": "today", "confidence": 0.6}
        self.assertEqual(sc.gemini_cut_outcome(record, "time", 0.5), "wrong")
        self.assertEqual(sc.gemini_cut_outcome(record, "time", 0.7), "unsure")
        self.assertEqual(sc.gemini_cut_outcome({**record, "confidence": None}, "time", 0.5), "unsure")
        self.assertEqual(sc.gemini_cut_outcome({**record, "word": "time", "confidence": 0.7}, "time", 0.7), "correct")

    def test_signclip_raw_and_cutoff(self):
        record = {"status": "ok", "top1": "time", "accepted": None}
        self.assertEqual(sc.signclip_raw_outcome(record, "time"), "correct")
        self.assertEqual(sc.signclip_cut_outcome(record, "time"), "unsure")
        self.assertEqual(sc.signclip_cut_outcome({**record, "accepted": "today"}, "time"), "wrong")
        self.assertEqual(sc.signclip_cut_outcome({**record, "accepted": "time"}, "time"), "correct")
        self.assertEqual(sc.signclip_raw_outcome({"status": "error"}, "time"), "error")
        self.assertEqual(sc.signclip_raw_outcome({**record, "top1": None}, "time"), "error")


def gemini(word, confidence=0.9, latency=2.0, cost=0.01):
    return {"status": "ok", "word": word, "confidence": confidence, "latency_s": latency, "cost_usd": cost, "sha256": H}


def signclip(top1, accepted=None, ms=900.0):
    return {"status": "ok", "top1": top1, "accepted": accepted, "top": [{"word": top1, "similarity": 0.8}],
            "margin": 0.01, "total_ms": ms, "sha256": H}


class Report(unittest.TestCase):
    def setUp(self):
        self.answers = {"c1": "time", "c2": "time", "c3": "dog", "c4": "dog", "c5": "hello"}
        self.provenance = {k: {"dataset": "youtube" if k == "c5" else "include"} for k in self.answers}
        self.gemini = {"c1": gemini("time"), "c2": gemini("today", 0.4), "c3": gemini("unsure"),
                       "c4": gemini("cat"), "c5": gemini("hello", latency=4.0, cost=0.03)}
        self.signclip = {"c1": signclip("time", "time"), "c2": signclip("today"), "c3": signclip("dog"),
                         "c4": signclip("cat", "cat"), "c5": signclip("hello")}

    def test_counts_rates_and_subsets(self):
        report = sc.score(self.answers, self.provenance, self.gemini, self.signclip)["report"]
        everything = report["subsets"]["all"]
        self.assertEqual({k: everything["gemini"][k]["n"] for k in ("correct", "wrong", "unsure", "error")},
                         {"correct": 2, "wrong": 2, "unsure": 1, "error": 0})
        self.assertEqual(everything["gemini"]["correct"]["of"], 5)
        self.assertEqual(everything["signclip_top1"]["correct"]["n"], 3)
        self.assertEqual({k: everything["signclip_cutoff"][k]["n"] for k in ("correct", "wrong", "unsure")},
                         {"correct": 1, "wrong": 1, "unsure": 3})
        demo = report["subsets"]["demo12"]
        self.assertEqual((demo["gemini"]["clips"], demo["words"]), (3, 2))
        self.assertEqual(demo["gemini"]["correct"]["n"], 2)
        self.assertEqual(report["subsets"]["dataset:youtube"]["gemini"]["clips"], 1)
        self.assertEqual(report["subsets"]["all"]["gemini_confidence_cuts"]["0.5"]["wrong"]["n"], 1)

    def test_confusions_latency_cost_and_agreement(self):
        report = sc.score(self.answers, self.provenance, self.gemini, self.signclip)["report"]
        self.assertEqual(report["confusions"]["gemini"],
                         [{"truth": "time", "predicted": "today", "count": 1},
                          {"truth": "dog", "predicted": "cat", "count": 1}])
        self.assertEqual(report["latency_s"]["gemini_request"]["p50"], 2.0)
        self.assertEqual(report["latency_s"]["gemini_request"]["max"], 4.0)
        self.assertAlmostEqual(report["gemini_cost_usd"]["total"], 0.07)
        self.assertEqual(report["agreement"]["cross"]["gemini_right+signclip_right"], 2)
        self.assertEqual(report["agreement"]["same_answer"], 4)
        self.assertEqual(report["agreement"]["same_answer_correct"], 2)
        self.assertEqual(report["per_word"]["dog"]["gemini_unsure"], 1)

    def test_missing_predictions_are_errors_not_dropped(self):
        del self.gemini["c5"]
        report = sc.score(self.answers, self.provenance, self.gemini, self.signclip)["report"]
        self.assertEqual(report["subsets"]["all"]["gemini"]["error"]["n"], 1)
        self.assertEqual(report["subsets"]["all"]["gemini"]["clips"], 5)

    def test_a_prediction_on_another_file_is_refused(self):
        manifest = {"c1": H}
        sc.check_identical(manifest, {"c1": {"sha256": H}}, "gemini")
        with self.assertRaisesRegex(ValueError, "not the manifest's file"):
            sc.check_identical(manifest, {"c1": {"sha256": "b" * 64}}, "gemini")
        with self.assertRaisesRegex(ValueError, "unknown clip"):
            sc.check_identical(manifest, {"zz": {"sha256": H}}, "signclip")

    def test_resumed_logs_keep_the_ok_record(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in (
                {"id": "c1", "status": "error"}, {"id": "c1", "status": "ok", "word": "time"},
                {"id": "c2", "status": "error"})))
            records = sc.load_gemini(path)
        self.assertEqual(records["c1"]["word"], "time")
        self.assertEqual(records["c2"]["status"], "error")


if __name__ == "__main__":
    unittest.main()
