"""SignCLIP on the probe's clips: embed, nearest reference per word, frozen cut-off (local, free).

    ../recognition/artifacts/signclip/.venv/bin/python signclip_adapter.py

Reuses the recognition spike unchanged: retrieval.Encoder("signclip") for embeddings
(legacy Holistic + the pinned SignCLIP checkpoint, whole clip), recognition_data.rank and
.decision for nearest-reference ranking and the accept rule, and retrieval.leave_one_out's
ranking + provisional_policy for the cut-offs. Those modules hard-code the 12 demo signs
as their vocabulary, so the probe's word list is swapped in for the duration of a call
(`vocabulary`); nothing in them is edited.

Order matters: references are embedded and the cut-offs frozen to policy.json before any
test clip is embedded. Test clips are read from manifest.json (no labels); the answer key
is never opened here. Outputs go to artifacts/gemini_probe/runs/signclip/.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECOGNITION = HERE.parent / "recognition"
sys.path.insert(0, str(RECOGNITION))
import recognition_data as data
import retrieval

ARTIFACTS = RECOGNITION / "artifacts" / "gemini_probe"
OUT = ARTIFACTS / "runs" / "signclip"
TOP_K = 5


@contextmanager
def vocabulary(words: Sequence[str]) -> Iterator[None]:
    """Let the recognition spike's rank/decision/policy code accept the probe's words."""
    saved = data.VOCABULARY
    data.VOCABULARY = tuple(words)
    try:
        yield
    finally:
        data.VOCABULARY = saved


def check_separation(references: Sequence[dict], tests: Sequence[dict]) -> None:
    """No test clip may be (or duplicate) a reference; references come from the dictionaries only."""
    for key in ("id", "sha256"):
        shared = {r[key] for r in references} & {t[key] for t in tests}
        if shared:
            raise ValueError(f"Leakage: test clips share {key} with references: {sorted(shared)[:5]}")
    datasets = {r["dataset"] for r in references}
    if not datasets <= {"islrtc", "bridgeconn"}:
        raise ValueError(f"References must come from the dictionaries only, got {sorted(datasets)}")


def loo_queries(references: Sequence[dict]) -> list[dict]:
    """References whose word has another reference from a different source (rank skips its own source)."""
    sources: dict[str, set[str]] = {}
    for row in references:
        sources.setdefault(row["label"], set()).add(row["source_id"])
    return [r for r in references if len(sources[r["label"]]) >= 2]


def freeze_policy(references: Sequence[dict], words: Sequence[str]) -> tuple[dict, dict]:
    with vocabulary(words):
        rows = retrieval.rank_records(loo_queries(references), references)
        return retrieval.provisional_policy(rows)


def top(ranking: Sequence[dict]) -> list[dict]:
    return [{"word": r["concept"], "similarity": round(r["similarity"], 4)} for r in ranking[:TOP_K]]


def recognize(test: dict, references: Sequence[dict], policy: dict, words: Sequence[str]) -> dict:
    if "embedding" not in test:
        return {"id": test["id"], "sha256": test["sha256"], "status": "error", "error": test.get("error")}
    with vocabulary(words):
        ranked = data.rank({**test, "source_id": f"test:{test['id']}"}, references)
        decision = data.decision(ranked, test["quality"], policy)
    return {"id": test["id"], "sha256": test["sha256"], "status": "ok",
            "top1": ranked["ranking"][0]["concept"] if ranked["ranking"] else None,
            "accepted": decision["concept"], "decision": decision["status"], "reason": decision["reason"],
            "margin": None if ranked["margin"] is None else round(ranked["margin"], 4),
            "top": top(ranked["ranking"]),
            "quality": {k: test["quality"].get(k) for k in ("frames", "pose_fraction", "hand_fraction")},
            "landmark_ms": round(test["quality"].get("landmark_ms", 0.0), 1),
            "model_ms": round(test.get("model_ms", 0.0), 1), "total_ms": round(test.get("total_ms", 0.0), 1)}


def embed(encoder: retrieval.Encoder, rows: Sequence[dict]) -> list[dict]:
    """Paths are relative to the gemini_probe artifacts; fresh=True keeps the shared cache untouched."""
    out = []
    for row in rows:
        relative = {**row, "path": str(Path("gemini_probe") / row["path"])}
        try:
            item = encoder.extract(relative, fresh=True)
        except ValueError as error:
            item = {**relative, "error": str(error), "quality": {}}
        out.append(item)
        print(f"embedded {row['id']}: {item.get('error', 'ok')}", flush=True)
    return out


def run(out: Path) -> int:
    words = json.loads((ARTIFACTS / "candidates.json").read_text())["words"]
    references = [r for r in json.loads((ARTIFACTS / "references.json").read_text())["references"]
                  if r["label"] in words]
    tests = json.loads((ARTIFACTS / "manifest.json").read_text())["clips"]
    check_separation(references, tests)
    out.mkdir(parents=True, exist_ok=True)
    encoder = retrieval.Encoder("signclip")
    embedded = embed(encoder, references)
    usable = [r for r in embedded if "embedding" in r]
    thresholds, counts = freeze_policy(usable, words)
    policy = {"thresholds": thresholds, "leave_one_out": counts, "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "references": len(usable), "references_failed": [{"id": r["id"], "error": r["error"]}
                                                               for r in embedded if "error" in r],
              "words_with_reference": sorted({r["label"] for r in usable}), "contract": encoder.contract}
    (out / "policy.json").write_text(json.dumps(policy, indent=1, default=str))
    print(f"frozen cut-offs {thresholds} from {len(usable)} references", flush=True)
    results = [recognize(t, usable, thresholds, words) for t in embed(encoder, tests)]
    (out / "predictions.json").write_text(json.dumps({"policy": thresholds, "results": results}, indent=1))
    print(f"{sum(r['status'] == 'ok' for r in results)} of {len(results)} test clips recognized -> {out}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT)
    return run(parser.parse_args(argv).out)


if __name__ == "__main__":
    raise SystemExit(main())
