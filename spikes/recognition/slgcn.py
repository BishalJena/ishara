"""Pinned OpenHands SL-GCN inference, using upstream modules without its trainer.

Source: AI4Bharat/OpenHands, Apache-2.0, at SOURCE_REVISION below.
The graph, decoder, and transforms are imported unchanged from the local clone.
"""
from __future__ import annotations

import csv
import hashlib
import importlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import time
import types
import zipfile
from pathlib import Path

import numpy as np
import torch
from omegaconf import OmegaConf

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"
SOURCE_REVISION = "b9ccf9eaf2a71301fc4601a64a6af06fdef04c9b"
SOURCE = ARTIFACTS / "OpenHands"
ARCHIVE_SHA = "0aa8eb27091dff71e5ae721a648a7410abb827c495731d3da43c55f195757a52"
METADATA_SHA = "f4d229aaf56cc85266feb9d8526407513382113294dbe75fc3772f881d0fc6e3"
CHECKPOINT_MEMBER = "include/sl_gcn/epoch=112-step=12203.ckpt"
# Diagnostic rules chosen before the first clip run; NOT calibrated reliability.
SUPPORTED = frozenset({"hello", "thankyou", "doctor", "hospital", "location", "today", "tomorrow"})
POLICY = {"score": 0.5, "margin": 0.15, "pose_fraction": 0.6, "hand_fraction": 0.2}


def canonical(label: str) -> str:
    return re.sub("[^a-z]", "", label.lower())


def checked_archive(name: str, expected_sha: str) -> zipfile.ZipFile:
    path = ARTIFACTS / name
    if not path.is_file():
        raise RuntimeError("Missing model assets. Run: .venv/bin/python setup_mini.py")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
        raise ValueError(f"Checksum mismatch: {name}")
    return zipfile.ZipFile(path)


def source_module(name: str, relative_path: str):
    """Load a single dependency-free upstream module, not the training package."""
    spec = importlib.util.spec_from_file_location(name, SOURCE / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _CheckpointMetadata:
    """Inert marker for an unused Lightning callback dictionary key."""


class _EarlyStoppingMetadata:
    """Inert marker for an unused Lightning callback dictionary key."""


def load_model():
    revision = subprocess.check_output(
        ["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "-C", str(SOURCE), "diff", "--name-only", "HEAD", "--", "openhands"],
        text=True,
    ).strip()
    if revision != SOURCE_REVISION or dirty:
        raise RuntimeError("OpenHands source must be unmodified at the pinned revision")

    # Relative imports in the graph work under a private namespace, without
    # importing Lightning, torchvision, Hydra, or training integrations.
    namespace = "_ishara_openhands_graph"
    if namespace not in sys.modules:
        package = types.ModuleType(namespace)
        package.__path__ = [str(SOURCE / "openhands/models/encoder/graph")]
        sys.modules[namespace] = package
    graph = importlib.import_module(namespace + ".decoupled_gcn")
    fc = source_module("_ishara_fc", "openhands/models/decoder/fc.py")
    network = source_module("_ishara_network", "openhands/models/network.py")
    with checked_archive("include_metadata.zip", METADATA_SHA) as archive:
        rows = csv.DictReader(io.StringIO(
            archive.read("Train_Test_Split/train_include.csv").decode()
        ))
        # Sorting happens BEFORE stripping the numeric prefixes in upstream.
        glosses = sorted({row["Word"] for row in rows})
    labels = [re.sub(r"^\d+\.", "", g).strip() for g in glosses]
    with checked_archive("include_slgcn.zip", ARCHIVE_SHA) as archive:
        config = OmegaConf.create(archive.read("include/sl_gcn/config.yaml").decode())
        checkpoint_bytes = io.BytesIO(archive.read(CHECKPOINT_MEMBER))
        # Only these inert metadata keys are allowlisted; never run pickle code
        # from Lightning. Network tensors are loaded with strict shape/key checks.
        with torch.serialization.safe_globals([
            (_CheckpointMetadata, "pytorch_lightning.callbacks.model_checkpoint.ModelCheckpoint"),
            (_EarlyStoppingMetadata, "pytorch_lightning.callbacks.early_stopping.EarlyStopping"),
        ]):
            checkpoint = torch.load(checkpoint_bytes, weights_only=True, map_location="cpu")
    encoder = graph.DecoupledGCN(in_channels=2, **config.model.encoder.params)
    decoder = fc.FC(n_features=encoder.n_out_features, num_class=len(labels),
                    **config.model.decoder.params)
    model = network.Network(encoder, decoder)
    state = checkpoint["state_dict"]
    if len(labels) != 263 or not all(k.startswith("model.") for k in state):
        raise ValueError("Unexpected checkpoint architecture or label inventory")
    model.load_state_dict({k.removeprefix("model."): v for k, v in state.items()}, strict=True)
    model.eval().requires_grad_(False)
    return model, labels


def features(keypoints: np.ndarray) -> torch.Tensor:
    """Use the exact published evaluation transforms; no post-hoc interpolation."""
    if keypoints.ndim != 3 or keypoints.shape[1:] != (75, 3):
        raise ValueError("Expected (frames, 75, 3) holistic coordinates")
    if not 4 <= len(keypoints) <= 600 or not np.isfinite(keypoints).all():
        raise ValueError("Clip must have 4–600 finite frames")
    transforms = source_module("_ishara_transforms", "openhands/datasets/pose_transforms.py")
    data = {"frames": torch.tensor(keypoints[:, :, :2], dtype=torch.float32).permute(2, 0, 1)}
    data = transforms.PoseSelect(preset="mediapipe_holistic_minimal_27")(data)
    data = transforms.CenterAndScaleNormalize(
        reference_points_preset="shoulder_mediapipe_holistic_minimal_27"
    )(data)
    return data["frames"].unsqueeze(0)


@torch.inference_mode()
def predict(model, labels: list[str], keypoints: np.ndarray, k=5) -> list[dict]:
    probabilities = model(features(keypoints)).softmax(dim=-1)[0]
    if not torch.isfinite(probabilities).all():
        raise ValueError("Model returned non-finite probabilities")
    scores, indices = probabilities.topk(k)
    return [{"label": labels[i], "concept": canonical(labels[i]), "score": float(score),
             "class_id": int(i)} for score, i in zip(scores, indices)]


def extract(path: Path, cache_dir: Path | None = None):
    """Upstream Holistic complexity=2, native frames, missing landmarks as zero.

    We retain XYZ plus visibility for inspection; the checkpoint consumes only XY.
    Each clip gets a fresh tracker. Face points are discarded, exactly as upstream.
    """
    import cv2
    import mediapipe as mp

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    contract = f"{digest}:holistic:{mp.__version__}:complexity2:native-frames:v1"
    cache = cache_dir / (hashlib.sha256(contract.encode()).hexdigest() + ".npz") if cache_dir else None
    if cache and cache.is_file():
        with np.load(cache, allow_pickle=False) as saved:
            stats = json.loads(str(saved["stats"]))
            return saved["keypoints"], {**stats, "cache_hit": True}
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        cap.release()
        raise ValueError("Cannot decode the video")
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    if not np.isfinite(fps) or fps <= 0:
        cap.release()
        raise ValueError("Video has no valid frame rate")
    rows, poses, hands, both = [], [], [], []
    start = time.perf_counter()
    try:
        with mp.solutions.holistic.Holistic(static_image_mode=False, model_complexity=2) as holistic:
            while True:
                ok, bgr = cap.read()
                if not ok:
                    break
                if len(rows) >= 600:
                    raise ValueError("Prototype limit: 600 frames per clip; no silent truncation")
                result = holistic.process(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                components = [(result.pose_landmarks, 33),
                              (result.left_hand_landmarks, 21),
                              (result.right_hand_landmarks, 21)]
                rows.append(np.concatenate([
                    np.array([[p.x, p.y, p.z] for p in item.landmark], dtype=np.float32)
                    if item else np.zeros((count, 3), np.float32)
                    for item, count in components
                ]))
                poses.append(bool(result.pose_landmarks and
                                  min(result.pose_landmarks.landmark[i].visibility for i in (11, 12)) >= 0.5))
                hands.append(bool(result.left_hand_landmarks or result.right_hand_landmarks))
                both.append(bool(result.left_hand_landmarks and result.right_hand_landmarks))
    finally:
        cap.release()
    if len(rows) < 4:
        raise ValueError("Video must contain at least four decoded frames")
    keypoints = np.stack(rows)
    stats = {
        "source_sha256": digest, "extractor": contract.split(":", 1)[1],
        "frames": len(rows), "fps": fps, "duration_s": len(rows) / fps,
        "pose_fraction": float(np.mean(poses)), "hand_fraction": float(np.mean(hands)),
        "both_hand_fraction": float(np.mean(both)),
        "landmark_ms": 1000 * (time.perf_counter() - start), "cache_hit": False,
    }
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache, keypoints=keypoints, stats=json.dumps(stats))
    return keypoints, stats


def decision(top: list[dict], quality: dict) -> dict:
    """Gate the full 263-class winner, never renormalize a supported-only subset."""
    reasons = []
    if top[0]["concept"] not in SUPPORTED:
        reasons.append("top prediction is outside this prototype's supported meanings")
    if top[0]["score"] < POLICY["score"]:
        reasons.append("score below the experimental threshold")
    if top[0]["score"] - top[1]["score"] < POLICY["margin"]:
        reasons.append("competing predictions are too close")
    for field in ("pose_fraction", "hand_fraction"):
        if quality[field] < POLICY[field]:
            reasons.append(f"insufficient {field.replace('_fraction', '')} tracking")
    return {"status": "abstain" if reasons else "candidate",
            "concept": None if reasons else top[0]["concept"], "reasons": reasons}


def analyze(model, labels, path: Path, cache_dir: Path | None = None) -> dict:
    keypoints, quality = extract(path, cache_dir)
    start = time.perf_counter()
    top = predict(model, labels, keypoints)
    model_ms = 1000 * (time.perf_counter() - start)
    return {"top5": top, "quality": quality, "model_ms": model_ms,
            "decision": decision(top, quality)}
