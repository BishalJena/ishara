"""Find and remove burned-in text (dictionary videos often caption the word) before Gemini sees a clip.

Apple Vision (VNRecognizeTextRequest, accurate level) reads every decoded frame. Any text
box found anywhere in a clip is pixelated in every frame (captions are static overlays),
the clip is re-encoded, and every frame is read again; a clip that still shows text, or
whose text covers too much of the picture to remove safely, is dropped.
"""
from __future__ import annotations

import subprocess
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

MIN_CONFIDENCE = 0.3
MAX_COVER = 0.25  # union of text boxes larger than this share of the frame -> drop, not blur
PAD = 0.02  # pad each box by this share of the frame on every side
MOSAIC = 24  # pixels per mosaic block


@dataclass(frozen=True)
class TextBox:
    text: str
    confidence: float
    box: tuple[float, float, float, float]  # x0, y0, x1, y1 normalized, origin top-left


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


def meaningful(boxes: Sequence[TextBox]) -> list[TextBox]:
    return [b for b in boxes if b.confidence >= MIN_CONFIDENCE and any(c.isalnum() for c in b.text)]


def scan(path: Path) -> list[dict]:
    """Every frame's meaningful text: [{"frame": i, "text": ..., "box": ...}]."""
    found = []
    for index, frame in enumerate(frames(path)):
        for box in meaningful(read_text(frame)):
            found.append({"frame": index, "text": box.text, "confidence": round(box.confidence, 3),
                          "box": [round(v, 4) for v in box.box]})
    return found


def union_box(found: Sequence[dict]) -> tuple[float, float, float, float]:
    x0 = min(f["box"][0] for f in found) - PAD
    y0 = min(f["box"][1] for f in found) - PAD
    x1 = max(f["box"][2] for f in found) + PAD
    y1 = max(f["box"][3] for f in found) + PAD
    return max(0.0, x0), max(0.0, y0), min(1.0, x1), min(1.0, y1)


def cover(box: tuple[float, float, float, float]) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def pixelate(frame: np.ndarray, box: tuple[float, float, float, float]) -> np.ndarray:
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


def clean(path: Path, encode_args: Sequence[str], fps: float) -> dict:
    """OCR, blur, re-OCR one clip in place. Returns the audit record (no clip content)."""
    found = scan(path)
    record = {"text_found": bool(found), "texts": sorted({f["text"] for f in found}), "frames_with_text":
              len({f["frame"] for f in found}), "action": "none"}
    if not found:
        return record
    box = union_box(found)
    record["box"] = [round(v, 4) for v in box]
    record["cover"] = round(cover(box), 4)
    if cover(box) > MAX_COVER:
        record["action"] = "drop: text covers too much of the frame"
        return record
    images = [pixelate(f, box) for f in frames(path)]
    temporary = path.with_name(path.stem + ".blur.mp4")
    encode_frames(images, fps, temporary, encode_args)
    temporary.replace(path)
    remaining = scan(path)
    record["recheck_texts"] = sorted({f["text"] for f in remaining})
    record["action"] = "drop: text still readable after blurring" if remaining else "blurred"
    return record
