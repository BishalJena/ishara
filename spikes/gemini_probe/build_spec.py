"""Choose the words, test clips and reference clips for the probe (writes a local spec).

    .venv/bin/python build_spec.py --tests-per-word 2 --max-words 120

References (SignCLIP only) come from two dictionaries: ISLRTC and Bridgeconn. Test clips
(both systems) come from datasets that are neither: INCLUDE and the YouTube channels of
the earlier public-video probe (set A). So no test clip can share a video, a signer
session or a recording studio with a reference by construction; prepare.py checks it again.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections.abc import Sequence
from pathlib import Path

from sources import ARTIFACTS, INDEX, ISLRTC_FILE, word_key

VIDEO_EVAL = ARTIFACTS.parent / "video_eval"
DEMO_WORDS = ("hello", "thank you", "yes", "no", "sorry", "doctor", "today", "tomorrow",
              "morning", "afternoon", "evening", "time")
# English homographs whose dictionary entry may show another sense than INCLUDE's
# (e.g. ISLRTC "Fall" vs INCLUDE's season), so a reference could be a different sign.
HOMOGRAPHS = frozenset({"fall", "spring", "mean", "cool", "fan", "bill", "card", "sign", "ring", "key",
                        "letter", "mouse", "orange", "park", "court", "it", "light", "train", "tool",
                        "hard", "fast", "low", "dry", "season"})
ISLRTC_TERMS = ("ISLRTC Indian Sign Language Dictionary (data.gov.in) via the re-encoded Hugging Face mirror "
                "silentone0725/Indian_Sign_Language_Data.gov_Rencoded (MIT on the mirror); ISLRTC FAQ Q23: "
                "research/teaching/ISL technology use with acknowledgement, no resale")
BRIDGECONN_TERMS = "Bridgeconn ISL Bible (ISLV) Dictionary, bridgeconn/sign-dictionary-isl, CC-BY-SA-4.0"
INCLUDE_TERMS = "INCLUDE (AI4Bharat), Zenodo 4010759, CC-BY-4.0"
MVI = re.compile(r"(\d+)")  # first number of the file name, e.g. MVI_0050_ (1).MOV -> 50


def spread(members: Sequence[Sequence[str]], count: int) -> list[Sequence[str]]:
    """`count` members evenly spaced over the file-number order.

    INCLUDE file numbers follow recording sessions, so spacing them out mixes signers
    instead of taking one person's consecutive takes.
    """
    ordered = sorted(members, key=lambda m: (int(MVI.search(m[1].rsplit("/", 1)[-1]).group(1)), m[1]))
    if count >= len(ordered):
        return list(ordered)
    step = len(ordered) / count
    return [ordered[int(step * i + step / 2)] for i in range(count)]


def choose_words(include: dict, islrtc: dict, bridgeconn: dict[str, list[dict]], tests_per_word: int,
                 max_words: int, seed: int) -> list[str]:
    """Words with test clips (INCLUDE, or set A for yes/no/sorry) and refs from both dictionaries."""
    eligible = sorted(w for w in set(include) & set(islrtc) & set(bridgeconn)
                      if w not in HOMOGRAPHS and len(include[w]) >= tests_per_word)
    # The 12 demo words stay in even without a Bridgeconn entry; yes/no/sorry have no
    # INCLUDE folder, so their test clips are set A only.
    demo = [w for w in DEMO_WORDS if w in islrtc]
    others = [w for w in eligible if w not in demo]
    random.Random(seed).shuffle(others)
    return sorted(demo + others[:max(0, max_words - len(demo))])


def bridgeconn_by_word(catalogue: list[dict]) -> dict[str, list[dict]]:
    words: dict[str, list[dict]] = {}
    for row in catalogue:
        if "file" not in row:
            continue
        for gloss in row["glosses"]:
            words.setdefault(word_key(gloss), []).append(row)
    return words


# Pictures that give the answer away, found by viewing frames of every set A cut. Text is
# handled by the OCR filter; pictures are not, so these cuts are cropped, trimmed or dropped.
SET_A_DROPPED = {"F1EDartPuC8"}  # Deaf Enabled Foundation: sun, clock and sky colour show the time of day
SET_A_FIXES = {
    # PHIN "time": a clock picture fills the left half, then T-I-M-E is fingerspelled;
    # keep the signer's half and only the final wrist-tap sign.
    ("mtjse9ZT1Fw", 0.0): {"start": 4.6, "end": 6.3, "crop": "640:720:640:0"},
    # PHIN "doctor": a captioned doctor photo on the left; the last 0.4 s is the end card.
    ("qeI6-V8YAKw", 0.0): {"start": 0.0, "end": 3.4, "crop": "742:720:538:0"},
}


def set_a_cuts(words: set[str]) -> tuple[list[dict], list[dict]]:
    """The earlier probe's YouTube test cuts (set A) for the demo words, minus picture leaks."""
    spec = json.loads((VIDEO_EVAL / "spec.json").read_text())
    sources = {s["source_id"]: s for s in spec["sources"]}
    used, cuts = {}, []
    for cut in spec["cuts"]:
        label = "thank you" if cut["label"] == "thankyou" else cut["label"]
        if cut["split"] != "test" or cut["set"] != "A" or label not in words:
            continue
        source = sources[cut["source_id"]]
        video = source["url"].rsplit("=", 1)[-1]
        if video in SET_A_DROPPED:
            continue
        cut = {**cut, **SET_A_FIXES.get((video, cut["start"]), {})}
        source_id = f"yt_{video}"
        used[source_id] = {"source_id": source_id, "dataset": "youtube", "signer_id": f"youtube-{source['signer_id']}",
                           "url": source["url"], "channel": source["channel"], "title": source["title"],
                           "terms": source["terms"], "file": f"../video_eval/{source['file']}",
                           "label_evidence": source["label_evidence"]}
        cuts.append({"source_id": source_id, "label": label, "split": "test", "set": "youtube",
                     "start": cut["start"], "end": cut["end"], **({"crop": cut["crop"]} if cut.get("crop") else {})})
    return list(used.values()), cuts


def islrtc_cuts() -> dict[str, tuple[float, float]]:
    """Curated sign spans of ISLRTC entries from the earlier probe (e.g. Doctor.mp4 is 14 s)."""
    spec = json.loads((VIDEO_EVAL / "spec.json").read_text())
    sources = {s["source_id"]: s for s in spec["sources"]}
    spans = {}
    for cut in spec["cuts"]:
        url = sources[cut["source_id"]]["url"]
        if url.startswith(ISLRTC_FILE):
            spans[url.removeprefix(ISLRTC_FILE)] = (cut["start"], cut["end"])
    return spans


def build(tests_per_word: int, max_words: int, seed: int) -> dict:
    include = json.loads((INDEX / "include.json").read_text())
    islrtc = json.loads((INDEX / "islrtc.json").read_text())
    bridgeconn = bridgeconn_by_word(json.loads((INDEX / "bridgeconn.json").read_text()))
    words = choose_words(include, islrtc, bridgeconn, tests_per_word, max_words, seed)
    sources, clips = [], []
    for word in words:
        for zip_name, member in spread(include.get(word, []), tests_per_word):
            # The member path names the word's folder, so the id is a hash of it, not the path.
            source_id = "inc_" + hashlib.sha1(member.encode()).hexdigest()[:12]
            sources.append({"source_id": source_id, "dataset": "include", "signer_id": "include",
                            "url": f"https://zenodo.org/records/4010759 ({zip_name}: {member})",
                            "include_member": [zip_name, member], "terms": INCLUDE_TERMS,
                            "file": f"raw/include/{member}", "label_evidence": "INCLUDE folder name"})
            clips.append({"source_id": source_id, "label": word, "split": "test", "set": "include"})
    spans = islrtc_cuts()
    for word in words:
        for path in islrtc[word]:
            source_id = "isl_" + re.sub(r"\W+", "_", path)
            sources.append({"source_id": source_id, "dataset": "islrtc", "signer_id": "islrtc",
                            "url": ISLRTC_FILE + path, "islrtc_path": path, "terms": ISLRTC_TERMS,
                            "file": f"raw/islrtc/{path}", "label_evidence": "ISLRTC dictionary entry name"})
            start, end = spans.get(path, (None, None))
            clips.append({"source_id": source_id, "label": word, "split": "reference", "set": "islrtc",
                          **({"start": start, "end": end} if start is not None else {})})
        for row in bridgeconn.get(word, []):
            source_id = f"bc_{row['shard']}_{row['key']}"
            sources.append({"source_id": source_id, "dataset": "bridgeconn", "signer_id": "bridgeconn",
                            "url": f"https://huggingface.co/datasets/bridgeconn/sign-dictionary-isl "
                                   f"(shard {row['shard']}, key {row['key']}, gloss {row['glosses'][0]!r})",
                            "terms": BRIDGECONN_TERMS, "file": row["file"],
                            "label_evidence": "Bridgeconn transcript gloss"})
            clips.append({"source_id": source_id, "label": word, "split": "reference", "set": "bridgeconn"})
    youtube_sources, youtube_cuts = set_a_cuts(set(words))
    sources += youtube_sources
    clips += youtube_cuts
    return {"version": 1, "seed": seed, "tests_per_word": tests_per_word, "words": words,
            "sources": sources, "clips": clips}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tests-per-word", type=int, default=2)
    parser.add_argument("--max-words", type=int, default=120)
    parser.add_argument("--seed", type=int, default=20261025)
    parser.add_argument("--out", type=Path, default=ARTIFACTS / "spec.json")
    args = parser.parse_args(argv)
    spec = build(args.tests_per_word, args.max_words, args.seed)
    args.out.write_text(json.dumps(spec, indent=1))
    splits = {s: sum(c["split"] == s for c in spec["clips"]) for s in ("test", "reference")}
    print(f"{len(spec['words'])} words, {splits['test']} test clips, {splits['reference']} reference clips "
          f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
