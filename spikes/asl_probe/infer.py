"""Run the public ASL Signs 1st-place TFLite over extracted landmark clips and score them.

Run with spikes/recognition/artifacts/asl_signs/.venv (ai-edge-litert). Reads the manifest
and the .npz files written by extract.py, feeds each clip whole ([T, 543, 3] float32, NaN
for missing points) and records the 250 logits. Scores:

- top-1 / top-5 over all 250 ASL glosses, against the ASL gloss mapped from the ISL label
  (only for labels that have one: hello, thankyou, yes, no, tomorrow, morning, time);
- top-1 restricted to the demo subset;
- softmax probability and margin of the top-1, for later cut-off work.

Variants: `raw` feeds normalized image coordinates as extracted; `portrait` rescales x so
the x/y aspect matches a 9:16 phone recording like the training data (the model normalizes
position and scale internally, but not aspect).

    .venv/bin/python ../../../asl_probe/infer.py --manifest ../asl_probe/manifest.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from ai_edge_litert.interpreter import Interpreter

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "recognition" / "artifacts" / "asl_signs"
ISL_TO_ASL = {"hello": "hello", "thankyou": "thankyou", "yes": "yes", "no": "no",
              "tomorrow": "tomorrow", "morning": "morning", "time": "time"}
DEMO = ["hello", "thankyou", "yes", "no", "sick", "tomorrow", "morning", "now", "time", "wait"]
TRAIN_ASPECT = 9 / 16


def softmax(z):
    z = z - z.max()
    e = np.exp(z)
    return e / e.sum()


def portrait(lm: np.ndarray, width: int, height: int) -> np.ndarray:
    out = lm.copy()
    out[..., 0] = (out[..., 0] - 0.5) * (width / height) / TRAIN_ASPECT + 0.5
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--variants", nargs="+", default=["raw", "portrait"])
    parser.add_argument("--out", type=Path)
    parser.add_argument("--window", type=float, default=0.0,
                        help="also score sliding windows of this many seconds (stride a quarter) on clips longer than it")
    parser.add_argument("--target-map", type=json.loads, default=None,
                        help="JSON object label -> ASL gloss (default: the ISL overlap map)")
    args = parser.parse_args(argv)
    target_map = args.target_map if args.target_map is not None else ISL_TO_ASL
    rows = json.loads(args.manifest.read_text())
    index = json.loads((ASSETS / "sign_to_prediction_index_map.json").read_text())
    glosses = [None] * len(index)
    for g, i in index.items():
        glosses[i] = g
    demo_idx = [index[g] for g in DEMO]
    it = Interpreter(model_path=str(ASSETS / "model.tflite"))
    run = it.get_signature_runner("serving_default")

    results = []
    for row in rows:
        f = args.manifest.parent / "landmarks" / f"{row['id']}.npz"
        if not f.exists():
            continue
        z = np.load(f)
        lm, w, h = z["landmarks"].astype(np.float32), int(z["width"]), int(z["height"])
        if len(lm) < 2:
            continue
        for variant in args.variants:
            x = portrait(lm, w, h) if variant == "portrait" else lm
            logits = run(inputs=x)["outputs"].astype(np.float64)
            p = softmax(logits)
            order = np.argsort(-p)
            top5 = [(glosses[i], round(float(p[i]), 3)) for i in order[:5]]
            d_order = sorted(demo_idx, key=lambda i: -p[i])
            demo_top = glosses[d_order[0]]
            demo_margin = float(p[d_order[0]] - p[d_order[1]])
            best_window = None
            fps = float(z["fps"]) or 25.0
            win = int(round(args.window * fps))
            if win and len(lm) > win:
                target = target_map.get(row["label"])
                for start in range(0, len(lm) - win + 1, max(1, win // 4)):
                    pw = softmax(run(inputs=x[start:start + win])["outputs"].astype(np.float64))
                    j = int(np.argmax(pw))
                    cand = {"start_s": round(start / fps, 2), "top1": glosses[j], "p1": round(float(pw[j]), 3),
                            "p_target": round(float(pw[index[target]]), 3) if target in index else None}
                    key = cand["p_target"] if cand["p_target"] is not None else cand["p1"]
                    if best_window is None or key > (best_window["p_target"] if best_window["p_target"] is not None else best_window["p1"]):
                        best_window = cand
            results.append({**{k: row[k] for k in ("id", "label", "source")}, "variant": variant, "frames": int(len(lm)),
                            "top5": top5, "top1": top5[0][0], "p1": top5[0][1],
                            "margin": round(float(p[order[0]] - p[order[1]]), 3),
                            "demo_top1": demo_top, "demo_p": round(float(p[d_order[0]]), 3),
                            "demo_margin": round(demo_margin, 3), "best_window": best_window})

    for variant in args.variants:
        print(f"\n=== variant: {variant} ===")
        sub = [r for r in results if r["variant"] == variant]
        per = defaultdict(lambda: {"n": 0, "top1": 0, "top5": 0, "demo_top1": 0, "preds": Counter(), "demo_preds": Counter()})
        for r in sub:
            s = per[r["label"]]
            s["n"] += 1
            s["preds"][r["top1"]] += 1
            s["demo_preds"][r["demo_top1"]] += 1
            target = target_map.get(r["label"])
            if target:
                s["top1"] += r["top1"] == target
                s["top5"] += target in [g for g, _ in r["top5"]]
                s["demo_top1"] += r["demo_top1"] == target
        print(f"{'ISL label':<10}{'n':>3}{'top1/250':>10}{'top5/250':>10}{'top1/demo10':>12}  most frequent 250-way predictions | demo-10 predictions")
        for label in sorted(per, key=lambda l: (l not in target_map, l)):
            s = per[label]
            scored = label in target_map
            fmt = (lambda v: f"{v}/{s['n']}") if scored else (lambda v: "n/a")
            print(f"{label:<10}{s['n']:>3}{fmt(s['top1']):>10}{fmt(s['top5']):>10}{fmt(s['demo_top1']):>12}  "
                  f"{dict(s['preds'].most_common(3))} | {dict(s['demo_preds'].most_common(3))}")
        scored = [r for r in sub if r["label"] in target_map]
        if scored:
            t1 = sum(r["top1"] == target_map[r["label"]] for r in scored)
            t5 = sum(target_map[r["label"]] in [g for g, _ in r["top5"]] for r in scored)
            d1 = sum(r["demo_top1"] == target_map[r["label"]] for r in scored)
            print(f"overlap words total: top1/250 {t1}/{len(scored)}, top5/250 {t5}/{len(scored)}, top1/demo10 {d1}/{len(scored)}")
    if args.out:
        args.out.write_text(json.dumps(results, indent=1))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
