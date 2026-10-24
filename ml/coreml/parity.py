"""Compare Core ML SignCLIPEncoder embeddings with the original PyTorch pipeline.

Reference = spikes/recognition/signclip.embed on each clip's unpadded features
(it pads to 256 internally, as upstream MMPTModel does). Reports per-clip cosine,
leave-one-out top-1 label agreement and predict latency per compute unit.
Pass criterion (PLAN P1): cosine >= 0.999 on every clip.
"""
from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch

import contract
import convert_signclip as cs

signclip = cs.signclip
PASS_COSINE = 0.999
CLIP_DIRS = {"corpus": cs.HERE.parents[1] / "spikes" / "recognition" / "artifacts" / "clips",
             "parity-extra": cs.ARTIFACTS / "clips"}
UNITS = ("ALL", "CPU_AND_NE", "CPU_AND_GPU", "CPU_ONLY")


def clips() -> list[dict]:
    found = []
    for source, root in CLIP_DIRS.items():
        for path in sorted(root.rglob("*")) if root.is_dir() else []:
            if path.suffix.lower() in {".mov", ".mp4", ".m4v"}:
                found.append({"id": f"{path.parent.name}/{path.name}", "label": path.parent.name,
                              "source": source, "path": path})
    return found


def percentiles(samples: list[float]) -> dict:
    return {"runs": len(samples), "p50_ms": float(np.percentile(samples, 50)),
            "p95_ms": float(np.percentile(samples, 95))}


def top1(rows: list[dict], key: str) -> list[str]:
    """Leave-one-out nearest neighbour label; the bank is embedded by the same backend."""
    bank = np.stack([contract.unit(r[key]) for r in rows])
    similarity = bank @ bank.T
    np.fill_diagonal(similarity, -np.inf)
    return [rows[i]["label"] for i in similarity.argmax(1)]


def embed_torch(rows: list[dict], wrapper: cs.SignCLIPEncoder, model: object) -> None:
    rng = np.random.default_rng(0)
    for row in rows:
        features = row.pop("features")
        start = time.perf_counter()
        row["torch"] = signclip.embed(model, features)
        row["torch_ms"] = 1000 * (time.perf_counter() - start)
        padded, mask = contract.pad(features)
        row["wrapper_cosine"] = contract.cosine(row["torch"], cs.torch_embed(wrapper, padded, mask))
        # Padding must be inert: garbage in padded frames may not move the embedding.
        noisy = padded.copy()
        noisy[0, len(features):] = rng.normal(size=noisy[0, len(features):].shape)
        row["garbage_padding_max_abs_diff"] = float(np.abs(
            cs.torch_embed(wrapper, noisy, mask) - cs.torch_embed(wrapper, padded, mask)).max())
        # Not the contract: upstream always pads to 256, so the video [SEP] position is fixed.
        unpadded = features[None], np.ones((1, len(features)), np.float32)
        row["unpadded_sequence_cosine"] = contract.cosine(row["torch"], cs.torch_embed(wrapper, *unpadded))
        row["inputs"] = (padded, mask)


def evaluate_coreml(rows: list[dict], package: Path, unit: str, runs: int) -> dict:
    import coremltools as ct

    start = time.perf_counter()
    model = ct.models.MLModel(str(package), compute_units=getattr(ct.ComputeUnit, unit))
    load_s = time.perf_counter() - start
    key = f"{package.stem}:{unit}"
    for row in rows:
        features, mask = row["inputs"]
        row[key] = model.predict({"features": features, "mask": mask})["embedding"][0]
        row.setdefault("cosine", {})[key] = contract.cosine(row["torch"], row[key])
    features, mask = rows[0]["inputs"]
    for _ in range(5):
        model.predict({"features": features, "mask": mask})
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        model.predict({"features": features, "mask": mask})
        samples.append(1000 * (time.perf_counter() - start))
    cosines = [r["cosine"][key] for r in rows]
    reference, candidate = top1(rows, "torch"), top1(rows, key)
    return {"package": package.name, "compute_units": unit, "load_s": load_s,
            "clips": len(rows), "min_cosine": min(cosines), "mean_cosine": float(np.mean(cosines)),
            "clips_below_threshold": sum(c < PASS_COSINE for c in cosines),
            "top1_agree": sum(a == b for a, b in zip(reference, candidate)),
            "top1_correct": sum(r["label"] == c for r, c in zip(rows, candidate)),
            "passes": min(cosines) >= PASS_COSINE, "latency": percentiles(samples)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--precision", choices=sorted(cs.PRECISIONS), nargs="+", default=["fp16", "fp32"])
    parser.add_argument("--units", choices=UNITS, nargs="+", default=list(UNITS))
    parser.add_argument("--runs", type=int, default=100)
    args = parser.parse_args()
    torch.set_num_threads(4)
    packages = [cs.ARTIFACTS / cs.PRECISIONS[p] for p in args.precision]
    if missing := [p.name for p in packages if not p.exists()]:
        raise SystemExit(f"Missing {missing}; run convert_signclip.py first")

    rows, skipped = [], []
    for clip in clips():
        try:
            features, quality = signclip.extract(clip["path"], cs.ARTIFACTS / "features")
        except ValueError as error:  # e.g. > 256 frames: rejected by contract, not truncated
            skipped.append({"id": clip["id"], "reason": str(error)})
            continue
        rows.append({**clip, "features": features, "frames": quality["frames"]})
        print(f"features: {clip['id']} ({quality['frames']} frames)", flush=True)
    if len(rows) < 2:
        raise SystemExit("Need at least two clips; run spikes/recognition/fetch_clips.py")

    wrapper, model = cs.load_wrapper()
    embed_torch(rows, wrapper, model)
    torch_ms = [r["torch_ms"] for r in rows]
    results = []
    for package in packages:
        for unit in args.units:
            results.append(evaluate_coreml(rows, package, unit, args.runs))
            r = results[-1]
            print(f"{r['package']:32} {unit:11} min {r['min_cosine']:.6f} mean {r['mean_cosine']:.6f} "
                  f"top1 {r['top1_agree']}/{r['clips']} p50 {r['latency']['p50_ms']:.1f} ms "
                  f"p95 {r['latency']['p95_ms']:.1f} ms {'PASS' if r['passes'] else 'FAIL'}", flush=True)

    report = {
        "scope": "Core ML vs PyTorch embedding parity on Mac-extracted features; not iOS landmarks",
        "pass_cosine": PASS_COSINE, "signclip_source": signclip.REVISION,
        "checkpoint_sha256": signclip.CHECKPOINT_SHA, "torch": torch.__version__,
        "coremltools": __import__("coremltools").__version__, "machine": platform.platform(),
        "processor": platform.processor(), "clips_found": len(rows) + len(skipped),
        "clips_compared": len(rows), "skipped": skipped,
        "latency_input_frames": rows[0]["frames"],
        "torch_cpu_embed": {"threads": torch.get_num_threads(), **percentiles(torch_ms)},
        "wrapper_min_cosine": min(r["wrapper_cosine"] for r in rows),
        "garbage_padding_max_abs_diff": max(r["garbage_padding_max_abs_diff"] for r in rows),
        "unpadded_sequence_min_cosine": min(r["unpadded_sequence_cosine"] for r in rows),
        "results": results,
        "clips": [{k: r[k] for k in ("id", "label", "source", "frames", "wrapper_cosine",
                                     "unpadded_sequence_cosine", "cosine")} for r in rows],
    }
    destination = cs.ARTIFACTS / "parity.json"
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrapper min cosine {report['wrapper_min_cosine']:.7f}; garbage padding max diff "
          f"{report['garbage_padding_max_abs_diff']:.2e}; skipped {len(skipped)}")
    print(f"Evidence: {destination.relative_to(cs.HERE)}")


if __name__ == "__main__":
    main()
