"""Find and remove burned-in text (dictionary videos often caption the word) before Gemini sees a clip.

Apple Vision (VNRecognizeTextRequest, accurate level) reads every decoded frame. Every
place where text shows up in any frame is pixelated in every frame (captions are static
overlays), the clip is re-encoded and every frame is read again. Text found on the
re-read is added and the original frames are blurred again, up to ROUNDS times; a clip
that still shows text, or whose text regions cover too much of the picture, is dropped.

Readable text means Vision's confidence is at least MIN_CONFIDENCE, or, at any
confidence, a whole token is one of the candidate words. On the INCLUDE studio clips
Vision's lowest bucket (0.3) is texture noise (window blinds, checked shirts read as
'ВЕҐ2Q5.'), while every caption and watermark in the YouTube clips reads at 1.0.
"""
from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

MIN_CONFIDENCE = 0.5
MAX_COVER = 0.25  # text regions together larger than this share of the frame -> drop, not blur
PAD = 0.02  # pad each box by this share of the frame on every side
MOSAIC = 24  # pixels per mosaic block
ROUNDS = 3  # blur, re-read, blur again with the new boxes; then give up and drop

Box = tuple[float, float, float, float]  # x0, y0, x1, y1 normalized, origin top-left


@dataclass(frozen=True)
class TextBox:
    text: str
    confidence: float
    box: Box


def frames(path: Path) -> Iterator[np.ndarray]:
    capture = cv2.VideoCapture(str(path))
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                return
            yield frame
    finally:
        capture.release()


def read_text(frame: np.ndarray) -> list[TextBox]:
    """Text Apple Vision finds in one BGR frame (macOS only)."""
    import Vision
    from Foundation import NSData

    ok, png = cv2.imencode(".png", frame)
    if not ok:
        raise ValueError("Cannot encode frame for OCR")
    handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(
        NSData.dataWithBytes_length_(png.tobytes(), len(png)), None)
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(False)
    success, error = handler.performRequests_error_([request], None)
    if not success:
        raise RuntimeError(f"Vision OCR failed: {error}")
    boxes = []
    for observation in request.results() or []:
        candidate = observation.topCandidates_(1)[0]
        text, confidence = str(candidate.string()), float(candidate.confidence())
        rect = observation.boundingBox()
        x, y, w, h = rect.origin.x, rect.origin.y, rect.size.width, rect.size.height
        boxes.append(TextBox(text, confidence, (x, 1 - y - h, x + w, 1 - y)))
    return boxes


def tokens(text: str) -> set[str]:
    """Lower-case alphanumeric tokens, plus the whole text squashed ('Thank you' -> 'thankyou')."""
    lowered = text.lower()
    return {t for t in re.split(r"[^0-9a-z]+", lowered) if t} | {re.sub(r"[^0-9a-z]", "", lowered)} - {""}


def vocabulary(words: Iterable[str]) -> set[str]:
    return {re.sub(r"[^0-9a-z]", "", w.lower()) for w in words} - {""}


def meaningful(boxes: Sequence[TextBox], words: Iterable[str] = ()) -> list[TextBox]:
    """Confident text, or text of any confidence that contains a candidate word as a token."""
    vocab = vocabulary(words)
    return [b for b in boxes if any(c.isalnum() for c in b.text)
            and (b.confidence >= MIN_CONFIDENCE or tokens(b.text) & vocab)]


def scan_frames(images: Iterable[np.ndarray], words: Iterable[str] = ()) -> tuple[list[dict], int]:
    """Every frame's readable text, and how many unreadable (noise) boxes were ignored."""
    words = list(words)
    found, ignored = [], 0
    for index, frame in enumerate(images):
        boxes = read_text(frame)
        kept = meaningful(boxes, words)
        ignored += len(boxes) - len(kept)
        found += [{"frame": index, "text": b.text, "confidence": round(b.confidence, 3),
                   "box": [round(v, 4) for v in b.box]} for b in kept]
    return found, ignored


def scan(path: Path, words: Iterable[str] = ()) -> list[dict]:
    """Every frame's readable text: [{"frame": i, "text": ..., "box": ...}]."""
    return scan_frames(frames(path), words)[0]


def padded(box: Sequence[float]) -> Box:
    return (max(0.0, box[0] - PAD), max(0.0, box[1] - PAD), min(1.0, box[2] + PAD), min(1.0, box[3] + PAD))


def overlaps(a: Box, b: Box) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def regions(boxes: Iterable[Sequence[float]]) -> list[Box]:
    """Padded boxes, overlapping ones merged into their bounding box; the result never overlaps.

    Blurring each region rather than one box around all text keeps a top-corner watermark
    and a bottom caption from blurring the signer in between.
    """
    merged: list[Box] = []
    for box in sorted({padded(b) for b in boxes}):
        current = box
        while True:
            hit = next((other for other in merged if overlaps(current, other)), None)
            if hit is None:
                break
            merged.remove(hit)
            current = (min(current[0], hit[0]), min(current[1], hit[1]),
                       max(current[2], hit[2]), max(current[3], hit[3]))
        merged.append(current)
    return sorted(merged)


def cover(boxes: Iterable[Box]) -> float:
    """Share of the frame covered by non-overlapping boxes."""
    return sum((b[2] - b[0]) * (b[3] - b[1]) for b in boxes)


def pixelate(frame: np.ndarray, box: Box) -> np.ndarray:
    height, width = frame.shape[:2]
    x0, y0 = int(box[0] * width), int(box[1] * height)
    x1, y1 = int(np.ceil(box[2] * width)), int(np.ceil(box[3] * height))
    region = frame[y0:y1, x0:x1]
    if region.size == 0:
        return frame
    small = cv2.resize(region, (max(1, (x1 - x0) // MOSAIC), max(1, (y1 - y0) // MOSAIC)),
                       interpolation=cv2.INTER_AREA)
    out = frame.copy()
    out[y0:y1, x0:x1] = cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)
    return out


def encode_frames(images: Sequence[np.ndarray], fps: float, destination: Path, encode_args: Sequence[str]) -> None:
    """Pipe BGR frames into ffmpeg with the same silent, metadata-free encoding as every clip."""
    height, width = images[0].shape[:2]
    command = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
               "-r", f"{fps}", "-i", "-", *encode_args, str(destination)]
    subprocess.run(command, input=b"".join(i.tobytes() for i in images), check=True)


def clean(path: Path, encode_args: Sequence[str], fps: float, words: Iterable[str] = ()) -> dict:
    """OCR, blur, re-OCR one clip in place. Returns the audit record (no clip content)."""
    words = list(words)
    original = list(frames(path))
    found, ignored = scan_frames(original, words)
    record = {"text_found": bool(found), "texts": sorted({f["text"] for f in found}),
              "frames_with_text": len({f["frame"] for f in found}), "ignored_noise_boxes": ignored,
              "action": "none"}
    if not found:
        return record
    boxes = [f["box"] for f in found]
    temporary = path.with_name(path.stem + ".blur.mp4")
    for attempt in range(1, ROUNDS + 1):
        blur = regions(boxes)
        record.update(regions=[[round(v, 4) for v in b] for b in blur], cover=round(cover(blur), 4), rounds=attempt)
        if cover(blur) > MAX_COVER:
            record["action"] = "drop: text covers too much of the frame"
            return record
        images = []
        for frame in original:
            for box in blur:
                frame = pixelate(frame, box)
            images.append(frame)
        encode_frames(images, fps, temporary, encode_args)
        remaining = scan(temporary, words)
        record["recheck_texts"] = sorted({f["text"] for f in remaining})
        if not remaining:
            temporary.replace(path)
            record["action"] = "blurred"
            return record
        boxes += [f["box"] for f in remaining]
    temporary.unlink()
    record["action"] = "drop: text still readable after blurring"
    return record
