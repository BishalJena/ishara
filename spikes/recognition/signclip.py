"""Frozen multilingual SignCLIP video embeddings; no training or remote inference.

Uses the pinned upstream pose preprocessing, MMBertForEncoder and forward_video.
The unused text encoder and optimizer are not instantiated.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "artifacts" / "signclip"
SOURCE = ASSETS / "source"
REVISION = "a819944093876443119f294a2c50c663cecd65b0"
CHECKPOINT = ASSETS / "baseline_temporal_checkpoint_best.pt"
CHECKPOINT_SHA = "a739751dd5b79a42f335725b4de4811c632f9f0cba616b74a8c8d87e55784df9"
BERT_REVISION = "cd5ef92a9fb2f889e972770a36d4ed042daf221e"
BERT_DIR = ASSETS / "bert-base-cased"
MAX_FRAMES = 256
CONTRACT = "signclip-multilingual:pose-format0.9:holistic0.10.21:complexity1:native:v1"


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def upstream():
    revision = subprocess.check_output(
        ["git", "-C", str(SOURCE), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(
        ["git", "-C", str(SOURCE), "diff", "--name-only", "HEAD"], text=True).strip()
    if revision != REVISION or dirty:
        raise RuntimeError("SignCLIP source must be unmodified at its pinned revision")
    directory = SOURCE / "examples" / "MMPT"
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
    from mmpt.models import MMBertForEncoder, MMFusionSeparate
    spec = importlib.util.spec_from_file_location("_ishara_signclip_demo", directory / "demo_sign.py")
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    return MMBertForEncoder, MMFusionSeparate, demo


def load_model():
    from transformers import BertConfig, AutoTokenizer

    if not CHECKPOINT_SHA or sha256(CHECKPOINT) != CHECKPOINT_SHA:
        raise RuntimeError("SignCLIP checkpoint has not passed its pinned checksum")
    encoder_cls, fusion_cls, _ = upstream()
    # Namespace is inert configuration metadata, not an executable model class.
    with torch.serialization.safe_globals([argparse.Namespace]):
        checkpoint = torch.load(CHECKPOINT, map_location="cpu", weights_only=True, mmap=True)
    state = checkpoint.get("model", checkpoint.get("state_dict", checkpoint))
    state = {k.removeprefix("mmmodel."): v for k, v in state.items()}
    video_state = {k.removeprefix("video_encoder."): v
                   for k, v in state.items() if k.startswith("video_encoder.")}
    if not video_state or any(k.startswith("video_projection.") for k in state):
        raise ValueError("Unexpected multilingual checkpoint architecture")
    config = BertConfig.from_pretrained(BERT_DIR, local_files_only=True)
    config.max_video_len = MAX_FRAMES
    config.num_hidden_layers = 12
    config.input_dim = 609
    config._attn_implementation = "eager"
    model = encoder_cls(config)
    # Older transformers serialized this deterministic buffer; 4.51 does not.
    # Verify its value before excluding it, rather than relaxing weight checks.
    positions = video_state.pop("bert.embeddings.position_ids", None)
    if positions is not None and not torch.equal(positions, model.bert.embeddings.position_ids):
        raise ValueError("Checkpoint positional IDs differ from the configured encoder")
    model.load_state_dict(video_state, strict=True)
    model.eval().requires_grad_(False)
    tokenizer = AutoTokenizer.from_pretrained(BERT_DIR, local_files_only=True)
    # Upstream Aligner uses CLS, SEP at the start of every caption, including "".
    caps = torch.tensor([[tokenizer.cls_token_id, tokenizer.sep_token_id]], dtype=torch.long)
    return SimpleNamespace(video_encoder=model, forward_video=fusion_cls.forward_video,
                           caps=caps, loaded_state_entries=len(video_state))


def extract(path, cache_dir=None):
    """Follow pose-format's native RGB extraction and upstream preprocessing.

    XY is in pixel units before normalization; Z follows pose-format unchanged.
    Long clips fail explicitly instead of silently cropping the intended sign.
    """
    import cv2
    import mediapipe as mp
    from pose_format.utils.holistic import load_holistic

    digest = sha256(path)
    key = hashlib.sha256(f"{digest}:{CONTRACT}:{REVISION}".encode()).hexdigest()
    cache = Path(cache_dir) / f"{key}.npz" if cache_dir else None
    if cache and cache.is_file():
        with np.load(cache, allow_pickle=False) as saved:
            return saved["features"], {**json.loads(str(saved["quality"])), "cache_hit": True}
    if mp.__version__ != "0.10.21":
        raise RuntimeError("Use the pinned SignCLIP extraction environment")
    cap = cv2.VideoCapture(str(path))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if not cap.isOpened() or not np.isfinite(fps) or fps <= 0 or min(width, height) <= 0:
        cap.release()
        raise ValueError("Cannot decode a video with valid dimensions and FPS")
    start = time.perf_counter()

    def frames():
        count = 0
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            count += 1
            if count > MAX_FRAMES:
                raise ValueError("SignCLIP limit is 256 frames; no silent truncation")
            yield cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    try:
        pose = load_holistic(frames(), fps=fps, width=width, height=height,
                             additional_holistic_config={"model_complexity": 1})
    finally:
        cap.release()
    confidence = pose.body.confidence[:, 0]
    if len(confidence) < 4:
        raise ValueError("Need at least four video frames")
    quality = {
        "source_sha256": digest, "extractor": CONTRACT, "frames": len(confidence),
        "fps": fps, "width": width, "height": height,
        "pose_fraction": float(np.mean(np.min(confidence[:, [11, 12]], axis=1) >= 0.5)),
        "hand_fraction": float(np.mean(np.any(confidence[:, 501:543] > 0, axis=1))),
        "face_fraction": float(np.mean(np.any(confidence[:, 33:501] > 0, axis=1))),
        "cache_hit": False,
    }
    if quality["pose_fraction"] == 0:
        raise ValueError("No tracked shoulders; cannot normalize SignCLIP input")
    _, _, demo = upstream()
    features = np.asarray(demo.preprocess_pose(pose)[0], dtype=np.float32)
    if features.shape != (len(confidence), 609) or not np.isfinite(features).all():
        raise ValueError("Invalid SignCLIP pose features")
    quality["landmark_ms"] = 1000 * (time.perf_counter() - start)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache, features=features, quality=json.dumps(quality))
    return features, quality


@torch.inference_mode()
def embed(model, features):
    features = np.asarray(features, dtype=np.float32)
    if (features.ndim != 2 or features.shape[1] != 609
            or not 4 <= len(features) <= MAX_FRAMES or not np.isfinite(features).all()):
        raise ValueError("Expected 4–256 finite frames of 609 SignCLIP features")
    padded = torch.zeros((1, MAX_FRAMES, 609))
    padded[0, :len(features)] = torch.from_numpy(features)
    mask = torch.arange(MAX_FRAMES)[None, :] < len(features)
    vector = model.forward_video(
        model, padded, mask, model.caps, torch.ones_like(model.caps, dtype=torch.bool)
    )[0].float().numpy()
    if vector.shape != (768,) or not np.isfinite(vector).all() or np.linalg.norm(vector) == 0:
        raise ValueError("SignCLIP returned an invalid embedding")
    return vector
