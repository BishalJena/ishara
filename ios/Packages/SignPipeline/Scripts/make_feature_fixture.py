"""Write golden SignCLIP feature vectors for the Swift FeatureBuilder tests.

Runs the same Python path as spikes/recognition/signclip.py `extract`, minus the
camera: pose-format 0.9.0 `load_holistic` assembles the Holistic results and the
pinned upstream `demo_sign.preprocess_pose` normalizes them. Only the MediaPipe
Holistic graph is replaced by scripted synthetic landmarks, so no video, model
weights or SignCLIP checkpoint are needed.

`demo_sign.py` imports the full SignCLIP model package at module level, so the
four preprocessing definitions are taken verbatim from the pinned file (checksum
verified) and executed without that import.

Environment (Python 3.11, versions pinned in spikes/recognition/requirements-signclip.txt):

    uv venv --python 3.11 /tmp/signpipeline-fixture
    uv pip install --python /tmp/signpipeline-fixture/bin/python \
        pose-format==0.9.0 mediapipe==0.10.21 numpy==1.26.4 torch==2.14.1
    /tmp/signpipeline-fixture/bin/python Scripts/make_feature_fixture.py
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import numpy as np
import torch
from pose_format.utils import holistic

REVISION = "a819944093876443119f294a2c50c663cecd65b0"
DEMO_URL = f"https://raw.githubusercontent.com/J22Melody/fairseq/{REVISION}/examples/MMPT/demo_sign.py"
DEMO_SHA = "9e208dcf9ffbe2ef284d6c2bed3b4d461d95e6c254682e9c5c1c68d3fe2f9d8e"
UPSTREAM_NAMES = {"FACEMESH_CONTOURS_POINTS", "pose_normalization_info", "pose_hide_legs", "preprocess_pose"}
OUTPUT = Path(__file__).resolve().parent.parent / "Tests" / "SignPipelineTests" / "Resources" / "feature_fixture.json"
MIN_TRACKED_SHOULDER_VISIBILITY = 0.5  # signclip.py `pose_fraction`


def upstream_preprocessing(source: bytes) -> dict:
    if hashlib.sha256(source).hexdigest() != DEMO_SHA:
        raise RuntimeError("demo_sign.py does not match the pinned SignCLIP revision")
    def defined_name(node):
        if isinstance(node, ast.FunctionDef):
            return node.name
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            return node.targets[0].id
        return None

    nodes = [node for node in ast.parse(source).body if defined_name(node) in UPSTREAM_NAMES]
    if {defined_name(node) for node in nodes} != UPSTREAM_NAMES:
        raise RuntimeError("Pinned demo_sign.py lacks an expected preprocessing definition")
    namespace = {"np": np, "torch": torch}
    # Runs only the four definitions above from the checksum-pinned upstream file.
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "demo_sign.py", "exec"), namespace)  # noqa: S102
    if namespace["FACEMESH_CONTOURS_POINTS"] != holistic.FACEMESH_CONTOURS_POINTS:
        raise RuntimeError("Upstream face contour list differs from MediaPipe 0.10.21")
    return namespace


class ScriptedHolistic:
    """Stands in for mp.solutions.holistic.Holistic and replays synthetic results."""

    script: ClassVar[list] = []

    def __init__(self, **config):
        if config.get("model_complexity") != 1:
            raise RuntimeError("signclip.py extracts with model_complexity=1")
        self.results = iter(type(self).script)

    def process(self, _frame):
        return next(self.results)

    def close(self):
        pass


def landmark_list(points, with_visibility):
    if points is None:
        return None
    return SimpleNamespace(landmark=[
        SimpleNamespace(x=float(p[0]), y=float(p[1]), z=float(p[2]),
                        visibility=float(p[3]) if with_visibility else 0.0)
        for p in points])


def f32(rng, low, high, shape):
    return rng.uniform(low, high, size=shape).astype(np.float32)


def person(rng):
    """Plausible upright signer: shoulders near mid-frame, hands in front of the chest."""
    pose = np.concatenate([f32(rng, 0.25, 0.75, (33, 2)), f32(rng, -0.6, 0.2, (33, 1)),
                           f32(rng, 0.55, 1.0, (33, 1))], axis=1)
    pose[11, :2] = (0.62 + rng.uniform(-0.02, 0.02), 0.55 + rng.uniform(-0.02, 0.02))  # LEFT_SHOULDER
    pose[12, :2] = (0.38 + rng.uniform(-0.02, 0.02), 0.56 + rng.uniform(-0.02, 0.02))  # RIGHT_SHOULDER
    face = np.concatenate([f32(rng, 0.42, 0.58, (468, 2)), f32(rng, -0.05, 0.05, (468, 1))], axis=1)
    hands = [np.concatenate([f32(rng, low, low + 0.15, (21, 1)), f32(rng, 0.45, 0.7, (21, 1)),
                             f32(rng, -0.1, 0.0, (21, 1))], axis=1) for low in (0.55, 0.3)]
    return {"pose": pose, "face": face, "left_hand": hands[0], "right_hand": hands[1]}


def full_tracking(rng):
    return [person(rng) for _ in range(5)]


def missing_parts(rng):
    frames = [person(rng) for _ in range(8)]
    frames[1]["left_hand"] = None
    frames[2]["right_hand"] = None
    frames[3]["face"] = None
    frames[4]["pose"] = None  # no person: excluded from the shoulder statistics
    frames[5]["left_hand"] = frames[5]["right_hand"] = None
    frames[6]["pose"][7, 3] = 0.0  # zero-visibility landmark stays masked (raw pixels)
    frames[6]["pose"][12, 3] = 0.0  # masked shoulder: frame drops out of centring and scale
    frames[7]["pose"][11, 3] = 0.3  # weakly visible shoulder still counts for normalization
    return frames


def no_tracked_shoulders(rng):
    frames = [person(rng) for _ in range(4)]
    for frame in frames:
        frame["pose"][11, 3] = 0.4
    return frames


CASES = [
    ("full_tracking_landscape", 1280, 720, full_tracking),
    ("missing_parts_portrait", 720, 1280, missing_parts),
    ("no_tracked_shoulders", 640, 480, no_tracked_shoulders),
]


def run_case(upstream, frames, width, height):
    ScriptedHolistic.script = [SimpleNamespace(
        pose_landmarks=landmark_list(f["pose"], True),
        face_landmarks=landmark_list(f["face"], False),
        left_hand_landmarks=landmark_list(f["left_hand"], False),
        right_hand_landmarks=landmark_list(f["right_hand"], False),
        pose_world_landmarks=landmark_list(f["pose"], True),
    ) for f in frames]
    holistic.mp_holistic.Holistic = ScriptedHolistic
    pose = holistic.load_holistic(range(len(frames)), fps=30.0, width=width, height=height,
                                  additional_holistic_config={"model_complexity": 1})
    confidence = pose.body.confidence[:, 0]
    if np.mean(np.min(confidence[:, [11, 12]], axis=1) >= MIN_TRACKED_SHOULDER_VISIBILITY) == 0:
        return None
    features = np.asarray(upstream["preprocess_pose"](pose)[0], dtype=np.float32)
    if features.shape != (len(frames), 609) or not np.isfinite(features).all():
        raise RuntimeError("Unexpected SignCLIP feature shape")
    return features


def shortest(values):
    """Shortest float32 round-trip literals keep the fixture small and exact."""
    return [float(np.format_float_scientific(np.float32(v), unique=True)) for v in values]


def encode_part(points, columns):
    return None if points is None else [shortest(p[:columns]) for p in points]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--demo-sign", type=Path, help="Local copy of the pinned demo_sign.py")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    source = args.demo_sign.read_bytes() if args.demo_sign else urllib.request.urlopen(DEMO_URL).read()
    upstream = upstream_preprocessing(source)
    rng = np.random.default_rng(20261027)
    cases = []
    for name, width, height, build in CASES:
        frames = build(rng)
        features = run_case(upstream, frames, width, height)
        cases.append({
            "name": name, "width": width, "height": height,
            "frames": [{"pose": encode_part(f["pose"], 4), "face": encode_part(f["face"], 3),
                        "leftHand": encode_part(f["left_hand"], 3),
                        "rightHand": encode_part(f["right_hand"], 3)} for f in frames],
            "expected": None if features is None else [shortest(row) for row in features],
            "expectedError": "noTrackedShoulders" if features is None else None,
        })
    fixture = {"source": {"signclip_revision": REVISION, "demo_sign_sha256": DEMO_SHA,
                          "pose_format": "0.9.0", "mediapipe": holistic.mp.__version__},
               "cases": cases}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(fixture, separators=(",", ":")) + "\n")
    print(f"Wrote {len(cases)} cases to {args.output}")


if __name__ == "__main__":
    main()
