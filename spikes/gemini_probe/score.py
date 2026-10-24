"""Score Gemini 4 Argon and SignCLIP against the hidden answer key (stdlib only).

    python3 score.py --gemini artifacts/gemini_probe/runs/gemini/predictions.jsonl \
                     --signclip artifacts/gemini_probe/runs/signclip/predictions.json --out-dir <evidence dir>

The only module that opens key/answer_key.json. Both systems must have seen the
identical file: a prediction whose sha256 differs from the manifest is an error.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE.parent / "recognition" / "artifacts" / "gemini_probe"
DEMO_WORDS = frozenset({"hello", "thank you", "yes", "no", "sorry", "doctor", "today", "tomorrow",
                        "morning", "afternoon", "evening", "time"})
UNSURE = "unsure"
CONFIDENCE_CUTS = (0.5, 0.7, 0.9)


def wilson(successes: int, total: int, z: float = 1.959964) -> list[float] | None:
    """Wilson score 95% interval for a proportion, rounded to 3 decimals."""
    if total == 0:
        return None
    p = successes / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return [round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)]


def rate(count: int, total: int) -> dict:
    return {"n": count, "of": total, "rate": round(count / total, 3) if total else None, "ci95": wilson(count, total)}


def percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(1, math.ceil(len(ordered) * q / 100)) - 1]


def gemini_outcome(record: dict | None, truth: str) -> str:
    if record is None or record.get("status") != "ok" or record.get("word") == "invalid":
        return "error"
    if record["word"] == UNSURE:
        return "unsure"
    return "correct" if record["word"] == truth else "wrong"


def gemini_cut_outcome(record: dict | None, truth: str, cut: float) -> str:
    """Descriptive only (cut not tuned): treat answers below `cut` confidence as unsure."""
    outcome = gemini_outcome(record, truth)
    if outcome in ("correct", "wrong") and (record.get("confidence") is None or record["confidence"] < cut):
        return "unsure"
    return outcome


def signclip_raw_outcome(record: dict | None, truth: str) -> str:
    if record is None or record.get("status") != "ok" or record.get("top1") is None:
        return "error"
    return "correct" if record["top1"] == truth else "wrong"


def signclip_cut_outcome(record: dict | None, truth: str) -> str:
    if record is None or record.get("status") != "ok":
        return "error"
    if record.get("accepted") is None:
        return "unsure"
    return "correct" if record["accepted"] == truth else "wrong"


def summarize(outcomes: Sequence[str]) -> dict:
    counts = Counter(outcomes)
    total = len(outcomes)
    return {"clips": total, **{k: rate(counts[k], total) for k in ("correct", "wrong", "unsure", "error")}}


def confusions(pairs: Iterable[tuple[str, str]], limit: int = 15) -> list[dict]:
    counts = Counter((t, p) for t, p in pairs if p is not None and p != t and p not in (UNSURE, "invalid"))
    return [{"truth": t, "predicted": p, "count": n} for (t, p), n in counts.most_common(limit)]


def latency_summary(values: Sequence[float]) -> dict:
    return {"count": len(values), "p50": percentile(values, 50), "p95": percentile(values, 95),
            "mean": round(statistics.fmean(values), 3) if values else None,
            "max": max(values) if values else None}


def check_identical(manifest: dict[str, str], predictions: dict[str, dict], system: str) -> None:
    for clip_id, record in predictions.items():
        if clip_id not in manifest:
            raise ValueError(f"{system}: prediction for unknown clip {clip_id}")
        if record.get("sha256") and record["sha256"] != manifest[clip_id]:
            raise ValueError(f"{system}: {clip_id} was not the manifest's file")


def load_gemini(path: Path) -> dict[str, dict]:
    """Last ok record per clip (a resumed run may log an earlier error for the same clip)."""
    records: dict[str, dict] = {}
    for record in map(json.loads, path.read_text().splitlines()):
        if record.get("status") == "ok" or record["id"] not in records:
            records[record["id"]] = record
    return records


SYSTEMS: dict[str, Callable[[dict | None, str], str]] = {
    "gemini": gemini_outcome,
    "signclip_top1": signclip_raw_outcome,
    "signclip_cutoff": signclip_cut_outcome,
}


def score(answers: dict[str, str], provenance: dict[str, dict], gemini: dict[str, dict],
          signclip: dict[str, dict]) -> dict:
    ids = sorted(answers)
    sources = {"gemini": gemini, "signclip_top1": signclip, "signclip_cutoff": signclip}
    per_clip = []
    for clip_id in ids:
        truth = answers[clip_id]
        g, s = gemini.get(clip_id), signclip.get(clip_id)
        per_clip.append({"id": clip_id, "truth": truth, "demo_word": truth in DEMO_WORDS,
                         "dataset": provenance[clip_id]["dataset"],
                         "gemini_word": g.get("word") if g else None,
                         "gemini_confidence": g.get("confidence") if g else None,
                         "gemini_latency_s": g.get("latency_s") if g else None,
                         "gemini_cost_usd": g.get("cost_usd") if g else None,
                         "signclip_top1": s.get("top1") if s else None,
                         "signclip_top1_similarity": s["top"][0]["similarity"] if s and s.get("top") else None,
                         "signclip_margin": s.get("margin") if s else None,
                         "signclip_accepted": s.get("accepted") if s else None,
                         "signclip_total_ms": s.get("total_ms") if s else None,
                         **{f"{name}_outcome": fn(sources[name].get(clip_id), truth) for name, fn in SYSTEMS.items()}})
    subsets = {"all": per_clip, "demo12": [r for r in per_clip if r["demo_word"]],
               **{f"dataset:{d}": [r for r in per_clip if r["dataset"] == d]
                  for d in sorted({r["dataset"] for r in per_clip})}}
    report: dict = {"words": len({r["truth"] for r in per_clip}), "test_clips": len(per_clip), "subsets": {}}
    for name, rows in subsets.items():
        block = {system: summarize([r[f"{system}_outcome"] for r in rows]) for system in SYSTEMS}
        block["gemini_confidence_cuts"] = {
            str(cut): summarize([gemini_cut_outcome(gemini.get(r["id"]), r["truth"], cut) for r in rows])
            for cut in CONFIDENCE_CUTS}
        block["words"] = len({r["truth"] for r in rows})
        report["subsets"][name] = block
    report["per_word"] = per_word(per_clip)
    report["confusions"] = {
        "gemini": confusions((r["truth"], r["gemini_word"]) for r in per_clip),
        "signclip_top1": confusions((r["truth"], r["signclip_top1"]) for r in per_clip),
        "signclip_cutoff": confusions((r["truth"], r["signclip_accepted"]) for r in per_clip)}
    report["latency_s"] = {
        "gemini_request": latency_summary([r["gemini_latency_s"] for r in per_clip if r["gemini_latency_s"]]),
        "signclip_cpu": latency_summary([round(r["signclip_total_ms"] / 1000, 3) for r in per_clip
                                         if r["signclip_total_ms"]])}
    costs = [r["gemini_cost_usd"] for r in per_clip if r["gemini_cost_usd"] is not None]
    report["gemini_cost_usd"] = {"total": round(sum(costs), 4), "clips": len(costs),
                                 "per_clip_mean": round(statistics.fmean(costs), 5) if costs else None,
                                 "per_clip_max": max(costs) if costs else None}
    report["agreement"] = agreement(per_clip)
    return {"report": report, "per_clip": per_clip}


def per_word(per_clip: Sequence[dict]) -> dict:
    words: dict[str, Counter] = {}
    for row in per_clip:
        counts = words.setdefault(row["truth"], Counter())
        counts["clips"] += 1
        for system in SYSTEMS:
            counts[f"{system}_{row[f'{system}_outcome']}"] += 1
    return {w: dict(sorted(c.items())) for w, c in sorted(words.items())}


def agreement(per_clip: Sequence[dict]) -> dict:
    """How the two systems' top-1 answers overlap (for judging a hybrid)."""
    both = Counter()
    for row in per_clip:
        g, s = row["gemini_outcome"] == "correct", row["signclip_top1_outcome"] == "correct"
        both[("gemini_right" if g else "gemini_not") + "+" + ("signclip_right" if s else "signclip_not")] += 1
    agree = [r for r in per_clip if r["gemini_word"] and r["gemini_word"] == r["signclip_top1"]]
    return {"cross": dict(both), "same_answer": len(agree),
            "same_answer_correct": sum(r["gemini_outcome"] == "correct" for r in agree)}


CSV_FIELDS = ("id", "truth", "demo_word", "dataset", "gemini_word", "gemini_confidence", "gemini_outcome",
              "gemini_latency_s", "gemini_cost_usd", "signclip_top1", "signclip_top1_similarity", "signclip_margin",
              "signclip_top1_outcome", "signclip_accepted", "signclip_cutoff_outcome", "signclip_total_ms")


def table(report: dict, subset: str) -> str:
    block = report["subsets"][subset]
    lines = [f"{subset}: {block['gemini']['clips']} clips, {block['words']} words",
             "| System | Correct | Wrong | Unsure / abstain | Error |", "|---|---|---|---|---|"]
    for system in SYSTEMS:
        b = block[system]
        cells = [f"{b[k]['n']}/{b[k]['of']} ({b[k]['rate']:.0%}, {b[k]['ci95']})" if b[k]["of"] else "-"
                 for k in ("correct", "wrong", "unsure", "error")]
        lines.append(f"| {system} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gemini", type=Path, default=ARTIFACTS / "runs" / "gemini" / "predictions.jsonl")
    parser.add_argument("--signclip", type=Path, default=ARTIFACTS / "runs" / "signclip" / "predictions.json")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = {c["id"]: c["sha256"] for c in json.loads((ARTIFACTS / "manifest.json").read_text())["clips"]}
    answers = json.loads((ARTIFACTS / "key" / "answer_key.json").read_text())["answers"]
    provenance = json.loads((ARTIFACTS / "key" / "provenance.json").read_text())["tests"]
    if set(answers) != set(manifest):
        raise SystemExit("Answer key and manifest list different clips")
    gemini = load_gemini(args.gemini)
    signclip = {r["id"]: r for r in json.loads(args.signclip.read_text())["results"]}
    check_identical(manifest, gemini, "gemini")
    check_identical(manifest, signclip, "signclip")
    scored = score(answers, provenance, gemini, signclip)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "results.json").write_text(json.dumps(scored["report"], indent=1) + "\n")
    with (args.out_dir / "per_clip.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(scored["per_clip"])
    for subset in scored["report"]["subsets"]:
        print(table(scored["report"], subset), end="\n\n")
    json.dump({k: scored["report"][k] for k in ("latency_s", "gemini_cost_usd", "agreement")}, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
