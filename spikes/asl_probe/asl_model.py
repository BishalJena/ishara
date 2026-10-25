"""Client for model_server.py plus the Kaggle landmark layout, importable from the MediaPipe venv.

    model = AslModel()                       # spawns the TFLite server in its own venv
    probs = model.predict(landmarks)         # [T, 543, 3] float32 with NaN -> 250 probabilities
    model.glosses[int(probs.argmax())]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "recognition" / "artifacts" / "asl_signs"
SERVER_PYTHON = ASSETS / ".venv" / "bin" / "python"
FACE, HAND, POSE = 468, 21, 33
POINTS = FACE + HAND + POSE + HAND  # 543, Kaggle order: face, left hand, pose, right hand


def kaggle_frame(result) -> np.ndarray:
    """One legacy-Holistic result -> [543, 3] in the Kaggle layout, NaN where a part is missing."""
    def part(landmarks, count):
        if landmarks is None:
            return np.full((count, 3), np.nan, dtype=np.float32)
        return np.array([[p.x, p.y, p.z] for p in landmarks.landmark], dtype=np.float32)
    return np.concatenate([part(result.face_landmarks, FACE), part(result.left_hand_landmarks, HAND),
                           part(result.pose_landmarks, POSE), part(result.right_hand_landmarks, HAND)])


def quality(landmarks: np.ndarray) -> dict[str, float]:
    """Fractions of frames with the body (shoulders) and with at least one hand tracked."""
    pose_ok = ~np.isnan(landmarks[:, FACE + HAND + 11:FACE + HAND + 13, 0]).any(axis=1)
    hands_ok = (~np.isnan(landmarks[:, FACE:FACE + HAND, 0]).any(axis=1)
                | ~np.isnan(landmarks[:, FACE + HAND + POSE:, 0]).any(axis=1))
    return {"pose_fraction": float(pose_ok.mean()), "hand_fraction": float(hands_ok.mean())}


class AslModel:
    def __init__(self) -> None:
        if not SERVER_PYTHON.exists():
            raise FileNotFoundError(f"{SERVER_PYTHON} missing: create it with python3 -m venv and pip install ai-edge-litert numpy")
        self.glosses: list[str] = [None] * 250
        for gloss, i in json.loads((ASSETS / "sign_to_prediction_index_map.json").read_text()).items():
            self.glosses[i] = gloss
        self.index = {g: i for i, g in enumerate(self.glosses)}
        self.proc = subprocess.Popen([str(SERVER_PYTHON), str(HERE / "model_server.py")], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=sys.stderr, bufsize=0)
        ready = json.loads(self.proc.stdout.readline())
        assert ready.get("ready"), ready

    def predict(self, landmarks: np.ndarray) -> np.ndarray:
        x = np.ascontiguousarray(landmarks, dtype="<f4")
        assert x.ndim == 3 and x.shape[1:] == (POINTS, 3), x.shape
        self.proc.stdin.write((json.dumps({"frames": int(x.shape[0])}) + "\n").encode())
        self.proc.stdin.write(x.tobytes())
        self.proc.stdin.flush()
        return np.array(json.loads(self.proc.stdout.readline())["probs"], dtype=np.float64)

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.stdin.close()
            self.proc.wait(timeout=5)
