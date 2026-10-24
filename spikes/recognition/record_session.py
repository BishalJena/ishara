"""Guided Sign Lab enrollment: a few takes of each of the 12 demo signs in one sitting.

    .venv/bin/python record_session.py --camera 0
    .venv/bin/python record_session.py --camera 0 --session signlab-20261024   # resume

For each sign (PLAN §5 order) it shows the sign, a one-line hint and where to watch
the public reference. Per take: hands resting on the table, SPACE, a 3-2-1 countdown
(the rest line is measured on it), then sign once and drop your hands. The start/stop
detector ends the take by itself after about 0.4 s of rest and keeps exactly the
detector's cut, the same frames the live recognizer will match. The take then
replays with the tracking overlay: K keeps it, R redoes it.

A kept take is saved to the pilot manifest (split enrollment, one session ID) and
marked verified with the signer's confirmation note. Q quits; kept takes stay saved,
and running again with the same --session skips signs that already have enough.
Reference videos are only linked, never downloaded or redistributed here.
"""
from __future__ import annotations

import argparse
import math
import time
import uuid
from collections import deque
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol

import recognition_data as data
from detect_clips import within
from detector import CalibrationError, Frame, Params, Segment, SignDetector, State, calibrate
from pilot_capture import MAX_BYTES, MAX_FRAMES, save_take

SOURCES = {
    "INCLUDE": "INCLUDE (CC-BY-4.0, https://zenodo.org/records/4010759)",
    "ISLRTC": "ISLRTC dictionary (bridgeconn copy: https://huggingface.co/datasets/bridgeconn/sign-dictionary-isl)",
}
HEAD = "The reference uses head movement too: keep your face in frame."


@dataclass(frozen=True)
class Guide:
    hint: str  # what the sign is for; the sign form itself comes from the reference
    source: str  # a SOURCES key
    entry: str  # the INCLUDE folder or dictionary word to watch

    @property
    def reference(self) -> str:
        return f"{SOURCES[self.source]}: {self.entry}"

    @property
    def short_reference(self) -> str:  # fits the window; the terminal prints the link
        return f"Watch: {self.source} {self.entry}"


GUIDES = {
    "hello": Guide("Greeting that opens the call.", "INCLUDE", "Greetings/48. Hello"),
    "thankyou": Guide("Thanks at the end of the call.", "INCLUDE", "Greetings/55. Thank you"),
    "yes": Guide(f"Answer yes. {HEAD}", "ISLRTC", "'yes'"),
    "no": Guide(f"Answer no. {HEAD}", "ISLRTC", "'no'"),
    "sorry": Guide("Apology, for repairs (spare).", "ISLRTC", "'sorry'"),
    "doctor": Guide("The person you want to see.", "INCLUDE", "Jobs/87. Doctor"),
    "today": Guide("Day: today (spare).", "INCLUDE", "Days_and_Time/73. Today"),
    "tomorrow": Guide("Day: tomorrow.", "INCLUDE", "Days_and_Time/74. Tomorrow"),
    "morning": Guide("Part of the day: morning.", "INCLUDE", "Days_and_Time/82. Morning"),
    "afternoon": Guide("Part of the day: afternoon (spare).", "INCLUDE", "Days_and_Time/83. Afternoon"),
    "evening": Guide("Part of the day: evening (spare).", "INCLUDE", "Days_and_Time/84. Evening"),
    "time": Guide("Asking about the time (spare).", "INCLUDE", "Days_and_Time/86. Time"),
}
assert tuple(GUIDES) == data.VOCABULARY

FRAMING = (
    "Sit so your face, shoulders and both hands are in the frame.",
    "Between signs, rest both hands on the table and keep still.",
    "After each sign, drop your hands and hold still for about half a second.",
)
COUNTDOWN_S = 3.0  # also the rest the detector calibrates on; must cover Params.calibration_s
NO_SIGN_S = 8.0  # after GO, give up if the hands never leave the rest
SPACE, KEEP, REDO, DISCARD, QUIT = ord(" "), ord("k"), ord("r"), ord("x"), ord("q")
ESCAPE = 27
DEFAULT_PARAMS = Params()


class Camera(Protocol):
    def read(self) -> tuple[bool, Any]: ...


@dataclass(frozen=True)
class Tracked:
    """One camera frame: the raw image (saved), the detector input and the overlay data."""
    t: float
    image: Any
    frame: Frame
    landmarks: Any = None


Track = Callable[[float, Any], "tuple[Frame, Any]"]  # (clock time, BGR) -> detector frame, overlay data


class Screen(Protocol):
    """phase is one of ready/countdown/recording/review; returns the pressed key or -1."""
    def show(self, tracked: Tracked, phase: str, lines: Sequence[str], big: str | None = None,
             delay_ms: int = 1) -> int: ...


@dataclass(frozen=True)
class Take:
    frames: list[Tracked]
    cut: str  # "detector" or "manual"

    @property
    def quality(self) -> dict[str, float]:
        """The two fractions SignCLIP's decision checks, from the same Holistic results."""
        count = max(len(self.frames), 1)
        return {"pose_fraction": sum(f.frame.body for f in self.frames) / count,
                "hand_fraction": sum(bool(f.frame.wrists) for f in self.frames) / count}


class Quit(Exception):
    """The signer pressed Q: stop the session, keeping what was already saved."""


class Recorder:
    """Camera loop for one take at a time: ready, countdown, recording, replay."""

    def __init__(self, camera: Camera, track: Track, screen: Screen, *, params: Params = DEFAULT_PARAMS,
                 auto_stop: bool = True, clock: Callable[[], float] = time.monotonic) -> None:
        if COUNTDOWN_S < params.calibration_s:
            raise ValueError("The countdown must be long enough to calibrate the rest line")
        self.camera, self.track, self.screen, self.params = camera, track, screen, params
        self.auto_stop, self.clock = auto_stop, clock

    def _next(self) -> Tracked:
        ok, image = self.camera.read()
        t = self.clock()
        if not ok:
            raise ValueError("Camera stopped; the unfinished take is discarded")
        frame, landmarks = self.track(t, image)
        return Tracked(t, image, frame, landmarks)

    def _show(self, tracked: Tracked, phase: str, lines: Sequence[str], **kwargs: Any) -> int:
        key = self.screen.show(tracked, phase, lines, **kwargs)
        if key in (QUIT, ESCAPE):
            raise Quit
        return key

    def record(self, header: Sequence[str]) -> Take:
        """Loops until one take is complete; problems show a message and start over."""
        message = "Hands resting on the table, then SPACE (3-2-1, then sign once)."
        while True:
            while self._show(self._next(), "ready", [*header, *FRAMING, message]) != SPACE:
                pass
            take, message = self._attempt(header)
            if take is not None:
                return take

    def _attempt(self, header: Sequence[str]) -> tuple[Take | None, str]:
        start = self.clock()
        rest: list[Tracked] = []
        while not rest or rest[-1].t - start < COUNTDOWN_S:
            tracked = self._next()
            rest.append(tracked)
            left = max(1, math.ceil(COUNTDOWN_S - (tracked.t - start)))
            self._show(tracked, "countdown", [*header, "Keep your hands resting..."], big=str(left))
        # Only the last second of countdown images can fall in the detector's pre-roll;
        # dropping the rest keeps a 720p take well under a gigabyte.
        rest_frames, recent = [r.frame for r in rest], deque(r for r in rest if r.t >= rest[-1].t - 1.0)
        del rest
        if not self.auto_stop:
            return self._manual(header)
        try:
            rest_y = calibrate(rest_frames, self.params)
        except CalibrationError as error:
            return None, (f"Couldn't measure the rest ({error.reason}): keep shoulders in view and "
                          "hands still on the table. SPACE to retry.")
        detector = SignDetector(rest_y, self.params)
        # The countdown is a rest, so it only primes the detector, as in live_source.
        primed = [e for f in rest_frames for e in detector.update(f) if isinstance(e, Segment)]
        if primed or detector.state is not State.WATCHING:
            return None, "Your hands moved during the countdown. Keep them down until GO; SPACE to retry."
        keep_s = self.params.pre_roll_s + self.params.max_sign_s + self.params.end_rest_s + 0.5
        go = recent[-1].t
        while True:
            tracked = self._next()
            recent.append(tracked)
            while recent[0].t < tracked.t - keep_s:
                recent.popleft()
            for event in detector.update(tracked.frame):
                if isinstance(event, Segment):
                    if not event.accepted:
                        return None, f"Take not usable ({event.reason.replace('_', ' ')}). SPACE to redo."
                    return Take([r for r in recent if within(r.t, event)], "detector"), ""
            if detector.state is State.WATCHING and tracked.t - go > NO_SIGN_S:
                return None, "No sign seen (hands stayed below the rest line). SPACE to retry."
            status = "SIGNING" if detector.state is State.SIGNING else "GO: sign once, then drop your hands"
            if self._show(tracked, "recording", [*header, status, "X discards"]) == DISCARD:
                return None, "Discarded. SPACE for a new take."

    def _manual(self, header: Sequence[str]) -> tuple[Take | None, str]:
        frames: list[Tracked] = []
        while True:
            tracked = self._next()
            if len(frames) >= MAX_FRAMES or (len(frames) + 1) * tracked.image.nbytes > MAX_BYTES:
                return None, "Take too long; discarded rather than cut. SPACE to retry."
            frames.append(tracked)
            key = self._show(tracked, "recording",
                             [*header, "RECORDING: sign, rest, then SPACE stops", "X discards"])
            if key == DISCARD:
                return None, "Discarded. SPACE for a new take."
            if key == SPACE:
                return Take(frames, "manual"), ""

    def review(self, take: Take, header: Sequence[str]) -> bool:
        """Replays the take with the tracking overlay until K (keep) or R (redo)."""
        quality = take.quality
        weak = (quality["pose_fraction"] < data.QUALITY["min_pose_fraction"]
                or quality["hand_fraction"] < data.QUALITY["min_hand_fraction"])
        lines = [*header, f"Replay: shoulders {quality['pose_fraction']:.0%}, hands {quality['hand_fraction']:.0%}"
                 + ("  WEAK TRACKING: redo recommended" if weak else ""),
                 "K keeps (you confirm it matches the reference) | R redoes"]
        span = take.frames[-1].t - take.frames[0].t
        delay = max(1, round(1000 * span / max(len(take.frames) - 1, 1)))
        while True:
            for tracked in take.frames:
                key = self._show(tracked, "review", lines, delay_ms=delay)
                if key in (KEEP, REDO):
                    return key == KEEP


def local_references(sign: str) -> list[str]:
    """Public INCLUDE clips that fetch_clips.py already saved under artifacts/clips/<sign>."""
    folder = data.ARTIFACTS / "clips" / sign
    return sorted(str(p) for p in folder.iterdir() if p.is_file()) if folder.is_dir() else []


def verification_note(sign: str) -> str:
    return (f"Self-checked during guided Sign Lab session against {GUIDES[sign].reference}; "
            "the signer confirmed this take after replaying it with the tracking overlay")


def kept_counts(records: Sequence[dict], signer: str, session: str) -> dict[str, int]:
    """Verified enrollment takes already saved in this session, per sign."""
    counts = dict.fromkeys(data.VOCABULARY, 0)
    for row in records:
        if (row["signer_id"], row["session_id"], row["split"]) == (signer, session, "enrollment") \
                and row["verified"] and row["label"] in counts:
            counts[row["label"]] += 1
    return counts


def metadata(signer: str, session: str, sign: str, cut: str) -> dict[str, Any]:
    how = "detector cut" if cut == "detector" else "SPACE start/stop"
    return {"signer_id": signer, "session_id": session, "split": "enrollment", "label": sign,
            "negative_kind": None,
            "provenance": f"Local camera; guided Sign Lab session (record_session.py, {how}); "
                          "intended label supplied by signer"}


def preflight(manifest, signer: str, session: str) -> list[dict]:
    """Fail on a session ID that another split already uses, before opening the camera."""
    records = data.load_dataset(manifest)
    candidate = {**metadata(signer, session, data.VOCABULARY[0], "detector"),
                 "id": uuid.uuid4().hex, "source_id": uuid.uuid4().hex, "path": "pilot/preflight.mp4",
                 "sha256": "0" * 64, "verified": False, "verification_note": ""}
    data.validate_records(records + [candidate], verify_files=False)
    return records


def run_session(recorder: Recorder, *, manifest, signer: str, session: str, takes: int,
                out: Callable[[str], None] = print) -> dict[str, int]:
    """Walks the 12 signs in order; returns the kept count per sign (this session)."""
    counts = kept_counts(preflight(manifest, signer, session), signer, session)
    out(f"Sign Lab session {session!r} (signer {signer!r}), {takes} takes per sign.")
    for line in FRAMING:
        out(f"  - {line}")
    try:
        for number, sign in enumerate(data.VOCABULARY, 1):
            guide = GUIDES[sign]
            if counts[sign] >= takes:
                out(f"[{number}/12] {sign}: {counts[sign]} kept already, skipping.")
                continue
            out(f"\n[{number}/12] {sign.upper()}: {guide.hint}\n  Reference: {guide.reference}")
            for clip in local_references(sign):
                out(f"  Local copy: {clip}")
            while counts[sign] < takes:
                header = [f"[{number}/12] {sign.upper()}  take {counts[sign] + 1}/{takes}", guide.hint,
                          guide.short_reference]
                take = recorder.record(header)
                if not recorder.review(take, header):
                    out(f"  {sign}: redo")
                    continue
                try:
                    row = save_take([f.image for f in take.frames], [f.t for f in take.frames],
                                    metadata(signer, session, sign, take.cut), manifest,
                                    verification_note=verification_note(sign))
                except ValueError as error:  # e.g. too few frames: say so and record again
                    out(f"  {sign}: not saved ({error}); please redo")
                    continue
                counts[sign] += 1
                out(f"  {sign}: kept {counts[sign]}/{takes} ({len(take.frames)} frames, id {row['id']})")
    except Quit:
        out(f"\nStopped. Kept takes are saved; resume with --session {session}.")
        return counts
    out("\nAll 12 signs recorded. Next: build the provisional try bundle, then open the Sign Lab:\n"
        "  artifacts/signclip/.venv/bin/python retrieval.py export-bundle --encoder signclip --provisional\n"
        "  ../../scripts/sign_lab.sh")
    return counts


# ---- real camera, Holistic and window: these need the full .venv ----

@contextmanager
def holistic_tracker() -> Iterator[Track]:
    import cv2

    from detect_clips import holistic, to_frame

    with holistic() as tracker:
        def track(t: float, image: Any) -> tuple[Frame, Any]:
            result = tracker.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            return to_frame(t, result), result

        yield track


class Window:
    TITLE = "Ishara Sign Lab recording"

    def __init__(self, mirror: bool) -> None:
        self.mirror = mirror

    def show(self, tracked: Tracked, phase: str, lines: Sequence[str], big: str | None = None,
             delay_ms: int = 1) -> int:
        import cv2
        import mediapipe as mp

        view = tracked.image.copy()
        if phase == "review" and tracked.landmarks is not None:
            holistic = mp.solutions.holistic
            for landmarks, connections in ((tracked.landmarks.pose_landmarks, holistic.POSE_CONNECTIONS),
                                           (tracked.landmarks.left_hand_landmarks, holistic.HAND_CONNECTIONS),
                                           (tracked.landmarks.right_hand_landmarks, holistic.HAND_CONNECTIONS)):
                if landmarks:
                    mp.solutions.drawing_utils.draw_landmarks(view, landmarks, connections)
        if self.mirror:
            view = cv2.flip(view, 1)
        view = cv2.resize(view, (960, int(view.shape[0] * 960 / view.shape[1])))
        colour = {"recording": (20, 30, 230), "countdown": (0, 200, 255)}.get(phase, (40, 220, 40))
        for row, text in enumerate(lines):
            cv2.putText(view, text, (12, 28 + 26 * row), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4)
            cv2.putText(view, text, (12, 28 + 26 * row), cv2.FONT_HERSHEY_SIMPLEX, 0.55, colour, 1)
        if big:
            cv2.putText(view, big, (430, view.shape[0] // 2 + 60), cv2.FONT_HERSHEY_SIMPLEX, 6, colour, 12)
        cv2.imshow(self.TITLE, view)
        key = cv2.waitKey(delay_ms) & 0xFF
        if cv2.getWindowProperty(self.TITLE, cv2.WND_PROP_VISIBLE) < 1:
            return QUIT
        return key if key != 255 else -1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=data.Path, default=data.DATASET)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--signer", default="demo", help="Local pseudonym, not a person's name")
    parser.add_argument("--session", default=f"signlab-{time.strftime('%Y%m%d')}",
                        help="One ID for the whole sitting; reuse it to resume (default: %(default)s)")
    parser.add_argument("--takes", type=int, default=3, help="Kept takes per sign (default: %(default)s)")
    parser.add_argument("--manual-stop", action="store_true",
                        help="SPACE also stops each take (whole take kept) instead of the detector")
    parser.add_argument("--no-mirror", action="store_true", help="The window is mirrored by default")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    from detect_clips import open_camera

    parser = build_parser()
    args = parser.parse_args(argv)
    if not 1 <= args.takes <= 10:
        parser.error("--takes must be between 1 and 10")
    preflight(args.manifest, args.signer, args.session)
    camera = open_camera(args.camera)
    try:
        with holistic_tracker() as track:
            recorder = Recorder(camera, track, Window(not args.no_mirror), auto_stop=not args.manual_stop)
            counts = run_session(recorder, manifest=args.manifest, signer=args.signer,
                                 session=args.session, takes=args.takes)
    finally:
        import cv2

        camera.release()
        cv2.destroyAllWindows()
    return 0 if all(c >= args.takes for c in counts.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
