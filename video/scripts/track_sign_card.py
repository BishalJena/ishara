"""Where the sign panel's camera card is in the app recording, every 0.1 s.

    cd video && python3 scripts/track_sign_card.py

Writes public/sign-card.json: [{"t": recording seconds, "box": [x, y, w, h] in recording
pixels}], so the founder's sign clip can be composited over the card as it moves (it rises
when the "Ishara will say" draft appears). The card is the only solid dark block at the
panel's left edge; its edge column is tracked, merging the gap the status pill leaves.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
W, H = 402, 874  # the recording (1206 × 2622) at 1/3


def main() -> None:
    events = json.loads((ROOT / "public/audio/manifest.json").read_text())["events"]
    held = [e for e in events if e["kind"] == "resolved" and e.get("outcome") == "held"][-1]["t"]
    speaking = next(e for e in events if e["kind"] == "status" and e.get("state") == "speaking")["t"]
    t0, t1 = held - 0.2, speaking + 2.5
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t0}", "-t", f"{t1 - t0}", "-i", str(ROOT / "raw/app.mp4"),
         "-vf", f"fps=10,scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
        check=True, capture_output=True,
    ).stdout
    track = []
    for i in range(len(out) // (W * H)):
        frame = out[i * W * H:(i + 1) * W * H]
        dark = [y for y in range(int(H * 0.4), H - 10) if frame[y * W + 19] < 90 and frame[y * W + 22] < 90]
        runs: list[list[int]] = []
        for y in dark:
            if runs and y - runs[-1][1] <= 14:
                runs[-1][1] = y
            else:
                runs.append([y, y])
        card = next((r for r in runs if 100 <= r[1] - r[0] <= 140), None)
        if card:
            box = [33, card[0] * 3 - 3, 294, (card[1] - card[0] + 1) * 3 + 6]
            track.append({"t": round(t0 + i / 10, 2), "box": box})
    (ROOT / "public/sign-card.json").write_text(json.dumps(track))
    print(f"tracked the camera card in {len(track)} frames")


if __name__ == "__main__":
    main()
