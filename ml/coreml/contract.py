"""Core ML I/O contract for SignCLIPEncoder.mlpackage (pure numpy, no model needed).

Inputs: features Float32 [1, 256, 609] (SignCLIP-normalized pose frames, zero-padded
at the end) and mask Float32 [1, 256] (1 = real frame). Output: embedding Float32
[1, 768], raw; consumers L2-normalize. Long clips are rejected, never truncated.
"""
from __future__ import annotations

import numpy as np

MAX_FRAMES = 256
FEATURE_DIM = 609
EMBEDDING_DIM = 768
# Mirrors spikes/recognition/signclip.embed, which refuses fewer than four frames.
MIN_FRAMES = 4


def pad(features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (features [1, 256, 609], mask [1, 256]) as float32 model inputs."""
    features = np.asarray(features, dtype=np.float32)
    if features.ndim != 2 or features.shape[1] != FEATURE_DIM:
        raise ValueError(f"Expected [frames, {FEATURE_DIM}] SignCLIP features, got {features.shape}")
    frames = len(features)
    if frames > MAX_FRAMES:
        raise ValueError(f"{frames} frames exceeds the {MAX_FRAMES}-frame limit; no truncation")
    if frames < MIN_FRAMES:
        raise ValueError(f"Need at least {MIN_FRAMES} frames, got {frames}")
    if not np.isfinite(features).all():
        raise ValueError("SignCLIP features must be finite")
    padded = np.zeros((1, MAX_FRAMES, FEATURE_DIM), dtype=np.float32)
    padded[0, :frames] = features
    mask = np.zeros((1, MAX_FRAMES), dtype=np.float32)
    mask[0, :frames] = 1
    return padded, mask


def unit(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float64).reshape(-1)
    norm = np.linalg.norm(vector)
    if not np.isfinite(vector).all() or norm == 0:
        raise ValueError("Embedding must be a finite nonzero vector")
    return vector / norm


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(unit(a), unit(b)))
