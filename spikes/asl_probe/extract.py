"""Legacy MediaPipe Holistic landmarks for whole clips, in the Kaggle ASL Signs layout.

Run with spikes/recognition/.venv (mediapipe 0.10.21). Writes one .npz per clip with
`landmarks` of shape [T, 543, 3] (x, y normalized to the image, z as MediaPipe gives it;
NaN where a part was not detected), plus fps, width, height. Row order per frame follows
the Kaggle competition parquet files: face (468), left_hand (21), pose (33), right_hand (21).

    .venv/bin/python ../asl_probe/extract.py --manifest artifacts/asl_probe/manifest.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np

FACE, HAND, POSE = 468, 21, 33
TOTAL = FACE + HAND + POSE + HAND  # 543


def part(landmarks, count: int) -> np.ndarray:
    if landmarks is None:
        return np.full((count, 3), np.nan, dtype=np.float32)
    return np.array([[p.x, p.y, p.z] for p in landmarks.landmark], dtype=np.float32)


def extract(video: Path, holistic) -> dict:
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frames = []
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        res = holistic.process(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        frames.append(np.concatenate([part(res.face_landmarks, FACE), part(res.left_hand_landmarks, HAND),
                                      part(res.pose_landmarks, POSE), part(res.right_hand_landmarks, HAND)]))
    cap.release()
    arr = np.stack(frames) if frames else np.zeros((0, TOTAL, 3), np.float32)
    return {"landmarks": arr, "fps": fps, "width": width, "height": height}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, required=True,
                        help="JSON list of {id, path, label, source}; .npz written next to the manifest under landmarks/")
    parser.add_argument("--complexity", type=int, default=1)
    args = parser.parse_args(argv)
    rows = json.loads(args.manifest.read_text())
    out_dir = args.manifest.parent / "landmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    with mp.solutions.holistic.Holistic(static_image_mode=False, model_complexity=args.complexity,
                                        refine_face_landmarks=False) as holistic:
        for i, row in enumerate(rows, 1):
            dest = out_dir / f"{row['id']}.npz"
            if dest.exists():
                continue
            data = extract(Path(row["path"]), holistic)
            lm = data["landmarks"]
            hands = float(np.mean(~np.isnan(lm[:, FACE:FACE + HAND, 0]).any(axis=1)
                                  | ~np.isnan(lm[:, FACE + HAND + POSE:, 0]).any(axis=1))) if len(lm) else 0.0
            np.savez_compressed(dest, **data)
            print(f"[{i}/{len(rows)}] {row['id']} {row['label']:<10} T={len(lm):>4} fps={data['fps']:.1f} "
                  f"{data['width']}x{data['height']} hands_seen={hands:.2f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
