"""Tiny stdin/stdout server around the ASL Signs 1st-place TFLite (run by asl_model.AslModel).

Runs in artifacts/asl_signs/.venv (ai-edge-litert), so the MediaPipe venv never has to
import TensorFlow. Protocol, one request at a time:

    -> one JSON line  {"frames": T}
    -> T * 543 * 3 float32 little-endian bytes (Kaggle layout, NaN for missing points)
    <- one JSON line  {"probs": [250 softmax values]}

Started by asl_model.AslModel; not meant to be run by hand.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from ai_edge_litert.interpreter import Interpreter

ASSETS = Path(__file__).resolve().parent / "artifacts" / "asl_signs"
POINTS, COORDS = 543, 3


def main() -> int:
    interpreter = Interpreter(model_path=str(ASSETS / "model.tflite"))
    run = interpreter.get_signature_runner("serving_default")
    stdin, stdout = sys.stdin.buffer, sys.stdout
    stdout.write(json.dumps({"ready": True}) + "\n")
    stdout.flush()
    while True:
        header = stdin.readline()
        if not header:
            return 0
        frames = int(json.loads(header)["frames"])
        raw = stdin.read(frames * POINTS * COORDS * 4)
        x = np.frombuffer(raw, dtype="<f4").reshape(frames, POINTS, COORDS).astype(np.float32)
        logits = run(inputs=x)["outputs"].astype(np.float64)
        z = logits - logits.max()
        probs = np.exp(z) / np.exp(z).sum()
        stdout.write(json.dumps({"probs": [round(float(p), 6) for p in probs]}) + "\n")
        stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
