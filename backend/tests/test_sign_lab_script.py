"""scripts/sign_lab.sh: preflight errors name the fix, and a run starts the backend,
hands the bridge the right arguments and stops the backend on exit or Ctrl-C.

The recognition folder is a fake: its "venv Pythons" are shell scripts, so no webcam,
model or bridge dependency is needed. Runs use --free, so no key is read and nothing
paid is reached.
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import stat
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "sign_lab.sh"
RUN_TIMEOUT_S = 60

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("curl") is None or shutil.which("uv") is None,
    reason="needs bash, curl and uv",
)


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT_S,
        env={**os.environ, **(env or {})},
    )


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def answers(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
            return True
    except (urllib.error.URLError, OSError):
        return False


def executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def recognition(tmp_path: Path) -> Path:
    """A spikes/recognition stand-in whose bridge records what it was given."""
    folder = tmp_path / "recognition"
    executable(folder / "artifacts/signclip/.venv/bin/python", "exit 0\n")
    executable(
        folder / "artifacts/bridge/.venv/bin/python",
        'out="$FAKE_BRIDGE_OUT"\n'
        '{ echo "cwd=$(pwd)"; echo "token=$APP_TOKEN"; echo "args=$*"; } > "$out"\n'
        'curl -fsS "http://127.0.0.1:$FAKE_BACKEND_PORT/health" >> "$out"\n'
        'sleep "${FAKE_BRIDGE_SLEEP:-0}"\n'
        'exit "${FAKE_BRIDGE_EXIT:-0}"\n',
    )
    (folder / "mac_bridge.py").write_text("")
    bundle = folder / "artifacts/evidence/recognition-bundle-signclip.json"
    bundle.parent.mkdir(parents=True)
    bundle.write_text("{}")
    return folder


def test_unknown_option_is_a_usage_error() -> None:
    result = run("--bogus")
    assert result.returncode == 2
    assert "unknown option: --bogus" in result.stderr


def test_manual_receptionist_needs_its_own_terminal() -> None:
    result = run("--receptionist", "manual")
    assert result.returncode == 2
    assert "scripts/sign_lab.sh --backend-only --receptionist manual" in result.stderr
    assert "scripts/sign_lab.sh --bridge-only" in result.stderr


def test_missing_venvs_and_bundle_print_the_commands_that_fix_them(tmp_path: Path) -> None:
    port = free_port()
    result = run("--free", "--port", str(port), "--recognition-dir", str(tmp_path))
    assert result.returncode == 1
    err = result.stderr
    assert "no bridge venv at" in err
    assert "--require-hashes -r requirements-bridge.lock" in err
    assert "no SignCLIP venv at" in err
    assert "setup_signclip.py" in err
    assert "no recognition bundle at" in err
    assert "retrieval.py export-bundle --encoder signclip" in err
    assert "no mac_bridge.py" in err
    assert not answers(port), "nothing may start before the preflight passes"


def test_bundle_flag_is_checked_too(recognition: Path, tmp_path: Path) -> None:
    missing = tmp_path / "other-bundle.json"
    result = run("--free", "--recognition-dir", str(recognition), "--bundle", str(missing))
    assert result.returncode == 1
    assert f"no recognition bundle at {missing}" in result.stderr


def test_run_starts_the_backend_hands_the_bridge_its_args_then_stops_it(
    recognition: Path, tmp_path: Path
) -> None:
    port = free_port()
    out = tmp_path / "bridge.out"
    env = {"FAKE_BRIDGE_OUT": str(out), "FAKE_BACKEND_PORT": str(port)}
    result = run("--free", "--port", str(port), "--recognition-dir", str(recognition), env=env)

    assert result.returncode == 0, result.stderr
    lines = out.read_text().splitlines()
    assert lines[0] == f"cwd={recognition}"
    assert lines[1] == "token=ishara-local-demo"
    assert lines[2] == (
        f"args=mac_bridge.py --base-url http://127.0.0.1:{port} --contact clinic "
        f"--confirm-cost --live --camera 0 "
        f"--bundle {recognition}/artifacts/evidence/recognition-bundle-signclip.json "
        f"--recognizer-python {recognition}/artifacts/signclip/.venv/bin/python"
    )
    assert lines[3].startswith('{"status":"ok"'), "the backend was up when the bridge ran"
    assert "[lab]   drafts        templates" in result.stdout
    assert "nothing is\n  dialled and the call is free" in result.stdout
    assert not answers(port), "the backend must stop when the bridge exits"


def test_replay_videos_replaces_the_camera(recognition: Path, tmp_path: Path) -> None:
    port = free_port()
    out = tmp_path / "bridge.out"
    env = {"FAKE_BRIDGE_OUT": str(out), "FAKE_BACKEND_PORT": str(port)}
    args = ("--free", "--port", str(port), "--recognition-dir", str(recognition))
    result = run(*args, "--", "--replay-videos", "clips", env=env)
    assert result.returncode == 0, result.stderr
    bridge_args = out.read_text().splitlines()[2]
    assert "--camera" not in bridge_args
    assert bridge_args.endswith("--replay-videos clips")


def test_a_failing_bridge_fails_the_run_and_still_stops_the_backend(
    recognition: Path, tmp_path: Path
) -> None:
    port = free_port()
    env = {
        "FAKE_BRIDGE_OUT": str(tmp_path / "bridge.out"),
        "FAKE_BACKEND_PORT": str(port),
        "FAKE_BRIDGE_EXIT": "3",
    }
    result = run("--free", "--port", str(port), "--recognition-dir", str(recognition), env=env)
    assert result.returncode == 3
    assert not answers(port)


def test_ctrl_c_stops_the_backend_too(recognition: Path, tmp_path: Path) -> None:
    port = free_port()
    env = {
        **os.environ,
        "FAKE_BRIDGE_OUT": str(tmp_path / "bridge.out"),
        "FAKE_BACKEND_PORT": str(port),
        "FAKE_BRIDGE_SLEEP": "30",
    }
    args = ["--free", "--port", str(port), "--recognition-dir", str(recognition)]
    # Its own process group, so the SIGINT reaches everything like a terminal Ctrl-C.
    process = subprocess.Popen(
        ["bash", str(SCRIPT), *args],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + RUN_TIMEOUT_S
        while not (tmp_path / "bridge.out").exists():
            assert time.monotonic() < deadline, "the bridge never started"
            assert process.poll() is None, "sign_lab.sh exited early"
            time.sleep(0.1)
        assert answers(port)
        os.killpg(process.pid, signal.SIGINT)
        assert process.wait(timeout=15) == 130
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
    assert not answers(port)
