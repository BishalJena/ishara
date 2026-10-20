"""Contract checks; real model/clip measurements live in mini.py evaluate."""
import json
import threading
import unittest
from http.client import HTTPConnection
from unittest.mock import Mock

import numpy as np
import torch

import slgcn
from mini import Backend, make_server
from sentence import Approval, SentenceModel, SentenceTemplates


def bare_backend():
    backend = Backend.__new__(Backend)
    backend.approval = Approval()
    backend.language = Mock()
    backend.language.suggest.return_value = {"status": "draft", "text": "Example suggestion"}
    backend.analyses = {}
    backend.clips = {}
    return backend


class RecognitionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.quality = {"pose_fraction": 1.0, "hand_fraction": 1.0}

    def test_unsupported_winner_cannot_be_replaced_by_supported_runner_up(self):
        result = slgcn.decision([{"concept": "orange", "score": .9},
                                {"concept": "hello", "score": .1}], self.quality)
        self.assertEqual(result["status"], "abstain")
        self.assertIsNone(result["concept"])

    def test_high_confidence_cannot_override_missing_tracking(self):
        result = slgcn.decision([{"concept": "hello", "score": .99},
                                {"concept": "doctor", "score": .01}],
                               {"pose_fraction": 0, "hand_fraction": 0})
        self.assertEqual(result["status"], "abstain")

    def test_close_predictions_abstain(self):
        result = slgcn.decision([{"concept": "hello", "score": .51},
                                {"concept": "doctor", "score": .49}], self.quality)
        self.assertEqual(result["status"], "abstain")

    def test_invalid_pose_rejected_before_model_execution(self):
        for value in (np.zeros((0, 75, 3)), np.zeros((20, 27, 2)),
                      np.full((20, 75, 3), np.nan)):
            with self.subTest(shape=value.shape), self.assertRaises(ValueError):
                slgcn.features(value)

    @unittest.skipUnless(slgcn.SOURCE.exists(), "Requires setup_mini.py source checkout")
    def test_training_transform_removes_translation_and_uniform_scale(self):
        rng = np.random.default_rng(31)
        points = rng.uniform(.1, .8, size=(20, 75, 3)).astype(np.float32)
        shifted = points.copy()
        shifted[:, :, :2] = shifted[:, :, :2] * 1.7 + np.array([.12, -.09])
        torch.testing.assert_close(slgcn.features(points), slgcn.features(shifted),
                                   atol=1e-5, rtol=1e-5)


class CompositionBoundaryTests(unittest.TestCase):
    def test_templates_preserve_explicit_appointment_day_and_subject(self):
        model = SentenceTemplates()
        for day in ("today", "tomorrow"):
            result = model.suggest(["doctor", day], "request_appointment")
            self.assertEqual(result["text"], f"I would like an appointment with a doctor {day}.")
            self.assertEqual(result["source"], "fixed_template")
            self.assertEqual(model.suggest([day], "specify_day")["text"], f"I would like {day}.")
        self.assertEqual(model.suggest(["hospital", "location"], "ask_location")["text"],
                         "Where is the hospital?")

    def test_templates_cannot_silently_drop_conflicts_or_invent_purpose(self):
        model = SentenceTemplates()
        for concepts, intent in ((["today", "tomorrow"], "specify_day"),
                                 (["hello", "doctor"], "greet"),
                                 (["location"], "ask_location"),
                                 (["thankyou"], "request_appointment"),
                                 (["doctor", "tomorrow"], "")):
            with self.subTest(concepts=concepts, intent=intent):
                result = model.suggest(concepts, intent)
                self.assertNotEqual(result["status"], "draft")
                self.assertIsNone(result["text"])
        self.assertEqual(model.suggest(["hello"])["text"], "Hello.")
        self.assertEqual(model.suggest(["thankyou"])["text"], "Thank you.")

    def test_ambiguous_fragments_require_intent_without_loading_llm(self):
        model = SentenceModel()
        self.assertEqual(model.suggest(["doctor", "tomorrow"])["status"], "needs_intent")
        self.assertIsNone(model.model)

    def test_unsupported_concepts_never_reach_llm(self):
        model = SentenceModel()
        for concepts in ([], ["orange"], ["doctor", "not"], "hello"):
            with self.subTest(concepts=concepts), self.assertRaises(ValueError):
                model.suggest(concepts, "request_appointment")
        self.assertIsNone(model.model)

    def test_expected_label_does_not_replace_actual_prediction(self):
        backend = bare_backend()
        backend.analyses["a"] = {"expected": "hello", "decision": {"status": "candidate", "concept": "doctor"}}
        result = backend.draft(analysis_ids=["a"], intent="request_appointment")
        backend.language.suggest.assert_called_once_with(["doctor"], "request_appointment")
        self.assertEqual(result["concepts_source"], "slgcn_predictions")

    def test_abstention_blocks_composition(self):
        backend = bare_backend()
        backend.analyses["a"] = {"decision": {"status": "abstain", "concept": None}}
        with self.assertRaises(ValueError):
            backend.draft(analysis_ids=["a"])
        backend.language.suggest.assert_not_called()

    def test_manual_and_recognized_sources_cannot_be_mixed(self):
        backend = bare_backend()
        with self.assertRaises(ValueError):
            backend.draft(analysis_ids=["a"], manual_concepts=["hello"])
        backend.language.suggest.assert_not_called()

    def test_generation_failure_clears_previous_draft(self):
        backend = bare_backend()
        backend.draft(manual_concepts=["hello"])
        backend.language.suggest.side_effect = RuntimeError("test failure")
        with self.assertRaises(RuntimeError):
            backend.draft(manual_concepts=["doctor"], intent="request_appointment")
        self.assertIsNone(backend.approval.pending)

    def test_edited_approval_is_exact_single_use_and_not_sent(self):
        approval = Approval()
        draft = approval.stage({"status": "draft", "text": "Hello."})
        text = "Hello. I'd like to ask a question."
        result = approval.approve(draft["draft_id"], text)
        self.assertEqual(result["text"], text)
        self.assertTrue(result["edited"])
        self.assertFalse(result["sent_to_bolna"])
        with self.assertRaises(ValueError):
            approval.approve(draft["draft_id"], text)

    def test_new_analysis_invalidates_pending_approval_even_if_it_fails(self):
        backend = bare_backend()
        draft = backend.draft(manual_concepts=["hello"])
        with self.assertRaises(ValueError):
            backend.analyze("nonexistent")
        with self.assertRaises(ValueError):
            backend.approval.approve(draft["draft_id"], "Hello.")

    def test_reset_invalidates_both_recognition_and_approval(self):
        backend = bare_backend()
        backend.analyses["a"] = {"decision": {"status": "candidate", "concept": "hello"}}
        draft = backend.draft(analysis_ids=["a"])
        backend.reset()
        with self.assertRaises(ValueError):
            backend.draft(analysis_ids=["a"])
        with self.assertRaises(ValueError):
            backend.approval.approve(draft["draft_id"], "Hello.")


class HTTPBoundaryTests(unittest.TestCase):
    preview_origin = "http://127.0.0.1:64343"

    def start_server(self, preview_origin=None):
        backend = Mock()
        backend.reset.return_value = {"status": "cleared"}
        server = make_server(backend, 0, preview_origin)
        self.addCleanup(server.server_close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.shutdown)
        return server, backend

    def post_reset(self, server, origin=None, **headers):
        headers["Content-Type"] = "application/json"
        if origin is not None:
            headers["Origin"] = origin
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        try:
            connection.request("POST", "/api/reset", "{}", headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_direct_access_works_without_preview_configuration(self):
        server, backend = self.start_server()
        for origin in (None, f"http://127.0.0.1:{server.server_port}",
                       f"http://localhost:{server.server_port}"):
            with self.subTest(origin=origin):
                self.assertEqual(self.post_reset(server, origin), (200, {"status": "cleared"}))
        self.assertEqual(backend.reset.call_count, 3)

    def test_preview_is_rejected_until_explicitly_configured(self):
        server, backend = self.start_server()
        status, body = self.post_reset(
            server, self.preview_origin, **{"X-Forwarded-Host": "127.0.0.1:64343"})
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "Cross-origin requests are not allowed")
        backend.reset.assert_not_called()

    def test_configured_preview_accepts_rewritten_or_preserved_host(self):
        server, backend = self.start_server(self.preview_origin)
        for host in (f"127.0.0.1:{server.server_port}", "127.0.0.1:64343"):
            with self.subTest(host=host):
                self.assertEqual(self.post_reset(server, self.preview_origin, Host=host),
                                 (200, {"status": "cleared"}))
        self.assertEqual(backend.reset.call_count, 2)

    def test_unrelated_origins_and_hosts_stay_blocked(self):
        server, backend = self.start_server(self.preview_origin)
        for origin, host in (
            ("http://127.0.0.1:64344", f"127.0.0.1:{server.server_port}"),
            ("https://example.com", f"127.0.0.1:{server.server_port}"),
            ("null", f"127.0.0.1:{server.server_port}"),
            (self.preview_origin, "example.com"),
        ):
            with self.subTest(origin=origin, host=host):
                self.assertEqual(self.post_reset(server, origin, Host=host)[0], 403)
        backend.reset.assert_not_called()

    def test_preview_configuration_requires_exact_loopback_origin(self):
        for value in ("*", "http://example.com:64343", "http://0.0.0.0:64343",
                      "http://127.0.0.1", "http://127.0.0.1:0",
                      "http://127.0.0.1:65536", "http://127.0.0.1:invalid",
                      "https://127.0.0.1:64343", "http://127.0.0.1:64343/",
                      "http://127.0.0.1:64343?query=1", "http://127.0.0.1:64343#fragment",
                      "http://user@127.0.0.1:64343"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                make_server(Mock(), 0, value)


if __name__ == "__main__":
    unittest.main()
