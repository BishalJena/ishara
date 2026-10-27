"""Per-word summary of a labelled ASL session, the gate check, and threshold suggestions (D8).

Three sources, each a list of labelled attempts:

    --records PATH   records.json from asl_probe/live_probe.py (detector cuts, Mac webcam)
    --clips DIR      one clip per attempt, named <word>_<n>.<ext> (e.g. tomorrow_03.mov); scored
                     whole on the Mac path (legacy Holistic -> asl-signs.tflite). "none_<n>" clips
                     are negatives: anything accepted on them is a false accept.
    --app DIR        the same clips as scored by the app path (ios/IsharaTests/ASLParityHarness:
                     simulator.json), so the numbers come from the landmarker the phone runs.
    --combine JSON.. runs saved with --json (each named with --name, e.g. "Mac, portrait"):
                     one column per run, every run's gate, and one suggestion fitted on all of
                     them at once, so no run gets a wrong accept from it.

The decision is the bundle's open-set rule (asl_matcher.asl_decision), re-applied here so the
thresholds can be swept. Outputs a markdown table (stdout or --markdown), --json (with every
attempt, for --combine) and --csv. --write-bundle PATH writes a frozen copy of the bundle
(provisional false) with the suggested global cut-off, plus per-word cut-offs with --per-word;
review it before shipping it in ios/Ishara/Resources/asl-bundle.json and fixtures/asl/. Add
--provisional for a candidate that keeps the app's provisional banner (e.g. from public clips).
--vocabulary a,b,c judges any source as if the bundle chipped only those glosses (a what-if).

Run with spikes/recognition/.venv (MediaPipe) for --clips; --records and --app need numpy only.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
DEFAULT_BUNDLE = HERE / "fixtures" / "asl" / "asl-bundle-provisional.json"
NEGATIVE = "none"
GATE_SHARE = 0.6  # ≥ 6/10 per script sign, counting a correct one-tap pick-one
VIDEO = {".mp4", ".mov", ".m4v"}
GRID = [round(x, 2) for x in np.arange(0.35, 0.96, 0.05)]
PER_WORD_FLOOR = 0.45


@dataclass(frozen=True)
class Attempt:
    word: str  # the intended sign, or "none" for a negative
    top: tuple[tuple[str, float], ...]  # ranked (gloss, p), at least two
    quality: dict[str, float]
    source: str = ""
    latency_s: float | None = None

    @property
    def p1(self) -> float:
        return self.top[0][1]

    @property
    def margin(self) -> float:
        return self.top[0][1] - self.top[1][1]


@dataclass
class Rule:
    vocabulary: frozenset[str]
    p: float
    margin: float
    pick_one_p: float
    per_word: dict[str, float] = field(default_factory=dict)
    min_pose: float = 0.6
    min_hand: float = 0.2

    @classmethod
    def from_bundle(cls, document: dict[str, Any]) -> "Rule":
        t, q = document["thresholds"], document["quality"]
        return cls(frozenset(document["vocabulary"]), float(t["p"]), float(t["margin"]), float(t["pick_one_p"]),
                   {k: float(v) for k, v in document.get("per_word", {}).items()},
                   float(q["min_pose_fraction"]), float(q["min_hand_fraction"]))

    def decide(self, a: Attempt) -> tuple[str, str | None]:
        """("chip", gloss) | ("pick_one", gloss) | ("abstain", None), as asl_matcher.asl_decision."""
        if a.quality.get("pose_fraction", 0) < self.min_pose or a.quality.get("hand_fraction", 0) < self.min_hand:
            return "abstain", None
        gloss = a.top[0][0]
        if gloss not in self.vocabulary:
            return "abstain", None
        if a.p1 >= self.per_word.get(gloss, self.p) and a.margin >= self.margin:
            return "chip", gloss
        if a.p1 >= self.pick_one_p:
            return "pick_one", gloss
        return "abstain", None


def tally(attempts: Sequence[Attempt], rule: Rule) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for a in attempts:
        r = rows.setdefault(a.word, {"n": 0, "chip": 0, "pick_one": 0, "unsure": 0, "wrong_chip": 0,
                                     "wrong_pick": 0, "top1": 0, "p_right": [], "latency": []})
        status, gloss = rule.decide(a)
        r["n"] += 1
        r["top1"] += a.top[0][0] == a.word
        if a.top[0][0] == a.word:
            r["p_right"].append(a.p1)
        if a.latency_s is not None:
            r["latency"].append(a.latency_s)
        if status == "chip":
            r["chip" if gloss == a.word else "wrong_chip"] += 1
        elif status == "pick_one":
            r["pick_one" if gloss == a.word else "wrong_pick"] += 1
        else:
            r["unsure"] += 1
    return rows


def gate(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    words = {w: (r["chip"] + r["pick_one"]) / r["n"] >= GATE_SHARE for w, r in rows.items() if w != NEGATIVE}
    wrong = sum(r["wrong_chip"] for w, r in rows.items() if w != NEGATIVE)
    negatives = rows.get(NEGATIVE, {}).get("wrong_chip", 0)
    latencies = [x for r in rows.values() for x in r["latency"]]
    slow = sum(x >= 2.0 for x in latencies)
    return {"words": words, "wrong_auto_accepts": wrong, "negative_auto_accepts": negatives,
            "slow_cuts": slow if latencies else None,
            "passes": all(words.values()) and wrong == 0 and negatives == 0 and not slow}


def suggest(attempts: Sequence[Attempt], rule: Rule) -> dict[str, Any]:
    """The lowest global cut-off, never below the bundle's, with zero wrong chips (negatives
    included): a session with no mistakes is no evidence that a lower one is safe. Then per-word
    cut-offs (never below PER_WORD_FLOOR) that add correct chips without adding a wrong one: of
    those that add the most, the highest, so each stays as far from a wrong accept as it can."""
    def chips(r: Rule) -> tuple[int, int]:
        right = wrong = 0
        for a in attempts:
            status, gloss = r.decide(a)
            if status == "chip":
                right += gloss == a.word
                wrong += gloss != a.word
        return right, wrong

    best_p = None
    for p in (x for x in GRID if x >= rule.p):
        if chips(Rule(rule.vocabulary, p, rule.margin, min(rule.pick_one_p, p)))[1] == 0:
            best_p = p
            break
    base = Rule(rule.vocabulary, best_p or 1.0, rule.margin, min(rule.pick_one_p, best_p or 1.0))
    base_right = chips(base)[0]
    per_word: dict[str, float] = {}
    for word in sorted({a.top[0][0] for a in attempts} & rule.vocabulary):
        best: tuple[int, float] | None = None
        for p in (x for x in GRID if PER_WORD_FLOOR <= x < base.p):
            right, wrong = chips(Rule(base.vocabulary, base.p, base.margin, base.pick_one_p, {**per_word, word: p}))
            if wrong == 0 and right > base_right and (best is None or (right, p) > best):
                best = (right, p)
        if best is not None:
            base_right, per_word[word] = best
    return {"p": best_p, "per_word": per_word, "chips_right_with_suggestion": base_right,
            "note": "fit on one session; check it does not undo zero wrong accepts on any other recording"}


def markdown(rows: dict[str, dict[str, Any]], verdict: dict[str, Any], rule: Rule, title: str) -> str:
    out = [f"### {title}", "",
           f"Rule: chip at p ≥ {rule.p} (per word: {rule.per_word or 'none'}) and margin ≥ {rule.margin}; "
           f"pick-one at p ≥ {rule.pick_one_p}.", "",
           "| sign | attempts | chip ✓ | one-tap ✓ | ? | wrong one-tap | wrong chip | top-1 right "
           "| median p when right | gate |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for word in sorted(rows, key=lambda w: (w == NEGATIVE, w)):
        r = rows[word]
        med = f"{float(np.median(r['p_right'])):.2f}" if r["p_right"] else "-"
        ok = "-" if word == NEGATIVE else ("pass" if verdict["words"][word] else "fail")
        out.append(f"| {word} | {r['n']} | {r['chip']} | {r['pick_one']} | {r['unsure']} | {r['wrong_pick']} | "
                   f"{r['wrong_chip']} | {r['top1']}/{r['n']} | {med} | {ok} |")
    out += ["", f"Wrong auto-accepts: {verdict['wrong_auto_accepts']}; on negatives: {verdict['negative_auto_accepts']}; "
                f"cuts ≥ 2 s: {verdict['slow_cuts'] if verdict['slow_cuts'] is not None else 'not measured'}. "
                f"Gate: {'PASS' if verdict['passes'] else 'FAIL'}."]
    return "\n".join(out)


def combine(runs: dict[str, Sequence[Attempt]], rule: Rule) -> dict[str, Any]:
    """Several runs over the same clips (Mac / app path, landscape / portrait): each run's own
    table and gate, a combined gate that every run must pass, and one suggestion fitted on all
    attempts at once, so a cut-off that is safe on one run but wrong on another is never offered."""
    out: dict[str, Any] = {"runs": {}}
    for name, attempts in runs.items():
        rows = tally(attempts, rule)
        signs = [r for w, r in rows.items() if w != NEGATIVE]
        negative = rows.get(NEGATIVE, {})
        totals = {"signs": sum(r["n"] for r in signs), **{k: sum(r[k] for r in signs) for k in
                                                           ("chip", "pick_one", "wrong_chip", "wrong_pick")},
                  "negatives": negative.get("n", 0), "negative_chip": negative.get("wrong_chip", 0),
                  "negative_pick": negative.get("wrong_pick", 0)}
        out["runs"][name] = {"rows": rows, "gate": gate(rows), "totals": totals}
    out["passes"] = all(r["gate"]["passes"] for r in out["runs"].values())
    out["suggestion"] = suggest([a for attempts in runs.values() for a in attempts], rule)
    return out


def combined_markdown(report: dict[str, Any]) -> str:
    """One row per sign, one column per run: `chip+one-tap/attempts pass|fail`; negatives show
    their auto-accepts (any is a failure)."""
    runs = report["runs"]
    words = sorted({w for r in runs.values() for w in r["rows"]}, key=lambda w: (w == NEGATIVE, w))
    out = ["| sign | clips | " + " | ".join(runs) + " |", "|---|---|" + "---|" * len(runs)]
    for word in words:
        cells = []
        for run in runs.values():
            r = run["rows"].get(word)
            if r is None:
                cells.append("-")
            elif word == NEGATIVE:
                cells.append(f"{r['wrong_chip']} auto-accepts, {r['wrong_pick']} one-tap tiles")
            else:
                verdict = "pass" if run["gate"]["words"][word] else "fail"
                wrong = f", {r['wrong_chip']} wrong chips" if r["wrong_chip"] else ""
                cells.append(f"{r['chip']}+{r['pick_one']}/{r['n']} {verdict}{wrong}")
        n = max(run["rows"][word]["n"] for run in runs.values() if word in run["rows"])
        out.append(f"| {word} | {n} | " + " | ".join(cells) + " |")
    def share(k: int, n: int, what: str) -> str:
        return f"{k} {what} ({k / n:.0%})" if n else f"{k} {what}"
    totals = [run["totals"] for run in runs.values()]
    out.append(f"| all signs | {max(t['signs'] for t in totals)} | " + " | ".join(
        f"{share(t['chip'], t['signs'], 'chips')} + {t['pick_one']} one-tap, {share(t['wrong_chip'], t['signs'], 'wrong chips')}"
        for t in totals) + " |")
    gates = "; ".join(f"{name}: {'PASS' if r['gate']['passes'] else 'FAIL'} ({r['gate']['wrong_auto_accepts']} wrong, "
                      f"{r['gate']['negative_auto_accepts']} on negatives)" for name, r in runs.items())
    s = report["suggestion"]
    out += ["", f"Gate per run: {gates}. All runs: {'PASS' if report['passes'] else 'FAIL'}.", "",
            f"Suggested on all runs together: global p = {s['p']}, per word = {s['per_word'] or 'none'} "
            f"({s['chips_right_with_suggestion']} correct chips over every run)."]
    return "\n".join(out)


# ---- sources ----

def attempts_json(attempts: Sequence[Attempt]) -> list[dict[str, Any]]:
    return [{"word": a.word, "source": a.source, "top": [list(t) for t in a.top], "quality": a.quality,
             "latency_s": a.latency_s} for a in attempts]


def from_json(path: Path) -> tuple[str, list[Attempt]]:
    """A run saved by --json: its source name and attempts."""
    data = json.loads(path.read_text())
    return data["source"], [Attempt(r["word"], tuple((g, float(p)) for g, p in r["top"]), dict(r["quality"]),
                                    r["source"], r["latency_s"]) for r in data["attempts"]]


def label_of(path: Path) -> str:
    return re.split(r"[_\-\s]", path.stem.lower(), maxsplit=1)[0]


def _top(probs: np.ndarray, glosses: Sequence[str], k: int = 5) -> tuple[tuple[str, float], ...]:
    order = np.argsort(-probs)[:k]
    return tuple((glosses[i], float(probs[i])) for i in order)


def from_records(path: Path) -> list[Attempt]:
    data = json.loads(path.read_text())
    out = []
    for r in data["records"]:
        top = tuple((g, float(p)) for g, p in r["top"])
        if len(top) == 1:
            top += (("", float(r["p1"]) - float(r["margin"])),)
        out.append(Attempt(r["word"], top, r.get("quality") or {}, r.get("npy", ""), r.get("latency_s")))
    return out


def from_app(directory: Path, glosses: Sequence[str]) -> list[Attempt]:
    from asl_model import quality

    out = []
    for r in json.loads((directory / "simulator.json").read_text()):
        stem = Path(r["clip"]).stem
        lm = np.fromfile(directory / f"{stem}.f32", dtype="<f4").reshape(-1, 543, 3)
        z = np.asarray(r["logits"], dtype=np.float64)
        probs = np.exp(z - z.max())
        out.append(Attempt(label_of(Path(r["clip"])), _top(probs / probs.sum(), glosses), quality(lm), r["clip"]))
    return out


def mac_landmarks(clips: Iterable[Path]) -> Iterator[tuple[Path, np.ndarray]]:
    """Legacy Holistic landmarks in the Kaggle layout, each clip with a tracker of its own. In video
    mode the tracker carries its hand and face regions from frame to frame, so one tracker shared
    over a folder made a clip's landmarks, and its score, depend on the clip sorted before it."""
    sys.path.insert(0, str(HERE.parent / "asl_probe"))
    import extract as ex
    from detect_clips import holistic

    for clip in clips:
        with holistic() as tracker:
            yield clip, ex.extract(clip, tracker)["landmarks"].astype(np.float32)


def from_clips(directory: Path) -> list[Attempt]:
    from asl_model import AslModel, quality

    model = AslModel()
    out = []
    try:
        for clip, lm in mac_landmarks(sorted(p for p in directory.iterdir() if p.suffix.lower() in VIDEO)):
            if len(lm):
                out.append(Attempt(label_of(clip), _top(model.predict(lm), model.glosses), quality(lm), clip.name))
    finally:
        model.close()
    return out


def write_bundle(document: dict[str, Any], suggestion: dict[str, Any], per_word: bool, source: str, path: Path,
                 provisional: bool = False) -> None:
    """A frozen bundle, or with `provisional` a candidate that keeps the app's provisional banner."""
    frozen = json.loads(json.dumps(document))
    if suggestion["p"] is None:
        raise SystemExit("no cut-off on the grid gives zero wrong accepts; not writing a bundle")
    frozen["thresholds"]["p"] = suggestion["p"]
    frozen["thresholds"]["pick_one_p"] = min(frozen["thresholds"]["pick_one_p"], suggestion["p"])
    frozen["per_word"] = suggestion["per_word"] if per_word else {}
    frozen["provisional"] = provisional
    frozen["calibration"] = (f"{'candidate' if provisional else 'frozen'} from {source} by asl_summary.py: lowest "
                             f"global cut-off with zero wrong accepts{', plus per-word cut-offs' if per_word else ''}. "
                             + document.get("calibration", ""))
    path.write_text(json.dumps(frozen, indent=1) + "\n")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--records", type=Path)
    source.add_argument("--clips", type=Path)
    source.add_argument("--app", type=Path)
    source.add_argument("--combine", type=Path, nargs="+", metavar="JSON",
                        help="runs saved with --json (e.g. Mac and app path, landscape and portrait), judged together")
    parser.add_argument("--name", help="the run's name in --json (default: the source)")
    parser.add_argument("--vocabulary", help="comma-separated glosses: judge as if the bundle chipped only these "
                                             "(a what-if; --write-bundle then carries this vocabulary)")
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--write-bundle", type=Path)
    parser.add_argument("--per-word", action="store_true", help="include per-word cut-offs in --write-bundle")
    parser.add_argument("--provisional", action="store_true",
                        help="--write-bundle writes a candidate that stays provisional instead of a frozen bundle")
    args = parser.parse_args(list(argv) if argv is not None else None)

    document = json.loads(args.bundle.read_text())
    if args.vocabulary:
        words = sorted({w.strip() for w in args.vocabulary.split(",") if w.strip()})
        unknown = [w for w in words if w not in document["glosses"]]
        if unknown:
            raise SystemExit(f"not among the model's glosses: {', '.join(unknown)}")
        document = {**document, "vocabulary": words}
    rule = Rule.from_bundle(document)
    if args.combine:
        runs = dict(from_json(path) for path in args.combine)
        if len(runs) != len(args.combine):
            raise SystemExit("two runs share a name; give each --json run its own --name")
        report = combine(runs, rule)
        text = combined_markdown(report)
        print(text)
        if args.markdown:
            args.markdown.write_text(text + "\n")
        if args.json:
            args.json.write_text(json.dumps(report, indent=1, default=float))
        if args.write_bundle:
            write_bundle(document, report["suggestion"], args.per_word, "combined runs: " + ", ".join(runs),
                         args.write_bundle, args.provisional)
            print(f"wrote {args.write_bundle} (provisional {str(args.provisional).lower()}): review before shipping")
        return 0
    if args.records:
        attempts, name = from_records(args.records), str(args.records)
    elif args.app:
        attempts, name = from_app(args.app, document["glosses"]), f"app path, {args.app}"
    else:
        attempts, name = from_clips(args.clips), f"Mac path, {args.clips}"
    name = args.name or name
    if not attempts:
        raise SystemExit("no labelled attempts found")
    rows = tally(attempts, rule)
    verdict = gate(rows)
    suggestion = suggest(attempts, rule)
    text = markdown(rows, verdict, rule, name) + (
        f"\n\nSuggested: global p = {suggestion['p']}, per word = {suggestion['per_word'] or 'none'} "
        f"({suggestion['chips_right_with_suggestion']} correct chips). {suggestion['note']}.")
    print(text)
    if args.markdown:
        args.markdown.write_text(text + "\n")
    if args.json:
        args.json.write_text(json.dumps({"source": name, "rows": rows, "gate": verdict, "suggestion": suggestion,
                                         "attempts": attempts_json(attempts)}, indent=1, default=float))
    if args.csv:
        with args.csv.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["word", "source", "top1", "p1", "margin", "decision", "decided_gloss"])
            for a in attempts:
                writer.writerow([a.word, a.source, a.top[0][0], f"{a.p1:.4f}", f"{a.margin:.4f}", *rule.decide(a)])
    if args.write_bundle:
        write_bundle(document, suggestion, args.per_word, name, args.write_bundle, args.provisional)
        print(f"wrote {args.write_bundle} (provisional {str(args.provisional).lower()}): review before shipping")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
