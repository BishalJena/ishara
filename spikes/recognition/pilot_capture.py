"""Explicit local capture, tracking overlay review, and human label verification.

SPACE starts/stops a complete sign; X discards it; Q exits without saving a take
in progress. Camera frames are stored without overlays or mirroring. No predictions
are displayed during collection or label review, including the locked test split.
"""
from __future__ import annotations

import argparse
import time
import uuid

import cv2
import numpy as np

import recognition_data as data

MAX_FRAMES = 256
MAX_BYTES = 384 * 1024 * 1024
WINDOW = "Ishara isolated-sign capture"


def video_writer(path, fps, shape):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps,
                             (shape[1], shape[0]))
    if not writer.isOpened():
        writer.release()
        raise ValueError("Cannot encode the local MP4")
    return writer


def save_take(frames, timestamps, metadata, manifest=data.DATASET):
    """Preserve measured frame rate and raw frames; never infer a verified label."""
    if not 4 <= len(frames) <= MAX_FRAMES or len(timestamps) != len(frames):
        raise ValueError("A take needs 4–256 frames")
    intervals = np.diff(timestamps)
    if not np.isfinite(intervals).all() or np.any(intervals <= 0):
        raise ValueError("Capture timestamps must be finite and strictly increasing")
    if any(frame.shape != frames[0].shape for frame in frames):
        raise ValueError("Camera resolution changed during this take")
    records = data.load_dataset(manifest)
    ident = uuid.uuid4().hex
    path = data.ARTIFACTS / "pilot" / "clips" / f"{ident}.mp4"
    fps = float(1 / intervals.mean())
    row = {**metadata, "id": ident, "source_id": ident,
           "path": str(path.relative_to(data.ARTIFACTS)),
           "verified": False, "verification_note": "", "sha256": "0" * 64,
           "capture": {"frames": len(frames), "fps": fps,
                       "width": frames[0].shape[1], "height": frames[0].shape[0],
                       "frame_times_s": [float(t - timestamps[0]) for t in timestamps],
                       "max_frame_gap_ms": float(intervals.max() * 1000)}}
    data.validate_records(records + [row], verify_files=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        writer = video_writer(path, fps, frames[0].shape)
        try:
            for frame in frames:
                writer.write(frame)
        finally:
            writer.release()
        row["sha256"] = data.sha256(path)
        data.validate_records(records + [row])
        data.write_json(manifest, {"version": 1, "records": records + [row]})
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return row


def capture(args):
    negative = args.concept in data.NEGATIVES
    metadata = {"signer_id": args.signer, "session_id": args.session, "split": args.split,
                "label": None if negative else args.concept,
                "negative_kind": args.concept if negative else None,
                "provenance": "Local camera; intended label supplied by signer; " + args.note}
    # Check metadata and split conflicts before opening the camera.
    candidate = {**metadata, "id": uuid.uuid4().hex, "source_id": uuid.uuid4().hex,
                 "path": "pilot/preflight.mp4", "sha256": "0" * 64,
                 "verified": False, "verification_note": ""}
    data.validate_records(data.load_dataset(args.manifest) + [candidate], verify_files=False)
    camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        camera.release()
        raise ValueError("Cannot open camera; check camera index and macOS permission")
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    camera.set(cv2.CAP_PROP_FPS, 30)
    frames, timestamps, recording, saved = [], [], False, 0
    message = "SPACE starts/stops; X discards; Q exits"
    try:
        while saved < args.takes:
            ok, frame = camera.read()
            now = time.perf_counter()
            if not ok:
                raise ValueError("Camera stopped; unfinished take discarded")
            if recording:
                if len(frames) >= MAX_FRAMES or (len(frames) + 1) * frame.nbytes > MAX_BYTES:
                    frames, timestamps, recording = [], [], False
                    message = "Take too long; discarded rather than truncated. SPACE retries."
                else:
                    frames.append(frame.copy())
                    timestamps.append(now)
            view = cv2.resize(frame, (960, int(frame.shape[0] * 960 / frame.shape[1])))
            status = f"{args.concept} | {saved}/{args.takes} saved | " + ("RECORDING" if recording else "READY")
            for y, text in ((30, status), (60, message), (90, "Keep face, shoulders and both hands in frame.")):
                cv2.putText(view, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, .55,
                            (20, 30, 230) if recording else (40, 220, 40), 2)
            cv2.imshow(WINDOW, view)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27) or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
            if key == ord("x"):
                frames, timestamps, recording = [], [], False
                message = "Discarded. SPACE starts a new complete sign."
            elif key == ord(" "):
                if recording:
                    try:
                        row = save_take(frames, timestamps, metadata, args.manifest)
                        saved += 1
                        print(f"Saved unverified {args.concept}: {row['id']}", flush=True)
                        message = "Saved unverified. Relax, then SPACE for the next take."
                    except ValueError as error:
                        message = str(error)
                    frames, timestamps, recording = [], [], False
                else:
                    recording = True
    finally:
        camera.release()
        cv2.destroyAllWindows()
    print(f"{saved} takes saved. Every label still requires review.")


def find_record(manifest, ident):
    records = data.load_dataset(manifest)
    row = next((row for row in records if row["id"] == ident), None)
    if row is None:
        raise ValueError("Unknown clip ID")
    return records, row


def review(args):
    import mediapipe as mp

    _, row = find_record(args.manifest, args.id)
    destination = data.ARTIFACTS / "pilot" / "review" / row["id"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(data.ARTIFACTS / row["path"]))
    expected_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    writer, counts, complete = None, np.zeros(4, dtype=int), False
    try:
        with mp.solutions.holistic.Holistic(model_complexity=1) as tracker:
            while True:
                ok, frame = cap.read()
                if not ok:
                    complete = counts[0] > 0 and counts[0] == expected_frames
                    break
                result = tracker.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                counts += [1, bool(result.pose_landmarks and
                                   min(result.pose_landmarks.landmark[i].visibility for i in (11, 12)) >= .5),
                           bool(result.left_hand_landmarks), bool(result.right_hand_landmarks)]
                for landmarks, connections in (
                    (result.pose_landmarks, mp.solutions.holistic.POSE_CONNECTIONS),
                    (result.left_hand_landmarks, mp.solutions.holistic.HAND_CONNECTIONS),
                    (result.right_hand_landmarks, mp.solutions.holistic.HAND_CONNECTIONS),
                ):
                    if landmarks:
                        mp.solutions.drawing_utils.draw_landmarks(frame, landmarks, connections)
                if writer is None:
                    writer = video_writer(destination.with_suffix(".mp4"), cap.get(cv2.CAP_PROP_FPS), frame.shape)
                writer.write(frame)
                if not args.headless:
                    cv2.imshow("Tracking review; label is still unverified", frame)
                    if cv2.waitKey(max(1, round(1000 / cap.get(cv2.CAP_PROP_FPS)))) & 0xFF in (27, ord("q")):
                        break
    finally:
        cap.release()
        if writer:
            writer.release()
        if not args.headless:
            cv2.destroyAllWindows()
    summary = {"source_sha256": row["sha256"], "complete": bool(complete), "frames": int(counts[0]),
               "extractor": f"mediapipe-{mp.__version__}:holistic-complexity1-review",
               "pose_fraction": float(counts[1] / max(counts[0], 1)),
               "left_hand_fraction": float(counts[2] / max(counts[0], 1)),
               "right_hand_fraction": float(counts[3] / max(counts[0], 1)),
               "label_verified": False}
    data.write_json(destination.with_suffix(".json"), summary)
    print(f"Tracking review saved: {destination.relative_to(data.ROOT)}.mp4")
    print(summary)


def verify(args):
    import json

    records, row = find_record(args.manifest, args.id)
    review_path = data.ARTIFACTS / "pilot" / "review" / f"{row['id']}.json"
    evidence = json.loads(review_path.read_text()) if review_path.exists() else {}
    if not evidence.get("complete") or evidence.get("source_sha256") != row["sha256"]:
        raise ValueError("Render the full tracking review for this exact clip first")
    if not args.note.strip():
        raise ValueError("Describe the human sign-form check and its reference")
    row.update(verified=True, verification_note=args.note.strip())
    data.validate_records(records)
    data.write_json(args.manifest, {"version": 1, "records": records})
    print("Recorded your explicit label verification; tracking alone does not verify ISL meaning.")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=data.Path, default=data.DATASET)
    sub = parser.add_subparsers(dest="command", required=True)
    record = sub.add_parser("capture")
    record.add_argument("--camera", type=int, default=0)
    record.add_argument("--signer", required=True, help="Local pseudonym, not a person's name")
    record.add_argument("--session", required=True, help="Keep the same ID throughout one recording session")
    record.add_argument("--split", choices=data.SPLITS, required=True)
    record.add_argument("--concept", choices=data.VOCABULARY + data.NEGATIVES, required=True)
    record.add_argument("--takes", type=int, default=3)
    record.add_argument("--note", default="Sign form not yet checked")
    for command in ("review", "verify"):
        child = sub.add_parser(command)
        child.add_argument("--id", required=True)
        if command == "review":
            child.add_argument("--headless", action="store_true")
        else:
            child.add_argument("--note", required=True, help="Your sign-form review/reference evidence")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "capture" and not 1 <= args.takes <= 50:
        parser.error("--takes must be between 1 and 50")
    {"capture": capture, "review": review, "verify": verify}[args.command](args)


if __name__ == "__main__":
    main()
