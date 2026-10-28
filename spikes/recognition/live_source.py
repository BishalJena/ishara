"""Live Mac recognizer (PLAN A4): webcam or saved clips -> detector -> SignCLIP -> frozen cut-off.

    artifacts/signclip/.venv/bin/python live_source.py --camera 0
    artifacts/signclip/.venv/bin/python live_source.py --replay-videos artifacts/rehearsal
    .venv/bin/python live_source.py --model asl --video rest.mp4 hello.mp4 rest.mp4 yes.mp4

--video plays saved clips back to back as if they were the webcam (one stream, one rest
calibration), so the Mac fallback can be rehearsed and tested without a camera.

Each frame goes through the legacy Holistic once. Its wrists drive the start/stop
detector (2 s rest calibration first); for every accepted segment, the same frames'
landmarks become SignCLIP features, one warm model embeds them, and the exported
recognition bundle decides with recognition_data.rank/decision and the frozen
thresholds. The result is a sign or None (unsure, shown as "?"); rejected segments
yield nothing. Without a bundle every segment is unsure: nothing is guessed.

The window (camera or replayed clip) shows the detector pill and rest line, and for
the latest sign a big green label or a red "?", its top-3 matches as bars against the
similarity cut-off, the margin, tracking quality and latency. q in the window stops.

mac_bridge.py --live runs this file in the SignCLIP venv as a child process: stdout
carries one JSON line per accepted segment, and all logs go to stderr. With --handshake
(which the bridge passes) the first stdout line says the recognizer is calibrated, and it
holds until the bridge writes "go" on stdin, so the call is only placed once the Mac can see.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import statistics
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, TextIO

import numpy as np

import recognition_data as data
from detect_clips import CALIBRATION_HELP, within
from detector import CalibrationError, Params, Segment, SignDetector, State, calibrate
from detector import Frame as DetectorFrame
from mac_bridge import GO, PROVISIONAL_BANNER, describe_result, ready_line, result_line, unsure_why

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
Show = Callable[[Any, "Overlay"], bool]  # image, what to draw on it -> keep going


TOP_K = 3  # candidates shown per sign so a person can judge how close the runners-up were
# Each check data.decision applies -> its cut-off's key in Match.thresholds.
FAILED_CHECKS = {"similarity": "similarity", "margin": "margin", "pose": "min_pose_fraction",
                 "hands": "min_hand_fraction"}


@dataclass(frozen=True)
class Candidate:
    sign: str
    similarity: float


@dataclass(frozen=True)
class Match:
    """The decision plus the evidence behind it; only `sign` ever becomes a chip."""
    sign: str | None  # None = unsure, a "?" chip that is never sent
    reason: str | None  # why it is unsure
    similarity: float | None = None
    margin: float | None = None
    top: tuple[Candidate, ...] = ()  # best reference per sign, highest first, at most TOP_K
    quality: dict[str, float] | None = None  # pose_fraction, hand_fraction of the segment
    thresholds: dict[str, float] | None = None  # bundle cut-offs plus data.QUALITY minimums
    failed_checks: tuple[str, ...] = ()  # FAILED_CHECKS keys the frozen decision tripped on
    provisional: bool = False  # the bundle says its thresholds are not calibrated yet
    pick_one: str | None = None  # ASL open-set rule: a vocabulary candidate the user must confirm; never a chip by itself


@dataclass(frozen=True)
class Recognition:
    match: Match
    latency_s: float  # hands back at rest (segment end) -> result
    segment: Segment

    @property
    def sign(self) -> str | None:
        return self.match.sign

    @property
    def reason(self) -> str | None:
        return self.match.reason


@dataclass(frozen=True)
class Overlay:
    """Everything the preview window draws over one frame."""
    status: str  # detector pill: calibrating, watching, signing, cant_see
    rest_y: float | None
    message: str
    last: Recognition | None = None  # the latest result stays up until the next one
    provisional: bool = False


class PlaybackClock:
    """Monotonic time that stands still while playback is held, so saved clips resume at
    their own pace after a hold instead of rushing through the frames they missed."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock, self._held_s = clock, 0.0

    def __call__(self) -> float:
        return self._clock() - self._held_s

    @contextmanager
    def held(self) -> Iterator[None]:
        start = self._clock()
        try:
            yield
        finally:
            self._held_s += self._clock() - start


class StartSignal:
    """mac_bridge writes GO on stdin once the call is connected; EOF means no call."""

    def __init__(self, lines: TextIO) -> None:
        self._done, self._go = threading.Event(), False
        threading.Thread(target=self._read, args=(lines,), daemon=True).start()

    def _read(self, lines: TextIO) -> None:
        self._go = lines.readline().strip() == GO
        self._done.set()

    def wait(self, timeout: float) -> bool | None:
        """True: go; False: stop; None: still waiting after `timeout` seconds."""
        return self._go if self._done.wait(timeout) else None


@dataclass(frozen=True)
class Handshake:
    """--handshake: tell mac_bridge once calibrated, then hold until the call is connected,
    so the call is only placed when the Mac can already see signs."""
    ready: Callable[[float], None]  # rest_y -> the ready line on stdout
    wait: Callable[[float], bool | None]  # StartSignal.wait
    # Saved clips pause while holding (and their clock with them); None means a live
    # camera, which keeps being read and shown so its first frames after the hold are fresh.
    playback: PlaybackClock | None = None


HOLD_POLL_S = 0.05  # how often a paused clip's window is redrawn while holding
HOLD_MESSAGE = "Ready: waiting for the call to connect"


@dataclass(frozen=True)
class Bundle:
    encoder: str
    thresholds: dict[str, float]
    references: list[dict[str, Any]]  # rows in the shape recognition_data.rank expects
    provisional: bool = False


def failed_checks(top: float, margin: float, quality: dict[str, float],
                  thresholds: dict[str, float]) -> tuple[str, ...]:
    """Which of data.decision's cut-offs a ranked segment misses, to explain a "?".

    Explanation only: data.decision stays the one that decides.
    """
    measured = {"similarity": top, "margin": margin, "pose": quality.get("pose_fraction", 0),
                "hands": quality.get("hand_fraction", 0)}
    return tuple(check for check, value in measured.items() if value < thresholds[FAILED_CHECKS[check]])


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
    provisional = document.get("provisional", False)
    if type(provisional) is not bool:
        raise ValueError(f"{path}: provisional must be true or false")
    if provisional:
        warn(f"WARNING: {PROVISIONAL_BANNER}. {path} was not calibrated on held-out takes.")
    # The bundle drops clip hashes; each reference stands for its own source.
    rows = [{"id": r["id"], "label": r["label"], "sha256": f"bundle:{r['id']}",
             "source_id": f"bundle:{r['id']}", "embedding": r["embedding"]} for r in references]
    return Bundle(document["encoder"], thresholds, rows, provisional)


@dataclass(frozen=True)
class Matcher:
    """Segment frames -> SignCLIP features -> embedding -> frozen decision."""
    bundle: Bundle
    featurize: Featurize
    embed: Embed
    max_frames: int  # SignCLIP's limit: longer segments are refused, never truncated

    @property
    def thresholds(self) -> dict[str, float]:
        return {**self.bundle.thresholds, **data.QUALITY}

    def __call__(self, observations: Sequence[Observation]) -> Match:
        unsure = replace(Match(None, None), thresholds=self.thresholds,
                         provisional=self.bundle.provisional)
        if len(observations) > self.max_frames:
            return replace(unsure, reason=f"{len(observations)} frames > {self.max_frames}; not truncated")
        try:
            features, quality = self.featurize(observations)
            embedding = self.embed(features)
        except ValueError as error:  # untrackable or too short for SignCLIP: unsure, not fatal
            return replace(unsure, reason=str(error))
        query = {"id": LIVE_ID, "sha256": LIVE_ID, "source_id": LIVE_ID, "embedding": embedding}
        result = data.rank(query, self.bundle.references)
        verdict = data.decision(result, quality, self.bundle.thresholds)
        best = result["ranking"][0] if result["ranking"] else None
        top, margin = (best["similarity"] if best else None), result["margin"]
        evidence = replace(unsure, similarity=top, margin=margin,
                           top=tuple(Candidate(r["concept"], r["similarity"]) for r in result["ranking"][:TOP_K]),
                           quality={k: quality.get(k, 0) for k in ("pose_fraction", "hand_fraction")})
        if verdict["concept"] is not None:
            return replace(evidence, sign=verdict["concept"])
        reason = verdict["reason"]
        if best is None or margin is None:
            return replace(evidence, reason=reason)
        reason += (f" (best {best['concept']} {top:.3f}, margin {margin:.3f}, pose "
                   f"{quality.get('pose_fraction', 0):.2f}, hands {quality.get('hand_fraction', 0):.2f})")
        return replace(evidence, reason=reason,
                       failed_checks=failed_checks(top, margin, quality, self.thresholds))


class LiveSource:
    """Yields one Recognition per accepted detector segment, across one or more clips.

    retry_calibration: the camera asks for a new 2 s rest when calibration fails; a saved
    clip is skipped instead. rest_y skips calibration (for clips that start mid-sign).
    handshake: after the first calibration, announce readiness and hold until the go.
    """

    def __init__(self, clips: Iterable[Clip], matcher: Matcher | None, *,
                 params: Params = DEFAULT_PARAMS, rest_y: float | None = None,
                 retry_calibration: bool = False, clock: Callable[[], float] = time.monotonic,
                 out: Callable[[str], None] = log, show: Show | None = None,
                 handshake: Handshake | None = None) -> None:
        self.clips, self.matcher, self.params, self.rest_y = clips, matcher, params, rest_y
        self.retry_calibration, self.clock, self.out, self.show = retry_calibration, clock, out, show
        self.handshake, self._held = handshake, False
        self.latencies: list[float] = []
        self.count = 0
        self._last: Recognition | None = None
        self._shown: Observation | None = None  # the latest frame on screen, redrawn while holding
        self._provisional = matcher is not None and matcher.bundle.provisional
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
        if self.show is None or observation.image is None:
            return
        overlay = Overlay(status, rest_y, self._message, self._last, self._provisional)
        self._shown = observation
        if not self.show(observation.image, overlay):
            self._stopped = True

    def _hold(self, frames: Iterator[Observation], rest_y: float) -> bool:
        """Says the recognizer is ready, then waits for the go. False: stop (no call)."""
        assert self.handshake is not None  # only called with a handshake
        ready, wait, playback = self.handshake.ready, self.handshake.wait, self.handshake.playback
        self._message = HOLD_MESSAGE
        self.out(self._message)
        go = None
        if playback is None:  # a camera: frames are fresh after the hold, and none is a sign
            for index, observation in enumerate(frames):
                if index == 0:  # a frame came, so the camera works (unproven yet with --rest-y)
                    ready(rest_y)
                self._display(observation, "watching", rest_y)
                if self._stopped or (go := wait(0)) is not None:
                    break
        else:
            ready(rest_y)
            with playback.held():
                while not self._stopped and (go := wait(HOLD_POLL_S)) is None:
                    if self._shown is not None:
                        self._display(self._shown, "watching", rest_y)
        if go:
            return not self._stopped
        if go is False:
            self.out("no call: the bridge closed the start-up handshake")
        return False

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
        if self.handshake is not None and not self._held:
            self._held = True  # once: later clips (--replay-videos) start right away
            if not self._hold(frames, rest_y):
                self._stopped = True
                return
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
        latency = self.clock() - sign_end_wall
        self.latencies.append(latency)
        self.count += 1
        over = "  OVER the 2 s budget" if latency >= LATENCY_BUDGET_S else ""
        recognition = self._last = Recognition(match, latency, segment)
        self._message = f"#{self.count} {match.sign or '?'}  {latency:.2f} s"
        self.out(f"#{self.count} {span}  {describe_result(result_details(recognition))}{over}")
        return recognition


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def result_details(recognition: Recognition) -> dict[str, Any]:
    """Everything the bridge and the session log show about one sign; only "sign" is acted on."""
    match, segment = recognition.match, recognition.segment
    return {"sign": match.sign, "reason": match.reason,
            "latency_ms": round(1000 * recognition.latency_s, 1),
            "similarity": _rounded(match.similarity), "margin": _rounded(match.margin),
            "segment": [round(segment.start, 3), round(segment.end, 3)],
            "top": [{"sign": c.sign, "similarity": _rounded(c.similarity)} for c in match.top],
            "quality": None if match.quality is None else {k: _rounded(v) for k, v in match.quality.items()},
            "thresholds": match.thresholds, "failed_checks": list(match.failed_checks),
            "provisional": match.provisional, "pick_one": match.pick_one}


def result_json(recognition: Recognition) -> str:
    """The line mac_bridge reads."""
    details = result_details(recognition)
    return result_line(details.pop("sign"), **details)


@dataclass(frozen=True)
class Panel:
    """The preview's result box: big label, top-3 bars and the numbers behind the decision."""
    label: str  # the sign, or "?"
    accepted: bool
    bars: tuple[tuple[str, float], ...]  # (sign, similarity), highest first
    similarity_cut: float | None  # drawn as a tick on every bar
    why: str | None  # why it is unsure
    footer: tuple[str, ...]


def result_panel(recognition: Recognition) -> Panel:
    details = result_details(recognition)
    thresholds, quality, margin = details["thresholds"] or {}, details["quality"], details["margin"]
    first = f"{recognition.latency_s:.2f} s"
    if margin is not None:
        first = f"margin {margin:.2f} (min {thresholds['margin']:.2f})  {first}"
    footer = [first]
    if quality is not None:
        footer.append(f"body {quality['pose_fraction']:.2f} (min {thresholds['min_pose_fraction']:.2f})  "
                      f"hands {quality['hand_fraction']:.2f} (min {thresholds['min_hand_fraction']:.2f})")
    return Panel(recognition.sign or "?", recognition.sign is not None,
                 tuple((c["sign"], c["similarity"]) for c in details["top"]),
                 thresholds.get("similarity"), unsure_why(details), tuple(footer))


GREEN, RED, GREY, WHITE, YELLOW = (60, 200, 60), (40, 40, 230), (150, 150, 150), (255, 255, 255), (0, 220, 255)
PANEL_WIDTH, BAR_WIDTH = 400, 170


def draw_overlay(view: Any, overlay: Overlay) -> None:
    """Detector pill, rest line and message, a loud banner for a provisional bundle and,
    once a sign was cut, the result box at the top right. Draws in place (BGR)."""
    import cv2

    from detect_clips import draw

    draw(view, overlay.status, overlay.rest_y, overlay.message)
    font, width = cv2.FONT_HERSHEY_SIMPLEX, view.shape[1]
    top = 10
    if overlay.provisional:
        cv2.rectangle(view, (0, 58), (width, 96), RED, -1)
        cv2.putText(view, PROVISIONAL_BANNER.replace("—", "-"), (12, 86), font, 0.8, WHITE, 2)
        top = 104
    if overlay.last is None:
        return
    panel = result_panel(overlay.last)
    left = max(width - PANEL_WIDTH - 10, 0)
    box = 96 + 24 * bool(panel.why) + 32 * len(panel.bars) + 24 * len(panel.footer)
    region = view[top:top + box, left:left + PANEL_WIDTH]
    region[:] = region // 3  # darken behind the text
    cv2.putText(view, panel.label, (left + 14, top + 66), font, 2.2, GREEN if panel.accepted else RED, 5)
    y = top + 88
    if panel.why:
        y += 6
        cv2.putText(view, panel.why[:40], (left + 14, y), font, 0.65, RED, 2)
        y += 18
    bar_left = left + 140
    for index, (sign, similarity) in enumerate(panel.bars):
        y += 32
        cv2.putText(view, sign, (left + 14, y), font, 0.65, WHITE, 2)
        length = int(BAR_WIDTH * min(max(similarity, 0.0), 1.0))
        colour = GREEN if panel.accepted and index == 0 else GREY
        cv2.rectangle(view, (bar_left, y - 18), (bar_left + length, y - 2), colour, -1)
        if panel.similarity_cut is not None:
            tick = bar_left + int(BAR_WIDTH * panel.similarity_cut)
            cv2.line(view, (tick, y - 22), (tick, y + 2), YELLOW, 2)
        cv2.putText(view, f"{similarity:.2f}", (bar_left + BAR_WIDTH + 10, y), font, 0.65, WHITE, 2)
    for line in panel.footer:
        y += 24
        cv2.putText(view, line, (left + 14, y), font, 0.5, WHITE, 1)


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


FALLBACK_FRAME_S = 1 / 30  # gap after a one-frame clip, whose frame rate can't be read off its times


def read_video(path: Path) -> Iterable[tuple[float, Any]]:
    from detect_clips import video_frames

    return video_frames(path)


def playlist_images(paths: Sequence[Path], realtime: bool,
                    read: Callable[[Path], Iterable[tuple[float, Any]]] | None = None,
                    clock: Callable[[], float] = time.monotonic,
                    sleep: Callable[[float], None] = time.sleep) -> Iterator[Image]:
    """Saved clips back to back as one camera stream: the clock never restarts (each clip
    begins one frame after the last one ended) and frames come at their own pace unless
    realtime is off, so calibration, the detector and latency see what a webcam would."""
    start, offset = clock(), 0.0
    for path in paths:
        t = step = None
        for t_clip, bgr in (read or read_video)(path):
            if t is not None:
                step = t_clip - t
            t = t_clip
            if realtime and (delay := start + offset + t - clock()) > 0:
                sleep(delay)
            yield offset + t, clock(), bgr
        if t is not None:
            offset += t + (step or FALLBACK_FRAME_S)


def video_images(path: Path, realtime: bool, clock: Callable[[], float] = time.monotonic) -> Iterator[Image]:
    """A saved clip, paced like a camera unless realtime is off, so latency stays comparable."""
    return playlist_images([path], realtime, clock=clock)


def videos_in(directory: Path) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.suffix.lower() in VIDEO_SUFFIXES)


def replay_clips(paths: Sequence[Path], realtime: bool, keep_image: bool,
                 tracker: Callable[..., Iterator[Observation]] | None = None,
                 clock: Callable[[], float] = time.monotonic) -> Iterator[Clip]:
    """Each clip gets a fresh tracker, as signclip.extract gives each enrollment clip."""
    for path in paths:
        log(f"replaying {path.name}")
        yield (tracker or track)(video_images(path, realtime, clock), keep_image)


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

    def show(image: Any, overlay: Overlay) -> bool:
        view = cv2.flip(image, 1) if mirror else image.copy()
        draw_overlay(view, overlay)
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
                        help="feed every .mp4/.mov/.m4v in DIR (sorted) through the same path, each clip "
                             "calibrated on its own first 2 s")
    source.add_argument("--video", type=Path, nargs="+", metavar="CLIP",
                        help="play these clips in order as one live camera: one 2 s rest calibration at "
                             "the start, then the same detector; start with a hands-down rest clip")
    parser.add_argument("--model", choices=("signclip", "asl"), default="signclip",
                        help="signclip: personalised reference matching (default); asl: the public ASL Signs "
                             "model with the open-set rule (asl_matcher.py), no references needed")
    parser.add_argument("--bundle", type=Path, default=None,
                        help="recognition bundle (default: retrieval.py export-bundle output for signclip, "
                             "fixtures/asl/asl-bundle-provisional.json for asl)")
    parser.add_argument("--rest-y", type=float, help="skip calibration and use this rest line (0-1)")
    parser.add_argument("--no-preview", action="store_true",
                        help="no window (by default it shows the camera or clip with the latest result)")
    parser.add_argument("--no-mirror", action="store_true", help="the window is mirrored by default")
    parser.add_argument("--fast", action="store_true",
                        help="replay as fast as possible; latency then no longer means live latency")
    parser.add_argument("--handshake", action="store_true",
                        help="for mac_bridge --live: once calibrated, print a ready line and wait for "
                             f"{GO!r} on stdin (the call is connected) before recognising; clips pause "
                             "meanwhile, a camera keeps running; EOF on stdin stops")
    args = parser.parse_args(argv)
    if args.rest_y is not None and not 0 < args.rest_y < 1:
        parser.error("--rest-y must be between 0 and 1")
    paths = []
    if args.replay_videos is not None:
        if not args.replay_videos.is_dir() or not (paths := videos_in(args.replay_videos)):
            parser.error(f"no .mp4/.mov/.m4v clips in {args.replay_videos}")
    for clip in args.video or ():
        if not clip.is_file() or clip.suffix.lower() not in VIDEO_SUFFIXES:
            parser.error(f"--video: {clip} is not an .mp4/.mov/.m4v file")

    results = result_stream()
    if args.model == "asl":
        import asl_matcher as am

        matcher: Any = am.asl_matcher(args.bundle or am.DEFAULT_ASL_BUNDLE)
        tracker = am.track_kaggle
    else:
        bundle = load_bundle(args.bundle or DEFAULT_BUNDLE)
        matcher = signclip_matcher(bundle) if bundle is not None else None
        tracker = track
    show = None if args.no_preview else preview(not args.no_mirror)
    clock: Callable[[], float] = time.monotonic
    handshake = None
    if args.handshake:
        playback = None if args.camera is not None else PlaybackClock()
        clock = playback or clock
        handshake = Handshake(lambda rest_y: results.write(ready_line(rest_y) + "\n"),
                              StartSignal(sys.stdin).wait, playback)
    if args.camera is not None:
        clips: Iterable[Clip] = [tracker(camera_images(args.camera), keep_image=show is not None)]
        log(f"{REST_PROMPT}, then sign one at a time. q in the window (or Ctrl-C) stops.")
    elif args.video:
        clips = [tracker(playlist_images(args.video, realtime=not args.fast, clock=clock),
                         keep_image=show is not None)]
        log(f"playing {len(args.video)} clips as one camera: {' '.join(p.name for p in args.video)}")
    else:
        clips = replay_clips(paths, realtime=not args.fast, keep_image=show is not None, tracker=tracker,
                             clock=clock)
    # A camera, real or played from clips, asks for a new rest until calibration works.
    live = LiveSource(clips, matcher, rest_y=args.rest_y, show=show, clock=clock, handshake=handshake,
                      retry_calibration=args.camera is not None or bool(args.video))
    try:
        for recognition in live:
            results.write(result_json(recognition) + "\n")
    except KeyboardInterrupt:
        pass
    finally:
        log(live.summary())
        if show is not None:
            close_preview()
        if hasattr(matcher, "close"):
            matcher.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
