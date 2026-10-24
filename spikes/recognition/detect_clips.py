"""Run the start/stop detector over saved clips or a live camera and cut the signs.

    .venv/bin/python detect_clips.py --video artifacts/pilot/clips/*.mp4 --rest-y 0.80
    .venv/bin/python detect_clips.py --camera 0 --write-clips artifacts/detector/live

Tracking is the legacy MediaPipe 0.10.21 Holistic (complexity 1) that signclip.py
and pilot_capture.py use: shoulders 11/12 with visibility >= 0.5 mean the body is
visible; each detected hand's landmark 0 is its wrist. Without --rest-y a saved
clip calibrates on its first 2 s (hands must rest then); live mode asks for a 2 s
rest first. Cut clips go under artifacts/ only, so recordings never reach Git.
Live keys: q/escape quit, c recalibrate.
"""
from __future__ import annotations

import argparse
import time
from collections import deque
from pathlib import Path
from typing import Iterable, Sequence

from detector import EPSILON, CalibrationError, Frame, Params, Segment, SignDetector, State, calibrate

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"
SHOULDERS, WRIST, MIN_VISIBILITY = (11, 12), 0, 0.5
PILL = {"watching": (60, 190, 60), "signing": (0, 210, 255), "cant_see": (40, 40, 230), "calibrating": (160, 160, 160)}
CALIBRATION_HELP = {"too_short": "keep resting a little longer",
                    "cant_see": "move back so both shoulders stay in view"}


def to_frame(t: float, result) -> Frame:
    """Map a Holistic result to detector input; wrists clamped to the [0, 1] image."""
    pose = result.pose_landmarks
    body = pose is not None and min(pose.landmark[i].visibility for i in SHOULDERS) >= MIN_VISIBILITY
    hands = (result.left_hand_landmarks, result.right_hand_landmarks)
    wrists = tuple((min(max(h.landmark[WRIST].x, 0.0), 1.0), min(max(h.landmark[WRIST].y, 0.0), 1.0))
                   for h in hands if h is not None)
    return Frame(t, body, wrists)


def clips_dir(path: str | Path) -> Path:
    directory = Path(path).resolve()
    if not directory.is_relative_to(ARTIFACTS.resolve()):
        raise ValueError(f"--write-clips must be inside {ARTIFACTS}: recordings stay out of Git")
    return directory


def calibration_window(frames: Sequence[Frame], params: Params) -> Sequence[Frame]:
    """Leading frames up to the first one that covers calibration_s."""
    for i, frame in enumerate(frames):
        if frame.t - frames[0].t >= params.calibration_s:
            return frames[:i + 1]
    return frames


def detect(frames: Sequence[Frame], params: Params, rest_y: float | None = None):
    """Calibrate on the leading rest (unless rest_y is given), then detect over the whole clip."""
    if rest_y is None:
        rest_y = calibrate(calibration_window(frames, params), params)
    detector = SignDetector(rest_y, params)
    segments = [e for frame in frames for e in detector.update(frame) if isinstance(e, Segment)]
    return rest_y, segments, detector.state


def describe(segment: Segment) -> str:
    verdict = "accepted" if segment.accepted else f"rejected ({segment.reason})"
    return f"{segment.start:6.2f}-{segment.end:6.2f} s  {segment.end - segment.start:4.2f} s  {verdict}"


def clip_name(stem: str, number: int, segment: Segment) -> str:
    return f"{stem}-{number:02d}-{'accepted' if segment.accepted else segment.reason}.mp4"


def within(t: float, segment: Segment) -> bool:
    return segment.start - EPSILON <= t <= segment.end + EPSILON


def holistic():
    import mediapipe as mp

    if mp.__version__ != "0.10.21":
        raise RuntimeError("Use the pinned MediaPipe 0.10.21 environment (requirements.txt)")
    return mp.solutions.holistic.Holistic(model_complexity=1)


def open_video(path: Path):
    import cv2

    cap = cv2.VideoCapture(str(path))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    if not cap.isOpened() or not fps > 0:
        cap.release()
        raise ValueError(f"Cannot decode {path} with a valid FPS")
    return cap, fps


def video_frames(path: Path) -> Iterable[tuple[float, object]]:
    cap, fps = open_video(path)
    try:
        index = 0
        while True:
            ok, bgr = cap.read()
            if not ok:
                return
            yield index / fps, bgr
            index += 1
    finally:
        cap.release()


def track(tracker, t: float, bgr) -> Frame:
    import cv2

    return to_frame(t, tracker.process(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))


def write_clip(path: Path, images: Sequence, fps: float):
    from pilot_capture import video_writer

    writer = video_writer(path, fps, images[0].shape)
    try:
        for image in images:
            writer.write(image)
    finally:
        writer.release()


def run_videos(paths: Sequence[Path], params: Params, rest_y: float | None, out: Path | None) -> int:
    single = 0
    with holistic() as tracker:
        for path in paths:
            frames = [track(tracker, t, bgr) for t, bgr in video_frames(path)]
            try:
                used_rest_y, segments, state = detect(frames, params, rest_y)
            except CalibrationError as error:
                print(f"{path.name}: calibration {error.reason}; the first {params.calibration_s:g} s must be a rest, "
                      "or pass --rest-y (0.80 default, or the value live mode prints)")
                continue
            print(f"{path.name}: rest line y={used_rest_y:.3f}, {len(frames)} frames")
            for number, segment in enumerate(segments, 1):
                print(f"  #{number} {describe(segment)}")
            if state is State.SIGNING:
                print("  unfinished: still signing at the end (hands never rested for "
                      f"{params.end_rest_s:g} s), not cut")
            single += sum(s.accepted for s in segments) == 1
            if out and segments:
                cap, fps = open_video(path)
                cap.release()
                cuts: list[list] = [[] for _ in segments]
                for t, bgr in video_frames(path):
                    for images, segment in zip(cuts, segments):
                        if within(t, segment):
                            images.append(bgr)
                for number, (images, segment) in enumerate(zip(cuts, segments), 1):
                    write_clip(out / clip_name(path.stem, number, segment), images, fps)
    print(f"{single}/{len(paths)} clips gave exactly one accepted sign")
    return single


def draw(view, status: str, rest_y: float | None, message: str):
    import cv2

    h, w = view.shape[:2]
    if rest_y is not None:
        y = int(rest_y * h)
        cv2.line(view, (0, y), (w, y), (255, 200, 0), 2)
        cv2.putText(view, "rest line", (10, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2)
    cv2.rectangle(view, (10, 10), (210, 50), PILL[status], -1)
    cv2.putText(view, status.replace("_", " "), (22, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
    cv2.putText(view, message, (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)


def open_camera(index: int):
    """The webcam at 1280x720, 30 FPS requested (the camera may deliver less)."""
    import cv2

    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        cap.release()
        raise SystemExit("Cannot open camera; check the index and macOS camera permission")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)
    return cap


def run_camera(index: int, params: Params, rest_y: float | None, out: Path | None, mirror: bool):
    import cv2

    cap = open_camera(index)
    keep_s = params.pre_roll_s + params.max_sign_s + params.end_rest_s + 0.5
    detector = SignDetector(rest_y, params) if rest_y is not None else None
    pending: list[Frame] = []
    recent: deque = deque()  # (t, bgr) long enough to cut any segment
    stamp, count, message = time.strftime("%Y%m%d-%H%M%S"), 0, "Rest both hands on the table for 2 s"
    try:
        with holistic() as tracker:
            while True:
                ok, bgr = cap.read()
                t = time.monotonic()
                if not ok:
                    raise SystemExit("Camera stopped")
                frame = track(tracker, t, bgr)
                if detector is None:
                    pending.append(frame)
                    if t - pending[0].t >= params.calibration_s:
                        try:
                            rest_y = calibrate(pending, params)
                            detector = SignDetector(rest_y, params)
                            message = "Ready: sign, then rest your hands"
                            print(f"rest line y={rest_y:.3f}")
                        except CalibrationError as error:
                            message = f"Calibration {error.reason}: {CALIBRATION_HELP[error.reason]}"
                        pending = []
                    status = "calibrating"
                else:
                    if out:
                        recent.append((t, bgr))
                        while recent[0][0] < t - keep_s:
                            recent.popleft()
                    for event in detector.update(frame):
                        if isinstance(event, Segment):
                            count += 1
                            message = f"#{count} {describe(event)}"
                            print(message)
                            images = [image for ts, image in recent if within(ts, event)]
                            if len(images) > 1:  # encode at the measured frame rate of the cut
                                fps = (len(images) - 1) / (event.end - event.start)
                                write_clip(out / clip_name(stamp, count, event), images, fps)
                    status = detector.status
                view = cv2.flip(bgr, 1) if mirror else bgr.copy()
                draw(view, status, rest_y, message)
                cv2.imshow("Ishara sign detector", view)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                if key == ord("c"):
                    detector, rest_y, pending, message = None, None, [], "Rest both hands on the table for 2 s"
    finally:
        cap.release()
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--video", type=Path, nargs="+", help="saved clip(s)")
    source.add_argument("--camera", type=int, help="live camera index")
    parser.add_argument("--rest-y", type=float, help="skip calibration and use this rest line (0-1, from the top)")
    parser.add_argument("--write-clips", metavar="DIR", help="cut each segment to an MP4 in DIR (inside artifacts/)")
    parser.add_argument("--no-mirror", action="store_true", help="live preview is mirrored by default")
    args = parser.parse_args()
    if args.rest_y is not None and not 0 < args.rest_y < 1:
        parser.error("--rest-y must be between 0 and 1")
    try:
        out = clips_dir(args.write_clips) if args.write_clips else None
    except ValueError as error:
        parser.error(str(error))
    if out:
        out.mkdir(parents=True, exist_ok=True)
    if args.video:
        run_videos(args.video, Params(), args.rest_y, out)
    else:
        run_camera(args.camera, Params(), args.rest_y, out, not args.no_mirror)


if __name__ == "__main__":
    main()
