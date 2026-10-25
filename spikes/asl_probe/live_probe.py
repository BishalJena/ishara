"""Live webcam probe: the public ASL Signs model behind the existing start/stop detector.

Run with spikes/recognition/.venv from spikes/recognition (it imports live_source):

    .venv/bin/python ../asl_probe/live_probe.py --camera 0 --attempts 5

Guided mode walks a word list; the window shows which word to sign and the attempt
number. Rest both hands on the table for 2 s first (calibration), then sign once and
rest again; the detector cuts the sign and the model scores it. Keys in the window:
n = skip to the next word, r = retry (discard the last attempt), q = quit.

Every accepted cut is saved as .npy with the intended word and the model's top-5, under
artifacts/asl_probe/live/<session>/ so thresholds can be re-fitted offline. Nothing is
spoken, sent, or uploaded; this is a measurement tool.

Decision shown in the window (probe defaults, not frozen cut-offs): the top gloss over
all 250 classes is "accepted" when it is in VOCAB, p >= --min-p and the margin over the
runner-up >= --min-margin; otherwise "?". Restricting to the vocabulary *before*
thresholding is deliberately not done (see infer.py and the probe record).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "recognition"))
sys.path.insert(0, str(HERE))

import live_source as ls  # noqa: E402
from asl_model import AslModel, kaggle_frame, quality  # noqa: E402
from detect_clips import holistic, open_camera, to_frame  # noqa: E402

# word -> which form to sign (teach.html shows the videos)
VOCAB = {"hello": "wave by the temple", "thankyou": "flat hand, chin, then forward", "yes": "fist nods at the wrist",
         "no": "index+middle close onto thumb", "now": "both hands drop, palms up", "please": "flat hand circles on chest",
         "tomorrow": "thumb on cheek, arc forward-down, once, slowly", "wait": "palms up, fingers wiggle",
         "morning": "forearm rises from under the other arm"}
DROPPED = {"sick": "read as taste/go", "time": "read as arm/weus"}  # still accepted by --words if you want to retry them
LIVE_DIR = HERE.parent / "recognition" / "artifacts" / "asl_probe" / "live"
TOP_K = 3


def portrait_crop(bgr, aspect: float = 9 / 16):
    """Centre crop a landscape camera frame to a phone-like portrait window, so hands that
    would be outside a phone's view are outside here too."""
    h, w = bgr.shape[:2]
    cw = int(h * aspect)
    if cw >= w:
        return bgr
    x0 = (w - cw) // 2
    return bgr[:, x0:x0 + cw]


def track_kaggle(images, keep_image: bool, portrait: bool = False) -> Iterator[ls.Observation]:
    """Legacy Holistic once per frame: detector wrists plus the Kaggle 543x3 frame."""
    import cv2

    with holistic() as tracker:
        for t, wall, bgr in images:
            if portrait:
                bgr = portrait_crop(bgr)
            result = tracker.process(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            yield ls.Observation(wall, to_frame(t, result), kaggle_frame(result), bgr if keep_image else None)


def draw_banner(view, text: str) -> None:
    """Big prompt across the bottom of the window: which word to sign and the attempt number."""
    import cv2

    h, w = view.shape[:2]
    band = 64
    cv2.rectangle(view, (0, h - band), (w, h), (20, 20, 20), -1)
    scale = 1.1 if len(text) < 48 else 0.8
    cv2.putText(view, text, (16, h - 22), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 220, 255), 2, cv2.LINE_AA)


class AslMatcher:
    """Duck-types live_source.Matcher: observations -> Match, with the model's probability as 'similarity'."""

    def __init__(self, model: AslModel, vocab: Sequence[str], min_p: float, min_margin: float) -> None:
        self.model, self.vocab, self.min_p, self.min_margin = model, set(vocab), min_p, min_margin
        self.bundle = SimpleNamespace(provisional=False)
        self.thresholds = {"similarity": min_p, "margin": min_margin, "min_pose_fraction": 0.6, "min_hand_fraction": 0.2}
        self.last_landmarks: np.ndarray | None = None

    def __call__(self, observations: Sequence[ls.Observation]) -> ls.Match:
        landmarks = np.stack([o.landmarks for o in observations])
        self.last_landmarks = landmarks
        q = quality(landmarks)
        probs = self.model.predict(landmarks)
        order = np.argsort(-probs)
        top = tuple(ls.Candidate(self.model.glosses[i], float(probs[i])) for i in order[:TOP_K])
        p1, margin = float(probs[order[0]]), float(probs[order[0]] - probs[order[1]])
        gloss = self.model.glosses[order[0]]
        failed = []
        if gloss not in self.vocab:
            failed.append("not in vocabulary")
        if p1 < self.min_p:
            failed.append("similarity")
        if margin < self.min_margin:
            failed.append("margin")
        if q["pose_fraction"] < self.thresholds["min_pose_fraction"]:
            failed.append("pose")
        if q["hand_fraction"] < self.thresholds["min_hand_fraction"]:
            failed.append("hands")
        match = ls.Match(None if failed else gloss, None if not failed else f"best {gloss} p={p1:.2f}; failed: {', '.join(failed)}",
                         similarity=p1, margin=margin, top=top, quality=q, thresholds=self.thresholds,
                         failed_checks=tuple(f for f in failed if f in ls.FAILED_CHECKS))
        return match


class GuidedSource(ls.LiveSource):
    """LiveSource that prompts a word list and records each accepted cut with its intended word."""

    def __init__(self, *args, words: Sequence[str], attempts: int, matcher: AslMatcher, out_dir: Path, **kwargs) -> None:
        super().__init__(*args, matcher=matcher, **kwargs)
        self.words, self.attempts, self.asl, self.out_dir = list(words), attempts, matcher, out_dir
        self.word_i, self.attempt = 0, 0
        self.records: list[dict] = []
        self.frames: deque | None = None  # (t, BGR image) ring buffer filled by the preview callback
        self.fps = 25.0

    @property
    def word(self) -> str | None:
        return self.words[self.word_i] if self.word_i < len(self.words) else None

    def prompt(self) -> str:
        if self.word is None:
            return "All words done. q to quit."
        return f"SIGN: {self.word.upper()}  ({self.attempt + 1}/{self.attempts})  {VOCAB.get(self.word, '')}"

    def _display(self, observation, status, rest_y) -> None:
        if self.show is None or observation.image is None:
            return
        overlay = ls.Overlay(status, rest_y, self._message, self._last, False)
        if not self.show(observation.image, overlay):
            self._stopped = True

    def save_clip(self, segment, frames: Sequence[tuple[float, Any]], path: Path, fps: float) -> None:
        """Write the camera frames of one cut (plus the detector's pre-roll/rest) as an .mp4 for review."""
        import cv2

        chosen = [img for t, img in frames if segment.start - 0.3 <= t <= segment.end + 0.3]
        if not chosen:
            return
        h, w = chosen[0].shape[:2]
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        for img in chosen:
            writer.write(img)
        writer.release()

    def handle_key(self, key: int) -> None:
        if key == ord("n") and self.word is not None:
            self.out(f"skipped {self.word} after {self.attempt} attempts")
            self.word_i, self.attempt = self.word_i + 1, 0
        elif key == ord("r") and self.records and self.records[-1]["word"] == self.word and self.attempt > 0:
            dropped = self.records.pop()
            Path(dropped["npy"]).unlink(missing_ok=True)
            self.attempt -= 1
            self.out(f"retry: dropped attempt for {self.word}")

    def _on_segment(self, segment, recent):
        recognition = super()._on_segment(segment, recent)
        if recognition is None or self.word is None:
            return recognition
        match = recognition.match
        stem = f"{len(self.records):03d}_{self.word}"
        npy = self.out_dir / f"{stem}.npy"
        np.save(npy, self.asl.last_landmarks)
        if self.frames is not None:
            self.save_clip(segment, list(self.frames), self.out_dir / f"{stem}.mp4", self.fps)
        self.records.append({"word": self.word, "attempt": self.attempt + 1, "npy": str(npy),
                             "accepted": match.sign, "top": [[c.sign, round(c.similarity, 4)] for c in match.top],
                             "p1": round(match.similarity or 0, 4), "margin": round(match.margin or 0, 4),
                             "quality": match.quality, "latency_s": round(recognition.latency_s, 3),
                             "segment": [round(segment.start, 2), round(segment.end, 2)], "reason": match.reason})
        verdict = "CORRECT" if match.sign == self.word else ("?" if match.sign is None else f"WRONG ({match.sign})")
        top = ", ".join(f"{c.sign} {c.similarity:.2f}" for c in match.top)
        self.out(f"  {self.word} attempt {self.attempt + 1}: {verdict}   top: {top}")
        self.attempt += 1
        if self.attempt >= self.attempts:
            self.word_i, self.attempt = self.word_i + 1, 0
        return recognition


def summarize(records: list[dict], words: Sequence[str]) -> str:
    lines = [f"{'word':<10}{'n':>3}{'correct':>9}{'?':>5}{'wrong':>7}  top-1 right (any p)  median p when right"]
    for w in words:
        rows = [r for r in records if r["word"] == w]
        if not rows:
            continue
        correct = sum(r["accepted"] == w for r in rows)
        unsure = sum(r["accepted"] is None for r in rows)
        wrong = len(rows) - correct - unsure
        top1 = sum(r["top"][0][0] == w for r in rows)
        ps = sorted(r["p1"] for r in rows if r["top"][0][0] == w)
        med = f"{ps[len(ps) // 2]:.2f}" if ps else "-"
        lines.append(f"{w:<10}{len(rows):>3}{correct:>9}{unsure:>5}{wrong:>7}  {top1}/{len(rows):<18}{med}")
    total = len(records)
    if total:
        c = sum(r["accepted"] == r["word"] for r in records)
        wr = sum(r["accepted"] not in (None, r["word"]) for r in records)
        lines.append(f"{'all':<10}{total:>3}{c:>9}{sum(r['accepted'] is None for r in records):>5}{wr:>7}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--words", nargs="+", default=list(VOCAB))
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--min-p", type=float, default=0.6)
    parser.add_argument("--min-margin", type=float, default=0.3)
    parser.add_argument("--no-mirror", action="store_true")
    parser.add_argument("--portrait", action="store_true",
                        help="crop the camera to a 9:16 window like a phone's front camera")
    parser.add_argument("--no-video", action="store_true", help="do not save an .mp4 per cut")
    parser.add_argument("--session", default=time.strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args(argv)

    out_dir = LIVE_DIR / args.session
    out_dir.mkdir(parents=True, exist_ok=True)
    model = AslModel()
    matcher = AslMatcher(model, args.words, args.min_p, args.min_margin)
    live: GuidedSource | None = None

    import cv2

    frames: deque = deque(maxlen=int(30 * 7))  # ~7 s of camera frames for the per-cut .mp4
    stamps: deque = deque(maxlen=60)

    def show(image, overlay) -> bool:
        now = time.monotonic()
        if not args.no_video:
            frames.append((now, image.copy()))
        stamps.append(now)
        view = cv2.flip(image, 1) if not args.no_mirror else image.copy()
        ls.draw_overlay(view, overlay)
        if live is not None:
            draw_banner(view, live.prompt())
        cv2.imshow("Ishara ASL probe", view)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            return False
        if live is not None and key in (ord("n"), ord("r")):
            live.handle_key(key)
        return True

    clips = [track_kaggle(ls.camera_images(args.camera), keep_image=True, portrait=args.portrait)]
    live = GuidedSource(clips, words=args.words, attempts=args.attempts, matcher=matcher, out_dir=out_dir,
                        retry_calibration=True, show=show)
    if not args.no_video:
        live.frames = frames

    _orig_on_segment = live._on_segment

    def on_segment(segment, recent):
        if len(stamps) > 10:
            live.fps = max(5.0, min(60.0, (len(stamps) - 1) / max(1e-3, stamps[-1] - stamps[0])))
        return _orig_on_segment(segment, recent)

    live._on_segment = on_segment
    ls.log(f"{ls.REST_PROMPT}; the window then tells you which word to sign. n skips a word, r retries, q quits.")
    try:
        for _ in live:
            pass
    except KeyboardInterrupt:
        pass
    finally:
        ls.close_preview()
        model.close()
        (out_dir / "records.json").write_text(json.dumps({"session": args.session, "min_p": args.min_p,
                                                           "min_margin": args.min_margin, "records": live.records}, indent=1))
        print("\n" + summarize(live.records, args.words), file=sys.stderr)
        print(f"\n{live.summary()}\nsaved {out_dir / 'records.json'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
