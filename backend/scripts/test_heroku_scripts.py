"""Heroku helper scripts against a fake `heroku` CLI: guards, what is sent, what is printed.

Stdlib only; no network. Run: python3 -m unittest discover -s backend/scripts -p 'test_*.py'
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
    if not seen and "FAKE_PS_TYPE_ERROR" in os.environ:
        print(os.environ["FAKE_PS_TYPE_ERROR"], file=sys.stderr)
        sys.exit(1)
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


BASIC_TYPES = """=== Process Types
 type   size    qty   cost/hour   max cost/month
──────────────────────────────────────────────────
 web    Basic   1     ~$0.010     $7

=== Dyno Totals
 type    total
───────────────
 Basic   1
"""
ECO_TYPES = """=== Process Types
 type   size   qty   cost/hour   max cost/month
─────────────────────────────────────────────────
 web    Eco    1

=== Dyno Totals
 type   total
──────────────
 Eco    1
$5 (flat monthly fee, shared across all Eco dynos)
"""
GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
}


class HealthHandler(BaseHTTPRequestHandler):
    payload: dict[str, object] = {}

    def do_GET(self) -> None:
        body = json.dumps(self.payload).encode() if self.path == "/health" else b"{}"
        self.send_response(200 if self.path == "/health" else 404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


class Deploy(HerokuScriptCase):
    def setUp(self) -> None:
        super().setUp()
        backend = self.repo / "backend"
        (backend / "Procfile").write_text("web: uvicorn app.main:app\n")
        (backend / ".python-version").write_text("3.11\n")
        (self.repo / "README.md").write_text("monorepo root\n")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "init")
        self.remote = self.tmp / "heroku.git"
        self.git("init", "-q", "--bare", str(self.remote))

        HealthHandler.payload = {
            "status": "ok",
            "missing_config": ["GROQ_API_KEY"],
            "extra": "not-for-output",
        }
        server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.env.update(
            GIT_ENV,
            HEROKU_GIT_URL=str(self.remote),
            FAKE_WEB_URL=f"http://127.0.0.1:{server.server_port}/",
            FAKE_PS_TYPE=BASIC_TYPES,
            HEALTH_ATTEMPTS="2",
            HEALTH_DELAY="0",
        )

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo,
            env={**os.environ, **GIT_ENV},
            check=True,
            capture_output=True,
            text=True,
        ).stdout

    def deployed_files(self) -> list[str] | None:
        listing = subprocess.run(
            ["git", "--git-dir", str(self.remote), "ls-tree", "--name-only", "main"],
            capture_output=True,
            text=True,
        )
        return listing.stdout.split() if listing.returncode == 0 else None

    def deploy(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        return self.run_script("heroku_deploy.sh", "--app", "ishara-test", *args, **env)

    def test_without_yes_does_nothing(self) -> None:
        result = self.deploy()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.heroku_calls(), [])
        self.assertIsNone(self.deployed_files())

    def test_pushes_only_backend_and_prints_status_and_missing_names(self) -> None:
        result = self.deploy("--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        files = self.deployed_files()
        self.assertIn("Procfile", files)
        self.assertIn(".python-version", files)
        self.assertNotIn("backend", files)
        self.assertNotIn("README.md", files)
        self.assertIn("status: ok", result.stdout)
        self.assertIn("missing_config: GROQ_API_KEY", result.stdout)
        self.assertNotIn("not-for-output", result.stdout + result.stderr)

    def test_refuses_eco_before_pushing(self) -> None:
        for listing in (ECO_TYPES, "│ web │ Eco │ 1 │"):
            with self.subTest(listing=listing):
                result = self.deploy("--yes", FAKE_PS_TYPE=listing)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ps:type web=basic", result.stderr)
                self.assertIsNone(self.deployed_files())

    def test_fails_when_new_app_comes_up_on_eco(self) -> None:
        result = self.deploy("--yes", FAKE_PS_TYPE="", FAKE_PS_TYPE_AFTER=ECO_TYPES)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ps:type web=basic", result.stderr)
        self.assertNotIn("status:", result.stdout)

    def test_brand_new_app_without_process_types_still_deploys(self) -> None:
        # The real CLI exits 1 with this message until the first build adds a Procfile.
        result = self.deploy("--yes", FAKE_PS_TYPE_ERROR=" ▸    No process types on ishara-test.")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Procfile", self.deployed_files())
        self.assertIn("status: ok", result.stdout)

    def test_one_web_dyno_deploys_without_scale_warning(self) -> None:
        result = self.deploy("--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("ps:scale", result.stderr)

    def test_more_than_one_web_dyno_warns_but_still_deploys(self) -> None:
        # Call state is in memory in one process, so a second web dyno splits calls.
        two_web = BASIC_TYPES.replace(" web    Basic   1 ", " web    Basic   2 ")
        for listing in (two_web, "│ web │ Basic │ 12 │"):
            with self.subTest(listing=listing):
                result = self.deploy("--yes", FAKE_PS_TYPE=listing)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("ps:scale web=1", result.stderr)
                self.assertIn("status: ok", result.stdout)

    def test_other_ps_type_failures_stop_before_pushing(self) -> None:
        result = self.deploy("--yes", FAKE_PS_TYPE_ERROR=" ▸    Invalid credentials provided.")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("could not read dyno types", result.stderr)
        self.assertIsNone(self.deployed_files())

    def test_refuses_uncommitted_backend_changes(self) -> None:
        (self.repo / "backend" / "Procfile").write_text("web: changed\n")
        result = self.deploy("--yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("uncommitted", result.stderr)
        self.assertIsNone(self.deployed_files())

    def test_unhealthy_status_fails(self) -> None:
        HealthHandler.payload = {"status": "degraded", "missing_config": []}
        result = self.deploy("--yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("status: degraded", result.stdout)
        self.assertIn("missing_config: none", result.stdout)


if __name__ == "__main__":
    unittest.main()
