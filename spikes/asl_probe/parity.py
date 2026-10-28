"""Mac vs app (simulator or phone) parity for the ASL Signs model on the same saved clips (PLAN P3).

The Mac path is legacy MediaPipe Holistic -> Kaggle 543x3 -> asl-signs.tflite (ai-edge-litert),
the one behind every number in docs/experiments/asl-model-probe.md. The app path is the
Holistic Landmarker task -> the same layout -> the same model through LiteRT on iOS, written
by ios/IsharaTests/ASLParityHarness.swift. Clips are fed whole, so the comparison isolates
the landmarker and the runtime from the detector.

Run with spikes/recognition/.venv from spikes/recognition, after the harness:

    .venv/bin/python ../asl_probe/parity.py --clips DIR --sim OUT_DIR [--out parity.json]

Reports per clip: top-1 and its probability on both paths, the bundle's decision on both
(chip / pick-one / ?), the Mac model run on the app's own landmarks (a runtime check: it
should equal the app's output), hand and pose tracking fractions, and how far apart the
two landmarkers put each hand. Where the decisions differ, `why` swaps one landmark part at a
time from the Mac into the app's clip (see `attribute`) and names the part that flips it.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "recognition"))
sys.path.insert(0, str(HERE))

FACE, HAND, POSE = 468, 21, 33
LEFT, POSE0, RIGHT = FACE, FACE + HAND, FACE + HAND + POSE
POINTS = FACE + HAND + POSE + HAND
PARTS = {"face": slice(0, FACE), "left_hand": slice(LEFT, LEFT + HAND), "pose": slice(POSE0, POSE0 + POSE),
         "right_hand": slice(RIGHT, RIGHT + HAND)}
VIDEO = {".mp4", ".mov", ".m4v"}


def _hand_distance(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Per frame, mean xy distance between two hands' 21 points; NaN where either is missing."""
    return np.linalg.norm(a[..., :2] - b[..., :2], axis=-1).mean(axis=-1)


def mirrored_frames(mac_lm: np.ndarray, app_lm: np.ndarray, tolerance: float = 0.05) -> np.ndarray:
    """Frames where the app reports a hand on the other side from the Mac: its left hand sits on
    the Mac's right hand (or the reverse) and not on the Mac's same-side hand."""
    n = min(len(mac_lm), len(app_lm))
    mac, app = mac_lm[:n], app_lm[:n]
    out = np.zeros(n, dtype=bool)
    for side, other in (("left_hand", "right_hand"), ("right_hand", "left_hand")):
        crossed = _hand_distance(app[:, PARTS[side]], mac[:, PARTS[other]])
        same = _hand_distance(app[:, PARTS[side]], mac[:, PARTS[side]])
        with np.errstate(invalid="ignore"):
            out |= (crossed < tolerance) & ~(same < tolerance)
    return out


def attribute(mac_lm: np.ndarray, app_lm: np.ndarray, decide) -> dict:
    """Why the two paths decide differently: the app's landmarks with one part taken from the Mac
    (face, left_hand, pose, right_hand, then both hands), with its hands exchanged on the frames
    where they sit on the Mac's other hand (handedness; only tried when there are such frames),
    and the Mac's landmarks cut to the app's frame count (frames). `decide` maps a [T, 543, 3]
    clip to a decision string. `explained_by` names the swaps that turn the app's decision into
    the Mac's: single parts first, both hands only if no single part does it."""
    mac_d, app_d = decide(mac_lm), decide(app_lm)
    n = min(len(mac_lm), len(app_lm))
    mac_n, app_n = mac_lm[:n], app_lm[:n]
    swaps: dict[str, str] = {}
    for name, part in PARTS.items():
        hybrid = app_n.copy()
        hybrid[:, part] = mac_n[:, part]
        swaps[name] = decide(hybrid)
    mirrored = mirrored_frames(mac_n, app_n)
    if mirrored.any():
        fixed = app_n.copy()
        left, right = PARTS["left_hand"], PARTS["right_hand"]
        fixed[mirrored, left], fixed[mirrored, right] = app_n[mirrored, right], app_n[mirrored, left]
        swaps["handedness"] = decide(fixed)
    hands = app_n.copy()
    for side in ("left_hand", "right_hand"):
        hands[:, PARTS[side]] = mac_n[:, PARTS[side]]
    swaps["hands"] = decide(hands)
    explained: list[str] = []
    if mac_d != app_d:
        singles = [k for k in (*PARTS, "handedness") if k in swaps and swaps[k] == mac_d]
        explained = singles or (["hands"] if swaps["hands"] == mac_d else [])
        if len(mac_lm) != len(app_lm) and decide(mac_lm[:len(app_lm)]) == app_d:
            explained.append("frames")
    return {"mac": mac_d, "app": app_d, "frames": [len(mac_lm), len(app_lm)], "mirrored_frames": int(mirrored.sum()),
            "swaps": swaps, "explained_by": explained}


def softmax(z) -> np.ndarray:
    z = np.asarray(z, dtype=np.float64)
    e = np.exp(z - z.max())
    return e / e.sum()


def tracking(lm: np.ndarray) -> dict[str, float]:
    present = lambda a, b: float((~np.isnan(lm[:, a:b, 0]).any(axis=1)).mean())  # noqa: E731
    return {"left": present(LEFT, LEFT + HAND), "right": present(RIGHT, RIGHT + HAND),
            "pose": present(POSE0, POSE0 + POSE)}


def part_gap(a: np.ndarray, b: np.ndarray, part: str) -> float | None:
    """Mean xy distance between the two landmarkers' points for one part (PARTS), over frames where both saw it."""
    n = min(len(a), len(b))
    pa, pb = a[:n, PARTS[part], :2], b[:n, PARTS[part], :2]
    both = ~np.isnan(pa[..., 0]).any(axis=1) & ~np.isnan(pb[..., 0]).any(axis=1)
    if not both.any():
        return None
    return float(np.linalg.norm(pa[both] - pb[both], axis=-1).mean())


def compare(rows: list[dict]) -> dict:
    agree = [r for r in rows if r["mac_top1"] == r["app_top1"]]
    confident = [r for r in rows if r["mac_p1"] >= 0.6]
    return {
        "clips": len(rows),
        "top1_agree": len(agree),
        "confident_mac_clips": len(confident),
        "confident_agree": sum(r["mac_top1"] == r["app_top1"] for r in confident),
        "decision_agree": sum(r["mac_decision"] == r["app_decision"] for r in rows),
        "clips_with_mirrored_hands": sum(r.get("mirrored_frames", 0) > 0 for r in rows),
        "runtime_max_abs_logit_diff": max((r["runtime_max_abs_diff"] for r in rows), default=None),
        "disagreements_explained_by": dict(Counter(
            "+".join(r["why"]["explained_by"]) or "no single swap" for r in rows if r.get("why"))),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clips", type=Path, required=True)
    parser.add_argument("--sim", type=Path, required=True, help="the harness output dir (simulator.json + .f32)")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    from asl_matcher import asl_decision, load_asl_bundle
    from asl_model import AslModel, quality
    from asl_summary import mac_landmarks

    app = {r["clip"]: r for r in json.loads((args.sim / "simulator.json").read_text())}
    bundle = load_asl_bundle()
    model = AslModel()
    glosses = model.glosses
    rows = []

    def label(d: dict) -> str:
        return d["status"] + (f":{d['sign'] or d['candidate']}" if d["status"] != "abstain" else "")

    def decide(lm: np.ndarray) -> str:
        return label(asl_decision(model.predict(lm), quality(lm), bundle))

    clips = sorted(p for p in args.clips.iterdir() if p.suffix.lower() in VIDEO)
    for clip in clips:
        if clip.name not in app:
            print(f"skip {clip.name}: not in simulator.json", file=sys.stderr)
    try:
        for clip, mac_lm in mac_landmarks(c for c in clips if c.name in app):
            app_row = app[clip.name]
            app_lm = np.fromfile(args.sim / f"{clip.stem}.f32", dtype="<f4").reshape(-1, FACE + HAND + POSE + HAND, 3)
            mac_p = model.predict(mac_lm)
            app_p = softmax(app_row["logits"])
            mac_on_app = model.predict(app_lm)
            mac_d = asl_decision(mac_p, quality(mac_lm), bundle)
            app_d = asl_decision(app_p, quality(app_lm), bundle)
            why = attribute(mac_lm, app_lm, decide) if label(mac_d) != label(app_d) else None
            rows.append({
                "clip": clip.name, "frames": [len(mac_lm), len(app_lm)],
                "mac_top1": glosses[int(mac_p.argmax())], "mac_p1": round(float(mac_p.max()), 3),
                "app_top1": glosses[int(app_p.argmax())], "app_p1": round(float(app_p.max()), 3),
                "mac_decision": label(mac_d), "app_decision": label(app_d), "why": why,
                "runtime_max_abs_diff": round(float(np.abs(mac_on_app - app_p).max()), 5),
                "tracking_mac": tracking(mac_lm), "tracking_app": tracking(app_lm),
                "left_gap": part_gap(mac_lm, app_lm, "left_hand"), "right_gap": part_gap(mac_lm, app_lm, "right_hand"),
                "face_gap": part_gap(mac_lm, app_lm, "face"), "pose_gap": part_gap(mac_lm, app_lm, "pose"),
                "mirrored_frames": int(mirrored_frames(mac_lm, app_lm).sum()),
                "app_seconds": round(app_row["seconds"], 2),
            })
    finally:
        model.close()

    print(f"{'clip':<34}{'mac':>18}{'app':>18}  {'decision mac / app':<34}{'hands mac':>12}{'hands app':>12}  gap L/R")
    for r in rows:
        tm, ta = r["tracking_mac"], r["tracking_app"]
        gap = "/".join("-" if g is None else f"{g:.3f}" for g in (r["left_gap"], r["right_gap"]))
        print(f"{r['clip']:<34}{r['mac_top1']:>12} {r['mac_p1']:.2f}{r['app_top1']:>12} {r['app_p1']:.2f}  "
              f"{r['mac_decision'] + ' / ' + r['app_decision']:<34}"
              f"{tm['left']:.2f}/{tm['right']:.2f}".rjust(12) + f"{ta['left']:.2f}/{ta['right']:.2f}".rjust(12) + f"  {gap}"
              + (f"  why: {'+'.join(r['why']['explained_by']) or 'no single swap'}" if r["why"] else ""))
    summary = compare(rows)
    print(json.dumps(summary, indent=1))
    if args.out:
        args.out.write_text(json.dumps({"summary": summary, "clips": rows}, indent=1))
        print(f"saved {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
