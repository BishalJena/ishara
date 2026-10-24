"""Clip preparation, spec choices and the OCR text filter.

The ffmpeg and Apple Vision tests make a synthetic clip (test pattern + tone + title
tag, or a frame with a drawn word) and skip when the tool is missing.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

import build_spec as bs
import ocr
import prepare as pp
from sources import word_key

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


class WordKeys(unittest.TestCase):
    def test_sources_name_the_same_word_the_same_way(self):
        cases = {"Thank_You_(Sign_2)": "thank you", "55. Thank you": "thank you", "Thank_You": "thank you",
                 "Adult (1)": "adult", "Adult_(Sign_2) (1)": "adult", "help (2)": "help",
                 "B_Ed": "b ed", "Good_Morning": "good morning", "48. Hello": "hello"}
        for name, key in cases.items():
            with self.subTest(name):
                self.assertEqual(word_key(name), key)


class Spec(unittest.TestCase):
    def test_spread_picks_evenly_over_file_numbers(self):
        members = [["z", f"Cat/1. Dog/MVI_{n:04d}.MOV"] for n in (9, 1, 5, 3, 7, 2, 8, 4, 6, 10)]
        picked = [m[1] for m in bs.spread(members, 2)]
        self.assertEqual(picked, ["Cat/1. Dog/MVI_0003.MOV", "Cat/1. Dog/MVI_0008.MOV"])
        self.assertEqual(len(bs.spread(members, 20)), 10)

    def test_words_need_both_dictionaries_and_skip_homographs_but_keep_demo_words(self):
        include = {w: [["z", f"a/b/MVI_{i}.MOV"] for i in range(3)]
                   for w in ("dog", "cat", "fall", "doctor", "horse", "hello")}
        islrtc = {w: ["x"] for w in ("dog", "cat", "fall", "doctor", "horse", "yes", "hello")}
        bridgeconn = {w: [{}] for w in ("dog", "fall", "horse", "yes")}
        words = bs.choose_words(include, islrtc, bridgeconn, tests_per_word=2, max_words=10, seed=1)
        self.assertEqual(words, ["doctor", "dog", "hello", "horse", "yes"])
        few = bs.choose_words(include, islrtc, bridgeconn, tests_per_word=2, max_words=4, seed=1)
        self.assertEqual(len(few), 4)
        self.assertTrue({"doctor", "hello", "yes"} <= set(few))
        self.assertEqual(bs.choose_words(include, islrtc, bridgeconn, tests_per_word=4, max_words=10, seed=1),
                         ["doctor", "hello", "yes"])


class Clips(unittest.TestCase):
    def test_neutral_ids_are_distinct_random_and_reproducible(self):
        ids = pp.neutral_ids(200, seed=3)
        self.assertEqual(len(set(ids)), 200)
        self.assertTrue(all(len(i) == 14 and i.startswith("c_") and int(i.removeprefix("c_"), 16) >= 0 for i in ids))
        self.assertEqual(ids, pp.neutral_ids(200, seed=3))
        self.assertNotEqual(ids, sorted(ids))

    def test_cut_command_drops_audio_subtitles_data_and_metadata(self):
        command = pp.cut_command(Path("in.mov"), Path("out.mp4"), 1.0, 3.5, crop="100:100:0:0")
        for flag in ("-an", "-sn", "-dn"):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("-map_metadata") + 1], "-1")
        self.assertEqual(command[command.index("-map") + 1], "0:v:0")
        self.assertIn("crop=100:100:0:0", command[command.index("-vf") + 1])
        self.assertEqual(command[command.index("-ss") + 1], "1.000")
        self.assertNotIn("-ss", pp.cut_command(Path("a"), Path("b")))

    def test_check_probe_refuses_audio_or_descriptive_tags(self):
        clean = {"streams": ["video"], "stream_tags": [{"language": "und"}], "format_tags": {"major_brand": "isom"}}
        pp.check_probe(clean)
        for bad in ({**clean, "streams": ["video", "audio"]}, {**clean, "format_tags": {"title": "Hello"}},
                    {**clean, "stream_tags": [{"handler_name": "Hello"}]}, {**clean, "stream_tags": [{"encoder": "doctor"}]}):
            with self.subTest(bad), self.assertRaises(ValueError):
                pp.check_probe(bad)

    def test_assert_disjoint_refuses_any_shared_key(self):
        reference = {"id": "c_1", "sha256": "a", "source_id": "isl_x", "signer_id": "islrtc", "dataset": "islrtc",
                     "url": "u1", "raw_sha256": "r1"}
        test = {"id": "c_2", "sha256": "b", "source_id": "inc_y", "signer_id": "include", "dataset": "include",
                "url": "u2", "raw_sha256": "r2"}
        pp.assert_disjoint([reference], [test])
        for key in ("id", "sha256", "source_id", "signer_id", "dataset", "url", "raw_sha256"):
            with self.subTest(key), self.assertRaisesRegex(ValueError, "Leakage"):
                pp.assert_disjoint([reference], [{**test, key: reference[key]}])


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg/ffprobe not installed")
class Encoding(unittest.TestCase):
    def test_encoded_clip_is_bare_silent_video_at_25_fps(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp) / "src.mov", Path(tmp) / "out.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=30:duration=3",
                            "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-metadata", "title=Hello",
                            "-metadata", "comment=thank you", "-c:v", "libx264", "-c:a", "aac", "-shortest",
                            str(source)], check=True)
            subprocess.run(pp.cut_command(source, out, 0.5, 2.5), check=True)
            info = pp.probe(out)
            pp.check_probe(info)
            self.assertEqual(info["streams"], ["video"])
            self.assertAlmostEqual(info["duration"], 2.0, delta=0.1)
            dims = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                                              "stream=height,r_frame_rate", "-of", "json", str(out)],
                                             capture_output=True, text=True, check=True).stdout)["streams"][0]
            self.assertEqual((dims["height"], dims["r_frame_rate"]), (720, "25/1"))
            self.assertNotIn(b"Hello", out.read_bytes())


class TextBoxes(unittest.TestCase):
    def test_union_pads_and_clamps(self):
        found = [{"box": [0.1, 0.8, 0.3, 0.9]}, {"box": [0.25, 0.85, 0.5, 0.99]}]
        box = ocr.union_box(found)
        self.assertEqual([round(v, 3) for v in box], [0.08, 0.78, 0.52, 1.0])
        self.assertAlmostEqual(ocr.cover((0.0, 0.0, 0.5, 0.5)), 0.25)

    def test_pixelate_changes_only_the_box(self):
        frame = np.random.default_rng(0).integers(0, 255, (100, 200, 3), dtype=np.uint8)
        out = ocr.pixelate(frame, (0.5, 0.5, 1.0, 1.0))
        self.assertTrue(np.array_equal(out[:50], frame[:50]))
        self.assertTrue(np.array_equal(out[:, :100], frame[:, :100]))
        self.assertFalse(np.array_equal(out[50:, 100:], frame[50:, 100:]))

    def test_meaningful_ignores_low_confidence_and_symbols(self):
        boxes = [ocr.TextBox("Hello", 0.9, (0, 0, 1, 1)), ocr.TextBox("|", 0.9, (0, 0, 1, 1)),
                 ocr.TextBox("Time", 0.1, (0, 0, 1, 1))]
        self.assertEqual([b.text for b in ocr.meaningful(boxes)], ["Hello"])


@unittest.skipUnless(sys.platform == "darwin" and HAS_FFMPEG, "Apple Vision OCR needs macOS and ffmpeg")
class VisionFilter(unittest.TestCase):
    def write_clip(self, path, text, box_height=0.12):
        import cv2
        frames = []
        for i in range(10):
            frame = np.full((360, 640, 3), 90, dtype=np.uint8)
            cv2.circle(frame, (200 + 10 * i, 150), 40, (40, 160, 220), -1)  # a moving "hand"
            if text:
                cv2.putText(frame, text, (230, int(360 * (1 - box_height / 2))), cv2.FONT_HERSHEY_SIMPLEX, 1.5,
                            (255, 255, 255), 3)
            frames.append(frame)
        ocr.encode_frames(frames, 25, path, pp.ENCODE_ARGS)

    def test_a_caption_is_found_blurred_and_gone_on_recheck(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.mp4"
            self.write_clip(path, "DOCTOR")
            self.assertIn("DOCTOR", {f["text"] for f in ocr.scan(path)})
            record = ocr.clean(path, pp.ENCODE_ARGS, 25)
            self.assertEqual(record["action"], "blurred")
            self.assertEqual(record["recheck_texts"], [])
            self.assertEqual(ocr.scan(path), [])
            pp.check_probe(pp.probe(path))

    def test_a_clip_without_text_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.mp4"
            self.write_clip(path, None)
            before = path.read_bytes()
            self.assertEqual(ocr.clean(path, pp.ENCODE_ARGS, 25)["action"], "none")
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
