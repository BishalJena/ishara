"""Run the pretrained INCLUDE model over labeled clips and report predictions + timing.

    .venv/bin/python eval_clips.py [--size large|small] [--clips artifacts/clips] [--device cpu|mps]

Expects <clips>/<label>/<file>.MOV; <label> is compared with the model's class name
after lowercasing and dropping non-letters (same normalisation as upstream).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import include_model as im
from include_features import LandmarkExtractor, frames_to_features, normalize_body, resample, video_to_frames


def norm(label: str) -> str:
    return "".join(c for c in label if c.isalpha()).lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="large", choices=list(im.CHECKPOINTS))
    ap.add_argument("--clips", default=str(im.ARTIFACTS / "clips"))
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--no-resample", action="store_true", help="skip 25 fps resampling")
    ap.add_argument("--normalize", action="store_true", help="map shoulders to the dataset's position/size first")
    ap.add_argument("--json", help="write per-clip results here")
    args = ap.parse_args()

    labels = im.load_labels()
    model = im.load_model(args.size, args.device)
    extractor = LandmarkExtractor()
    paths = sorted(p for p in Path(args.clips).rglob("*") if p.suffix.lower() in {".mov", ".mp4", ".m4v"})
    if not paths:
        raise SystemExit(f"no clips under {args.clips}; run fetch_clips.py or record some")

    rows, correct = [], 0
    print(f"{'clip':34} {'expected':10} {'top1':12} {'p':>5}  {'top3':40} {'frames':>6} {'lm ms':>6} {'nn ms':>6}")
    for p in paths:
        expected = norm(p.parent.name)
        t0 = time.perf_counter()
        frames, fps = video_to_frames(str(p), extractor)
        if not args.no_resample:
            frames = resample(frames, fps)
        if args.normalize:
            frames = normalize_body(frames)
        feats = frames_to_features(frames)
        t1 = time.perf_counter()
        top = im.predict(model, feats, labels, k=3)
        t2 = time.perf_counter()
        hit = top[0][0] == expected
        correct += hit
        top3 = ", ".join(f"{l}:{pr:.2f}" for l, pr in top)
        print(f"{str(p.relative_to(args.clips)):34} {expected:10} {top[0][0]:12} {top[0][1]:5.2f}  {top3:40} {len(frames):6d} {1000*(t1-t0):6.0f} {1000*(t2-t1):6.0f}")
        rows.append({"clip": str(p), "expected": expected, "top3": top, "n_frames": len(frames),
                     "src_fps": fps, "landmark_ms": 1000 * (t1 - t0), "model_ms": 1000 * (t2 - t1), "correct": hit})
    extractor.close()
    print(f"\ntop-1 correct: {correct}/{len(rows)}  (model={args.size}, device={args.device})")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
