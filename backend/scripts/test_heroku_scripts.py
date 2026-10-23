"""Heroku helper scripts against a fake `heroku` CLI: guards, what is sent, what is printed.

Stdlib only; no network. Run: python3 -m unittest discover -s backend/scripts -p 'test_*.py'
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

# Logs every call as a JSON argv line. Like the real CLI, config:set echoes the values it set,
# so a script that forgets to discard that output leaks secrets and fails the tests.
FAKE_HEROKU = r"""#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
log = os.environ["FAKE_LOG"]
previous = open(log).read().splitlines() if os.path.exists(log) else []
with open(log, "a") as handle:
    handle.write(json.dumps(args) + "\n")
command = args[0] if args else ""
if command == "config:set":
    print("Setting config vars and restarting... done")
    for pair in args[1:]:
        if "=" in pair:
            name, value = pair.split("=", 1)
            print(f"{name}: {value}")
elif command == "ps:type":
    seen = sum(1 for line in previous if json.loads(line)[:1] == ["ps:type"])
    key = "FAKE_PS_TYPE_AFTER" if seen and "FAKE_PS_TYPE_AFTER" in os.environ else "FAKE_PS_TYPE"
    print(os.environ.get(key, ""))
elif command == "info":
    print("name=" + args[-1])
    print("web_url=" + os.environ.get("FAKE_WEB_URL", ""))
"""

EXAMPLE = """# comment lines and blank lines are ignored

APP_TOKEN=
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
ALLOWED_RECIPIENTS=
PUBLIC_BASE_URL=
HEROKU_APP_NAME=
"""

SECRETS = ("tok-111", "gsk-222", "+910000000000")


class HerokuScriptCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.repo = self.tmp / "repo"
        scripts = self.repo / "backend" / "scripts"
        scripts.mkdir(parents=True)
        for name in ("heroku_common.sh", "heroku_config_push.sh", "heroku_deploy.sh"):
            if (SCRIPTS / name).exists():
                shutil.copy2(SCRIPTS / name, scripts / name)
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "heroku"
        fake.write_text(FAKE_HEROKU)
        fake.chmod(0o755)
        self.log = self.tmp / "heroku.log"
        self.env = {
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "FAKE_LOG": str(self.log),
        }

    def run_script(self, name: str, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.repo / "backend" / "scripts" / name), *args],
            cwd=self.repo,
            env={**self.env, **env},
            capture_output=True,
            text=True,
            timeout=60,
        )

    def heroku_calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]


class ConfigPush(HerokuScriptCase):
    def setUp(self) -> None:
        super().setUp()
        (self.repo / ".env.example").write_text(EXAMPLE)
        (self.repo / ".env").write_text(
            "APP_TOKEN=old-value\n"
            f'APP_TOKEN="{SECRETS[0]}"\n'
            f"export GROQ_API_KEY='{SECRETS[1]}'\r\n"
            "GROQ_MODEL=openai/gpt-oss-120b\n"
            f"ALLOWED_RECIPIENTS={SECRETS[2]}\n"
            "PUBLIC_BASE_URL=\n"
            "HEROKU_APP_NAME=local-only\n"
            "HEROKU_API_KEY=local-key\n"
            "NOT_IN_EXAMPLE=stray\n"
        )

    def assert_no_secret_printed(self, result: subprocess.CompletedProcess[str]) -> None:
        for secret in (*SECRETS, "old-value", "local-key", "local-only"):
            self.assertNotIn(secret, result.stdout + result.stderr)

    def test_without_yes_lists_names_and_never_calls_heroku(self) -> None:
        result = self.run_script("heroku_config_push.sh", "--app", "ishara-test")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.heroku_calls(), [])
        self.assertIn(
            "will set: APP_TOKEN GROQ_API_KEY GROQ_MODEL ALLOWED_RECIPIENTS", result.stdout
        )
        self.assertIn("skipped: PUBLIC_BASE_URL", result.stdout)
        self.assert_no_secret_printed(result)

    def test_sends_exact_example_names_with_parsed_values(self) -> None:
        result = self.run_script("heroku_config_push.sh", "--app", "ishara-test", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.heroku_calls(),
            [
                [
                    "config:set",
                    "--app",
                    "ishara-test",
                    f"APP_TOKEN={SECRETS[0]}",
                    f"GROQ_API_KEY={SECRETS[1]}",
                    "GROQ_MODEL=openai/gpt-oss-120b",
                    f"ALLOWED_RECIPIENTS={SECRETS[2]}",
                ]
            ],
        )
        self.assert_no_secret_printed(result)

    def test_heroku_names_are_never_sent_even_if_listed_in_example(self) -> None:
        self.run_script("heroku_config_push.sh", "--app", "ishara-test", "--yes")
        sent = " ".join(" ".join(call) for call in self.heroku_calls())
        self.assertNotIn("HEROKU_", sent)
        self.assertNotIn("NOT_IN_EXAMPLE", sent)

    def test_missing_env_file_fails_before_heroku(self) -> None:
        (self.repo / ".env").unlink()
        result = self.run_script("heroku_config_push.sh", "--app", "ishara-test", "--yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".env", result.stderr)
        self.assertEqual(self.heroku_calls(), [])

    def test_rejects_missing_or_invalid_app_name(self) -> None:
        for args in ((), ("--app", "Bad_Name"), ("--app", "x;rm"), ("--app",)):
            with self.subTest(args=args):
                result = self.run_script("heroku_config_push.sh", *args, "--yes")
                self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.heroku_calls(), [])

    def test_heroku_failure_is_reported(self) -> None:
        failing = self.tmp / "bin" / "heroku"
        failing.write_text("#!/bin/sh\nexit 7\n")
        result = self.run_script("heroku_config_push.sh", "--app", "ishara-test", "--yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Set 4 config vars", result.stdout)


if __name__ == "__main__":
    unittest.main()
