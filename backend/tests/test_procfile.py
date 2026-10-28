"""The Heroku web command keeps connections alive past the router's limits."""

from __future__ import annotations

import shlex
from pathlib import Path

PROCFILE = Path(__file__).resolve().parents[1] / "Procfile"


def _web_args() -> list[str]:
    (line,) = [line for line in PROCFILE.read_text().splitlines() if line.startswith("web:")]
    return shlex.split(line.removeprefix("web:"))


def _option(args: list[str], name: str) -> int:
    return int(args[args.index(name) + 1])


def test_web_process_serves_the_module_level_app() -> None:
    args = _web_args()
    assert args[:2] == ["uvicorn", "app.main:app"]
    assert args[args.index("--port") + 1] == "$PORT"


def test_web_process_runs_exactly_one_worker() -> None:
    # Call state lives in memory per process, so webhooks, custom-LLM requests and the app
    # socket must reach the same process. Without an explicit flag uvicorn takes its worker
    # count from WEB_CONCURRENCY, which the Heroku Python buildpack sets above 1.
    args = _web_args()
    assert args.count("--workers") == 1
    assert not [arg for arg in args if arg.startswith("--workers=")]
    assert _option(args, "--workers") == 1


def test_keep_alive_outlasts_the_heroku_router_pool() -> None:
    # The router keeps idle pooled connections for 90 s; a shorter server keep-alive
    # closes them under the router (H13/H18).
    assert _option(_web_args(), "--timeout-keep-alive") > 90


def test_websocket_pings_beat_the_router_idle_window() -> None:
    # The router drops connections idle for 55 s, WebSockets included.
    args = _web_args()
    assert _option(args, "--ws-ping-interval") < 55
    assert _option(args, "--ws-ping-timeout") < 55
