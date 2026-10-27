"""Public per-word ASL clips for the Gate 2 run on public data (Run 5 of docs/experiments/asl-model-probe.md).

Local evaluation only: everything lands in the gitignored OUT directory (default
spikes/recognition/artifacts/T03) and nothing is uploaded. Three steps, in order:

    python3 public_clips.py fetch            # raw/ + raw/sources.json         (any python3; yt-dlp on PATH)
    python3 public_clips.py prep             # landscape/, portrait/, manifest.json   (ffmpeg on PATH)
    ../recognition/.venv/bin/python public_clips.py rest   # rest-only negatives (MediaPipe)

Sources: Lifeprint / ASL University (Bill Vicars) YouTube videos and site clips, ASL Signbank
(CC BY-NC-SA 4.0), and per-word dictionary videos aggregated by SignASL.org (copyright of each
original publisher). Never ASL Citizen. Clips are named `<label>_<source>-<key>.mp4`, the
asl_summary.py convention; negatives are `none_...`.

landscape/ is the whole clip as H.264 (the simulator can't decode VP9 or AV1), no audio, height
capped at 480. portrait/ is a centred 9:16 crop of the same frames scaled to 360x640: a hand that
leaves the crop is gone, as on a phone held upright. Lifeprint videos whose page caption marks a
modified form (ALL-MORNING, EVERY-MORNING, WAIT-a-long-time) or a sample sentence are set aside in
excluded/ so every scored clip is one citation-form sign.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE.parent / "recognition" / "artifacts" / "T03"
UA = {"User-Agent": "Mozilla/5.0"}
FACE, HAND, POSE = 468, 21, 33
LEFT, RIGHT = FACE, FACE + HAND + POSE

LIFEPRINT_YT = {"thankyou": ["2W0BDFUjsG0"], "yes": ["0usayvOXzHo"], "no": ["QJXKaOSyl4o"], "now": ["g2j70neQ_lI"],
                "please": ["rnb9FxPO7is"], "tomorrow": ["6gFOZMDptIk", "E17VasimjWo"],
                "morning": ["PKrGMspKng4", "iH8N44QMh7c", "jMJYpa-xIjI", "pzDK3fj_Jsg"],
                "wait": ["4gAd3p_Jgq8", "6GXWaW1omCI", "El-hYok08Qk", "YfwgS9ZsBVw"]}
LIFEPRINT_SITE = {"hello": ["https://www.lifeprint.com/asl101/videos/hi.mp4"]}
SIGNBANK_SIGNS = {"hello": [482], "thankyou": [1198], "yes": [1472], "no": [512], "now": [517], "please": [527],
                  "tomorrow": [301], "morning": [190, 2537], "wait": [1405]}
# Signs outside the bundle's vocabulary: SORRY, HAPPY, GOOD, NAME, AFTERNOON, WEEK, HOSPITAL, MEDICINE,
# DOCTOR, BYE-BYE, MOTHER, FATHER, DEAF, FINE, NOSE, NOT, NORTH, THANKSGIVING, WAITER, HOPE, NOT-YET, NONE.
SIGNBANK_NEGATIVES = [566, 476, 472, 511, 6, 1418, 1759, 1621, 344, 425, 509, 452, 103, 455, 514, 515, 645, 3142,
                      3116, 1760, 200, 513]
SIGNASL_PAGES = {"hello": "hello", "thankyou": "thank-you", "yes": "yes", "no": "no", "now": "now",
                 "please": "please", "tomorrow": "tomorrow", "morning": "morning", "wait": "wait"}
# Listed on those pages but another word or a compound (or Signbank, fetched directly above).
SIGNASL_SKIP = re.compile(r"good|every|immediately|thanks|HOPE|waiting|aslsignbank", re.I)
EXCLUDED = {
    "morning_lifeprint-yt-PKrGMspKng4": "ALL-MORNING (modified form), per the Lifeprint page caption",
    "morning_lifeprint-yt-jMJYpa-xIjI": "EVERY-MORNING (modified form), per the Lifeprint page caption",
    "morning_lifeprint-yt-pzDK3fj-Jsg": "sample sentence NOW MORNING EAT WHAT, not an isolated sign",
    "wait_lifeprint-yt-6GXWaW1omCI": "sample sentence SUPPOSE TEACHER NOT COME, WAIT HALF-HOUR YOU",
    "wait_lifeprint-yt-El-hYok08Qk": "WAIT-a-long-time (modified form), per the Lifeprint page caption",
    "wait_lifeprint-yt-4gAd3p-Jgq8": "WAIT-[long] inside a sample sentence, modified form",
}
LANDSCAPE = "scale=-2:'min(480,ih)',scale=trunc(iw/2)*2:trunc(ih/2)*2"
PORTRAIT = "crop='trunc(ih*9/16/2)*2':ih,scale=360:640,setsar=1"
REST_MIN_S, REST_MAX, REST_PER_SOURCE, REST_BOTTOM = 1.0, 10, 2, 0.85


# ---- naming and rest detection (pure) ----

def clip_name(label: str, source: str, key: str) -> str:
    """`<label>_<source>-<key>.mp4`; the label is everything before the first `_`, `-` or space."""
    source = source.replace("/", "-").replace("signasl-", "")
    key = re.sub(r"[^A-Za-z0-9-]+", "-", key).strip("-")
    return f"{label}_{source}-{key}.mp4"


def resting(landmarks: np.ndarray, bottom: float = REST_BOTTOM) -> np.ndarray:
    """Per frame: no hand in the picture, or every tracked hand point below `bottom` of the frame height."""
    def up(start: int) -> np.ndarray:
        y = landmarks[:, start:start + HAND, 1]
        seen = ~np.isnan(y).any(axis=1)
        top = np.min(np.where(np.isnan(y), np.inf, y), axis=1)
        return seen & (top < bottom)
    return ~(up(LEFT) | up(RIGHT))


def longest_run(mask: np.ndarray) -> tuple[int, int]:
    """[start, end) of the longest run of True; (0, 0) when there is none."""
    best, start = (0, 0), None
    for i, value in enumerate([*mask, False]):
        if value and start is None:
            start = i
        elif not value and start is not None:
            if i - start > best[1] - best[0]:
                best = (start, i)
            start = None
    return best


# ---- steps (network, ffmpeg, MediaPipe) ----

def _get(url: str) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as response:
        return response.read()


def _save(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    try:
        data = _get(url)
    except OSError as error:  # network boundary: report and carry on with the rest
        print(f"failed {url}: {error}", file=sys.stderr)
        return False
    partial = dest.with_suffix(".part")
    partial.write_bytes(data)
    partial.rename(dest)
    return True


def _signbank_video(gloss_id: int) -> tuple[str, str] | None:
    html = _get(f"https://aslsignbank.com/dictionary/gloss/{gloss_id}/").decode("utf-8", "replace")
    match = re.search(r'/dictionary/protected_media/glossvideo/[^"]+\.mp4', html)
    return ("https://aslsignbank.com" + match.group(0), Path(match.group(0)).stem) if match else None


def fetch(out: Path) -> None:
    raw = out / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    yt_dlp = shutil.which("yt-dlp")
    if yt_dlp is None:
        raise SystemExit("yt-dlp is not on PATH (uv tool install yt-dlp)")
    rows: list[dict] = []
    for word, ids in LIFEPRINT_YT.items():
        for vid in ids:
            dest = raw / f"lifeprint-yt_{word}_{vid}.mp4"
            if not dest.exists():
                subprocess.run([yt_dlp, "--js-runtimes", "node", "-q", "-f",
                                "bv*[height<=480][ext=mp4]/b[height<=480]/b", "--remux-video", "mp4", "-o", str(dest),
                                f"https://www.youtube.com/watch?v={vid}"], check=False)
            if dest.exists():
                rows.append({"label": word, "path": str(dest), "source": "lifeprint-yt", "key": vid,
                             "url": f"https://www.youtube.com/watch?v={vid}",
                             "licence": "Lifeprint / ASL University (Bill Vicars), standard YouTube licence; local evaluation only"})
    for word, urls in LIFEPRINT_SITE.items():
        for url in urls:
            dest = raw / f"lifeprint-site_{word}_{Path(url).stem}.mp4"
            if _save(url, dest):
                rows.append({"label": word, "path": str(dest), "source": "lifeprint-site", "key": Path(url).name, "url": url,
                             "licence": "Lifeprint / ASL University (Bill Vicars), all rights reserved; local evaluation only"})
    for label, ids in [*SIGNBANK_SIGNS.items(), *(("none", [g]) for g in SIGNBANK_NEGATIVES)]:
        for gloss_id in ids:
            found = _signbank_video(gloss_id)
            if found is None:
                print(f"Signbank gloss {gloss_id}: no video", file=sys.stderr)
                continue
            url, stem = found
            dest = raw / f"signbank_{label}_{stem}.mp4"
            if _save(url, dest):
                rows.append({"label": label, "path": str(dest), "source": "asl-signbank", "key": stem,
                             "gloss": stem.rsplit("-", 1)[0].lower(), "url": f"https://aslsignbank.com/dictionary/gloss/{gloss_id}/",
                             "licence": "ASL Signbank (Hochgesang, Crasborn, Lillo-Martin), CC BY-NC-SA 4.0"})
    for word, page in SIGNASL_PAGES.items():
        html = _get(f"https://www.signasl.org/sign/{page}").decode("utf-8", "replace")
        for url in dict.fromkeys(re.findall(r'src="(https://media\.signbsl\.com/videos/asl/[^"]+\.mp4)"', html)):
            if SIGNASL_SKIP.search(url):
                continue
            publisher = url.split("/videos/asl/")[1].split("/")[0]
            name = re.sub(r"[^A-Za-z0-9-]+", "-", Path(urllib.parse.unquote(url)).stem).strip("-")
            dest = raw / f"signasl-{publisher}_{word}_{name}.mp4"
            if _save(url, dest):
                rows.append({"label": word, "path": str(dest), "source": f"signasl/{publisher}", "key": name, "url": url,
                             "licence": f"{publisher} via SignASL.org, copyright of the original publisher; local evaluation only"})
    (raw / "sources.json").write_text(json.dumps(rows, indent=1))
    print(f"{len(rows)} clips in {raw}")


def _ffmpeg(src: Path, dest: Path, video_filter: str, trim: tuple[float, float] | None = None) -> None:
    if dest.exists():
        return
    cut = ["-ss", f"{trim[0]:.3f}", "-to", f"{trim[1]:.3f}"] if trim else []
    subprocess.run(["ffmpeg", "-v", "error", "-y", *cut, "-i", str(src), "-vf", video_filter, "-c:v", "libx264",
                    "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", "-an", str(dest)], check=True)


def prep(out: Path) -> None:
    for folder in ("landscape", "portrait", "excluded/landscape", "excluded/portrait"):
        (out / folder).mkdir(parents=True, exist_ok=True)
    manifest = []
    for row in json.loads((out / "raw" / "sources.json").read_text()):
        name = clip_name(row["label"], row["source"], row["key"])
        stem = Path(name).stem
        prefix = "excluded/" if stem in EXCLUDED else ""
        _ffmpeg(Path(row["path"]), out / f"{prefix}landscape" / name, LANDSCAPE)
        _ffmpeg(Path(row["path"]), out / f"{prefix}portrait" / name, PORTRAIT)
        entry = {"id": stem, "label": row["label"], "kind": "sign" if row["label"] != "none" else "negative-sign",
                 "gloss": row.get("gloss", row["label"]), "landscape": f"{prefix}landscape/{name}",
                 "portrait": f"{prefix}portrait/{name}", "source": row["source"], "key": row["key"], "url": row["url"],
                 "licence": row["licence"]}
        if stem in EXCLUDED:
            entry["excluded"] = EXCLUDED[stem]
        manifest.append(entry)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"{len(manifest)} clips, {len(EXCLUDED)} set aside")


def rest(out: Path) -> None:
    import mediapipe as mp

    import extract

    manifest = [r for r in json.loads((out / "manifest.json").read_text()) if r["kind"] != "negative-rest"]
    picked: list[dict] = []
    per_source: dict[str, int] = {}
    with mp.solutions.holistic.Holistic(static_image_mode=False, model_complexity=1, refine_face_landmarks=False) as tracker:
        for row in sorted((r for r in manifest if "excluded" not in r), key=lambda r: r["id"]):
            family = row["source"].split("/")[-1]
            if len(picked) >= REST_MAX or per_source.get(family, 0) >= REST_PER_SOURCE:
                continue
            data = extract.extract(out / row["landscape"], tracker)
            landmarks, fps = data["landmarks"], data["fps"] or 30.0
            if not len(landmarks):
                continue
            start, end = longest_run(resting(landmarks))
            if (end - start) / fps < REST_MIN_S:
                continue
            trim = (start / fps, end / fps)
            name = f"none_rest-{row['id'].split('_', 1)[1]}.mp4"
            _ffmpeg(out / row["landscape"], out / "landscape" / name, "null", trim)
            _ffmpeg(out / row["landscape"], out / "portrait" / name, PORTRAIT, trim)
            per_source[family] = per_source.get(family, 0) + 1
            picked.append({"id": Path(name).stem, "label": "none", "kind": "negative-rest", "gloss": "rest",
                           "landscape": f"landscape/{name}", "portrait": f"portrait/{name}", "source": row["source"],
                           "key": row["key"], "url": row["url"], "licence": row["licence"],
                           "trim_s": [round(trim[0], 3), round(trim[1], 3)], "cut_from": row["id"]})
            print(f"{name}: {trim[0]:.2f}-{trim[1]:.2f} s", flush=True)
    (out / "manifest.json").write_text(json.dumps(manifest + picked, indent=1))
    print(f"{len(picked)} rest clips")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=["fetch", "prep", "rest"])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    {"fetch": fetch, "prep": prep, "rest": rest}[args.step](args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
