"""light_tests.py: the one recognition test list picks up every test file but the named exclusions."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import light_tests


def ids_of(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from ids_of(test)
        else:
            yield test.id()


def modules_and_classes(suite):
    ids = list(ids_of(suite))
    return {i.split(".")[0] for i in ids}, {".".join(i.split(".")[:2]) for i in ids}


class LightSuite(unittest.TestCase):
    def test_runs_every_test_file_of_both_folders_but_test_mini(self):
        modules, _ = modules_and_classes(light_tests.light_suite(unittest.TestLoader()))
        expected = {path.stem for folder in light_tests.FOLDERS for path in folder.glob("test_*.py")}
        self.assertEqual(modules, expected - {"test_mini"})
        # the ones the hand-written lists missed (issue #48), and the asl_probe ones
        self.assertLessEqual({"test_asl_matcher", "test_asl_summary", "test_fetch_clips", "test_light_tests",
                              "test_parity", "test_public_clips", "test_extract"}, modules)

    def test_leaves_the_clip_driven_fallback_to_its_own_category(self):
        _, classes = modules_and_classes(light_tests.light_suite(unittest.TestLoader()))
        self.assertNotIn("test_mac_bridge.ClipDrivenFallback", classes)
        self.assertLessEqual({"test_mac_bridge.SignLabVideo", "test_mac_bridge.BridgeTests"}, classes)

    def test_a_new_test_file_is_picked_up_without_editing_a_list(self):
        with TemporaryDirectory() as folder:
            Path(folder, "test_brand_new.py").write_text(
                "import unittest\n\nclass New(unittest.TestCase):\n    def test_it(self):\n        pass\n")
            try:
                suite = light_tests.light_suite(unittest.TestLoader(), (*light_tests.FOLDERS, Path(folder)))
            finally:
                sys.path.remove(folder)
                sys.modules.pop("test_brand_new", None)
        self.assertIn("test_brand_new.New.test_it", list(ids_of(suite)))

    def test_two_folders_with_the_same_test_file_name_fail(self):
        # one module name can be imported once, so the second file would silently not run
        with TemporaryDirectory() as one, TemporaryDirectory() as two:
            for folder in (one, two):
                Path(folder, "test_same.py").write_text("")
            try:
                with self.assertRaisesRegex(RuntimeError, "share a module name"):
                    light_tests.light_suite(unittest.TestLoader(), (Path(one), Path(two)))
            finally:
                for folder in (one, two):
                    if folder in sys.path:
                        sys.path.remove(folder)

    def test_a_stale_exclusion_fails_instead_of_silently_running_everything(self):
        for table, name in ((light_tests.HEAVY_MODULES, "test_renamed"),
                            (light_tests.OWN_CATEGORY, "test_mac_bridge.Renamed")):
            with self.subTest(name=name), mock.patch.dict(table, {name: "gone"}), \
                    self.assertRaisesRegex(RuntimeError, name):
                light_tests.light_suite(unittest.TestLoader())

    def test_unittest_runs_the_light_suite_through_load_tests(self):
        with contextlib.redirect_stderr(io.StringIO()) as err:
            suite = unittest.TestLoader().loadTestsFromModule(light_tests)
        modules, _ = modules_and_classes(suite)
        self.assertIn("test_fetch_clips", modules)
        self.assertNotIn("test_mini", modules)
        self.assertIn("not run here: test_mini", err.getvalue())


if __name__ == "__main__":
    unittest.main()
