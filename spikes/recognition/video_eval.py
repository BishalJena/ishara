"""Evaluate the recognizer on neutral, silent clips cut from public videos (local only).

    python video_eval.py prepare   --spec artifacts/video_eval/spec.json
    artifacts/signclip/.venv/bin/python video_eval.py bundle
    artifacts/signclip/.venv/bin/python video_eval.py recognize --set A
    artifacts/signclip/.venv/bin/python video_eval.py turns --turns artifacts/video_eval/turns.json
    python video_eval.py score

prepare cuts every clip of a local spec with ffmpeg (no audio, no subtitles, no
metadata), pads it with 2 s of its first frame and 1 s of its last (the rest a live
user gives the detector), names it clip_NNN in a seeded shuffled order and writes
the label-free manifest plus a separate labels file. The recognizer commands read
the manifest only; labels are read by `bundle` (references only) and `score`.

bundle embeds the reference clips through the live path (legacy Holistic, detector
cut, SignCLIP) and freezes provisional cut-offs by leave-one-out over the references
alone (retrieval.leave_one_out + provisional_policy), before any test clip is seen.
recognize and turns replay test clips through live_source.LiveSource with that
bundle, exactly like `live_source.py --replay-videos`, and refuse any clip whose
id, content hash or source also backs a reference.
Everything is written under the ignored artifacts/video_eval/.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import subprocess
import time
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import recognition_data as data

ROOT = data.ARTIFACTS / "video_eval"
MANIFEST = ROOT / "manifest.json"
LABELS = ROOT / "labels.json"
BUNDLE = ROOT / "bundle-provisional.json"
PROVENANCE = ROOT / "bundle-provenance.json"
SPLITS = ("reference", "test")
CLIP_ID = re.compile(r"clip_\d{3}")  # neutral: nothing about the sign in the name
LEAD_REST_S, TAIL_REST_S = 2.0, 1.0  # the detector calibrates on the first 2 s
UNSURE = "?"


# ---- manifest, labels and leakage ----

@dataclass(frozen=True)
class Clip:
    id: str
    path: str  # relative to recognition_data.ARTIFACTS
    sha256: str
    source_id: str
    signer_id: str
    split: str
    set: str  # test sets are scored separately (e.g. A = other channels, B = held-out signers)


def parse_manifest(document: dict[str, Any]) -> list[Clip]:
    """Label-free clip list; a label, a non-neutral id or a mismatched file name is an error."""
    if document.get("version") != 1:
        raise ValueError("Unknown video_eval manifest version")
    clips, seen = [], set()
    for row in document["clips"]:
        if "label" in row:
            raise ValueError(f"{row.get('id')}: labels belong in labels.json, never in the manifest")
        clip = Clip(**row)
        if not CLIP_ID.fullmatch(clip.id) or Path(clip.path).name != f"{clip.id}.mp4":
            raise ValueError(f"{clip.id}: clip ids and file names must be neutral (clip_NNN.mp4)")
        if clip.split not in SPLITS:
            raise ValueError(f"{clip.id}: unknown split {clip.split!r}")
        if clip.id in seen:
            raise ValueError(f"Duplicate clip id {clip.id}")
        seen.add(clip.id)
        clips.append(clip)
    return clips


def load_manifest(path: Path = MANIFEST) -> list[Clip]:
    return parse_manifest(json.loads(Path(path).read_text()))


def parse_labels(document: dict[str, Any], clips: Sequence[Clip]) -> dict[str, str]:
    labels = document["labels"]
    unknown = sorted(set(labels) - {c.id for c in clips})
    if unknown:
        raise ValueError(f"Labels for clips not in the manifest: {', '.join(unknown)}")
    missing = sorted(c.id for c in clips if c.id not in labels)
    if missing:
        raise ValueError(f"Clips without a label: {', '.join(missing)}")
    bad = sorted(i for i, label in labels.items() if label not in data.VOCABULARY)
    if bad:
        raise ValueError(f"Labels outside the 12-sign vocabulary: {', '.join(bad)}")
    return dict(labels)


def assert_no_leakage(references: Iterable[dict[str, str]], tests: Iterable[dict[str, str]]) -> None:
    """No test clip may share an id, content hash, source video or signer with a reference."""
    references, tests = list(references), list(tests)
    for key in ("id", "sha256", "source_id", "signer_id"):
        shared = {r[key] for r in references} & {t[key] for t in tests if key in t}
        if shared:
            raise ValueError(f"Leakage: test and reference clips share {key} {sorted(shared)}")


def records(clips: Sequence[Clip], labels: dict[str, str], provenance: dict[str, str]) -> list[dict]:
    """The pilot manifest's record shape, so recognition_data.validate_records checks the split."""
    return [{"id": c.id, "signer_id": c.signer_id, "session_id": c.source_id, "source_id": c.source_id,
             "split": "enrollment" if c.split == "reference" else "test", "label": labels[c.id],
             "negative_kind": None, "verified": True, "verification_note": provenance[c.source_id],
             "provenance": f"public video {c.source_id}; local evaluation only, never redistributed",
             "sha256": c.sha256, "path": c.path} for c in clips]


# ---- preparing neutral clips ----

def cut_command(source: Path, start: float, end: float, destination: Path,
                crop: str | None = None) -> list[str]:
    """ffmpeg arguments: silent (-an), no subtitle or data tracks, no metadata, padded rests."""
    filters = [f"crop={crop}"] if crop else []
    filters += ["scale=-2:'min(720,ih)'",
                f"tpad=start_mode=clone:start_duration={LEAD_REST_S}:stop_mode=clone:stop_duration={TAIL_REST_S}"]
    return ["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(source),
            "-map", "0:v:0", "-an", "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1",
            "-vf", ",".join(filters), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
            str(destination)]


def neutral_ids(count: int, seed: int) -> list[str]:
    """clip_001.. in a shuffled order, so neither the id nor the order says which sign it is."""
    ids = [f"clip_{i:03d}" for i in range(1, count + 1)]
    random.Random(seed).shuffle(ids)
    return ids


def prepare(spec_path: Path, seed: int) -> int:
    spec = json.loads(spec_path.read_text())
    sources = {s["source_id"]: s for s in spec["sources"]}
    clips_dir = ROOT / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    clips, labels = [], {}
    for clip_id, cut in zip(neutral_ids(len(spec["cuts"]), seed), spec["cuts"], strict=True):
        source = sources[cut["source_id"]]
        destination = clips_dir / f"{clip_id}.mp4"
        subprocess.run(cut_command(ROOT / source["file"], cut["start"], cut["end"], destination,
                                   cut.get("crop")), check=True)
        clips.append(Clip(clip_id, str(destination.relative_to(data.ARTIFACTS)), data.sha256(destination),
                          source["source_id"], source["signer_id"], cut["split"], cut.get("set", "-")))
        labels[clip_id] = cut["label"]
    clips.sort(key=lambda c: c.id)
    by_split = {split: [vars(c) for c in clips if c.split == split] for split in SPLITS}
    assert_no_leakage(by_split["reference"], by_split["test"])
    data.validate_records(records(clips, labels, {s: v["label_evidence"] for s, v in sources.items()}))
    data.write_json(MANIFEST, {"version": 1, "clips": [vars(c) for c in clips]})
    data.write_json(LABELS, {"labels": dict(sorted(labels.items()))})
    print(f"{len(clips)} clips -> {MANIFEST.relative_to(data.ROOT)}; labels kept apart in "
          f"{LABELS.relative_to(data.ROOT)}")
    return 0


# ---- running the live path (SignCLIP venv) ----

def recording_source():
    """LiveSource that also keeps rejected segments, so every detector cut is reported."""
    from live_source import LiveSource

    class RecordingSource(LiveSource):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.segments: list[Any] = []

        def _on_segment(self, segment, recent):
            self.segments.append(segment)
            return super()._on_segment(segment, recent)

    return RecordingSource


def replay(paths: Sequence[Path], matcher: Any, realtime: bool = True) -> dict[str, Any]:
    """One live_source replay over `paths` (a clip, or the clips of a turn in order)."""
    import live_source as ls

    lines: list[str] = []
    source = recording_source()(ls.replay_clips(paths, realtime=realtime, keep_image=False), matcher,
                                out=lines.append)
    recognitions = list(source)
    return {"segments": [{"start": round(s.start, 3), "end": round(s.end, 3), "accepted": s.accepted,
                          "reason": s.reason} for s in source.segments],
            "recognitions": [ls.result_details(r) for r in recognitions],
            "chips": [r.sign for r in recognitions if r.sign is not None],
            "shown": [r.sign or UNSURE for r in recognitions],
            "log": lines}


class Embedder:
    """Stands in for live_source.Matcher while building references: keeps each cut's embedding."""

    def __init__(self, featurize: Any, embed: Any, max_frames: int) -> None:
        from live_source import Bundle, Match

        self.bundle = Bundle("", {}, [], False)
        self._featurize, self._embed, self._max = featurize, embed, max_frames
        self._match = Match
        self.cuts: list[dict[str, Any]] = []

    def __call__(self, observations):
        if len(observations) > self._max:
            self.cuts.append({"error": f"{len(observations)} frames > {self._max}"})
            return self._match(None, "too long for SignCLIP")
        try:
            features, quality = self._featurize(observations)
            self.cuts.append({"embedding": self._embed(features), "quality": quality})
        except ValueError as error:
            self.cuts.append({"error": str(error)})
        return self._match(None, "reference")


def manual_take(path: Path, embedder: Embedder) -> dict[str, Any]:
    """The whole sign span of a reference clip (padding dropped), embedded like a cut."""
    import live_source as ls

    observations = list(ls.track(ls.video_images(path, realtime=False), keep_image=False))
    end = observations[-1].frame.t - TAIL_REST_S
    span = [o for o in observations if LEAD_REST_S - 1e-6 <= o.frame.t <= end + 1e-6]
    embedder(span)
    return dict(embedder.cuts[-1], take="manual")


def build_bundle(manifest: Path, labels_path: Path) -> int:
    import live_source as ls
    import retrieval
    import signclip

    clips = load_manifest(manifest)
    references = [c for c in clips if c.split == "reference"]
    labels = parse_labels(json.loads(labels_path.read_text()), clips)
    encoder = retrieval.Encoder("signclip")
    rows, dropped = [], []
    for clip in references:
        embedder = Embedder(ls.signclip_features, lambda f: signclip.embed(encoder.model, f), signclip.MAX_FRAMES)
        run = replay([data.ARTIFACTS / clip.path], embedder, realtime=False)
        # A Sign Lab take keeps the first accepted detector cut. When the detector cuts nothing
        # usable, the take is kept whole, like record_session.py --manual-stop: every frame
        # between the padded rests.
        cut = next((dict(c, take="detector") for c in embedder.cuts if "embedding" in c), None)
        if cut is None:
            cut = manual_take(data.ARTIFACTS / clip.path, embedder)
        if "embedding" not in cut:
            dropped.append({"id": clip.id, "segments": run["segments"], "log": run["log"],
                            "errors": [c.get("error") for c in embedder.cuts]})
            continue
        rows.append({"id": clip.id, "label": labels[clip.id], "sha256": clip.sha256,
                     "source_id": clip.source_id, "embedding": data.unit(cut["embedding"]),
                     "quality": cut["quality"], "take": cut["take"], "segments": run["segments"]})
    for drop in dropped:
        print(f"dropped reference {drop['id']}: segments {drop['segments']}, errors {drop['errors']}, "
              f"log {drop['log']}", flush=True)
    thresholds, counts = retrieval.provisional_policy(retrieval.leave_one_out(rows))
    document = {"version": 1, "provisional": True,
                **retrieval.bundle(encoder.contract, thresholds, rows), "leave_one_out": counts}
    data.write_json(BUNDLE, document)
    signers = {c.id: c.signer_id for c in references}
    data.write_json(PROVENANCE, {"references": [{k: r[k] for k in ("id", "sha256", "source_id", "take",
                                                                   "segments", "quality")}
                                                | {"signer_id": signers[r["id"]]} for r in rows],
                                 "dropped": dropped})
    print(retrieval.provisional_banner(thresholds, counts, BUNDLE))
    print(f"{len(rows)} references embedded, {len(dropped)} dropped (no usable detector cut)")
    return 0


def checked_tests(clips: Sequence[Clip], wanted: set[str] | None) -> list[Clip]:
    provenance = json.loads(PROVENANCE.read_text())["references"]
    tests = [c for c in clips if c.split == "test" and (wanted is None or c.set in wanted)]
    assert_no_leakage(provenance, [vars(c) for c in tests])
    return tests


def matcher_for(bundle_path: Path):
    import live_source as ls

    bundle = ls.load_bundle(bundle_path)
    if bundle is None:
        raise SystemExit(f"No bundle at {bundle_path}; run `video_eval.py bundle` first")
    return ls.signclip_matcher(bundle)


def recognize(manifest: Path, bundle_path: Path, sets: set[str] | None, out: Path) -> int:
    tests = checked_tests(load_manifest(manifest), sets)
    matcher = matcher_for(bundle_path)
    results = []
    for clip in tests:
        started = time.perf_counter()
        run = replay([data.ARTIFACTS / clip.path], matcher)
        results.append({"id": clip.id, "set": clip.set, "wall_s": round(time.perf_counter() - started, 2), **run})
        print(f"{clip.id}: {' '.join(run['shown']) or '(nothing)'}", flush=True)
    data.write_json(out, {"bundle": str(bundle_path.relative_to(data.ARTIFACTS)), "results": results})
    print(f"Results: {out}")
    return 0


def run_turns(manifest: Path, bundle_path: Path, turns_path: Path, out: Path) -> int:
    clips = {c.id: c for c in load_manifest(manifest)}
    turns = json.loads(turns_path.read_text())["turns"]
    used = sorted({i for t in turns for i in t["clips"]})
    checked_tests([clips[i] for i in used], None)
    matcher = matcher_for(bundle_path)
    results = []
    for turn in turns:
        run = replay([data.ARTIFACTS / clips[i].path for i in turn["clips"]], matcher)
        results.append({"turn": turn["turn"], "clips": turn["clips"], **run})
        print(f"{turn['turn']}: {' '.join(run['shown']) or '(nothing)'} -> chips {run['chips']}", flush=True)
    data.write_json(out, {"results": results})
    print(f"Turn results: {out}")
    return 0


# ---- scoring (any Python) ----

def clip_outcome(shown: Sequence[str], label: str) -> str:
    """correct: exactly the right chip; wrong: any other accepted sign (it would reach the
    composer); unsure: only "?"; missed: the detector cut no usable segment at all."""
    accepted = [s for s in shown if s != UNSURE]
    if any(s != label for s in accepted):
        return "wrong"
    if accepted:
        return "correct" if len(accepted) == 1 else "repeated"
    return "unsure" if shown else "missed"


def percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile (no interpolation), or None without values."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * q // 100))  # ceil(n * q / 100)
    return ordered[int(rank) - 1]


OUTCOMES = ("correct", "repeated", "wrong", "unsure", "missed")


def score(results: Sequence[dict[str, Any]], labels: dict[str, str]) -> dict[str, Any]:
    per_sign = {label: Counter() for label in data.VOCABULARY}
    confusion: Counter = Counter()
    top1: Counter = Counter()
    latencies = []
    for row in results:
        label = labels[row["id"]]
        outcome = clip_outcome(row["shown"], label)
        per_sign[label]["clips"] += 1
        per_sign[label][outcome] += 1
        for recognition in row["recognitions"]:
            latencies.append(recognition["latency_ms"])
            if recognition["sign"] is not None and recognition["sign"] != label:
                confusion[(label, recognition["sign"])] += 1
            if recognition["top"]:
                top1["segments"] += 1
                top1["top1_right"] += recognition["top"][0]["sign"] == label
    total = Counter()
    for counts in per_sign.values():
        total.update(counts)
    return {"per_sign": {k: dict(v) for k, v in per_sign.items() if v["clips"]}, "total": dict(total),
            "accuracy": total["correct"] / total["clips"] if total["clips"] else None,
            "confusion": [{"truth": t, "accepted": a, "count": n} for (t, a), n in confusion.most_common()],
            "top1": dict(top1),
            "latency_ms": {"count": len(latencies), "p50": percentile(latencies, 50),
                           "p95": percentile(latencies, 95),
                           "mean": statistics.fmean(latencies) if latencies else None}}


def table(summary: dict[str, Any]) -> str:
    lines = ["| Sign | Clips | Correct accepted | Wrong accepted | Unsure (?) | No accepted segment | Repeated |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for sign, c in summary["per_sign"].items():
        lines.append(f"| {sign} | {c['clips']} | {c.get('correct', 0)} | {c.get('wrong', 0)} | "
                     f"{c.get('unsure', 0)} | {c.get('missed', 0)} | {c.get('repeated', 0)} |")
    t = summary["total"]
    lines.append(f"| **all** | **{t.get('clips', 0)}** | **{t.get('correct', 0)}** | **{t.get('wrong', 0)}** | "
                 f"**{t.get('unsure', 0)}** | **{t.get('missed', 0)}** | **{t.get('repeated', 0)}** |")
    return "\n".join(lines)


def score_command(results_path: Path, labels_path: Path, manifest: Path, out: Path | None) -> int:
    clips = load_manifest(manifest)
    labels = parse_labels(json.loads(labels_path.read_text()), clips)
    rows = json.loads(results_path.read_text())["results"]
    report = {}
    for test_set in sorted({r["set"] for r in rows}):
        summary = score([r for r in rows if r["set"] == test_set], labels)
        report[test_set] = summary
        print(f"\nSet {test_set}: accuracy {summary['accuracy']:.2f}, top-1 {summary['top1']}, "
              f"latency {summary['latency_ms']}, confusion {summary['confusion']}")
        print(table(summary))
    if out is not None:
        data.write_json(out, report)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["prepare", "bundle", "recognize", "turns", "score"])
    parser.add_argument("--spec", type=Path, default=ROOT / "spec.json")
    parser.add_argument("--seed", type=int, default=20261024)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--labels", type=Path, default=LABELS)
    parser.add_argument("--bundle", type=Path, default=BUNDLE)
    parser.add_argument("--set", action="append", dest="sets", help="test set(s) to run (default: all)")
    parser.add_argument("--turns", type=Path, default=ROOT / "turns.json")
    parser.add_argument("--results", type=Path, default=ROOT / "results.json")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        return prepare(args.spec, args.seed)
    if args.command == "bundle":
        return build_bundle(args.manifest, args.labels)
    if args.command == "recognize":
        return recognize(args.manifest, args.bundle, set(args.sets) if args.sets else None,
                         args.out or args.results)
    if args.command == "turns":
        return run_turns(args.manifest, args.bundle, args.turns, args.out or ROOT / "turn-results.json")
    return score_command(args.results, args.labels, args.manifest, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
