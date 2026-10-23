from __future__ import annotations

import pytest

from app.utterances import UtteranceTracker, new_utterances


@pytest.mark.parametrize(
    ("seen", "current", "expected"),
    [
        pytest.param([], [], [], id="nothing yet"),
        pytest.param(
            [], ["Hello?", "Who is this?"], ["Hello?", "Who is this?"], id="first request"
        ),
        pytest.param(["a", "b"], ["a", "b"], [], id="history resent unchanged"),
        pytest.param(["a"], ["a", "b", "c"], ["b", "c"], id="two appended"),
        pytest.param(["okay"], ["okay", "okay"], ["okay"], id="same words said twice"),
        pytest.param(["a", "b", "c"], ["b", "c", "d"], ["d"], id="window slid by one"),
        pytest.param(["a", "b", "c"], ["c"], [], id="window slid, nothing new"),
        pytest.param(["a", "Hi"], ["a", "Hi, how can I help?"], ["Hi, how can I help?"], id="stub"),
        pytest.param(["a", "b", "Hi"], ["b", "Hi there", "x"], ["Hi there", "x"], id="slide+stub"),
        pytest.param(["a", "b"], ["x", "y"], ["y"], id="unalignable: newest only"),
        pytest.param(
            ["a", "Hi"], ["x", "Hi there", "y"], ["y"], id="unalignable despite extension"
        ),
        pytest.param(["a", "b"], ["x", "b"], [], id="unalignable, newest already seen"),
        pytest.param(["a", "b"], [], [], id="history emptied"),
    ],
)
def test_new_utterances(seen: list[str], current: list[str], expected: list[str]) -> None:
    assert new_utterances(seen, current) == expected


def test_tracker_is_per_call_and_remembers_latest_request() -> None:
    tracker = UtteranceTracker()
    assert tracker.take_new("c1", ["Hello?"]) == ["Hello?"]
    assert tracker.take_new("c1", ["Hello?"]) == []
    assert tracker.take_new("c2", ["Hello?"]) == ["Hello?"]
    assert tracker.take_new("c1", ["Hello?", "Yes?"]) == ["Yes?"]
