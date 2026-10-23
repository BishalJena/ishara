"""Live Mac recognizer (PLAN A4): webcam or saved clips -> detector -> SignCLIP -> frozen cut-off.

    artifacts/signclip/.venv/bin/python live_source.py --camera 0
    artifacts/signclip/.venv/bin/python live_source.py --replay-videos artifacts/rehearsal

Each frame goes through the legacy Holistic once. Its wrists drive the start/stop
detector (2 s rest calibration first); for every accepted segment, the same frames'
landmarks become SignCLIP features, one warm model embeds them, and the exported
recognition bundle decides with recognition_data.rank/decision and the frozen
thresholds. The result is a sign or None (unsure, shown as "?"); rejected segments
yield nothing. Without a bundle every segment is unsure: nothing is guessed.

mac_bridge.py --live runs this file in the SignCLIP venv as a child process: stdout
carries one JSON line per accepted segment, and all logs go to stderr.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import statistics
import sys
import time
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

import recognition_data as data
from detect_clips import CALIBRATION_HELP, within
from detector import CalibrationError, Params, Segment, SignDetector, State, calibrate
from detector import Frame as DetectorFrame
from mac_bridge import result_line

DEFAULT_BUNDLE = data.ARTIFACTS / "evidence" / "recognition-bundle-signclip.json"
LATENCY_BUDGET_S = 2.0  # G2: sign end to chip
LIVE_ID = "live"  # the query's id/hash/source for rank(); bundle references never use it
DEFAULT_PARAMS = Params()
REST_PROMPT = "Rest both hands on the table for 2 s"


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


@dataclass(frozen=True)
class Observation:
    """One tracked frame.

    frame.t is the clip clock the detector runs on; wall is the monotonic time the frame
    was captured or read, so latency means the same in live and replay. landmarks is
    whatever the featurizer needs; image is only for the preview and is never buffered.
    """
    wall: float
    frame: DetectorFrame
    landmarks: Any
    image: Any = None


Clip = Iterable[Observation]  # one continuous recording; the camera is one endless clip
Featurize = Callable[[Sequence[Observation]], "tuple[np.ndarray, dict[str, float]]"]
Embed = Callable[[np.ndarray], np.ndarray]
Show = Callable[[Any, str, "float | None", str], bool]  # image, status, rest_y, message -> keep going


@dataclass(frozen=True)
class Match:
    sign: str | None  # None = unsure, a "?" chip that is never sent
    reason: str | None  # why it is unsure
    similarity: float | None = None
    margin: float | None = None


@dataclass(frozen=True)
class Recognition:
    sign: str | None  # None = unsure, a "?" chip that is never sent
    reason: str | None  # why it is unsure
    latency_s: float  # hands back at rest (segment end) -> result
    segment: Segment
    similarity: float | None = None
    margin: float | None = None


@dataclass(frozen=True)
class Bundle:
    encoder: str
    thresholds: dict[str, float]
    references: list[dict[str, Any]]  # rows in the shape recognition_data.rank expects


def load_bundle(path: Path | None, warn: Callable[[str], None] = log) -> Bundle | None:
    """The export-bundle file, or None (with a warning) when it does not exist yet.

    A file that exists but does not match this code's contract is an error, not a
    reason to fall back.
    """
    if path is None or not path.is_file():
        warn(f"WARNING: no recognition bundle at {path}. Every sign will show as ? and "
             "nothing is guessed. Run retrieval.py calibrate, then export-bundle.")
        return None
    document = json.loads(path.read_text())
    if document.get("version") != 1:
        raise ValueError(f"{path}: unknown bundle version {document.get('version')!r}")
    if document["quality"] != data.QUALITY:
        raise ValueError(f"{path}: quality thresholds {document['quality']} differ from {data.QUALITY}")
    thresholds = {k: document["thresholds"][k] for k in ("similarity", "margin")}
    if not all(type(v) in (int, float) and np.isfinite(v) for v in thresholds.values()):
        raise ValueError(f"{path}: thresholds must be finite numbers")
    references = document["references"]
    if {r["label"] for r in references} != set(data.VOCABULARY):
        raise ValueError(f"{path}: references must cover exactly {', '.join(data.VOCABULARY)}")
    if any(len(r["embedding"]) != document["embedding_dim"] for r in references):
        raise ValueError(f"{path}: every reference needs embedding_dim values")
    # The bundle drops clip hashes; each reference stands for its own source.
    rows = [{"id": r["id"], "label": r["label"], "sha256": f"bundle:{r['id']}",
             "source_id": f"bundle:{r['id']}", "embedding": r["embedding"]} for r in references]
    return Bundle(document["encoder"], thresholds, rows)


@dataclass(frozen=True)
class Matcher:
    """Segment frames -> SignCLIP features -> embedding -> frozen decision."""
    bundle: Bundle
    featurize: Featurize
    embed: Embed
    max_frames: int  # SignCLIP's limit: longer segments are refused, never truncated

    def __call__(self, observations: Sequence[Observation]) -> Match:
        if len(observations) > self.max_frames:
            return Match(None, f"{len(observations)} frames > {self.max_frames}; not truncated")
        try:
            features, quality = self.featurize(observations)
            embedding = self.embed(features)
        except ValueError as error:  # untrackable or too short for SignCLIP: unsure, not fatal
            return Match(None, str(error))
        query = {"id": LIVE_ID, "sha256": LIVE_ID, "source_id": LIVE_ID, "embedding": embedding}
        result = data.rank(query, self.bundle.references)
        verdict = data.decision(result, quality, self.bundle.thresholds)
        best = result["ranking"][0] if result["ranking"] else None
        top, margin = (best["similarity"] if best else None), result["margin"]
        if verdict["concept"] is not None:
            return Match(verdict["concept"], None, top, margin)
        reason = verdict["reason"]
        if best is not None and margin is not None:
            reason += (f" (best {best['concept']} {top:.3f}, margin {margin:.3f}, pose "
                       f"{quality.get('pose_fraction', 0):.2f}, hands {quality.get('hand_fraction', 0):.2f})")
        return Match(None, reason, top, margin)


class LiveSource:
    """Yields one Recognition per accepted detector segment, across one or more clips.

    retry_calibration: the camera asks for a new 2 s rest when calibration fails; a saved
    clip is skipped instead. rest_y skips calibration (for clips that start mid-sign).
    """

    def __init__(self, clips: Iterable[Clip], matcher: Matcher | None, *,
                 params: Params = DEFAULT_PARAMS, rest_y: float | None = None,
                 retry_calibration: bool = False, clock: Callable[[], float] = time.monotonic,
                 out: Callable[[str], None] = log, show: Show | None = None) -> None:
        self.clips, self.matcher, self.params, self.rest_y = clips, matcher, params, rest_y
        self.retry_calibration, self.clock, self.out, self.show = retry_calibration, clock, out, show
        self.latencies: list[float] = []
        self.count = 0
        self._stopped = False
        self._message = REST_PROMPT

    def __iter__(self) -> Iterator[Recognition]:
        for clip in self.clips:
            yield from self._run_clip(iter(clip))
            if self._stopped:
                return

    def summary(self) -> str:
        if not self.latencies:
            return "no accepted segments"
        worst = max(self.latencies)
        verdict = "within" if worst < LATENCY_BUDGET_S else "OVER"
        return (f"{len(self.latencies)} segments: latency median {statistics.median(self.latencies):.2f} s, "
                f"max {worst:.2f} s ({verdict} the {LATENCY_BUDGET_S:g} s budget)")

    def _display(self, observation: Observation, status: str, rest_y: float | None) -> None:
        if (self.show is not None and observation.image is not None
                and not self.show(observation.image, status, rest_y, self._message)):
            self._stopped = True

    def _calibrate(self, frames: Iterator[Observation]) -> tuple[float, list[Observation]] | None:
        pending: list[Observation] = []
        for observation in frames:
            pending.append(replace(observation, image=None))
            self._display(observation, "calibrating", None)
            if self._stopped:
                return None
            if observation.frame.t - pending[0].frame.t < self.params.calibration_s:
                continue
            try:
                rest_y = calibrate([o.frame for o in pending], self.params)
            except CalibrationError as error:
                self._message = f"Calibration {error.reason}: {CALIBRATION_HELP[error.reason]}"
                self.out(self._message)
                if not self.retry_calibration:
                    return None
                pending = []
                continue
            self.out(f"rest line y={rest_y:.3f}")
            return rest_y, pending
        return None

    def _run_clip(self, frames: Iterator[Observation]) -> Iterator[Recognition]:
        rest_y, replayed = self.rest_y, []
        if rest_y is None:
            calibrated = self._calibrate(frames)
            if calibrated is None:
                return
            rest_y, replayed = calibrated
        else:
            self.out(f"rest line y={rest_y:.3f} (given)")
        self._message = "Ready: sign, then rest your hands"
        detector = SignDetector(rest_y, self.params)
        keep_s = self.params.pre_roll_s + self.params.max_sign_s + self.params.end_rest_s + 0.5
        recent: deque[Observation] = deque()
        # Calibration frames are a rest, so replaying them only primes the detector,
        # exactly like detect_clips on a saved clip.
        for observation in itertools.chain(replayed, frames):
            recent.append(replace(observation, image=None))
            while recent[0].frame.t < observation.frame.t - keep_s:
                recent.popleft()
            for event in detector.update(observation.frame):
                if isinstance(event, Segment):
                    if result := self._on_segment(event, recent):
                        yield result
            self._display(observation, detector.status or "watching", rest_y)
            if self._stopped:
                return
        if detector.state is State.SIGNING:
            self.out("unfinished: the clip ended mid-sign, nothing recognised")

    def _on_segment(self, segment: Segment, recent: Sequence[Observation]) -> Recognition | None:
        span = f"{segment.start:.2f}-{segment.end:.2f} s"
        if not segment.accepted:
            self.out(f"segment {span} rejected ({segment.reason}); nothing shown")
            return None
        observations = [o for o in recent if within(o.frame.t, segment)]
        sign_end_wall = observations[-1].wall  # the first rest frame is the segment end
        match = Match(None, "no recognition bundle") if self.matcher is None else self.matcher(observations)
        sign, reason = match.sign, match.reason
        latency = self.clock() - sign_end_wall
        self.latencies.append(latency)
        self.count += 1
        over = "  OVER the 2 s budget" if latency >= LATENCY_BUDGET_S else ""
        shown = sign or f"? ({reason})"
        self._message = f"#{self.count} {sign or '?'}  {latency:.2f} s"
        self.out(f"#{self.count} {span} -> {shown}  latency {latency:.2f} s{over}")
        return Recognition(sign, reason, latency, segment, match.similarity, match.margin)


def result_json(recognition: Recognition) -> str:
    """The line mac_bridge reads; everything besides the sign is for logs and evidence."""
    def rounded(value: float | None) -> float | None:
        return None if value is None else round(value, 4)

    segment = recognition.segment
    return result_line(recognition.sign, reason=recognition.reason,
                       latency_ms=round(1000 * recognition.latency_s, 1),
                       similarity=rounded(recognition.similarity), margin=rounded(recognition.margin),
                       segment=[round(segment.start, 3), round(segment.end, 3)])


# ---- real camera, clips and model: these need the SignCLIP venv ----

VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v"}
Image = tuple[float, float, Any]  # clip time, wall time, BGR image


@dataclass(frozen=True)
class Landmarks:
    """One frame in pose-format's Holistic layout, ready for signclip.holistic_pose."""
    points: np.ndarray
    confidence: np.ndarray
    width: int
    height: int


def track(images: Iterable[Image], keep_image: bool) -> Iterator[Observation]:
    """Legacy Holistic once per frame: detector wrists and SignCLIP landmarks from one result."""
    import cv2

    import signclip
    from detect_clips import holistic, to_frame

    with holistic() as tracker:
        for t, wall, bgr in images:
            result = tracker.process(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            height, width = bgr.shape[:2]
            points, confidence = signclip.holistic_frame(result, width, height)
            yield Observation(wall, to_frame(t, result), Landmarks(points, confidence, width, height),
                              bgr if keep_image else None)


def camera_images(index: int) -> Iterator[Image]:
    from detect_clips import open_camera

    cap = open_camera(index)
    try:
        while True:
            ok, bgr = cap.read()
            now = time.monotonic()
            if not ok:
                raise SystemExit("Camera stopped")
            yield now, now, bgr
    finally:
        cap.release()


def video_images(path: Path, realtime: bool) -> Iterator[Image]:
    """A saved clip, paced like a camera unless realtime is off, so latency stays comparable."""
    from detect_clips import video_frames

    start = time.monotonic()
    for t, bgr in video_frames(path):
        if realtime and (delay := start + t - time.monotonic()) > 0:
            time.sleep(delay)
        yield t, time.monotonic(), bgr


def videos_in(directory: Path) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.suffix.lower() in VIDEO_SUFFIXES)


def replay_clips(paths: Sequence[Path], realtime: bool) -> Iterator[Clip]:
    """Each clip gets a fresh tracker, as signclip.extract gives each enrollment clip."""
    for path in paths:
        log(f"replaying {path.name}")
        yield track(video_images(path, realtime), keep_image=False)


def signclip_features(observations: Sequence[Observation]) -> tuple[np.ndarray, dict[str, float]]:
    import signclip

    first, span = observations[0], observations[-1].frame.t - observations[0].frame.t
    fps = (len(observations) - 1) / span if span > 0 else 30.0  # metadata only; features ignore it
    pose = signclip.holistic_pose([(o.landmarks.points, o.landmarks.confidence) for o in observations],
                                  fps, first.landmarks.width, first.landmarks.height)
    return signclip.pose_features(pose)


def signclip_matcher(bundle: Bundle) -> Matcher:
    """One warm SignCLIP model, checked against the encoder the bundle was exported with."""
    import retrieval
    import signclip

    start = time.perf_counter()
    encoder = retrieval.Encoder("signclip")
    if retrieval.encoder_id(encoder.contract) != bundle.encoder:
        raise SystemExit("The bundle was exported with a different SignCLIP setup (checkpoint, source, "
                         "torch or threads). Re-run retrieval.py export-bundle in this venv.")

    def embed(features: np.ndarray) -> np.ndarray:
        return signclip.embed(encoder.model, features)

    # The first forward pass is slow; pay for it before the first sign, not during it.
    embed(np.random.default_rng(0).normal(size=(32, 609)).astype(np.float32))
    log(f"SignCLIP ready in {time.perf_counter() - start:.1f} s")
    return Matcher(bundle, signclip_features, embed, signclip.MAX_FRAMES)


def preview(mirror: bool) -> Show:
    import cv2

    from detect_clips import draw

    def show(image: Any, status: str, rest_y: float | None, message: str) -> bool:
        view = cv2.flip(image, 1) if mirror else image.copy()
        draw(view, status, rest_y, message)
        cv2.imshow("Ishara live recognizer", view)
        return (cv2.waitKey(1) & 0xFF) not in (ord("q"), 27)

    return show


def close_preview() -> None:
    import cv2

    cv2.destroyAllWindows()


def result_stream() -> Any:
    """Keep the real stdout for result lines; everything else printed (by this file,
    MediaPipe or torch, even from C) goes to stderr so it can't corrupt the JSON."""
    sys.stdout.flush()
    stream = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return stream


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--camera", type=int, help="live camera index")
    source.add_argument("--replay-videos", type=Path, metavar="DIR",
                        help="feed every .mp4/.mov/.m4v in DIR (sorted) through the same path")
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE,
                        help="retrieval.py export-bundle output (default: %(default)s)")
    parser.add_argument("--rest-y", type=float, help="skip calibration and use this rest line (0-1)")
    parser.add_argument("--no-preview", action="store_true", help="no camera window")
    parser.add_argument("--no-mirror", action="store_true", help="the camera window is mirrored by default")
    parser.add_argument("--fast", action="store_true",
                        help="replay as fast as possible; latency then no longer means live latency")
    args = parser.parse_args(argv)
    if args.rest_y is not None and not 0 < args.rest_y < 1:
        parser.error("--rest-y must be between 0 and 1")
    paths = []
    if args.replay_videos is not None:
        if not args.replay_videos.is_dir() or not (paths := videos_in(args.replay_videos)):
            parser.error(f"no .mp4/.mov/.m4v clips in {args.replay_videos}")

    results = result_stream()
    bundle = load_bundle(args.bundle)
    matcher = signclip_matcher(bundle) if bundle is not None else None
    show = preview(not args.no_mirror) if args.camera is not None and not args.no_preview else None
    if args.camera is not None:
        clips: Iterable[Clip] = [track(camera_images(args.camera), keep_image=show is not None)]
        log(f"{REST_PROMPT}, then sign one at a time. q in the window (or Ctrl-C) stops.")
    else:
        clips = replay_clips(paths, realtime=not args.fast)
    live = LiveSource(clips, matcher, rest_y=args.rest_y, retry_calibration=args.camera is not None,
                      show=show)
    try:
        for recognition in live:
            results.write(result_json(recognition) + "\n")
    except KeyboardInterrupt:
        pass
    finally:
        log(live.summary())
        if show is not None:
            close_preview()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
