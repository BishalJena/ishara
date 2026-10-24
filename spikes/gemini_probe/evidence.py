"""Copy the probe's own outputs (no media, no third-party text) into the committed evidence folder.

    python3 evidence.py --out ../../docs/experiments/evidence/gemini-video-probe

Run after score.py has written results.json and per_clip.csv into the same folder.
Copies: Gemini predictions and cost logs (main run, thinking-high pilot, API smoke),
SignCLIP predictions and its frozen policy, the answer key, the burned-in text audit,
the prompt template with its response schema, and the list of source URLs with terms.
"""
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

import prompt
from sources import ARTIFACTS

RUNS = ARTIFACTS / "runs"
SOURCE_ROLES = {"include": "test", "youtube": "test", "islrtc": "reference", "bridgeconn": "reference"}


def sources_list(spec: dict, used: set[str]) -> dict:
    """One entry per source video that ended up in the probe, grouped by dataset; no media."""
    datasets: dict[str, dict] = {}
    for source in spec["sources"]:
        if source["source_id"] not in used:
            continue
        block = datasets.setdefault(source["dataset"], {"role": SOURCE_ROLES[source["dataset"]],
                                                        "terms": source["terms"], "urls": []})
        block["urls"].append(source["url"])
    for block in datasets.values():
        block["urls"] = sorted(set(block["urls"]))
        block["count"] = len(block["urls"])
    return datasets


def export(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    spec = json.loads((ARTIFACTS / "spec.json").read_text())
    provenance = json.loads((ARTIFACTS / "key" / "provenance.json").read_text())
    references = json.loads((ARTIFACTS / "references.json").read_text())["references"]
    used = {t["source_id"] for t in provenance["tests"].values()} | {r["source_id"] for r in references}
    copies = {
        ARTIFACTS / "key" / "answer_key.json": "answer_key.json",
        ARTIFACTS / "ocr.json": "ocr_audit.json",
        ARTIFACTS / "candidates.json": "candidates.json",
        RUNS / "gemini" / "predictions.jsonl": "gemini_predictions.jsonl",
        RUNS / "gemini" / "cost_log.jsonl": "gemini_cost_log.jsonl",
        RUNS / "pilot_high" / "predictions.jsonl": "gemini_pilot_thinking_high_predictions.jsonl",
        RUNS / "pilot_high" / "cost_log.jsonl": "gemini_pilot_thinking_high_cost_log.jsonl",
        RUNS / "smoke.json": "gemini_api_smoke.json",
        RUNS / "signclip" / "predictions.json": "signclip_predictions.json",
        RUNS / "signclip" / "policy.json": "signclip_policy.json",
    }
    for source, name in copies.items():
        shutil.copyfile(source, out / name)
    words = json.loads((ARTIFACTS / "candidates.json").read_text())["words"]
    (out / "prompt_template.json").write_text(json.dumps({
        "template": prompt.TEMPLATE, "candidates": "the candidate words, freshly shuffled per clip "
        "(random.Random(f'{seed}:{clip_id}'), seed 20261025), joined with ', '",
        "response_schema_example": prompt.response_schema(words),
        "example_prompt_with_sorted_list": prompt.build_prompt(words)}, indent=1) + "\n")
    (out / "sources.json").write_text(json.dumps({
        "downloaded": "24-25 October 2026, for local evaluation only; no media is committed",
        "datasets": sources_list(spec, used),
        "test_clips_per_dataset": dict(Counter(t["dataset"] for t in provenance["tests"].values())),
        "reference_clips_per_dataset": dict(Counter(r["dataset"] for r in references)),
        "skipped_too_long": provenance["skipped"]}, indent=1) + "\n")
    print(f"evidence -> {out}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    export(parser.parse_args(argv).out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
