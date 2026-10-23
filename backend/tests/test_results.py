from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from tools.results import (
    ID_REMOVED,
    NUMBER_REMOVED,
    CheckResult,
    append_run,
    redact,
    render_run_section,
)
from tools.timing import TurnTiming

STARTED = datetime(2026, 10, 24, 14, 5)
TURN_ID = "0123456789abcdef0123456789abcdef"


@pytest.mark.parametrize(
    "number",
    ["+919876543210", "+91 98765 43210", "98765-43210", "(022) 2345 6789", "1234567"],
)
def test_phone_like_digit_runs_are_removed(number: str) -> None:
    redacted = redact(f"teammate on {number} said hi", ())
    assert redacted == f"teammate on {NUMBER_REMOVED} said hi"


@pytest.mark.parametrize(
    "text",
    ["agreed 4 pm", "10:30 tomorrow", "took 1.42 s", "about 15 s, then 3 s", "123456"],
)
def test_times_latencies_and_short_numbers_survive(text: str) -> None:
    assert redact(text, ()) == text


def test_known_ids_uuids_and_long_hex_are_removed() -> None:
    text = (
        "call c_42abc, run 3f1e2d3c-4b5a-4c6d-8e7f-9a0b1c2d3e4f, turn " + TURN_ID + " heard twice"
    )
    assert redact(text, {"c_42abc"}) == (
        f"call {ID_REMOVED}, run {ID_REMOVED}, turn {ID_REMOVED} heard twice"
    )


def test_longer_secret_is_scrubbed_before_its_prefix() -> None:
    assert redact("id abc-123-xyz", {"abc", "abc-123-xyz"}) == f"id {ID_REMOVED}"


def _result(note: str, measured: tuple[tuple[str, str], ...] = ()) -> CheckResult:
    return CheckResult(2, "Exact text spoken", "yes", measured, note)


def test_section_has_date_rows_and_timings_but_no_ids() -> None:
    section = render_run_section(
        STARTED,
        [
            _result(
                "heard it | word for word\non +91 98765 43210",
                (("SEND → spoken", "1.42 s"), ("outcome", "spoken")),
            ),
            CheckResult(7, "end_call ends the call", "skipped", (), ""),
        ],
        [TurnTiming("check 2", TURN_ID, spoken_latency_s=1.42, outcome="spoken")],
        scrub={"call-xyz"},
    )
    lines = section.splitlines()
    assert lines[0] == "## Run 2026-10-24 14:05 (local time)"
    assert (
        f"| 2 | Exact text spoken | yes | SEND → spoken: 1.42 s; outcome: spoken | "
        f"heard it \\| word for word on {NUMBER_REMOVED} |"
    ) in lines
    assert "| 7 | end_call ends the call | skipped | — | — |" in lines
    assert "| check 2 | — | 1.42 | spoken |" in lines
    assert TURN_ID not in section
    assert "98765" not in section


def test_section_scrubs_call_id_from_notes() -> None:
    section = render_run_section(
        STARTED, [_result("dashboard showed call-xyz")], [], scrub={"call-xyz"}
    )
    assert "call-xyz" not in section
    assert f"dashboard showed {ID_REMOVED}" in section


def test_section_refuses_when_an_id_appears_outside_redacted_cells() -> None:
    with pytest.raises(ValueError, match="leak"):
        render_run_section(STARTED, [], [TurnTiming("label-call-xyz", "t")], scrub={"call-xyz"})


def test_append_run_keeps_existing_text_and_separates_sections(tmp_path: Path) -> None:
    record = tmp_path / "voice.md"
    record.write_text("# Voice\n\n## Runs\n\nNo runs yet.\n", encoding="utf-8")
    append_run(record, "## Run A\n")
    append_run(record, "## Run B\n")
    assert record.read_text(encoding="utf-8") == (
        "# Voice\n\n## Runs\n\nNo runs yet.\n\n## Run A\n\n## Run B\n"
    )


def test_append_run_requires_the_template(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        append_run(tmp_path / "missing.md", "## Run\n")
