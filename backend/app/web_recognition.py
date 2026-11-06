"""The unchanged ASL model for browser-extracted landmarks, never camera images.

The interpreter is optional and lazy. HTTP work runs off the call event loop and
one lock owns its dynamic input tensor. No uploaded coordinates are saved.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
from pathlib import Path

BUNDLE_PATH = Path(__file__).resolve().parents[1] / "recognition" / "asl-bundle.json"
VALUES_PER_FRAME = 543 * 3
MAX_FRAMES = 64
MAX_BYTES = MAX_FRAMES * VALUES_PER_FRAME * 4


def load_bundle() -> dict:
    return json.loads(BUNDLE_PATH.read_text())


def decision(logits: list[float], bundle: dict) -> dict:
    if len(logits) != len(bundle["glosses"]) or not all(math.isfinite(x) for x in logits):
        return {"kind": "unsure", "reason": "The sign could not be read."}
    # Rank the full model before checking vocabulary. Never renormalize a subset.
    maximum = max(logits)
    weights = [math.exp(x - maximum) for x in logits]
    total = sum(weights)
    ranked = sorted(range(len(weights)), key=lambda i: weights[i], reverse=True)
    first, second = ranked[:2]
    p = weights[first] / total
    margin = p - weights[second] / total
    gloss = bundle["glosses"][first]
    result = {"kind": "unsure", "p": p, "margin": margin, "provisional": True}
    if gloss not in bundle["vocabulary"]:
        return {**result, "reason": "That sign is outside this demo's vocabulary."}
    # Review choices come from the original full-model top three, never a
    # vocabulary-only softmax. They require a tap and never become automatic chips.
    result["suggestions"] = [
        bundle["glosses"][index]
        for index in ranked[:3]
        if bundle["glosses"][index] in bundle["vocabulary"]
    ]
    thresholds = bundle["thresholds"]
    cutoff = bundle.get("per_word", {}).get(gloss, thresholds["p"])
    if p >= cutoff and margin >= thresholds["margin"]:
        return {**result, "kind": "chip", "gloss": gloss}
    if p >= thresholds["pick_one_p"]:
        return {**result, "kind": "candidate", "gloss": gloss}
    return {**result, "reason": "Not sure. Please try that sign again."}


class ASLRecognizer:
    def __init__(self, path: str | None) -> None:
        self.path = Path(path) if path else None
        self._interpreter = None
        self._lock = threading.Lock()
        self.bundle = load_bundle()

    @property
    def available(self) -> bool:
        if self.path is None or not self.path.is_file():
            return False
        import importlib.util

        return importlib.util.find_spec("ai_edge_litert") is not None

    def recognize(self, raw: bytes) -> dict:
        import numpy as np

        if not raw or len(raw) > MAX_BYTES or len(raw) % (VALUES_PER_FRAME * 4):
            raise ValueError("invalid clip size")
        frames = len(raw) // (VALUES_PER_FRAME * 4)
        if frames < 6:
            return {"kind": "unsure", "reason": "Record one complete sign, then finish."}
        points = np.frombuffer(raw, dtype="<f4").reshape(frames, 543, 3)
        if np.isinf(points).any():
            raise ValueError("invalid coordinates")
        quality = self.bundle["quality"]
        pose = np.isfinite(points[:, [500, 501], :2]).all(axis=(1, 2)).mean()
        left = np.isfinite(points[:, 468:489, :2]).all(axis=(1, 2))
        right = np.isfinite(points[:, 522:543, :2]).all(axis=(1, 2))
        if (
            pose < quality["min_pose_fraction"]
            or (left | right).mean() < quality["min_hand_fraction"]
        ):
            return {
                "kind": "unsure",
                "reason": "Keep your shoulders and hands visible, then try again.",
            }
        # A participating hand leaving the image while raised invalidates the clip.
        for tracked, wrist in [(left, 504), (right, 505)]:
            outside = (
                ~tracked
                & (points[:, wrist, 1] < 0.85)
                & (
                    (points[:, wrist, 0] < 0.02)
                    | (points[:, wrist, 0] > 0.98)
                    | (points[:, wrist, 1] < 0.02)
                )
            )
            run = 0
            for out in outside:
                run = run + 1 if out else 0
                if tracked.any() and run >= 4:
                    return {
                        "kind": "unsure",
                        "reason": "A hand left the picture. Keep it inside the frame.",
                    }
        with self._lock:
            if self._interpreter is None:
                if not self.available:
                    raise RuntimeError("recognition not installed")
                if (
                    hashlib.sha256(self.path.read_bytes()).hexdigest()
                    != self.bundle["model"]["sha256"]
                ):
                    raise RuntimeError("model checksum mismatch")
                from ai_edge_litert.interpreter import Interpreter

                self._interpreter = Interpreter(model_path=str(self.path), num_threads=2)
            interpreter = self._interpreter
            input_index = interpreter.get_input_details()[0]["index"]
            interpreter.resize_tensor_input(input_index, [frames, 543, 3])
            interpreter.allocate_tensors()
            interpreter.set_tensor(input_index, points.copy())
            interpreter.invoke()
            output = interpreter.get_tensor(interpreter.get_output_details()[0]["index"])
            return decision(output.reshape(-1).tolist(), self.bundle)
