"""Prompt builder and Gemini client on synthetic data: no network, no key, no money.

Guards the leakage rules (only the clip, the instruction and the shuffled list are sent;
the answer key is never opened), the JSON contract, pricing and the budget guard.
"""
import builtins
import inspect
import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import gemini_run as gr
import prompt

WORDS = ["hello", "thank you", "doctor", "good morning", "time"]


class Prompt(unittest.TestCase):
    def test_every_query_gets_a_fresh_permutation(self):
        orders = {tuple(prompt.shuffled(WORDS, random.Random(seed))) for seed in range(20)}
        self.assertGreater(len(orders), 10)
        for order in orders:
            self.assertEqual(sorted(order), sorted(WORDS))

    def test_duplicates_or_unsure_in_the_list_are_refused(self):
        for bad in (["hello", "hello"], ["hello", "unsure"]):
            with self.subTest(bad), self.assertRaises(ValueError):
                prompt.shuffled(bad, random.Random(0))

    def test_prompt_lists_each_word_once_in_the_given_order(self):
        text = prompt.build_prompt(["time", "hello", "thank you"])
        self.assertTrue(text.endswith("Candidate words: time, hello, thank you"))
        self.assertIn('"unsure"', text)
        self.assertIn("Indian Sign Language", text)

    def test_schema_allows_only_list_words_or_unsure(self):
        schema = prompt.response_schema(["time", "hello"])
        self.assertEqual(schema["properties"]["word"]["enum"], ["time", "hello", "unsure"])
        self.assertEqual(schema["required"], ["word", "confidence"])
        self.assertEqual((schema["properties"]["confidence"]["minimum"],
                          schema["properties"]["confidence"]["maximum"]), (0, 1))

    def test_prompt_module_cannot_read_files(self):
        source = inspect.getsource(prompt)
        for forbidden in ("open(", "read_text", "read_bytes", "answer_key", "import os", "pathlib", "json.load"):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("{", prompt.TEMPLATE.replace("{{", "").replace("}}", "").replace("{candidates}", ""))


class FakeInteractions:
    def __init__(self, responses):
        self.responses, self.bodies = list(responses), []

    def create(self, **body):
        self.bodies.append(body)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeFiles:
    def __init__(self):
        self.uploaded, self.deleted = [], []

    def upload(self, file):
        self.uploaded.append(file)
        return SimpleNamespace(name="files/abc", uri="https://files/abc", state=SimpleNamespace(name="ACTIVE"))

    def delete(self, name):
        self.deleted.append(name)


def interaction(word="doctor", confidence=0.8, input_tokens=5000, output=20, thought=300):
    usage = SimpleNamespace(total_input_tokens=input_tokens, total_output_tokens=output, total_thought_tokens=thought,
                            total_cached_tokens=0, total_tool_use_tokens=None,
                            total_tokens=input_tokens + output + thought,
                            input_tokens_by_modality=[SimpleNamespace(modality="video", tokens=input_tokens - 400)])
    return SimpleNamespace(output_text=json.dumps({"word": word, "confidence": confidence}), usage=usage,
                           status="completed")


class ApiError(Exception):
    def __init__(self, code, message="boom"):
        super().__init__(message)
        self.status_code = code


class Workspace(unittest.TestCase):
    """A temporary artifacts tree with a manifest, candidates, a clip and an answer key."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "clips").mkdir()
        (self.root / "key").mkdir()
        self.clip_bytes = b"\x00\x00\x00 ftypisom fake-video-bytes"
        (self.root / "clips" / "c_00000000abcd.mp4").write_bytes(self.clip_bytes)
        self.clip = {"id": "c_00000000abcd", "path": "clips/c_00000000abcd.mp4", "sha256": "f" * 64}
        (self.root / "manifest.json").write_text(json.dumps({"version": 1, "clips": [self.clip]}))
        (self.root / "candidates.json").write_text(json.dumps({"words": WORDS}))
        self.key = self.root / "key" / "answer_key.json"
        self.key.write_text(json.dumps({"answers": {self.clip["id"]: "doctor"}}))

    def tearDown(self):
        self.tmp.cleanup()

    def probe(self, responses, cap=10.0, secret=""):
        client = SimpleNamespace(interactions=FakeInteractions(responses), files=FakeFiles())
        return gr.GeminiProbe(client, WORDS, gr.Budget(cap), seed=7, secret=secret, sleep=lambda s: None), client


class ManifestAndKey(Workspace):
    def test_manifest_with_a_label_or_source_is_refused(self):
        for field in ("label", "word", "source_id", "url"):
            (self.root / "m.json").write_text(json.dumps({"clips": [{**self.clip, field: "x"}]}))
            with self.subTest(field), self.assertRaisesRegex(ValueError, "no label or source"):
                gr.load_manifest(self.root / "m.json")

    def test_a_whole_query_never_opens_the_answer_key(self):
        opened = []
        real_open = builtins.open

        def tracking_open(file, *args, **kwargs):
            opened.append(str(file))
            return real_open(file, *args, **kwargs)

        with mock.patch.object(builtins, "open", tracking_open), \
                mock.patch.object(Path, "open", lambda self, *a, **k: tracking_open(self, *a, **k)):
            clips = gr.load_manifest(self.root / "manifest.json")
            words = gr.load_candidates(self.root / "candidates.json")
            probe, _ = self.probe([interaction()])
            probe.words = words
            record = probe.ask(clips[0], root=self.root)
        self.assertEqual(record["status"], "ok")
        self.assertTrue(any("manifest.json" in p for p in opened))
        self.assertFalse([p for p in opened if "key" in Path(p).parts or "answer_key" in p], opened)

    def test_read_key_finds_the_value_and_never_echoes_the_file(self):
        env = self.root / ".env"
        env.write_text("OTHER=1\nexport GEMINI_API_KEY='abc123'\n")
        self.assertEqual(gr.read_key(env), "abc123")
        env.write_text("GEMINI_API_KEY=\nSECRET_THING=zzz\n")
        with self.assertRaises(SystemExit) as raised:
            gr.read_key(env)
        self.assertNotIn("zzz", str(raised.exception))


class Request(Workspace):
    def test_only_the_video_the_instruction_and_a_shuffled_list_are_sent(self):
        probe, client = self.probe([interaction()])
        probe.ask(self.clip, root=self.root)
        body = client.interactions.bodies[0]
        self.assertEqual(set(body), {"model", "store", "input", "generation_config", "response_format"})
        self.assertEqual(body["model"], "gemini-4-argon")
        self.assertIs(body["store"], False)
        video, text = body["input"]
        self.assertEqual(set(video), {"type", "mime_type", "processing", "resolution", "data"})
        self.assertEqual(video["processing"], {"type": "static", "fps": gr.VIDEO_FPS})
        self.assertEqual(video["data"], gr.base64.b64encode(self.clip_bytes).decode())
        self.assertEqual(set(text), {"type", "text"})
        listed = text["text"].rsplit("Candidate words: ", 1)[1].split(", ")
        self.assertEqual(sorted(listed), sorted(WORDS))
        self.assertEqual(body["response_format"]["schema"]["properties"]["word"]["enum"], [*listed, "unsure"])
        self.assertEqual(body["generation_config"]["thinking_level"], "low")
        serialized = json.dumps({**body, "input": [{**video, "data": ""}, text]})
        for leak in (self.clip["id"], "c_0000", ".mp4", "clips/", self.clip["sha256"], "answer_key", "doctor\"}"):
            self.assertNotIn(leak, serialized)

    def test_the_order_differs_between_clips_but_repeats_for_the_same_clip(self):
        probe, client = self.probe([interaction() for _ in range(3)])
        other = {**self.clip, "id": "c_0000000000ef"}
        (self.root / "clips" / "x.mp4").write_bytes(self.clip_bytes)
        other["path"] = "clips/x.mp4"
        for clip in (self.clip, other, self.clip):
            probe.ask(clip, root=self.root)
        texts = [b["input"][1]["text"] for b in client.interactions.bodies]
        self.assertEqual(texts[0], texts[2])
        self.assertNotEqual(texts[0], texts[1])

    def test_answer_record_has_word_confidence_usage_cost_and_latency(self):
        probe, _ = self.probe([interaction("thank you", 0.6, input_tokens=10_000, output=30, thought=470)])
        record = probe.ask(self.clip, root=self.root)
        self.assertEqual((record["status"], record["word"], record["confidence"]), ("ok", "thank you", 0.6))
        self.assertAlmostEqual(record["cost_usd"], 10_000 * 2e-6 + 500 * 10e-6)
        self.assertEqual(record["usage"]["total_thought_tokens"], 470)
        self.assertGreaterEqual(record["latency_s"], 0)
        self.assertEqual(record["sha256"], self.clip["sha256"])


class Answers(unittest.TestCase):
    def test_parse_answer(self):
        cases = [('{"word": "time", "confidence": 0.9}', ("time", 0.9)),
                 ('{"word": "unsure", "confidence": 0.1}', ("unsure", 0.1)),
                 ('{"word": "Time", "confidence": 0.9}', ("invalid", None)),
                 ('{"word": "banana", "confidence": 0.9}', ("invalid", None)),
                 ('{"confidence": 0.9}', ("invalid", None)),
                 ("not json", ("invalid", None)), (None, ("invalid", None)),
                 ('{"word": "time"}', ("time", None))]
        for text, expected in cases:
            with self.subTest(text):
                self.assertEqual(gr.parse_answer(text, WORDS), expected)

    def test_cost_counts_thinking_at_the_output_price(self):
        usage = {"total_input_tokens": 1_000_000, "total_output_tokens": 100_000, "total_thought_tokens": 400_000}
        self.assertAlmostEqual(gr.cost_usd(usage), 2.0 + 5.0)
        self.assertEqual(gr.cost_usd({}), 0.0)


class BudgetGuard(Workspace):
    def test_reserve_refuses_what_would_cross_the_cap(self):
        budget = gr.Budget(1.0)
        self.assertTrue(budget.reserve(0.6))
        self.assertFalse(budget.reserve(0.5))
        budget.settle(0.6, 0.2)
        self.assertAlmostEqual(budget.spent_usd, 0.2)
        self.assertTrue(budget.reserve(0.8))
        self.assertFalse(budget.reserve(0.01))

    def test_no_call_is_made_when_the_worst_case_does_not_fit(self):
        probe, client = self.probe([interaction()], cap=gr.MAX_OUTPUT_TOKENS * gr.PRICE_OUTPUT / 2)
        record = probe.ask(self.clip, root=self.root)
        self.assertEqual(record["status"], "skipped_budget")
        self.assertEqual(client.interactions.bodies, [])

    def test_spending_is_settled_to_the_actual_cost(self):
        probe, _ = self.probe([interaction(input_tokens=1000, output=0, thought=0)])
        probe.ask(self.clip, root=self.root)
        self.assertAlmostEqual(probe.budget.spent_usd, 1000 * 2e-6)
        self.assertAlmostEqual(probe.budget.reserved_usd, 0.0)

    def test_estimate_grows_to_the_largest_input_seen(self):
        probe, _ = self.probe([interaction(input_tokens=90_000)])
        first = probe.estimate_input(3.0)
        probe.ask(self.clip, root=self.root)
        self.assertGreater(first, 3 * gr.VIDEO_FPS * 280)
        self.assertEqual(probe.estimate_input(3.0), 90_000)


class Failures(Workspace):
    def test_rate_limits_are_retried(self):
        probe, client = self.probe([ApiError(429), ApiError(503), interaction()])
        self.assertEqual(probe.ask(self.clip, root=self.root)["status"], "ok")
        self.assertEqual(len(client.interactions.bodies), 3)

    def test_other_errors_fail_the_clip_and_never_show_the_key(self):
        probe, client = self.probe([ApiError(400, "bad key sk-SECRET-123 rejected")], secret="sk-SECRET-123")
        record = probe.ask(self.clip, root=self.root)
        self.assertEqual(record["status"], "error")
        self.assertNotIn("sk-SECRET-123", record["error"])
        self.assertEqual(len(client.interactions.bodies), 1)
        self.assertAlmostEqual(probe.budget.reserved_usd, 0.0)

    def test_large_clips_are_uploaded_and_always_deleted(self):
        for responses in ([interaction()], [ApiError(400)]):
            probe, client = self.probe(responses)
            with self.subTest(responses), mock.patch.object(gr, "INLINE_LIMIT", 4):
                probe.ask(self.clip, root=self.root)
                self.assertEqual(client.files.deleted, ["files/abc"])
                self.assertEqual(client.interactions.bodies[0]["input"][0]["uri"], "https://files/abc")
                self.assertNotIn("data", client.interactions.bodies[0]["input"][0])


class Resume(Workspace):
    def test_done_ids_and_spent_read_the_logs(self):
        log = self.root / "p.jsonl"
        gr.append(log, {"id": "a", "status": "ok"})
        gr.append(log, {"id": "b", "status": "error"})
        self.assertEqual(gr.done_ids(log), {"a"})
        costs = self.root / "c.jsonl"
        gr.append(costs, {"id": "a", "cost_usd": 0.25})
        gr.append(costs, {"id": "c", "cost_usd": 0.5})
        self.assertAlmostEqual(gr.spent(costs), 0.75)
        self.assertEqual(gr.spent(self.root / "missing.jsonl"), 0.0)


if __name__ == "__main__":
    unittest.main()
