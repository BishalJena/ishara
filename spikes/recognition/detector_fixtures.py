"""Readable scenarios for the start/stop detector, expanded into shared JSON fixtures.

    python detector_fixtures.py     # rewrites fixtures/detector/*.json

Expectations are written by hand from the specification, never produced by running
the detector, so the Python and Swift detectors are both checked against them.
Frames are 30 fps on t = round(t0 + i / 30, 4); ("at", kind, t) inserts one
off-grid frame (camera jitter) and continues the 30 fps grid from it.
"""
from __future__ import annotations

import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "detector"
FPS = 30
REST, UP, GONE, HANDS_ONLY, NO_HANDS = "rest", "up", "gone", "hands_only", "no_hands"
KINDS = {  # kind: (shoulders visible, wrists)
    REST: (True, ((0.40, 0.90), (0.60, 0.90))),
    UP: (True, ((0.45, 0.55), (0.60, 0.90))),
    GONE: (False, ()),
    HANDS_ONLY: (False, ((0.45, 0.55),)),  # too close: a raised hand without shoulders
    NO_HANDS: (True, ()),  # hands below the frame edge
    "on_line": (True, ((0.40, 0.80), (0.60, 0.80))),  # exactly on the default rest line
    "above_line": (True, ((0.45, 0.79), (0.60, 0.90))),
    "high": (True, ((0.40, 0.30), (0.60, 0.30))),
    "bottom": (True, ((0.40, 0.98), (0.60, 0.98))),
    "mixed": (True, ((0.40, 0.86), (0.60, 0.90))),
}
CALIBRATION = [(REST, 61)]  # exactly 2.0 s; rest line 0.90 - 0.08 = 0.82


def T(i: int, t0: float = 0.0) -> float:
    """Time of grid frame i."""
    return round(t0 + i / FPS, 4)


def build(steps, t0: float = 0.0) -> list[dict]:
    frames, base, k = [], t0, 0
    for step in steps:
        if step[0] == "at":
            _, kind, t = step
            base, k, runs = t, 0, [kind]
        else:
            kind, count = step
            runs = [kind] * count
        for kind in runs:
            body, wrists = KINDS[kind]
            frames.append({"t": round(base + k / FPS, 4), "body": body, "wrists": [list(w) for w in wrists]})
            k += 1
    return frames


def seg(start: float, end: float, accepted: bool = True, reason: str | None = None) -> dict:
    return {"start": round(start, 4), "end": round(end, 4), "accepted": accepted, "reason": reason}


def scenario(name, frames=(), segments=(), statuses=(), calibration=CALIBRATION, params=None,
             rest_y=0.82, error=None, t0=0.0) -> dict:
    return {"name": name, "params": params or {}, "calibration": build(calibration),
            "frames": build(frames, t0), "expected_rest_y": None if error else rest_y,
            "expected_calibration_error": error, "expected_segments": list(segments),
            "expected_statuses": list(statuses)}


W, S, C = "watching", "signing", "cant_see"
SCENARIOS = [
    # Rest from frame 60 (2.0 s) reaches exactly 0.40 s on frame 72, whose float gap is
    # 0.3999999999999999, so the 1e-9 tolerance matters. The next raise is a new sign.
    scenario("rest_exactly_0_40_s_ends_sign",
             [(REST, 30), (UP, 30), (REST, 13), (UP, 30), (REST, 30)],
             [seg(T(30) - 0.2, T(60)), seg(T(73) - 0.2, T(103))], [W, S, W, S, W]),
    # Rest from 2.0 s to a jittered frame at 2.39 s is 0.39 s: still the same sign.
    scenario("rest_0_39_s_does_not_end_sign",
             [(REST, 30), (UP, 30), (REST, 12), ("at", REST, 2.39), (UP, 30), (REST, 30)],
             [seg(T(30) - 0.2, round(2.39 + 31 / FPS, 4))], [W, S, W]),
    # Hands already up on the first frame: pre-roll clamps to t = 0, so the end on
    # frame 9 makes the duration exactly 0.30 s (float 0.3 == 0.3).
    scenario("sign_exactly_0_30_s_accepted", [(UP, 9), (REST, 20)],
             [seg(0.0, T(9))], [W, S, W]),
    scenario("sign_0_27_s_rejected_too_short", [(UP, 8), (REST, 20)],
             [seg(0.0, T(8), False, "too_short")], [W, S, W]),
    # 4 raised frames from 1.0333 s span 0.0999999 s in floats: enough to start.
    scenario("raise_exactly_0_10_s_starts_sign", [(REST, 31), (UP, 4), (REST, 30)],
             [seg(T(31) - 0.2, T(35))], [W, S, W]),
    # A 0.05 s twitch, a 0.067 s raise and 0.33 s of a hand without shoulders start nothing.
    scenario("fidgets_ignored",
             [(REST, 30), (UP, 1), ("at", UP, 1.05), (REST, 30), (UP, 3), (REST, 30),
              (HANDS_ONLY, 10), (REST, 30)],
             [], [W]),
    # Start 0.8 s; t - start is exactly 4.0 on frame 144 (not over), over on frame 145.
    # COOLDOWN ignores a raise after a short rest; only a full rest re-arms detection.
    scenario("sign_over_4_s_rejected_then_cooldown_until_rest",
             [(REST, 30), (UP, 135), (REST, 6), (UP, 10), (REST, 20), (UP, 10), (REST, 20)],
             [seg(T(30) - 0.2, T(145), False, "too_long"), seg(T(201) - 0.2, T(211))],
             [W, S, W, S, W]),
    # Body lost from frame 50; 0.5 s later (frame 65) the sign is dropped. Coming back
    # with a hand up waits in COOLDOWN (yellow) until the hands rest.
    scenario("lost_tracking_mid_sign",
             [(REST, 30), (UP, 20), (GONE, 20), (UP, 10), (REST, 20)],
             [seg(T(30) - 0.2, T(65), False, "lost_tracking")], [W, S, C, S, W]),
    # A 0.43 s dropout is neither rest nor body loss: the sign continues.
    scenario("brief_dropout_keeps_sign",
             [(REST, 30), (UP, 10), (GONE, 14), (UP, 10), (REST, 20)],
             [seg(T(30) - 0.2, T(64))], [W, S, W]),
    scenario("cant_see_while_watching_returns_at_rest",
             [(REST, 30), (GONE, 20), (REST, 20), (UP, 10), (REST, 20)],
             [seg(T(70) - 0.2, T(80))], [W, C, W, S, W]),
    scenario("long_pauses_produce_nothing", [(REST, 600), (NO_HANDS, 150), (REST, 300)], [], [W]),
    # First frame at 10.0 s: the first sign's pre-roll clamps to it, the second's doesn't.
    scenario("two_signs_with_pre_roll_clamping",
             [(REST, 3), (UP, 15), (REST, 20), (UP, 15), (REST, 20)],
             [seg(10.0, T(18, 10.0)), seg(T(38, 10.0) - 0.2, T(53, 10.0))], [W, S, W, S, W], t0=10.0),
    # No wrists in calibration -> default line 0.80; a wrist exactly on it counts as rest.
    scenario("wrist_on_rest_line_is_rest", [("on_line", 30), ("above_line", 15), (REST, 20)],
             [seg(T(30) - 0.2, T(45))], [W, S, W], calibration=[(NO_HANDS, 61)], rest_y=0.80),
    scenario("calibration_too_short", calibration=[(REST, 60)], error="too_short"),
    scenario("calibration_too_short_checked_before_cant_see", calibration=[(GONE, 60)], error="too_short"),
    scenario("calibration_cant_see", calibration=[(REST, 28), (GONE, 15), (REST, 27)], error="cant_see"),
    scenario("calibration_body_exactly_80_percent", calibration=[(REST, 28), (GONE, 14), (REST, 28)]),
    scenario("calibration_no_wrists_uses_default", calibration=[(NO_HANDS, 61)], rest_y=0.80),
    scenario("calibration_clamped_low", calibration=[("high", 61)], rest_y=0.50),
    # With valid y <= 1 the default margin can never exceed 0.95, so drop the margin.
    scenario("calibration_clamped_high", calibration=[("bottom", 61)], params={"rest_margin": 0.0}, rest_y=0.95),
    # 61 wrists at 0.86 and 61 at 0.90: median averages the middle pair (0.88).
    scenario("calibration_median_of_even_count", calibration=[("mixed", 61)], rest_y=0.80),
    # A raised hand during calibration doesn't drag the line up (mean would give 0.72).
    scenario("calibration_median_ignores_raised_hand", calibration=[(REST, 51), ("high", 10)], rest_y=0.82),
]


def dump(fixture: dict) -> str:
    """JSON with one frame or segment per line so diffs stay readable."""
    lines = []
    for key, value in fixture.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            rows = ",\n".join("    " + json.dumps(row) for row in value)
            lines.append(f"  {json.dumps(key)}: [\n{rows}\n  ]")
        else:
            lines.append(f"  {json.dumps(key)}: {json.dumps(value)}")
    return "{\n" + ",\n".join(lines) + "\n}\n"


def main():
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for stale in FIXTURES.glob("*.json"):
        stale.unlink()
    for fixture in SCENARIOS:
        (FIXTURES / f"{fixture['name']}.json").write_text(dump(fixture))
    print(f"wrote {len(SCENARIOS)} fixtures to {FIXTURES}")


if __name__ == "__main__":
    main()
