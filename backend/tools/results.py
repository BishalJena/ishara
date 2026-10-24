"""Redacted, dated results sections appended to docs/experiments/voice.md.

Results files hold timings, counts and observations only: no phone numbers, call ids,
run ids or turn ids (AGENTS.md, PLAN.md §10).
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from tools.timing import TurnTiming, format_timing_table

Verdict = Literal["yes", "no", "skipped"]

ID_REMOVED = "[id removed]"
NUMBER_REMOVED = "[number removed]"
MIN_PHONE_DIGITS = 7

_UUID = re.compile(r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b")
_LONG_HEX = re.compile(r"\b[0-9a-fA-F]{16,}\b")
_DIGIT_RUN = re.compile(r"[+(]?\d[\d\s().-]*\d")


@dataclass(frozen=True)
class CheckResult:
    number: int
    title: str
    verdict: Verdict
    measured: tuple[tuple[str, str], ...]
    note: str


def _hide_phone_like(match: re.Match[str]) -> str:
    digits = sum(char.isdigit() for char in match.group())
    return NUMBER_REMOVED if digits >= MIN_PHONE_DIGITS else match.group()


def redact(text: str, scrub: Collection[str]) -> str:
    """Remove known ids, anything id-shaped and digit runs long enough to be a phone
    number. Over-redaction is fine; a leak is not."""
    for secret in sorted((s for s in scrub if s), key=len, reverse=True):
        text = text.replace(secret, ID_REMOVED)
    text = _UUID.sub(ID_REMOVED, text)
    text = _LONG_HEX.sub(ID_REMOVED, text)
    return _DIGIT_RUN.sub(_hide_phone_like, text)


def _cell(text: str, scrub: Collection[str]) -> str:
    flat = " ".join(redact(text, scrub).split())
    return flat.replace("|", "\\|") or "—"


def render_run_section(
    started_at: datetime,
    results: Iterable[CheckResult],
    timings: Iterable[TurnTiming],
    scrub: Collection[str],
) -> str:
    rows = [
        f"## Run {started_at:%Y-%m-%d %H:%M} (local time)",
        "",
        "Executed observations recorded by `scripts/voice_spike.py`. Verdicts are the",
        "tester's; measured values come from WebSocket events. SEND → spoken is when the",
        "backend saw the reply stream finish, not first audio on the phone.",
        "",
        "| # | Check | Tester verdict | Measured | Note |",
        "|---|---|---|---|---|",
    ]
    for result in results:
        measured = "; ".join(f"{name}: {value}" for name, value in result.measured)
        rows.append(
            f"| {result.number} | {_cell(result.title, scrub)} | {result.verdict} | "
            f"{_cell(measured, scrub)} | {_cell(result.note, scrub)} |"
        )
    rows += ["", "### Timings", "", format_timing_table(timings)]
    section = "\n".join(rows) + "\n"
    leaked = [secret for secret in scrub if secret and secret in section]
    if leaked:
        raise ValueError("refusing to write results: an id would leak into the file")
    return section


def append_run(path: Path, section: str) -> None:
    """Append to the existing experiment record (the template must already exist)."""
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing; restore the template first")
    existing = path.read_text(encoding="utf-8")
    separator = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(separator + section)
