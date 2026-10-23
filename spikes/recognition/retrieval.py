"""Compare frozen sign embeddings; calibrate and evaluate on disjoint sessions.

replay is development-only. calibrate/evaluate require a verified pilot manifest.
No result from this module is automatically sent to composition or speech.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time

import numpy as np

import recognition_data as data

EVIDENCE = data.ARTIFACTS / "retrieval"
REPORTS = data.ARTIFACTS / "evidence"


class Encoder:
    def __init__(self, name):
        import torch

        torch.set_num_threads(4)
        self.name = name
        if name == "signclip":
            import signclip
            self.module = signclip
            self.model = signclip.load_model()
            self.contract = {"encoder": name, "checkpoint": signclip.CHECKPOINT_SHA,
                             "source": signclip.REVISION, "input": signclip.CONTRACT}
        else:
            import slgcn
            self.module = slgcn
            self.model, _ = slgcn.load_model()
            self.contract = {"encoder": name, "checkpoint": slgcn.ARCHIVE_SHA,
                             "source": slgcn.SOURCE_REVISION, "input": "slgcn.features:v1"}
        self.contract.update(torch=torch.__version__, device="cpu", threads=4)

    def extract(self, row, fresh=False):
        import torch

        start = time.perf_counter()
        cache = None if fresh else EVIDENCE / self.name / "features"
        features, quality = self.module.extract(data.ARTIFACTS / row["path"], cache)
        inference_start = time.perf_counter()
        with torch.inference_mode():
            vector = (self.module.embed(self.model, features) if self.name == "signclip"
                      else self.model.encoder(self.module.features(features))[0].numpy())
        vector = data.unit(vector)
        return {**row, "embedding": vector, "quality": quality,
                "model_ms": 1000 * (time.perf_counter() - inference_start),
                "total_ms": 1000 * (time.perf_counter() - start)}


def embed_records(encoder, records, fresh=False):
    output = []
    for row in records:
        try:
            item = encoder.extract(row, fresh)
        except ValueError as error:
            item = {**row, "error": str(error), "quality": {}}
        output.append(item)
        print(f"{encoder.name}: {row['id']} — {item.get('error', 'embedded')}", flush=True)
    return output


def rank_records(queries, references):
    references = [r for r in references if "embedding" in r]
    output = []
    for query in queries:
        ranking = data.rank(query, references) if "embedding" in query else {"ranking": [], "margin": None}
        output.append({**{k: v for k, v in query.items() if k != "embedding"}, **ranking})
    return output


def score(rows, policy):
    outcomes = [{**r, "decision": data.decision(r, r["quality"], policy)} for r in rows]
    by_concept = {}
    for label in data.VOCABULARY:
        subset = [r for r in outcomes if r["label"] == label]
        by_concept[label] = {
            "total": len(subset),
            "correct_accepted": sum(r["decision"]["concept"] == label for r in subset),
            "wrong_accepted": sum(r["decision"]["status"] == "candidate"
                                  and r["decision"]["concept"] != label for r in subset),
            "abstentions": sum(r["decision"]["status"] == "abstain" for r in subset),
        }
    negatives = [r for r in outcomes if r["label"] is None]
    return {"per_concept": by_concept, "negative_count": len(negatives),
            "negative_false_accepts": sum(r["decision"]["status"] == "candidate" for r in negatives),
            "rows": outcomes}


def fingerprint(records):
    return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()


def calibrate_policy(rows):
    if any(r.get("error") for r in rows):
        raise ValueError("Resolve extraction errors before calibrating a policy")
    # Without attempts for a sign or enough negatives, "0 wrong accepts" is vacuous.
    missing = [label for label in data.VOCABULARY if not any(r["label"] == label for r in rows)]
    if missing:
        raise ValueError("Calibration needs attempts for every sign; missing " + ", ".join(missing))
    negatives, needed = sum(r["label"] is None for r in rows), data.NEGATIVE_MINIMUM["calibration"]
    if negatives < needed:
        raise ValueError(f"Calibration needs {needed} negative clips; found {negatives}")
    thresholds = sorted({-1.0, *(r["ranking"][0]["similarity"] + 1e-7
                               for r in rows if r["ranking"])})
    margins = sorted({0.0, *(r["margin"] + 1e-7 for r in rows if r["margin"] is not None)})
    best, best_correct = None, -1
    for threshold in thresholds:
        for margin in margins:
            candidate = {"similarity": threshold, "margin": margin}
            summary = score(rows, candidate)
            classes = summary["per_concept"].values()
            wrong = sum(c["wrong_accepted"] for c in classes) + summary["negative_false_accepts"]
            correct = sum(c["correct_accepted"] for c in classes)
            covered = all(c["correct_accepted"] >= 0.6 * c["total"] for c in classes)
            if wrong == 0 and covered and correct > best_correct:
                best, best_correct = candidate, correct
    # Reject-all policies cannot qualify as successful calibration.
    if best is None:
        raise ValueError("Calibration cannot retain 60% per concept without wrong accepts")
    return best, score(rows, best)


def calibration_report(name, thresholds, summary, data_fingerprint):
    """Markdown record of a frozen cut-off with every count and denominator."""
    classes = summary["per_concept"]
    attempts = sum(c["total"] for c in classes.values())
    wrong = sum(c["wrong_accepted"] for c in classes.values())
    lines = [f"# Calibration report: {name}", "",
             "Frozen on the calibration session only (PLAN R2b). Similarities are not probabilities.",
             "", f"- Similarity cut-off: {thresholds['similarity']:.7f}",
             f"- Margin over the runner-up: {thresholds['margin']:.7f}",
             f"- Tracking quality: pose >= {data.QUALITY['min_pose_fraction']}, "
             f"hands >= {data.QUALITY['min_hand_fraction']}",
             f"- Wrong accepts: {wrong} of {attempts} sign attempts",
             f"- Negative accepts: {summary['negative_false_accepts']} of "
             f"{summary['negative_count']} negative clips",
             f"- Enrollment/calibration fingerprint: `{data_fingerprint}`", "",
             "| Sign | Accepted | Attempts | Accepted % | Wrong accepts |",
             "|---|---:|---:|---:|---:|"]
    lines += [f"| {label} | {c['correct_accepted']} | {c['total']} | "
              f"{100 * c['correct_accepted'] / c['total']:.0f}% | {c['wrong_accepted']} |"
              for label, c in classes.items()]
    return "\n".join(lines) + "\n"


def replay(name):
    from mini import inventory

    records = []
    for item in inventory():
        digest = data.sha256(item["path"])
        records.append({"id": item["id"], "path": item["name"],
                        "sha256": digest, "source_id": digest,
                        "label": item["expected"] if item["expected"] in data.VOCABULARY else None,
                        "intended": item["expected"], "kind": item["kind"]})
    encoder = Encoder(name)
    embedded = embed_records(encoder, records)
    references = [r for r in embedded if r["kind"] == "dataset" and r["label"] is not None]
    rows = rank_records(embedded, references)
    for row in rows:
        available = {r["concept"] for r in row["ranking"]}
        row["scorable_supported_query"] = row["label"] is not None and row["label"] in available
        row["top1_matches_intended"] = (
            row["ranking"][0]["concept"] == row["label"]
            if row["scorable_supported_query"] else None)
        row["decision"] = data.decision(row, row["quality"])
    summary = {}
    for kind in ("dataset", "recorded_attempt"):
        subset = [r for r in rows if r["kind"] == kind and r["scorable_supported_query"]]
        summary[kind] = {"scorable": len(subset),
                         "top1_matches_intended": sum(r["top1_matches_intended"] for r in subset)}
    report = {"scope": "uncalibrated development reference matching; not an acceptance test",
              "encoder": encoder.contract, "vocabulary": data.VOCABULARY,
              "reference_ids": [r["id"] for r in references if "embedding" in r],
              "exclusion": "same clip ID, source ID, or content hash cannot be its own reference",
              "summary": summary, "rows": rows}
    destination = EVIDENCE / f"replay-{name}.json"
    data.write_json(destination, report)
    print(json.dumps(summary, indent=2), flush=True)
    print(f"Evidence: {destination.relative_to(data.ROOT)}")
    return report


def pilot(command, name, manifest, fresh):
    records = data.load_dataset(manifest)
    ready = data.readiness(records, final=command == "evaluate")
    if not ready["ready"]:
        print(json.dumps({"status": "blocked", **ready}, indent=2))
        return 2
    development = [r for r in records if r["split"] != "test"]
    policy_path = EVIDENCE / f"policy-{name}.json"
    if command == "evaluate":
        if not policy_path.is_file():
            raise ValueError("Calibrate on development sessions before evaluating test")
        saved_policy = json.loads(policy_path.read_text())
        if saved_policy["data_fingerprint"] != fingerprint(development):
            raise ValueError("Enrollment/calibration changed since the policy was frozen")
    encoder = Encoder(name)
    if command == "evaluate" and saved_policy["encoder"] != encoder.contract:
        raise ValueError("Policy was calibrated for a different encoder contract")
    split = "calibration" if command == "calibrate" else "test"
    embedded = embed_records(encoder, [r for r in records if r["split"] in ("enrollment", split)], fresh)
    references = [r for r in embedded if r["split"] == "enrollment"]
    if any(r.get("error") for r in references):
        raise ValueError("An enrollment reference could not be embedded")
    rows = rank_records([r for r in embedded if r["split"] == split], references)
    if command == "calibrate":
        thresholds, summary = calibrate_policy(rows)
        data_fingerprint = fingerprint(development)
        data.write_json(policy_path, {"version": 1, "encoder": encoder.contract,
                                     "data_fingerprint": data_fingerprint,
                                     "thresholds": thresholds, "calibration": summary})
        report = calibration_report(name, thresholds, summary, data_fingerprint)
        report_path = REPORTS / f"calibration-{name}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report)
        print("Calibration policy frozen from enrollment/calibration only:", thresholds)
        print(report, flush=True)
        print(f"Report: {report_path}")
        return 0
    summary = score(rows, saved_policy["thresholds"])
    measured_fresh = all("total_ms" in r and not r["quality"].get("cache_hit", True) for r in rows)
    p95_ms = float(np.percentile([r["total_ms"] for r in rows], 95)) if measured_fresh else None
    gates = {
        "correct_accepts": all(c["correct_accepted"] >= 0.9 * c["total"]
                              for c in summary["per_concept"].values()),
        "no_wrong_accepts": all(c["wrong_accepted"] == 0 for c in summary["per_concept"].values()),
        "no_negative_accepts": summary["negative_false_accepts"] == 0,
        "fresh_batch_latency_p95_under_2s": p95_ms is not None and p95_ms <= 2000,
    }
    report = {"scope": "personalized isolated-sign pilot; not general ISL",
              "latency_scope": "warm-model batch extraction plus embedding; excludes capture, ranking and display",
              "live_latency_validated": False, "demo_ready": False,
              "encoder": encoder.contract, "policy": saved_policy["thresholds"],
              "policy_sha256": data.sha256(policy_path), "dataset_fingerprint": fingerprint(records),
              "fresh_batch_latency_p95_ms": p95_ms, "gates": gates,
              "passed": all(gates.values()), **summary}
    data.write_json(EVIDENCE / f"test-{name}-{report['dataset_fingerprint'][:12]}.json", report)
    print(json.dumps({"passed": report["passed"], "gates": gates}, indent=2))
    return 0 if report["passed"] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["replay", "status", "calibrate", "evaluate"])
    parser.add_argument("--encoder", choices=["slgcn", "signclip"], default="slgcn")
    parser.add_argument("--manifest", type=data.Path, default=data.DATASET)
    parser.add_argument("--fresh", action="store_true", help="Disable feature cache for latency measurement")
    args = parser.parse_args()
    if args.command == "status":
        print(json.dumps(data.readiness(data.load_dataset(args.manifest), final=True), indent=2))
        return 0
    if args.command == "replay":
        replay(args.encoder)
        return 0
    return pilot(args.command, args.encoder, args.manifest, args.fresh)


if __name__ == "__main__":
    raise SystemExit(main())
