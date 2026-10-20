"""Local diagnostic backend: real SL-GCN -> fixed sentence -> explicit approval.

    .venv/bin/python mini.py evaluate
    .venv/bin/python mini.py serve

Pass --composer llm to reproduce the earlier optional local Qwen experiment.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import torch

import slgcn
from sentence import Approval, INTENTS, LLM_ID, LLM_REVISION, SentenceModel, SentenceTemplates

EVIDENCE = slgcn.ARTIFACTS / "mini"
CACHE = EVIDENCE / "features"
VIDEO_SUFFIXES = {".mov", ".mp4", ".m4v"}


def inventory():
    items = []
    for path in sorted((slgcn.ARTIFACTS / "clips").rglob("*")):
        if path.suffix.lower() in VIDEO_SUFFIXES:
            items.append({"path": path, "kind": "dataset", "expected": slgcn.canonical(path.parent.name)})
    # These are the two documented intended-hello sessions; exclude the unrelated
    # earlier smoke-test recording. Expected labels never enter inference.
    for session in ("20261020-085528", "20261020-090502"):
        for path in sorted((slgcn.ARTIFACTS / "sessions" / session).glob("*.mp4")):
            items.append({"path": path, "kind": "recorded_attempt", "expected": "hello"})
    for index, item in enumerate(items):
        item.update(id=str(index), name=str(item["path"].relative_to(slgcn.ARTIFACTS)))
    return items


class Backend:
    def __init__(self, composer="templates"):
        if composer not in {"templates", "llm"}:
            raise ValueError("Unknown sentence composer")
        torch.set_num_threads(4)
        self.model, self.labels = slgcn.load_model()
        self.composer = composer
        self.language = SentenceModel() if composer == "llm" else SentenceTemplates()
        self.approval = Approval()
        self.clips = {item["id"]: item for item in inventory()}
        self.analyses = {}

    def reset(self):
        self.approval.clear()
        self.analyses.clear()
        return {"status": "cleared"}

    def analyze(self, clip_id):
        self.approval.clear()
        if not isinstance(clip_id, str) or clip_id not in self.clips:
            raise ValueError("Unknown clip")
        if len(self.analyses) >= 32:
            raise ValueError("Reset this turn before analyzing more clips")
        item = self.clips[clip_id]
        result = slgcn.analyze(self.model, self.labels, item["path"], CACHE)
        analysis_id = uuid.uuid4().hex
        result.update(analysis_id=analysis_id, clip_id=clip_id, clip=item["name"])
        self.analyses[analysis_id] = result
        return result

    def draft(self, *, analysis_ids=None, manual_concepts=None, intent=""):
        self.approval.clear()
        if (analysis_ids is None) == (manual_concepts is None):
            raise ValueError("Use recognition results OR explicitly supplied concepts")
        if manual_concepts is not None:
            concepts = manual_concepts
            source = "manually_supplied_not_recognition"
        else:
            if not isinstance(analysis_ids, list) or not 1 <= len(analysis_ids) <= 8:
                raise ValueError("Select 1–8 recognition results")
            concepts = []
            for ident in analysis_ids:
                if not isinstance(ident, str) or ident not in self.analyses:
                    raise ValueError("Recognition result expired; analyze the clip again")
                result = self.analyses[ident]["decision"]
                if result["status"] != "candidate":
                    raise ValueError("Cannot compose from an abstained recognition result")
                concepts.append(result["concept"])
            source = "slgcn_predictions"
        suggestion = self.language.suggest(concepts, intent)
        return self.approval.stage({**suggestion, "concepts_source": source})


def negative_clips():
    """Synthetic boundary checks, not a real idle or unknown-sign benchmark."""
    import cv2
    import numpy as np

    root = EVIDENCE / "negatives"
    root.mkdir(parents=True, exist_ok=True)
    reference = next(item["path"] for item in inventory() if item["expected"] == "hello" and item["kind"] == "dataset")
    cap = cv2.VideoCapture(str(reference))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise ValueError("Cannot decode the static negative's reference frame")
    frames = {"black": np.zeros((360, 640, 3), np.uint8),
              "static_reference": cv2.resize(frame, (640, 360))}
    items = []
    for name, frame in frames.items():
        path = root / f"{name}.mp4"
        if not path.exists():
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 25, (640, 360))
            if not writer.isOpened():
                raise RuntimeError("Cannot encode synthetic negative")
            try:
                for _ in range(50):
                    writer.write(frame)
            finally:
                writer.release()
        items.append({"path": path, "kind": "synthetic_negative", "expected": None,
                      "name": str(path.relative_to(slgcn.ARTIFACTS))})
    return items


def evaluate(composer="templates"):
    backend = Backend(composer)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    destination = EVIDENCE / ("evaluation.json" if composer == "llm" else "evaluation-templates.json")
    report = {
        "scope": "development replay, not a held-out test or live conversation",
        "source_revision": slgcn.SOURCE_REVISION,
        "checkpoint_archive_sha256": slgcn.ARCHIVE_SHA,
        "composer": backend.language.name,
        "llm": {"id": LLM_ID, "revision": LLM_REVISION} if composer == "llm" else None,
        "policy": slgcn.POLICY, "supported": sorted(slgcn.SUPPORTED),
        "machine": {"platform": platform.platform(), "torch": torch.__version__,
                    "device": "cpu", "threads": torch.get_num_threads()},
        "recognition": [], "sentences": [],
    }
    for item in inventory() + negative_clips():
        result = slgcn.analyze(backend.model, backend.labels, item["path"], CACHE)
        hit = result["top5"][0]["concept"] == item["expected"] if item["expected"] else None
        row = {**{k: v for k, v in item.items() if k != "path"}, **result, "top1_matches_intended": hit}
        report["recognition"].append(row)
        print(f"{item['name']}: {result['top5'][0]['label']} "
              f"{result['top5'][0]['score']:.3f} -> {result['decision']['status']}", flush=True)
        # Preserve partial evidence if a later case fails.
        destination.write_text(json.dumps(report, indent=2))
    for concepts, intent in [
        (["hello"], ""), (["thankyou"], ""), (["doctor", "tomorrow"], "request_appointment"),
        (["hospital", "location"], "ask_location"), (["today"], "specify_day"),
        (["doctor", "tomorrow"], ""),
    ]:
        result = backend.draft(manual_concepts=concepts, intent=intent)
        report["sentences"].append(result)
        print("Sentence-only:", concepts, "->", result.get("text") or result["status"], flush=True)
    # Fixed end-to-end case: model results from doctor + tomorrow, no gold-label
    # substitution. If either abstains, the chain is explicitly blocked.
    actual = [row for row in report["recognition"] if row["kind"] == "dataset"
              and row["expected"] in ("doctor", "tomorrow")]
    ids = []
    for row in actual:
        ident = uuid.uuid4().hex
        backend.analyses[ident] = row
        ids.append(ident)
    try:
        draft = backend.draft(analysis_ids=ids, intent="request_appointment")
        report["end_to_end"] = {"source_clips": [r["name"] for r in actual], "draft": draft}
    except ValueError as error:
        report["end_to_end"] = {"status": "blocked", "reason": str(error)}
    summary = {}
    for kind in ("dataset", "recorded_attempt", "synthetic_negative"):
        rows = [r for r in report["recognition"] if r["kind"] == kind]
        accepted = [r for r in rows if r["decision"]["status"] == "candidate"]
        summary[kind] = {
            "clips": len(rows), "top1_matches_intended": sum(r["top1_matches_intended"] is True for r in rows),
            "candidates": len(accepted), "wrong_candidates": sum(r["top1_matches_intended"] is not True for r in accepted),
            "abstentions": len(rows) - len(accepted),
        }
    summary["median_model_ms"] = statistics.median(r["model_ms"] for r in report["recognition"])
    summary["median_original_extraction_ms"] = statistics.median(r["quality"]["landmark_ms"] for r in report["recognition"])
    report["summary"] = summary
    destination.write_text(json.dumps(report, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"Evidence saved under {destination.relative_to(slgcn.ROOT)}")


def loopback_origin(value):
    """Accept an exact local preview origin, never a wildcard or arbitrary host."""
    try:
        parsed = urlsplit(value)
        if (parsed.hostname in {"127.0.0.1", "localhost"}
                and parsed.port is not None and 1 <= parsed.port <= 65535
                and value == f"http://{parsed.hostname}:{parsed.port}"):
            return value
    except ValueError:
        pass
    raise ValueError("Use an exact loopback origin, e.g. http://127.0.0.1:64343 (no path)")


def make_server(backend, port, preview_origin=None):
    if preview_origin is not None:
        preview_origin = loopback_origin(preview_origin)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def respond(self, code, body, content_type="application/json"):
            if content_type == "application/json":
                body = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                             "style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def allowed_host(self):
            if self.headers.get("Host") not in hosts:
                self.respond(403, {"error": "Local diagnostic requests only"})
                return False
            return True

        def do_GET(self):
            if not self.allowed_host():
                return
            path = urlsplit(self.path).path
            if path == "/":
                self.respond(200, (slgcn.ROOT / "mini.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/config":
                self.respond(200, {
                    "clips": [{k: v for k, v in item.items() if k != "path"} for item in backend.clips.values()],
                    "intents": INTENTS, "supported": sorted(slgcn.SUPPORTED),
                    "recognizer": "OpenHands INCLUDE SL-GCN", "sentence_model": backend.language.name,
                    "speech_status": "not_connected", "policy": slgcn.POLICY,
                })
            elif path == "/api/evidence":
                saved = EVIDENCE / ("evaluation.json" if backend.composer == "llm" else "evaluation-templates.json")
                self.respond(200, json.loads(saved.read_text()) if saved.exists() else {"summary": None})
            elif path == "/favicon.ico":
                self.respond(204, b"", "image/x-icon")
            else:
                self.respond(404, {"error": "Not found"})

        def do_POST(self):
            if not self.allowed_host():
                return
            if self.headers.get("Origin") not in origins | {None}:
                self.respond(403, {"error": "Cross-origin requests are not allowed"})
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self.respond(415, {"error": "Use application/json"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    raise ValueError("Invalid request size")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("Request must be a JSON object")
                with lock:
                    if self.path == "/api/analyze":
                        result = backend.analyze(data.get("clip_id"))
                    elif self.path == "/api/draft":
                        result = backend.draft(
                            analysis_ids=data.get("analysis_ids"),
                            manual_concepts=data.get("manual_concepts"),
                            intent=data.get("intent", ""))
                    elif self.path == "/api/approve":
                        result = backend.approval.approve(data.get("draft_id"), data.get("text"))
                    elif self.path == "/api/reset":
                        result = backend.reset()
                    else:
                        self.respond(404, {"error": "Not found"})
                        return
                self.respond(200, result)
            except (ValueError, TypeError, UnicodeError) as error:
                self.respond(400, {"error": str(error)})
            except Exception as error:
                self.log_error("Inference failed: %s", type(error).__name__)
                self.respond(500, {"error": "Inference failed; check assets and the server terminal"})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    origins = {f"http://127.0.0.1:{server.server_port}", f"http://localhost:{server.server_port}"}
    if preview_origin is not None:
        origins.add(preview_origin)
    hosts = {urlsplit(origin).netloc for origin in origins}
    return server


def serve(port, preview_origin=None, composer="templates"):
    backend = Backend(composer)
    server = make_server(backend, port, preview_origin)
    print(f"Open http://127.0.0.1:{port} — local diagnostic only; speech is not connected", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        backend.reset()
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["evaluate", "serve"])
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--composer", choices=["templates", "llm"], default="templates")
    parser.add_argument("--preview-origin", type=loopback_origin,
                        help="Allow this exact local browser-preview origin, including its port")
    args = parser.parse_args()
    if args.command == "evaluate":
        evaluate(args.composer)
    else:
        serve(args.port, args.preview_origin, args.composer)
