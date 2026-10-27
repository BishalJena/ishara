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
two landmarkers put each hand.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "recognition"))
sys.path.insert(0, str(HERE))

FACE, HAND, POSE = 468, 21, 33
LEFT, POSE0, RIGHT = FACE, FACE + HAND, FACE + HAND + POSE
VIDEO = {".mp4", ".mov", ".m4v"}


def softmax(z) -> np.ndarray:
    z = np.asarray(z, dtype=np.float64)
    e = np.exp(z - z.max())
    return e / e.sum()


def tracking(lm: np.ndarray) -> dict[str, float]:
    present = lambda a, b: float((~np.isnan(lm[:, a:b, 0]).any(axis=1)).mean())  # noqa: E731
    return {"left": present(LEFT, LEFT + HAND), "right": present(RIGHT, RIGHT + HAND),
            "pose": present(POSE0, POSE0 + POSE)}


def hand_gap(a: np.ndarray, b: np.ndarray, start: int) -> float | None:
    """Mean xy distance between the two landmarkers' points for one hand, over frames where both saw it."""
    n = min(len(a), len(b))
    pa, pb = a[:n, start:start + HAND, :2], b[:n, start:start + HAND, :2]
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
        "runtime_max_abs_logit_diff": max((r["runtime_max_abs_diff"] for r in rows), default=None),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clips", type=Path, required=True)
    parser.add_argument("--sim", type=Path, required=True, help="the harness output dir (simulator.json + .f32)")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)

    import extract as ex
    from asl_matcher import asl_decision, load_asl_bundle
    from asl_model import AslModel, quality
    from detect_clips import holistic

    app = {r["clip"]: r for r in json.loads((args.sim / "simulator.json").read_text())}
    bundle = load_asl_bundle()
    model = AslModel()
    glosses = model.glosses
    rows = []
    try:
        with holistic() as tracker:
            for clip in sorted(p for p in args.clips.iterdir() if p.suffix.lower() in VIDEO):
                if clip.name not in app:
                    print(f"skip {clip.name}: not in simulator.json", file=sys.stderr)
                    continue
                mac_lm = ex.extract(clip, tracker)["landmarks"].astype(np.float32)
                app_row = app[clip.name]
                app_lm = np.fromfile(args.sim / f"{clip.stem}.f32", dtype="<f4").reshape(-1, FACE + HAND + POSE + HAND, 3)
                mac_p = model.predict(mac_lm)
                app_p = softmax(app_row["logits"])
                mac_on_app = model.predict(app_lm)
                mac_d = asl_decision(mac_p, quality(mac_lm), bundle)
                app_d = asl_decision(app_p, quality(app_lm), bundle)
                rows.append({
                    "clip": clip.name, "frames": [len(mac_lm), len(app_lm)],
                    "mac_top1": glosses[int(mac_p.argmax())], "mac_p1": round(float(mac_p.max()), 3),
                    "app_top1": glosses[int(app_p.argmax())], "app_p1": round(float(app_p.max()), 3),
                    "mac_decision": mac_d["status"] + (f":{mac_d['sign'] or mac_d['candidate']}" if mac_d["status"] != "abstain" else ""),
                    "app_decision": app_d["status"] + (f":{app_d['sign'] or app_d['candidate']}" if app_d["status"] != "abstain" else ""),
                    "runtime_max_abs_diff": round(float(np.abs(mac_on_app - app_p).max()), 5),
                    "tracking_mac": tracking(mac_lm), "tracking_app": tracking(app_lm),
                    "left_gap": hand_gap(mac_lm, app_lm, LEFT), "right_gap": hand_gap(mac_lm, app_lm, RIGHT),
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
              f"{tm['left']:.2f}/{tm['right']:.2f}".rjust(12) + f"{ta['left']:.2f}/{ta['right']:.2f}".rjust(12) + f"  {gap}")
    summary = compare(rows)
    print(json.dumps(summary, indent=1))
    if args.out:
        args.out.write_text(json.dumps({"summary": summary, "clips": rows}, indent=1))
        print(f"saved {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
