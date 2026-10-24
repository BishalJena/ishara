"""Dataset and retrieval boundaries for a personalized isolated-sign pilot."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"
DATASET = ARTIFACTS / "pilot" / "dataset.json"
VOCABULARY = ("hello", "thankyou", "yes", "no", "sorry", "doctor",
              "today", "tomorrow", "morning", "afternoon", "evening", "time")
SPLITS = ("enrollment", "calibration", "test")
NEGATIVES = ("idle", "transition", "incomplete", "unsupported")
NEGATIVE_MINIMUM = {"calibration": 20, "test": 50}
# Shared with the iPhone through the exported bundle; change both sides together.
QUALITY = {"min_pose_fraction": 0.6, "min_hand_fraction": 0.2}


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def validate_records(records, root=ARTIFACTS, verify_files=True):
    """Fail on leakage, missing provenance, path escapes and changed recordings."""
    if not isinstance(records, list):
        raise ValueError("Dataset records must be a list")
    ids, sessions, sources, digests = set(), {}, {}, {}
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("Each dataset record must be an object")
        for field in ("id", "signer_id", "session_id", "source_id"):
            if not isinstance(row.get(field), str) or not re.fullmatch(r"[\w-]{1,100}", row[field]):
                raise ValueError(f"Invalid {field}")
        if row["id"] in ids:
            raise ValueError("Duplicate clip ID")
        ids.add(row["id"])
        split, label = row.get("split"), row.get("label")
        if split not in SPLITS or (label not in VOCABULARY and label is not None):
            raise ValueError("Unknown split or target concept")
        if label is None and row.get("negative_kind") not in NEGATIVES:
            raise ValueError("Negative clips need an explicit negative kind")
        if label is not None and row.get("negative_kind") is not None:
            raise ValueError("A supported sign cannot also be labeled negative")
        if split == "enrollment" and label is None:
            raise ValueError("Enrollment references must be supported signs")
        if type(row.get("verified")) is not bool:
            raise ValueError("Verification must be explicit")
        if row["verified"] and (not isinstance(row.get("verification_note"), str)
                                or not row["verification_note"].strip()):
            raise ValueError("Verified labels need a review/reference note")
        if not isinstance(row.get("provenance"), str) or not row["provenance"].strip():
            raise ValueError("Missing recording provenance")
        if not re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", "")):
            raise ValueError("Missing video content hash")
        path = (Path(root) / row.get("path", "")).resolve()
        if not path.is_relative_to(Path(root).resolve()) or path.suffix.lower() not in {".mp4", ".mov", ".m4v"}:
            raise ValueError("Video path must stay inside the local artifacts directory")
        if verify_files and (not path.is_file() or sha256(path) != row["sha256"]):
            raise ValueError("Missing or changed recording")
        for mapping, key, description in (
            (sessions, (row["signer_id"], row["session_id"]), "capture session"),
            (sources, row["source_id"], "source recording"),
            (digests, row["sha256"], "identical video"),
        ):
            if key in mapping and mapping[key] != split:
                raise ValueError(f"Leakage: {description} occurs in multiple splits")
            mapping[key] = split
    if len(digests) != len(records):
        raise ValueError("Duplicate video cannot increase sample counts")
    return records


def load_dataset(path=DATASET):
    if not Path(path).exists():
        return []
    document = json.loads(Path(path).read_text())
    if document.get("version") != 1:
        raise ValueError("Unknown dataset manifest version")
    return validate_records(document["records"])


def readiness(records, final=False):
    """Coverage is a prerequisite, never a substitute for measured accuracy."""
    if not final:
        records = [r for r in records if r["split"] != "test"]
    issues = []
    if not records:
        issues.append("No fresh pilot recordings")
    if any(not r["verified"] for r in records):
        issues.append("Unverified labels remain")
    if len({r["signer_id"] for r in records}) > 1:
        issues.append("This personalized pilot requires one designated signer")
    required = {"enrollment": 3, "calibration": 5}
    if final:
        required["test"] = 10
    counts = {}
    for split, minimum in required.items():
        counts[split] = dict(Counter(r["label"] or "negative" for r in records if r["split"] == split))
        for label in VOCABULARY:
            if counts[split].get(label, 0) < minimum:
                issues.append(f"{split}: need {minimum} verified examples of {label}")
        negative_minimum = NEGATIVE_MINIMUM.get(split, 0)
        if counts[split].get("negative", 0) < negative_minimum:
            issues.append(f"{split}: need {negative_minimum} negative clips")
        if negative_minimum:
            kinds = {r.get("negative_kind") for r in records if r["split"] == split and r["label"] is None}
            for kind in NEGATIVES:
                if kind not in kinds:
                    issues.append(f"{split}: missing {kind} negatives")
    return {"ready": not issues, "issues": issues, "counts": counts}


def unit(vector):
    vector = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(vector))
    if vector.ndim != 1 or not np.isfinite(vector).all() or not np.isfinite(norm) or norm <= 0:
        raise ValueError("Embedding must be a finite nonzero vector")
    return vector / norm


def rank(query, references):
    """Labels come only from reference annotations, never from query truth."""
    vector = unit(query["embedding"])
    best = {}
    for reference in references:
        if (reference["id"] == query["id"] or reference["sha256"] == query["sha256"]
                or reference["source_id"] == query["source_id"]):
            continue
        label = reference["label"]
        if label not in VOCABULARY:
            raise ValueError("Unsupported enrollment concept")
        other = unit(reference["embedding"])
        if other.shape != vector.shape:
            raise ValueError("Cannot mix encoders in a reference bank")
        score = float(np.clip(np.dot(vector, other), -1, 1))
        if label not in best or score > best[label]["similarity"]:
            best[label] = {"concept": label, "similarity": score, "reference_id": reference["id"]}
    ranking = sorted(best.values(), key=lambda r: (-r["similarity"], r["concept"]))
    return {"ranking": ranking, "margin": ranking[0]["similarity"] - ranking[1]["similarity"]
            if len(ranking) >= 2 else None}


def decision(result, quality, policy=None):
    if policy is None:
        return {"status": "abstain", "concept": None, "reason": "uncalibrated"}
    for field in ("similarity", "margin"):
        if (type(policy.get(field)) not in (int, float)
                or not np.isfinite(policy[field])):
            raise ValueError("Rejection policy must contain finite thresholds")
    top = result["ranking"]
    measurements = [result.get("margin"), quality.get("pose_fraction", 0),
                    quality.get("hand_fraction", 0)]
    if top:
        measurements.append(top[0]["similarity"])
    if any(v is None or not np.isfinite(v) for v in measurements):
        return {"status": "abstain", "concept": None, "reason": "invalid evidence"}
    if (not top or top[0]["concept"] not in VOCABULARY
            or quality.get("pose_fraction", 0) < QUALITY["min_pose_fraction"]
            or quality.get("hand_fraction", 0) < QUALITY["min_hand_fraction"]
            or top[0]["similarity"] < policy["similarity"] or result["margin"] < policy["margin"]):
        return {"status": "abstain", "concept": None, "reason": "insufficient evidence"}
    return {"status": "candidate", "concept": top[0]["concept"], "reason": None}
