"""Start/stop detector: cuts one isolated sign at a time from per-frame wrist heights.

Pure state machine (stdlib only) shared with the Swift port through the JSON
fixtures in fixtures/detector/. Hands above the calibrated rest line start a
sign; hands back at rest for end_rest_s end it. Body loss, too-short and too-long
segments are rejected so they are never matched or spoken.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Sequence

EPSILON = 1e-9
Status = Literal["watching", "signing", "cant_see"]


@dataclass(frozen=True)
class Params:
    calibration_s: float = 2.0
    rest_margin: float = 0.08
    default_rest_y: float = 0.80
    rest_y_min: float = 0.50
    rest_y_max: float = 0.95
    min_body_fraction: float = 0.8
    start_hold_s: float = 0.10
    end_rest_s: float = 0.40
    pre_roll_s: float = 0.20
    min_sign_s: float = 0.30
    max_sign_s: float = 4.0
    lost_body_s: float = 0.50


@dataclass(frozen=True)
class Frame:
    """t in monotonic seconds; wrists are normalized image (x, y), y grows downward."""
    t: float
    body: bool
    wrists: tuple[tuple[float, float], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class StatusChanged:
    status: Status


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    accepted: bool
    reason: str | None


Event = StatusChanged | Segment


class CalibrationError(ValueError):
    def __init__(self, reason: Literal["too_short", "cant_see"]):
        super().__init__(reason)
        self.reason = reason


class State(Enum):
    WATCHING = "watching"
    SIGNING = "signing"
    COOLDOWN = "cooldown"
    CANT_SEE = "cant_see"


STATUS: dict[State, Status] = {State.WATCHING: "watching", State.SIGNING: "signing",
                               State.COOLDOWN: "signing", State.CANT_SEE: "cant_see"}


def calibrate(frames: Sequence[Frame], params: Params = Params()) -> float:
    """Rest line from a still, hands-down period: slightly above the median wrist height."""
    if not frames or frames[-1].t - frames[0].t < params.calibration_s:
        raise CalibrationError("too_short")
    if sum(f.body for f in frames) / len(frames) < params.min_body_fraction:
        raise CalibrationError("cant_see")
    heights = [y for f in frames for _, y in f.wrists]
    if not heights:
        return params.default_rest_y
    return min(max(statistics.median(heights) - params.rest_margin, params.rest_y_min), params.rest_y_max)


def held(since: float | None, t: float, duration: float) -> bool:
    return since is not None and t - since >= duration - EPSILON


class SignDetector:
    def __init__(self, rest_y: float, params: Params = Params()):
        self.rest_y, self.params = rest_y, params
        self.state = State.WATCHING
        self.status: Status | None = None  # nothing emitted yet, so the first frame reports "watching"
        self.start: float | None = None
        self._first_t: float | None = None
        self._last_t: float | None = None
        self._active_since: float | None = None
        self._rest_since: float | None = None
        self._lost_since: float | None = None

    def update(self, frame: Frame) -> list[Event]:
        t, p = frame.t, self.params
        if self._last_t is not None and t < self._last_t:
            raise ValueError("Frame times must not go backwards")
        self._last_t = t
        if self._first_t is None:
            self._first_t = t
        active = frame.body and any(y < self.rest_y for _, y in frame.wrists)
        rest = frame.body and not active
        self._active_since = (t if self._active_since is None else self._active_since) if active else None
        self._rest_since = (t if self._rest_since is None else self._rest_since) if rest else None
        self._lost_since = None if frame.body else (t if self._lost_since is None else self._lost_since)

        events: list[Event] = []
        if self.state is not State.CANT_SEE and held(self._lost_since, t, p.lost_body_s):
            if self.state is State.SIGNING:
                events.append(self._close(t, False, "lost_tracking"))
            self.state = State.CANT_SEE
        elif self.state is State.CANT_SEE:
            if frame.body:
                self.state = State.WATCHING if rest else State.COOLDOWN
        elif self.state is State.WATCHING:
            if held(self._active_since, t, p.start_hold_s):
                self.start = max(self._first_t, self._active_since - p.pre_roll_s)
                self.state = State.SIGNING
        elif self.state is State.SIGNING:
            if held(self._rest_since, t, p.end_rest_s):
                end = self._rest_since
                accepted = end - self.start >= p.min_sign_s
                events.append(self._close(end, accepted, None if accepted else "too_short"))
                self.state = State.WATCHING
            elif t - self.start > p.max_sign_s:
                events.append(self._close(t, False, "too_long"))
                self.state = State.COOLDOWN
        elif held(self._rest_since, t, p.end_rest_s):  # COOLDOWN
            self.state = State.WATCHING

        if STATUS[self.state] != self.status:
            self.status = STATUS[self.state]
            events.append(StatusChanged(self.status))
        return events

    def _close(self, end: float, accepted: bool, reason: str | None) -> Segment:
        segment = Segment(self.start, end, accepted, reason)
        self.start = None
        return segment
