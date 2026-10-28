"""The recognition light tests: the one list scripts/verify.sh and CI both run.

Every test_*.py in spikes/recognition and spikes/asl_probe runs, except the modules and classes
named below with their reason, so a new test file is picked up without editing either runner:

    cd spikes/recognition && .venv-light/bin/python -m unittest -v light_tests

Light means requirements-light.txt (numpy, OpenCV). A test that needs more skips itself
(test_extract without MediaPipe) or is excluded here.
"""
from __future__ import annotations

import sys
import unittest
from collections.abc import Iterable
from pathlib import Path

HERE = Path(__file__).resolve().parent
FOLDERS = (HERE, HERE.parent / "asl_probe")
HEAVY_MODULES = {"test_mini": "imports torch and transformers (requirements.txt)"}
OWN_CATEGORY = {"test_mac_bridge.ClipDrivenFallback":
                'about 1.5 min with local venvs, model and clips; scripts/verify.sh "clip-driven fallback"'}


def light_suite(loader: unittest.TestLoader, folders: Iterable[Path] = FOLDERS) -> unittest.TestSuite:
    names: dict[str, Path] = {}
    for folder in folders:
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))
        for path in sorted(folder.glob("test_*.py")):
            if path.stem in names:
                raise RuntimeError(f"{path} and {names[path.stem]} share a module name; rename one")
            names[path.stem] = path
    if stale := set(HEAVY_MODULES) - set(names):
        raise RuntimeError(f"HEAVY_MODULES names missing test files: {sorted(stale)}")
    dropped: set[str] = set()
    suite = unittest.TestSuite()
    for name in names:
        if name not in HEAVY_MODULES:
            suite.addTest(_without_own_category(loader.loadTestsFromName(name), dropped))
    if stale := set(OWN_CATEGORY) - dropped:
        raise RuntimeError(f"OWN_CATEGORY names classes with no tests: {sorted(stale)}")
    return suite


def _without_own_category(suite: unittest.TestSuite, dropped: set[str]) -> unittest.TestSuite:
    kept = unittest.TestSuite()
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            kept.addTest(_without_own_category(test, dropped))
            continue
        name = f"{type(test).__module__}.{type(test).__qualname__}"
        if name in OWN_CATEGORY:
            dropped.add(name)
        else:
            kept.addTest(test)
    return kept


def load_tests(loader: unittest.TestLoader, standard_tests: unittest.TestSuite, pattern: str | None):
    """unittest's hook: `python -m unittest light_tests` runs this suite."""
    for name, reason in {**HEAVY_MODULES, **OWN_CATEGORY}.items():
        print(f"not run here: {name} ({reason})", file=sys.stderr)
    return light_suite(loader)
