"""Per-word summary of a labelled ASL session, the gate check, and threshold suggestions (D8).

Three sources, each a list of labelled attempts:

    --records PATH   records.json from asl_probe/live_probe.py (detector cuts, Mac webcam)
    --clips DIR      one clip per attempt, named <word>_<n>.<ext> (e.g. tomorrow_03.mov); scored
                     whole on the Mac path (legacy Holistic -> asl-signs.tflite). "none_<n>" clips
                     are negatives: anything accepted on them is a false accept.
    --app DIR        the same clips as scored by the app path (ios/IsharaTests/ASLParityHarness:
                     simulator.json), so the numbers come from the landmarker the phone runs.

The decision is the bundle's open-set rule (asl_matcher.asl_decision), re-applied here so the
thresholds can be swept. Outputs a markdown table (stdout or --markdown), --json and --csv.
--write-bundle PATH writes a frozen copy of the bundle (provisional false) with the suggested
global cut-off, plus per-word cut-offs with --per-word; review it before shipping it in
ios/Ishara/Resources/asl-bundle.json and fixtures/asl/.

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
from typing import Any, Iterable, Sequence

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


# ---- sources ----

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


def from_clips(directory: Path) -> list[Attempt]:
    sys.path.insert(0, str(HERE.parent / "asl_probe"))
    import extract as ex
    from asl_model import AslModel, quality
    from detect_clips import holistic

    model = AslModel()
    out = []
    try:
        with holistic() as tracker:
            for clip in sorted(p for p in directory.iterdir() if p.suffix.lower() in VIDEO):
                lm = ex.extract(clip, tracker)["landmarks"].astype(np.float32)
                if not len(lm):
                    continue
                out.append(Attempt(label_of(clip), _top(model.predict(lm), model.glosses), quality(lm), clip.name))
    finally:
        model.close()
    return out


def write_bundle(document: dict[str, Any], suggestion: dict[str, Any], per_word: bool, source: str, path: Path) -> None:
    frozen = json.loads(json.dumps(document))
    if suggestion["p"] is None:
        raise SystemExit("no cut-off on the grid gives zero wrong accepts; not writing a bundle")
    frozen["thresholds"]["p"] = suggestion["p"]
    frozen["thresholds"]["pick_one_p"] = min(frozen["thresholds"]["pick_one_p"], suggestion["p"])
    frozen["per_word"] = suggestion["per_word"] if per_word else {}
    frozen["provisional"] = False
    frozen["calibration"] = (f"frozen from {source} by asl_summary.py: lowest global cut-off with zero wrong "
                             f"accepts{', plus per-word cut-offs' if per_word else ''}. " + document.get("calibration", ""))
    path.write_text(json.dumps(frozen, indent=1) + "\n")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--records", type=Path)
    source.add_argument("--clips", type=Path)
    source.add_argument("--app", type=Path)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--write-bundle", type=Path)
    parser.add_argument("--per-word", action="store_true", help="include per-word cut-offs in --write-bundle")
    args = parser.parse_args(list(argv) if argv is not None else None)

    document = json.loads(args.bundle.read_text())
    rule = Rule.from_bundle(document)
    if args.records:
        attempts, name = from_records(args.records), str(args.records)
    elif args.app:
        attempts, name = from_app(args.app, document["glosses"]), f"app path, {args.app}"
    else:
        attempts, name = from_clips(args.clips), f"Mac path, {args.clips}"
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
        args.json.write_text(json.dumps({"source": name, "rows": rows, "gate": verdict, "suggestion": suggestion},
                                        indent=1, default=float))
    if args.csv:
        with args.csv.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["word", "source", "top1", "p1", "margin", "decision", "decided_gloss"])
            for a in attempts:
                writer.writerow([a.word, a.source, a.top[0][0], f"{a.p1:.4f}", f"{a.margin:.4f}", *rule.decide(a)])
    if args.write_bundle:
        write_bundle(document, suggestion, args.per_word, name, args.write_bundle)
        print(f"wrote {args.write_bundle} (provisional false): review before shipping")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
