"""MediaPipe landmark extraction matching INCLUDE's generate_keypoints.py + dataset.py.

Upstream used the legacy ``mp.solutions`` Hands + Pose with ``upper_body_only=True``
(25 body landmarks). That flag no longer exists; the full 33-point model shares
the same ordering for its first 25 points, so we slice. Everything else follows
upstream: hand slots assigned by MediaPipe order then swapped by wrist distance,
missing landmarks as NaN, linear interpolation over time (both directions), and
scaling to 1920x1080 pixel coordinates. Per frame: 25 pose + 21 + 21 hand points,
x and y each = 134 values.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import mediapipe as mp
import numpy as np
import pandas as pd

from include_model import FRAME_H, FRAME_W

POSE_POINTS, HAND_POINTS = 25, 21
TRAIN_FPS = 25.0
LEFT_WRIST, RIGHT_WRIST = 15, 16


class Frame:
    """Normalised (0-1) landmarks for one frame; NaN rows where nothing was detected."""

    __slots__ = ("pose", "hand1", "hand2", "t")

    def __init__(self, pose, hand1, hand2, t=0.0):
        self.pose, self.hand1, self.hand2, self.t = pose, hand1, hand2, t

    @property
    def hands_visible(self) -> int:
        return int(not np.isnan(self.hand1[0, 0])) + int(not np.isnan(self.hand2[0, 0]))

    @property
    def pose_visible(self) -> bool:
        return not np.isnan(self.pose[0, 0])


def _xy(landmarks, n):
    if landmarks is None:
        return np.full((n, 2), np.nan, dtype=np.float32)
    return np.array([[lm.x, lm.y] for lm in landmarks.landmark][:n], dtype=np.float32)


def _closer_to(hand_wrist, left_wrist, right_wrist) -> str:
    dl = np.sum((left_wrist - hand_wrist) ** 2)
    dr = np.sum((right_wrist - hand_wrist) ** 2)
    return "left" if dl < dr else "right"


class LandmarkExtractor:
    def __init__(self, detection=0.5, tracking=0.5, static_image_mode=False):
        self.hands = mp.solutions.hands.Hands(
            static_image_mode=static_image_mode,
            max_num_hands=2,
            min_detection_confidence=detection,
            min_tracking_confidence=tracking,
        )
        self.pose = mp.solutions.pose.Pose(
            static_image_mode=static_image_mode,
            min_detection_confidence=detection,
            min_tracking_confidence=tracking,
        )
        self.last_results = (None, None)
        self.pool = ThreadPoolExecutor(max_workers=2)  # hands and pose graphs run concurrently

    def close(self):
        self.pool.shutdown()
        self.hands.close()
        self.pose.close()

    def process(self, bgr) -> Frame:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        hf = self.pool.submit(self.hands.process, rgb)
        pr = self.pose.process(rgb)
        hr = hf.result()
        self.last_results = (hr, pr)

        pose = _xy(pr.pose_landmarks, POSE_POINTS)
        hands = hr.multi_hand_landmarks or []
        h1 = _xy(hands[0] if len(hands) > 0 else None, HAND_POINTS)
        h2 = _xy(hands[1] if len(hands) > 1 else None, HAND_POINTS)

        # Upstream: with exactly one hand, move it to slot 2 if it is nearer the right wrist
        # (slot 1 if nearer the left). Pose landmark 15 is the signer's left wrist.
        if len(hands) == 1 and pr.pose_landmarks is not None:
            side = _closer_to(h1[0], pose[LEFT_WRIST], pose[RIGHT_WRIST])
            if side == "right":
                h1, h2 = h2, h1
        return Frame(pose, h1, h2, time.monotonic())


def _interpolate(arr: np.ndarray) -> np.ndarray:
    """(T, N, 2) with NaNs -> filled and scaled to pixel coords, as in dataset.py."""
    out = np.empty_like(arr, dtype=np.float32)
    for axis, scale in ((0, FRAME_W), (1, FRAME_H)):
        df = pd.DataFrame(arr[:, :, axis].astype(np.float64))
        filled = df.interpolate(method="linear", limit_direction="both").to_numpy()
        if np.count_nonzero(~np.isnan(filled)) == 0:
            filled = np.zeros_like(filled)
        out[:, :, axis] = filled * scale
    return out


def frames_to_features(frames: list[Frame]) -> np.ndarray:
    """List of Frame -> (T, 134) float32 in the exact column order the model expects."""
    if not frames:
        return np.zeros((0, POSE_POINTS * 2 + HAND_POINTS * 4), dtype=np.float32)
    pose = _interpolate(np.stack([f.pose for f in frames]))
    h1 = _interpolate(np.stack([f.hand1 for f in frames]))
    h2 = _interpolate(np.stack([f.hand2 for f in frames]))
    return np.concatenate(
        [pose.reshape(len(frames), -1), h1.reshape(len(frames), -1), h2.reshape(len(frames), -1)],
        axis=1,
    ).astype(np.float32)


# Measured over 11 INCLUDE test clips (normalised coords): shoulder midpoint and
# shoulder width are nearly constant because every signer stood on the same mark.
DATASET_SHOULDER_MID = np.array([0.499, 0.378], dtype=np.float32)
DATASET_SHOULDER_WIDTH = 0.138
L_SHOULDER, R_SHOULDER = 11, 12


def normalize_body(frames: list[Frame], mid=DATASET_SHOULDER_MID, width=DATASET_SHOULDER_WIDTH) -> list[Frame]:
    """Translate/scale a segment so its median shoulder line matches the dataset's.

    One similarity transform per segment (not per frame), so the signer's own motion is
    kept and only camera distance/position is removed. Returns new Frame objects.
    """
    if not frames:
        return frames
    pose = np.stack([f.pose for f in frames])
    seg_mid = np.nanmedian((pose[:, L_SHOULDER] + pose[:, R_SHOULDER]) / 2, axis=0)
    seg_width = np.nanmedian(np.linalg.norm(pose[:, L_SHOULDER] - pose[:, R_SHOULDER], axis=1))
    if np.any(np.isnan(seg_mid)) or not seg_width or np.isnan(seg_width):
        return frames
    s = width / seg_width

    def tf(a):
        return ((a - seg_mid) * s + mid).astype(np.float32)

    return [Frame(tf(f.pose), tf(f.hand1), tf(f.hand2), f.t) for f in frames]


def resample(frames: list[Frame], src_fps: float, dst_fps: float = TRAIN_FPS) -> list[Frame]:
    """Pick frames so a sequence captured at src_fps approximates dst_fps (nearest index)."""
    if not frames or src_fps <= 0 or abs(src_fps - dst_fps) < 0.5:
        return frames
    n_out = max(1, int(round(len(frames) * dst_fps / src_fps)))
    idx = np.round(np.linspace(0, len(frames) - 1, n_out)).astype(int)
    return [frames[i] for i in idx]


def video_to_frames(path: str, extractor: LandmarkExtractor | None = None) -> tuple[list[Frame], float]:
    own = extractor is None
    extractor = extractor or LandmarkExtractor()
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or TRAIN_FPS
    frames = []
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        frames.append(extractor.process(bgr))
    cap.release()
    if own:
        extractor.close()
    return frames, fps
