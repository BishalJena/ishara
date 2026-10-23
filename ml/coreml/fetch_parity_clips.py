"""Fetch extra public INCLUDE clips (CC-BY-4.0) so parity covers more than the 11-clip corpus.

Four clips per demo sign that INCLUDE has, chosen as the first sorted members not
already in spikes/recognition's default set. Reuses fetch_clips' range-request
reader; clips land in ml/coreml/artifacts/clips/<label>/ (gitignored).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "spikes" / "recognition"))
import fetch_clips  # noqa: E402  (spikes/recognition is not a package)

FOLDERS = {
    "Days_and_Time/73. Today": ("4615", "4617", "4618", "5031"),
    "Days_and_Time/74. Tomorrow": ("4619", "4620", "4621", "4622"),
    "Days_and_Time/82. Morning": ("4651", "4652", "4653", "4654"),
    "Days_and_Time/83. Afternoon": ("4655", "4656", "4657", "4658"),
    "Days_and_Time/84. Evening": ("4659", "4660", "4661", "4662"),
    "Days_and_Time/86. Time": ("4667", "4668", "4669", "4670"),
    "Greetings/48. Hello": ("0030", "0031", "0032", "0037"),
    "Greetings/55. Thank you": ("0006", "0007", "0008", "0058"),
    "Jobs/87. Doctor": ("4470", "4472", "4473", "4754"),
}
CLIPS = [f"{folder}/MVI_{number}.MOV" for folder, numbers in FOLDERS.items() for number in numbers]


def main() -> None:
    fetch_clips.ARTIFACTS = HERE / "artifacts"
    fetch_clips.CLIPS = fetch_clips.ARTIFACTS / "clips"
    # An interrupted transfer leaves an empty file that fetch_clips would treat as done.
    for empty in (p for p in fetch_clips.CLIPS.rglob("*.MOV") if p.stat().st_size == 0):
        empty.unlink()
    fetched = fetch_clips.fetch(CLIPS)
    if len(fetched) != len(CLIPS):
        raise SystemExit(f"Fetched {len(fetched)}/{len(CLIPS)} clips; rerun to resume")


if __name__ == "__main__":
    main()
