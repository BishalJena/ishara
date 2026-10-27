"""Offline analysis of saved live cuts: TTA, repeat accumulation, phone-framing simulation, latency.

Runs in artifacts/asl_signs/.venv (no MediaPipe needed; cuts are landmark .npy files).

    .venv/bin/python ../../../asl_probe/offline_analysis.py --session 20261025-213120 --labels labels.json
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from ai_edge_litert.interpreter import Interpreter

HERE = Path(__file__).resolve().parent
ART = HERE.parent / "recognition" / "artifacts"
ASSETS = ART / "asl_signs"
FACE, HAND, POSE = 468, 21, 33
NOSE = FACE + HAND + 0  # pose landmark 0


def softmax(z):
    z = z - z.max()
    e = np.exp(z)
    return e / e.sum()


class Model:
    def __init__(self):
        it = Interpreter(model_path=str(ASSETS / "model.tflite"))
        self.run = it.get_signature_runner("serving_default")
        idx = json.loads((ASSETS / "sign_to_prediction_index_map.json").read_text())
        self.glosses = [None] * 250
        for g, i in idx.items():
            self.glosses[i] = g
        self.index = idx

    def probs(self, x):
        return softmax(self.run(inputs=np.ascontiguousarray(x, dtype=np.float32))["outputs"].astype(np.float64))


def hflip(x):
    """Mirror: x -> 1-x and swap left/right hand blocks (face/pose left-right indices are left as is;
    the model saw hflip augmentation in training, so this is a mild perturbation, not an exact mirror)."""
    y = x.copy()
    y[..., 0] = 1.0 - y[..., 0]
    lh, rh = y[:, FACE:FACE + HAND].copy(), y[:, FACE + HAND + POSE:].copy()
    y[:, FACE:FACE + HAND], y[:, FACE + HAND + POSE:] = rh, lh
    return y


def time_crop(x, frac_start, frac_end):
    n = len(x)
    a, b = int(n * frac_start), max(int(n * frac_end), int(n * frac_start) + 4)
    return x[a:b]


def scale(x, s):
    c = np.nanmean(x[:, NOSE, :2], axis=0)
    y = x.copy()
    y[..., :2] = (y[..., :2] - c) * s + c
    return y


def resample(x, factor):
    """Change the frame rate by linear interpolation in time (NaN stays NaN where either neighbour is NaN)."""
    n = len(x)
    m = max(4, int(round(n * factor)))
    src = np.linspace(0, n - 1, m)
    lo = np.floor(src).astype(int)
    hi = np.minimum(lo + 1, n - 1)
    w = (src - lo)[:, None, None]
    return x[lo] * (1 - w) + x[hi] * w


def portrait_crop(x, aspect=9 / 16, keep_frac=1.0):
    """Simulate a phone front camera: keep only a centred 9:16 window of the landscape frame (in
    normalized coords of a 16:9 frame, that is x within 0.5 +- aspect*keep/2 ... ); landmarks outside
    become NaN as the phone would not see them; then renormalize x so the window spans 0..1."""
    half = (aspect / (16 / 9)) * keep_frac / 2  # half-width of the window in landscape normalized x
    cx = float(np.nanmean(x[:, NOSE, 0]))
    y = x.copy()
    outside = (y[..., 0] < cx - half) | (y[..., 0] > cx + half)
    y[outside] = np.nan
    y[..., 0] = (y[..., 0] - (cx - half)) / (2 * half)
    return y


def tta(model, x):
    variants = [x, time_crop(x, 0.0, 0.85), time_crop(x, 0.15, 1.0), scale(x, 0.93), scale(x, 1.07), hflip(x)]
    return np.mean([model.probs(v) for v in variants], axis=0)


def describe(model, p, k=3):
    o = np.argsort(-p)[:k]
    return ", ".join(f"{model.glosses[i]} {p[i]:.2f}" for i in o)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--labels", type=Path, help="JSON {cut index: word} with inferred/true labels")
    args = ap.parse_args(argv)
    sdir = ART / "asl_probe" / "live" / args.session
    recs = json.loads((sdir / "records.json").read_text())["records"]
    labels = {int(k): v for k, v in json.loads(args.labels.read_text()).items()} if args.labels else {}
    model = Model()
    cuts = [(i, np.load(r["npy"]).astype(np.float32)) for i, r in enumerate(recs)]

    # latency
    t0 = time.perf_counter()
    for _, x in cuts[:20]:
        model.probs(x)
    per = (time.perf_counter() - t0) / 20
    t0 = time.perf_counter()
    for _, x in cuts[:10]:
        tta(model, x)
    per_tta = (time.perf_counter() - t0) / 10
    print(f"model latency on Mac CPU: {per * 1000:.1f} ms per cut plain, {per_tta * 1000:.1f} ms with 6-way TTA\n")

    rows = []
    for i, x in cuts:
        word = labels.get(i, "?")
        base, aug = model.probs(x), tta(model, x)
        phone = model.probs(portrait_crop(x))
        fps15, fps60 = model.probs(resample(x, 0.5)), model.probs(resample(x, 2.0))
        rows.append((i, word, base, aug, phone, fps15, fps60))

    print(f"{'#':>3} {'word':<9} {'plain':<34} {'TTA':<34} {'phone 9:16 crop':<34} {'15 fps':<22} {'60 fps'}")
    for i, word, base, aug, phone, f15, f60 in rows:
        print(f"{i:>3} {word:<9} {describe(model, base):<34} {describe(model, aug):<34} {describe(model, phone):<34} "
              f"{describe(model, f15, 2):<22} {describe(model, f60, 2)}")

    # per-word summary of the target probability
    if labels:
        print("\nper word: target probability, median over cuts (plain / TTA / phone crop / 15fps / 60fps), top-1 hit rate plain -> TTA")
        by = defaultdict(list)
        for row in rows:
            if row[1] in model.index:
                by[row[1]].append(row)
        for word, rs in by.items():
            t = model.index[word]
            med = lambda j: np.median([r[j][t] for r in rs])  # noqa: E731
            hit = lambda j: sum(int(np.argmax(r[j]) == t) for r in rs)  # noqa: E731
            print(f"  {word:<9} n={len(rs):<3} p: {med(2):.2f} / {med(3):.2f} / {med(4):.2f} / {med(5):.2f} / {med(6):.2f}   "
                  f"top-1: {hit(2)}/{len(rs)} -> {hit(3)}/{len(rs)}")

        # repeat accumulation: pairs of consecutive same-word cuts, average TTA probs
        print("\nrepeat-to-confirm: average of two consecutive attempts (TTA), target p and top-1")
        for word, rs in by.items():
            t = model.index[word]
            pairs = [(rs[k], rs[k + 1]) for k in range(len(rs) - 1)]
            if not pairs:
                continue
            ps = [((a[3] + b[3]) / 2) for a, b in pairs]
            hits = sum(int(np.argmax(p) == t) for p in ps)
            print(f"  {word:<9} pairs={len(ps):<3} median p {np.median([p[t] for p in ps]):.2f}, top-1 {hits}/{len(ps)}, "
                  f"min p {min(p[t] for p in ps):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
