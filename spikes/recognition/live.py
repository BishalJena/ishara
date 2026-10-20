"""Live ISL sign recognition from a camera with the pretrained INCLUDE model.

    .venv/bin/python live.py                       # default camera, auto segmentation
    .venv/bin/python live.py --list-cameras        # find the iPhone (Continuity Camera) index
    .venv/bin/python live.py --camera 1 --speak    # read the accepted label aloud (macOS `say`)
    .venv/bin/python live.py --score hello,thankyou,hospital,idle --attempts 10

How a sign is captured (auto mode): dataset clips start and end with the signer at
rest, hands by the sides. So recording starts when a wrist rises above the hips
(plus ~0.5 s of the rest pose before it) and stops ~0.4 s after both wrists are
back down, or at the model's 169-frame limit. Stand far enough back that your
hips are in frame. SPACE toggles manual recording instead; 'a' switches auto mode
on/off. Every finished segment is saved (video + landmarks + top-k) to
artifacts/sessions/<timestamp>/ so it can be replayed through other models later.

Scoring mode cycles through the given targets ("idle" and "other" are negatives)
and records expected vs predicted per attempt; 'x' discards the last attempt
(bad segmentation), 'n' skips to the next target. A summary is written on exit.

Keys: q quit · SPACE manual record · a auto on/off · g framing guide · m mirror · n next · x discard
"""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
from collections import Counter, deque
from pathlib import Path

import cv2
import numpy as np

import include_model as im
from include_features import LandmarkExtractor, frames_to_features, normalize_body, resample

SESSIONS = im.ARTIFACTS / "sessions"
START_FRAMES = 3          # consecutive frames with a wrist raised before a segment starts
END_GAP_S = 0.8           # seconds with both wrists down before a segment ends
PRE_ROLL_S = 0.7          # rest pose kept from before the hand rose (dataset clips have this)
MIN_SEG_FRAMES = 15       # shorter segments are ignored (noise, hand passing through)
NEGATIVE_TARGETS = {"idle", "other"}
L_WRIST, R_WRIST, L_SHOULDER, R_SHOULDER, L_HIP, R_HIP = 15, 16, 11, 12, 23, 24


def wrist_raised(frame) -> bool:
    """True when either wrist is clearly above hip level (uses pose, so works when the hand detector misses)."""
    if not frame.pose_visible:
        return False
    hip_y = np.nanmean(frame.pose[[L_HIP, R_HIP], 1])
    shoulder_y = np.nanmean(frame.pose[[L_SHOULDER, R_SHOULDER], 1])
    threshold = hip_y - 0.25 * (hip_y - shoulder_y)
    return bool(min(frame.pose[L_WRIST, 1], frame.pose[R_WRIST, 1]) < threshold)


def list_cameras(max_index=6):
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        ok = cap.isOpened() and cap.read()[0]
        if ok:
            print(f"camera {i}: {int(cap.get(3))}x{int(cap.get(4))} @ {cap.get(5):.0f} fps")
        cap.release()


def speak(text: str):
    subprocess.Popen(["say", text.replace("_", " ")])


class CameraThread:
    """Keeps only the newest camera frame so the main loop never blocks on capture."""

    def __init__(self, cap):
        self.cap, self.frame, self.ok, self.lock = cap, None, True, threading.Lock()
        self.event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while self.ok:
            ok, f = self.cap.read()
            if not ok:
                self.ok = False
                self.event.set()
                return
            with self.lock:
                self.frame = f
            self.event.set()

    def read(self):
        self.event.wait(timeout=2.0)
        with self.lock:
            f, self.frame = self.frame, None
        self.event.clear()
        return (f is not None), f

    def release(self):
        self.ok = False
        self.cap.release()


def draw_guide(img):
    h, w = img.shape[:2]
    # Dataset framing (measured on INCLUDE clips): signer standing ~2 m from the camera,
    # head centre ~17% down, head radius ~7% of height, shoulders ~30%, hips ~65%, knees cut off.
    c = (255, 200, 0)
    cx = w // 2
    cv2.circle(img, (cx, int(h * 0.17)), int(h * 0.07), c, 1)
    cv2.line(img, (int(w * 0.42), int(h * 0.30)), (int(w * 0.58), int(h * 0.30)), c, 1)
    cv2.line(img, (int(w * 0.44), int(h * 0.65)), (int(w * 0.56), int(h * 0.65)), c, 1)
    cv2.rectangle(img, (int(w * 0.30), int(h * 0.05)), (int(w * 0.70), int(h * 0.98)), c, 1)
    cv2.putText(img, "step back: head in circle, shoulders on top line, hips on lower line",
                (int(w * 0.30), int(h * 0.04)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 1, cv2.LINE_AA)


class ReferenceClip:
    """Loops a dataset clip for a label in a corner so the user can copy the dataset's sign."""

    def __init__(self, width=320):
        self.width, self.label, self.frames, self.i = width, None, [], 0

    def set_label(self, label):
        if label == self.label:
            return
        self.label, self.frames, self.i = label, [], 0
        clips = sorted((im.ARTIFACTS / "clips" / (label or "")).glob("*.MOV")) if label else []
        if clips:
            cap = cv2.VideoCapture(str(clips[0]))
            while True:
                ok, f = cap.read()
                if not ok:
                    break
                scale = self.width / f.shape[1]
                self.frames.append(cv2.resize(f, None, fx=scale, fy=scale))
            cap.release()

    def draw(self, view):
        if not self.frames:
            return
        f = self.frames[self.i // 2 % len(self.frames)]  # ~half speed for easier copying
        self.i += 1
        fh, fw = f.shape[:2]
        x0, y0 = view.shape[1] - fw - 10, 40
        view[y0 : y0 + fh, x0 : x0 + fw] = f
        cv2.rectangle(view, (x0, y0), (x0 + fw, y0 + fh), (255, 200, 0), 1)
        cv2.putText(view, f"dataset: {self.label}", (x0, y0 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 200, 0), 1, cv2.LINE_AA)


def draw_landmarks(img, extractor):
    hr, pr = extractor.last_results
    du, st = mp_drawing(), mp_styles()
    if pr is not None and pr.pose_landmarks is not None:
        du.draw_landmarks(img, pr.pose_landmarks, mp_pose_connections(), landmark_drawing_spec=st.get_default_pose_landmarks_style())
    if hr is not None and hr.multi_hand_landmarks:
        for hand in hr.multi_hand_landmarks:
            du.draw_landmarks(img, hand, mp_hand_connections(), st.get_default_hand_landmarks_style(), st.get_default_hand_connections_style())


def mp_drawing():
    import mediapipe as mp
    return mp.solutions.drawing_utils


def mp_styles():
    import mediapipe as mp
    return mp.solutions.drawing_styles


def mp_pose_connections():
    import mediapipe as mp
    return mp.solutions.pose.POSE_CONNECTIONS


def mp_hand_connections():
    import mediapipe as mp
    return mp.solutions.hands.HAND_CONNECTIONS


class Session:
    def __init__(self, root: Path, args):
        self.dir = root / time.strftime("%Y%m%d-%H%M%S")
        self.dir.mkdir(parents=True)
        self.attempts = []
        (self.dir / "config.json").write_text(json.dumps(vars(args), indent=1))

    def save(self, seg_id, frames_bgr, frames, fps, feats, top, expected, size):
        clip = self.dir / f"{seg_id:03d}.mp4"
        if frames_bgr:
            h, w = frames_bgr[0].shape[:2]
            vw = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
            for f in frames_bgr:
                vw.write(f)
            vw.release()
        np.savez_compressed(self.dir / f"{seg_id:03d}.npz", features=feats,
                            pose=np.stack([f.pose for f in frames]), hand1=np.stack([f.hand1 for f in frames]),
                            hand2=np.stack([f.hand2 for f in frames]))
        rec = {"id": seg_id, "expected": expected, "top": top, "n_frames": len(frames), "capture_fps": fps,
               "model": size, "time": time.time()}
        self.attempts.append(rec)
        (self.dir / "attempts.json").write_text(json.dumps(self.attempts, indent=1))
        return rec

    def discard_last(self):
        if self.attempts:
            rec = self.attempts.pop()
            rec["discarded"] = True
            (self.dir / "attempts.json").write_text(json.dumps(self.attempts, indent=1))
            return rec

    def summary(self, threshold):
        per = {}
        for a in self.attempts:
            if a["expected"] is None:
                continue
            label, p = a["top"][0]
            accepted = p >= threshold
            s = per.setdefault(a["expected"], Counter())
            s["n"] += 1
            if a["expected"] in NEGATIVE_TARGETS:
                s["false_accept"] += accepted
            else:
                s["correct"] += accepted and label == a["expected"]
                s["wrong_accepted"] += accepted and label != a["expected"]
                s["abstain"] += not accepted
        out = {"threshold": threshold, "per_target": {k: dict(v) for k, v in per.items()}}
        (self.dir / "summary.json").write_text(json.dumps(out, indent=1))
        return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--video", help="read from a video file instead of a camera (replay/testing)")
    ap.add_argument("--headless", action="store_true", help="no preview window (for file replay)")
    ap.add_argument("--list-cameras", action="store_true")
    ap.add_argument("--size", default="large", choices=list(im.CHECKPOINTS))
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--proc-width", type=int, default=640,
                    help="downscale frames to this width before landmark detection (speed; coords are normalised)")
    ap.add_argument("--reference", help="show this label's dataset clip picture-in-picture (needs fetch_clips.py)")
    ap.add_argument("--threshold", type=float, default=0.5, help="min top-1 probability to accept a label")
    ap.add_argument("--no-normalize", action="store_true",
                    help="feed raw positions; by default each segment's shoulders are mapped to the dataset's position/size")
    ap.add_argument("--speak", action="store_true", help="say accepted labels aloud (macOS)")
    ap.add_argument("--no-mirror", action="store_true", help="do not mirror the preview")
    ap.add_argument("--no-save", action="store_true", help="do not write session clips/landmarks")
    ap.add_argument("--score", help="comma-separated targets to cycle through, e.g. hello,thankyou,idle,other")
    ap.add_argument("--attempts", type=int, default=10, help="attempts per target in scoring mode")
    args = ap.parse_args()

    if args.list_cameras:
        return list_cameras()

    labels = im.load_labels()
    known = set(labels)
    targets = [t.strip() for t in args.score.split(",")] if args.score else []
    for t in targets:
        if t not in known and t not in NEGATIVE_TARGETS:
            raise SystemExit(f"'{t}' is not an INCLUDE class (and not idle/other)")

    model = im.load_model(args.size, args.device)
    extractor = LandmarkExtractor()
    session = None if args.no_save else Session(SESSIONS, args)

    cap = cv2.VideoCapture(args.video) if args.video else cv2.VideoCapture(args.camera)
    if not args.video:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    if not cap.isOpened():
        raise SystemExit(f"could not open {args.video or f'camera {args.camera}'} (try --list-cameras; grant the terminal camera access)")
    file_fps = cap.get(cv2.CAP_PROP_FPS) if args.video else 0.0
    if not args.video:
        cap = CameraThread(cap)

    reference = ReferenceClip()
    auto, mirror, guide = True, not args.no_mirror, True
    recording, seg_frames, seg_bgr = False, [], []
    raised_streak, last_raised_t = 0, 0.0
    pre_roll = deque()  # (t, frame, bgr) for the last PRE_ROLL_S while idle
    fps_hist = deque(maxlen=30)
    seg_id, last = 0, None
    target_i, target_done = 0, 0
    print("ready — press q to quit")

    while True:
        ok, bgr = cap.read()
        if not ok:
            if args.video:
                last_raised_t = -1e9  # end of file: flush any open segment
                if not recording:
                    break
                bgr = np.zeros_like(seg_bgr[-1]) if seg_bgr else np.zeros((args.height, args.width, 3), np.uint8)
            else:
                print("camera read failed")
                break
        now = time.monotonic() if not args.video else (cap.get(cv2.CAP_PROP_POS_FRAMES) / (file_fps or 25.0))
        fps_hist.append(now)
        fps = file_fps if args.video else (
            (len(fps_hist) - 1) / (fps_hist[-1] - fps_hist[0]) if len(fps_hist) > 1 and fps_hist[-1] > fps_hist[0] else 0.0)

        proc = bgr
        if args.proc_width and bgr.shape[1] > args.proc_width:
            s = args.proc_width / bgr.shape[1]
            proc = cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        frame = extractor.process(proc)
        hands = frame.hands_visible
        raised = wrist_raised(frame)
        raised_streak = raised_streak + 1 if raised else 0
        if raised:
            last_raised_t = now

        if not recording:
            pre_roll.append((now, frame, bgr.copy() if session else None))
            while pre_roll and now - pre_roll[0][0] > PRE_ROLL_S:
                pre_roll.popleft()
        if auto and not recording and raised_streak >= START_FRAMES:
            recording = True
            seg_frames = [f for _, f, _ in pre_roll]
            seg_bgr = [b for _, _, b in pre_roll] if session else []
            pre_roll.clear()
        if recording:
            seg_frames.append(frame)
            if session:
                seg_bgr.append(bgr.copy())
            gap = now - last_raised_t
            if (auto and gap >= END_GAP_S) or len(seg_frames) >= im.MAX_FRAMES:
                recording = False
                if len(seg_frames) >= MIN_SEG_FRAMES:
                    seg_id += 1
                    seq = resample(seg_frames, fps) if fps else seg_frames
                    if not args.no_normalize:
                        seq = normalize_body(seq)
                    feats = frames_to_features(seq)
                    t0 = time.perf_counter()
                    top = im.predict(model, feats, labels, k=3)
                    infer_ms = 1000 * (time.perf_counter() - t0)
                    expected = targets[target_i] if targets else None
                    accepted = top[0][1] >= args.threshold
                    last = {"top": top, "accepted": accepted, "n": len(seq), "ms": infer_ms, "expected": expected, "t": now}
                    print(f"#{seg_id:03d} {len(seq):3d} frames  {', '.join(f'{l}:{p:.2f}' for l, p in top)}"
                          f"  -> {'ACCEPT ' + top[0][0] if accepted else 'unsure'}" + (f"  (expected {expected})" if expected else ""))
                    if session:
                        session.save(seg_id, seg_bgr, seq, fps or 30.0, feats, top, expected, args.size)
                    if args.speak and accepted:
                        speak(top[0][0])
                    if targets:
                        target_done += 1
                        if target_done >= args.attempts:
                            target_i, target_done = (target_i + 1) % len(targets), 0
                seg_frames, seg_bgr = [], []
                raised_streak = 0

        if args.headless:
            continue

        # ---- draw ----
        view = bgr
        draw_landmarks(view, extractor)
        if mirror:
            view = cv2.flip(view, 1)
        h, w = view.shape[:2]
        if guide:
            draw_guide(view)
        reference.set_label(targets[target_i] if targets else args.reference)
        reference.draw(view)
        status = (f"{fps:4.1f} fps  hands:{hands}  {'RAISED' if raised else 'rest  '}  {'AUTO' if auto else 'MANUAL'}  "
                  f"{'REC ' + str(len(seg_frames)) if recording else 'idle'}")
        cv2.putText(view, status, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0) if recording else (200, 200, 200), 2, cv2.LINE_AA)
        if targets:
            cv2.putText(view, f"SIGN: {targets[target_i].upper()}   attempt {target_done + 1}/{args.attempts}", (10, h - 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2, cv2.LINE_AA)
        if last and now - last["t"] < 4.0:
            big = last["top"][0][0].upper() if last["accepted"] else "unsure"
            color = (0, 255, 0) if last["accepted"] else (0, 165, 255)
            cv2.putText(view, big, (10, int(h * 0.5)), cv2.FONT_HERSHEY_SIMPLEX, 2.0, color, 4, cv2.LINE_AA)
            for i, (l, p) in enumerate(last["top"]):
                cv2.putText(view, f"{l} {p:.2f}", (10, int(h * 0.5) + 36 * (i + 1)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.putText(view, f"{last['n']} frames  model {last['ms']:.0f} ms", (10, int(h * 0.5) + 36 * 4), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
        cv2.imshow("Ishara — INCLUDE live", view)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord(" "):
            if recording:
                last_raised_t, auto = -1e9, True  # force the end condition on the next loop
            else:
                recording, auto = True, False
                seg_frames = [f for _, f, _ in pre_roll]
                seg_bgr = [b for _, _, b in pre_roll] if session else []
                pre_roll.clear()
        elif key == ord("a"):
            auto = not auto
        elif key == ord("g"):
            guide = not guide
        elif key == ord("m"):
            mirror = not mirror
        elif key == ord("n") and targets:
            target_i, target_done = (target_i + 1) % len(targets), 0
        elif key == ord("x") and session:
            rec = session.discard_last()
            if rec:
                print(f"discarded #{rec['id']:03d}")
                if targets and target_done > 0:
                    target_done -= 1

    cap.release()
    cv2.destroyAllWindows()
    extractor.close()
    if session:
        print(f"session saved to {session.dir}")
        if targets:
            print(json.dumps(session.summary(args.threshold), indent=1))


if __name__ == "__main__":
    main()
