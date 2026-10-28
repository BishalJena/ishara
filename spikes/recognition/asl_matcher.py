"""The public ASL Signs model as a live_source Matcher, with the open-set decision rule (D8).

Pure parts (no model, no MediaPipe) are `load_asl_bundle` and `asl_decision`, so the rule can
be unit-tested and mirrored in Swift. `AslMatcher` runs the model through asl_model.AslModel
and turns the 250 probabilities into a live_source.Match: `sign` for a chip, `pick_one` for a
candidate the user must confirm, neither for "?". `track_kaggle` produces the observations
the matcher needs (legacy Holistic -> Kaggle 543x3 frame) alongside the detector frame.
"""
from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

import live_source as ls
from asl_model import AslModel, kaggle_frame, quality
from detect_clips import holistic, to_frame

ROOT = Path(__file__).resolve().parent
DEFAULT_ASL_BUNDLE = ROOT / "fixtures" / "asl" / "asl-bundle-provisional.json"
PROVISIONAL_BANNER = "PROVISIONAL — public-clip candidate, not frozen on the iPhone clips"
TOP_K = 3


@dataclass(frozen=True)
class AslBundle:
    glosses: tuple[str, ...]
    vocabulary: frozenset[str]
    thresholds: dict[str, float]  # p, margin, pick_one_p
    per_word: dict[str, float]  # gloss -> chip cut-off overriding thresholds["p"]
    quality: dict[str, float]  # min_pose_fraction, min_hand_fraction
    provisional: bool
    model_sha256: str

    def chip_cutoff(self, gloss: str) -> float:
        return self.per_word.get(gloss, self.thresholds["p"])


def load_asl_bundle(path: Path = DEFAULT_ASL_BUNDLE) -> AslBundle:
    document = json.loads(Path(path).read_text())
    if document.get("version") != 2 or document.get("kind") != "asl-signs-logits":
        raise ValueError(f"{path}: not a version-2 asl-signs-logits bundle")
    glosses = tuple(document["glosses"])
    if len(glosses) != len(set(glosses)) or len(glosses) < 2:
        raise ValueError(f"{path}: glosses must be unique")
    vocabulary = frozenset(document["vocabulary"])
    unknown = vocabulary - set(glosses)
    if unknown:
        raise ValueError(f"{path}: vocabulary words the model has no class for: {sorted(unknown)}")
    thresholds = {k: float(document["thresholds"][k]) for k in ("p", "margin", "pick_one_p")}
    if not all(0 <= v <= 1 for v in thresholds.values()) or thresholds["pick_one_p"] > thresholds["p"]:
        raise ValueError(f"{path}: thresholds must be in [0, 1] with pick_one_p <= p")
    per_word = {k: float(v) for k, v in document.get("per_word", {}).items()}
    if set(per_word) - vocabulary:
        raise ValueError(f"{path}: per_word entries must be vocabulary words")
    q = {k: float(document["quality"][k]) for k in ("min_pose_fraction", "min_hand_fraction")}
    return AslBundle(glosses, vocabulary, thresholds, per_word, q, bool(document.get("provisional", True)),
                     str(document["model"]["sha256"]))


def softmax(logits: np.ndarray) -> np.ndarray:
    z = np.asarray(logits, dtype=np.float64)
    z = z - z.max()
    e = np.exp(z)
    return e / e.sum()


def asl_decision(probs: np.ndarray, quality_: dict[str, float], bundle: AslBundle) -> dict[str, Any]:
    """The open-set rule over the full probability vector. Never restricts to the vocabulary first.

    status: "chip" (sign set), "pick_one" (candidate set, sign None) or "abstain".
    """
    p = np.asarray(probs, dtype=np.float64)
    if p.shape != (len(bundle.glosses),) or not np.isfinite(p).all():
        return {"status": "abstain", "sign": None, "candidate": None, "reason": "invalid evidence",
                "p": None, "margin": None, "top": []}
    order = np.argsort(-p)
    top = [(bundle.glosses[i], float(p[i])) for i in order[:TOP_K]]
    gloss, p1 = top[0]
    margin = float(p[order[0]] - p[order[1]])
    base = {"candidate": None, "p": p1, "margin": margin, "top": top}
    failed: list[str] = []
    for key, name in (("min_pose_fraction", "pose"), ("min_hand_fraction", "hands")):
        if quality_.get(key.replace("min_", ""), 0.0) < bundle.quality[key]:
            failed.append(name)
    if failed:
        return {**base, "status": "abstain", "sign": None, "reason": "tracking: " + ", ".join(failed)}
    if gloss not in bundle.vocabulary:
        return {**base, "status": "abstain", "sign": None, "reason": f"not in vocabulary: {gloss} {p1:.2f}"}
    if p1 >= bundle.chip_cutoff(gloss) and margin >= bundle.thresholds["margin"]:
        return {**base, "status": "chip", "sign": gloss, "reason": None}
    if p1 >= bundle.thresholds["pick_one_p"]:
        return {**base, "status": "pick_one", "sign": None, "candidate": gloss,
                "reason": f"pick one: {gloss} {p1:.2f} (chip needs {bundle.chip_cutoff(gloss):.2f}, margin {margin:.2f})"}
    return {**base, "status": "abstain", "sign": None, "reason": f"unsure: {gloss} {p1:.2f}"}


def track_kaggle(images, keep_image: bool) -> Iterator[ls.Observation]:
    """Legacy Holistic once per frame: detector wrists plus the Kaggle 543x3 frame."""
    import cv2

    with holistic() as tracker:
        for t, wall, bgr in images:
            result = tracker.process(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            yield ls.Observation(wall, to_frame(t, result), kaggle_frame(result), bgr if keep_image else None)


class AslMatcher:
    """Duck-types live_source.Matcher: observations -> Match. `similarity` carries the probability."""

    def __init__(self, bundle: AslBundle, model: AslModel | None = None) -> None:
        self.bundle = SimpleNamespace(provisional=bundle.provisional, asl=bundle)
        self.asl = bundle
        self.model = model or AslModel()
        if tuple(self.model.glosses) != bundle.glosses:
            raise ValueError("bundle glosses do not match the model's class map")
        self.thresholds = {"similarity": bundle.thresholds["p"], "margin": bundle.thresholds["margin"],
                           **bundle.quality}
        self.last_landmarks: np.ndarray | None = None

    def __call__(self, observations: Sequence[ls.Observation]) -> ls.Match:
        landmarks = np.stack([o.landmarks for o in observations]).astype(np.float32)
        self.last_landmarks = landmarks
        q = quality(landmarks)
        verdict = asl_decision(self.model.predict(landmarks), q, self.asl)
        top = tuple(ls.Candidate(g, p) for g, p in verdict["top"])
        failed = tuple(k for k in ("pose", "hands") if verdict["reason"] and k in verdict["reason"])
        return ls.Match(verdict["sign"], verdict["reason"], similarity=verdict["p"], margin=verdict["margin"],
                        top=top, quality=q, thresholds=self.thresholds, failed_checks=failed,
                        provisional=self.asl.provisional, pick_one=verdict["candidate"])

    def close(self) -> None:
        self.model.close()


def asl_matcher(bundle_path: Path = DEFAULT_ASL_BUNDLE) -> AslMatcher:
    bundle = load_asl_bundle(bundle_path)
    if bundle.provisional:
        ls.log(f"WARNING: {PROVISIONAL_BANNER} ({bundle_path.name})")
    return AslMatcher(bundle)
