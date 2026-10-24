"""Compare frozen sign embeddings; calibrate and evaluate on disjoint sessions.

replay is development-only. calibrate/evaluate require a verified pilot manifest.
export-bundle packs the frozen policy and enrollment embeddings for the iPhone.
export-bundle --provisional builds a separate, clearly marked try bundle from
enrollment alone (leave-one-out cut-offs); calibrate/evaluate never accept it.
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
PROVISIONAL_BANNER = "PROVISIONAL — uncalibrated, for trying only, not Gate 2"
# Used when no leave-one-out cut-off accepts a take without a wrong accept. SignCLIP
# similarities cluster high (public clips: 0.79-0.94, margins 0.00-0.13), so only a
# strong match with a clear lead over the runner-up gets through.
PROVISIONAL_FALLBACK = {"similarity": 0.90, "margin": 0.05}
LEAVE_ONE_OUT_MINIMUM = 2  # takes per sign, so every take has another take of its sign


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


def leave_one_out(references):
    """Each enrollment take ranked against all the other takes; rank() skips the take itself.

    Unlike calibration (R2b), query and references come from the same session.
    """
    if any(r.get("error") for r in references):
        raise ValueError("An enrollment reference could not be embedded")
    takes = {label: sum(r["label"] == label for r in references) for label in data.VOCABULARY}
    short = [f"{label} ({count})" for label, count in takes.items() if count < LEAVE_ONE_OUT_MINIMUM]
    if short:
        raise ValueError(f"Leave-one-out needs {LEAVE_ONE_OUT_MINIMUM} takes of every sign; short: "
                         + ", ".join(short))
    return rank_records(references, references)


def provisional_policy(rows):
    """Enrollment-only cut-off for trying the Sign Lab before a calibration session exists.

    Cut-offs sit at observed correct top matches (never below the weakest one); among
    those with 0 wrong accepts, the one accepting the most takes wins, the lowest on ties
    (the most permissive). With no negatives and same-session references the counts are
    optimistic. A cut-off that accepts nothing is never chosen: if every useful one has a
    wrong accept, PROVISIONAL_FALLBACK is used and flagged.
    """
    correct = [r for r in rows if r["ranking"] and r["ranking"][0]["concept"] == r["label"]]
    similarities = sorted({r["ranking"][0]["similarity"] for r in correct})
    margins = sorted({r["margin"] for r in correct})
    best, best_key = None, None
    for threshold in similarities:
        for margin in margins:
            candidate = {"similarity": threshold, "margin": margin}
            summary = score(rows, candidate)
            classes = summary["per_concept"].values()
            accepted = sum(c["correct_accepted"] for c in classes)
            if accepted and not sum(c["wrong_accepted"] for c in classes):
                key = (accepted, -threshold, -margin)
                if best_key is None or key > best_key:
                    best, best_key = candidate, key
    fallback = best is None
    thresholds = dict(PROVISIONAL_FALLBACK) if fallback else best
    summary = score(rows, thresholds)
    classes = summary["per_concept"]
    counts = {"method": "leave-one-out over enrollment takes: same-session references, no negatives",
              "queries": len(rows),
              "correct_accepted": sum(c["correct_accepted"] for c in classes.values()),
              "wrong_accepted": sum(c["wrong_accepted"] for c in classes.values()),
              "abstentions": sum(c["abstentions"] for c in classes.values()),
              "fallback": fallback, "per_concept": classes}
    return thresholds, counts


def provisional_banner(thresholds, counts, destination):
    rule = "=" * 72
    lines = [rule, PROVISIONAL_BANNER,
             f"Leave-one-out on {counts['queries']} enrollment takes (same session, no negatives):",
             f"  similarity >= {thresholds['similarity']:.4f}, margin >= {thresholds['margin']:.4f}",
             f"  accepted {counts['correct_accepted']} of {counts['queries']}, "
             f"wrong accepts {counts['wrong_accepted']}, abstained {counts['abstentions']}"]
    if counts["fallback"]:
        lines.append("  FALLBACK: no cut-off accepted a take without a wrong accept, so the conservative "
                     f"default {PROVISIONAL_FALLBACK} is used. Some signs look alike: expect ? and mix-ups.")
    lines += ["  Idle and unsupported movement were never measured: expect some false chips.",
              f"Bundle: {destination}", rule]
    return "\n".join(lines)


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


def frozen_policy(policy_path, records, purpose):
    """A policy is valid only for the exact enrollment/calibration data it was frozen on."""
    if not policy_path.is_file():
        raise ValueError(f"Calibrate on development sessions before {purpose}")
    policy = json.loads(policy_path.read_text())
    if policy.get("provisional"):
        raise ValueError(f"{PROVISIONAL_BANNER}: cut-offs from enrollment alone cannot be used for {purpose}; "
                         "run calibrate on a calibration session")
    if policy["data_fingerprint"] != fingerprint([r for r in records if r["split"] != "test"]):
        raise ValueError("Enrollment/calibration changed since the policy was frozen")
    return policy


def check_encoder(policy, encoder):
    if policy["encoder"] != encoder.contract:
        raise ValueError("Policy was calibrated for a different encoder contract")


def pilot(command, name, manifest, fresh):
    records = data.load_dataset(manifest)
    ready = data.readiness(records, final=command == "evaluate")
    if not ready["ready"]:
        print(json.dumps({"status": "blocked", **ready}, indent=2))
        return 2
    development = [r for r in records if r["split"] != "test"]
    policy_path = EVIDENCE / f"policy-{name}.json"
    if command == "evaluate":
        saved_policy = frozen_policy(policy_path, records, "evaluating test")
    encoder = Encoder(name)
    if command == "evaluate":
        check_encoder(saved_policy, encoder)
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


def encoder_id(contract):
    """The encoder contract as one comparable string (sorted keys, no spaces)."""
    return json.dumps(contract, sort_keys=True, separators=(",", ":"))


def bundle(contract, thresholds, references):
    """iPhone matcher input; the field layout is shared with the Swift side."""
    dims = {len(r["embedding"]) for r in references}
    if len(dims) != 1:
        raise ValueError("Enrollment embeddings must all have one dimension")
    if {r["label"] for r in references} != set(data.VOCABULARY):
        raise ValueError("The bundle needs enrollment references for every sign")
    return {"version": 1, "encoder": encoder_id(contract),
            "embedding_dim": dims.pop(),
            "thresholds": {"similarity": float(thresholds["similarity"]),
                           "margin": float(thresholds["margin"])},
            "quality": dict(data.QUALITY),
            "references": [{"id": r["id"], "label": r["label"],
                            "embedding": [float(v) for v in data.unit(r["embedding"])]}
                           for r in references]}


def export_bundle(name, manifest):
    records = data.load_dataset(manifest)
    policy = frozen_policy(EVIDENCE / f"policy-{name}.json", records, "exporting a bundle")
    encoder = Encoder(name)
    check_encoder(policy, encoder)
    references = embed_records(encoder, [r for r in records if r["split"] == "enrollment"])
    if any(r.get("error") for r in references):
        raise ValueError("An enrollment reference could not be embedded")
    destination = REPORTS / f"recognition-bundle-{name}.json"
    data.write_json(destination, bundle(encoder.contract, policy["thresholds"], references))
    print(f"Bundle with {len(references)} Mac-extracted references: {destination}")
    return 0


def provisional_bundle_path(name):
    """Never the calibrated bundle's path, so a try bundle can't silently replace it."""
    return REPORTS / f"recognition-bundle-{name}-provisional.json"


def export_provisional_bundle(name, manifest):
    """Bundle from verified enrollment takes alone, cut-offs by leave-one-out; no policy file."""
    enrollment = [r for r in data.load_dataset(manifest) if r["split"] == "enrollment"]
    unverified = sum(not r["verified"] for r in enrollment)
    if unverified:
        raise ValueError(f"{unverified} enrollment takes are unverified; verify or remove them first")
    encoder = Encoder(name)
    references = embed_records(encoder, enrollment)
    thresholds, counts = provisional_policy(leave_one_out(references))
    calibrated = bundle(encoder.contract, thresholds, references)
    document = {"version": calibrated["version"], "provisional": True, **calibrated,
                "leave_one_out": counts}
    destination = provisional_bundle_path(name)
    data.write_json(destination, document)
    print(provisional_banner(thresholds, counts, destination), flush=True)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["replay", "status", "calibrate", "evaluate",
                                            "export-bundle"])
    parser.add_argument("--encoder", choices=["slgcn", "signclip"], default="slgcn")
    parser.add_argument("--manifest", type=data.Path, default=data.DATASET)
    parser.add_argument("--fresh", action="store_true", help="Disable feature cache for latency measurement")
    parser.add_argument("--provisional", action="store_true",
                        help="export-bundle only: enrollment-only try bundle, cut-offs by leave-one-out "
                             "(uncalibrated, never Gate 2)")
    args = parser.parse_args(argv)
    if args.provisional and args.command != "export-bundle":
        parser.error("--provisional only applies to export-bundle")
    if args.command == "status":
        print(json.dumps(data.readiness(data.load_dataset(args.manifest), final=True), indent=2))
        return 0
    if args.command == "replay":
        replay(args.encoder)
        return 0
    if args.command == "export-bundle":
        if args.provisional:
            return export_provisional_bundle(args.encoder, args.manifest)
        return export_bundle(args.encoder, args.manifest)
    return pilot(args.command, args.encoder, args.manifest, args.fresh)


if __name__ == "__main__":
    raise SystemExit(main())
