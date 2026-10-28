from __future__ import annotations

import pytest

from app.protocol import CallState
from app.sessions import CallSession, Rejection, TurnPhase, TurnRejected

TEXT = "Hello, I'd like a doctor's appointment tomorrow."


def live_session() -> CallSession:
    session = CallSession(call_id="c1", purpose="doctor_appointment", run_id="r1")
    session.advance(CallState.IN_CALL)
    return session


def rejected(code: Rejection, action) -> None:
    with pytest.raises(TurnRejected) as error:
        action()
    assert error.value.code is code


def test_new_turn_id_becomes_current_and_closes_previous() -> None:
    session = live_session()
    session.set_chips("t1", ["hello"])
    session.set_chips("t2", ["no"])
    assert session.current is not None and session.current.turn_id == "t2"
    rejected(Rejection.STALE_TURN, lambda: session.set_chips("t1", ["yes"]))
    rejected(Rejection.STALE_TURN, lambda: session.approve("t1", TEXT))
    assert session.current.turn_id == "t2" and session.current.chips == ("no",)


def test_chip_changes_bump_revision_and_invalidate_older_drafts() -> None:
    session = live_session()
    first = session.set_chips("t1", ["hello"]).chips_rev
    second = session.set_chips("t1", ["hello", "doctor"]).chips_rev
    assert second == first + 1
    assert session.draft_is_current("t1", second)
    assert not session.draft_is_current("t1", first)
    assert not session.draft_is_current("t0", second)


def test_drafts_are_not_current_after_approval_new_turn_or_end() -> None:
    session = live_session()
    rev = session.set_chips("t1", ["hello"]).chips_rev
    session.approve("t1", TEXT)
    assert not session.draft_is_current("t1", rev)

    session = live_session()
    rev = session.set_chips("t1", ["hello"]).chips_rev
    session.set_chips("t2", ["no"])
    assert not session.draft_is_current("t1", rev)

    session = live_session()
    rev = session.set_chips("t1", ["hello"]).chips_rev
    session.advance(CallState.ENDED)
    assert not session.draft_is_current("t1", rev)


def test_approval_is_single_use() -> None:
    session = live_session()
    session.set_chips("t1", ["hello"])
    turn = session.approve("t1", TEXT)
    assert turn.phase is TurnPhase.APPROVED and session.in_flight is turn
    assert session.state is CallState.SPEAKING
    rejected(Rejection.ALREADY_APPROVED, lambda: session.approve("t1", TEXT))
    rejected(Rejection.ALREADY_APPROVED, lambda: session.set_chips("t1", ["no"]))
    assert turn.approved_text == TEXT


@pytest.mark.parametrize("line", [CallState.DIALING, CallState.RINGING])
def test_approval_before_live_rejected_without_opening_turn(line: CallState) -> None:
    session = CallSession(call_id="c1", purpose="doctor_appointment", line=line)
    rejected(Rejection.CALL_NOT_LIVE, lambda: session.approve("t1", TEXT))
    assert session.in_flight is None and session.current is None
    assert "t1" not in session.seen_turn_ids


def test_approval_without_run_id_rejected() -> None:
    session = CallSession(call_id="c1", purpose="doctor_appointment")
    session.hear_caption("Hello?")
    rejected(Rejection.CALL_NOT_LIVE, lambda: session.approve("t1", TEXT))
    assert session.in_flight is None


@pytest.mark.parametrize("line", [CallState.ENDED, CallState.ERROR])
def test_finished_call_rejects_chips_and_approval(line: CallState) -> None:
    session = live_session()
    session.advance(line)
    rejected(Rejection.CALL_ENDED, lambda: session.approve("t1", TEXT))
    rejected(Rejection.CALL_ENDED, lambda: session.set_chips("t1", ["no"]))
    assert session.current is None and session.in_flight is None


def test_approval_for_brand_new_turn_without_chips_is_accepted() -> None:
    session = live_session()
    session.set_chips("t1", ["hello"])
    turn = session.approve("quick-1", "Sorry, could you please repeat that?")
    assert session.current is turn and session.in_flight is turn
    rejected(Rejection.STALE_TURN, lambda: session.set_chips("t1", ["no"]))


def test_claim_returns_the_approved_turn_exactly_once() -> None:
    session = live_session()
    turn = session.approve("t1", TEXT)
    claimed = session.claim()
    assert claimed is turn and claimed.approved_text == TEXT
    assert turn.phase is TurnPhase.CLAIMED and session.in_flight is turn
    assert session.claim() is None


def test_claim_after_a_superseding_approval_gets_the_newer_turn() -> None:
    session = live_session()
    first = session.approve("t1", TEXT)
    second = session.approve("t2", "No.")
    assert first.phase is TurnPhase.CANCELLED
    assert session.claim() is second


def test_claim_none_for_unapproved_turn() -> None:
    session = live_session()
    session.set_chips("t1", ["hello"])
    assert session.claim() is None


def test_stop_before_claim_cancels() -> None:
    session = live_session()
    turn = session.approve("t1", TEXT)
    assert session.stop() is turn
    assert turn.phase is TurnPhase.CANCELLED and session.state is CallState.IN_CALL
    assert session.claim() is None
    rejected(Rejection.ALREADY_APPROVED, lambda: session.approve("t1", TEXT))


def test_stop_after_claim_cannot_interrupt() -> None:
    session = live_session()
    turn = session.approve("t1", TEXT)
    session.claim()
    rejected(Rejection.CANNOT_INTERRUPT, session.stop)
    assert session.in_flight is turn and turn.phase is TurnPhase.CLAIMED


def test_stop_with_nothing_in_flight_is_a_no_op() -> None:
    session = live_session()
    assert session.stop() is None


def test_new_turn_revokes_unclaimed_approval() -> None:
    session = live_session()
    turn = session.approve("t1", TEXT)
    session.set_chips("t2", ["no"])
    assert turn.phase is TurnPhase.CANCELLED and session.in_flight is None
    assert session.claim() is None


def test_new_turn_keeps_a_reply_that_is_already_being_spoken() -> None:
    session = live_session()
    turn = session.approve("t1", TEXT)
    session.claim()
    session.set_chips("t2", ["no"])
    assert session.in_flight is turn and session.state is CallState.SPEAKING
    rejected(Rejection.BUSY_SPEAKING, lambda: session.approve("t2", "No."))
    assert session.current is not None and session.current.phase is TurnPhase.OPEN
    assert session.mark_spoken("t1")
    assert session.approve("t2", "No.").phase is TurnPhase.APPROVED


def test_mark_spoken_only_after_claim() -> None:
    session = live_session()
    turn = session.approve("t1", TEXT)
    assert not session.mark_spoken("t1")
    session.claim()
    assert not session.mark_spoken("t2")
    assert session.mark_spoken("t1")
    assert turn.phase is TurnPhase.SPOKEN and session.state is CallState.IN_CALL
    assert not session.mark_spoken("t1")


def test_failed_delivery_blocks_late_claim() -> None:
    session = live_session()
    turn = session.approve("t1", TEXT)
    assert not session.fail_delivery("t2")
    assert session.fail_delivery("t1")
    assert turn.phase is TurnPhase.UNDELIVERED and session.state is CallState.IN_CALL
    assert session.claim() is None
    assert not session.fail_delivery("t1")


def test_failed_delivery_after_claim_ignores_late_spoken() -> None:
    session = live_session()
    session.approve("t1", TEXT)
    session.claim()
    assert session.fail_delivery("t1")
    assert not session.mark_spoken("t1")


def test_revoke_unclaimed_leaves_claimed_reply() -> None:
    session = live_session()
    session.approve("t1", TEXT)
    session.claim()
    assert session.revoke_unclaimed() is None
    assert session.in_flight is not None
    other = live_session()
    turn = other.approve("t1", TEXT)
    assert other.revoke_unclaimed() is turn and other.claim() is None


def test_end_wipes_pending_turns_and_blocks_claim() -> None:
    session = live_session()
    session.approve("t1", TEXT)
    assert session.advance(CallState.ENDED)
    assert session.current is None and session.in_flight is None
    assert session.state is CallState.ENDED
    assert session.claim() is None


def test_claim_none_once_call_finished_even_if_in_flight_kept() -> None:
    session = live_session()
    session.approve("t1", TEXT)
    session.line = CallState.ENDED
    assert session.claim() is None


def test_caption_marks_line_live_and_is_remembered() -> None:
    session = CallSession(call_id="c1", purpose="doctor_appointment")
    session.hear_caption("We have 4 pm tomorrow.")
    assert session.line is CallState.IN_CALL
    assert session.last_caption == "We have 4 pm tomorrow."


@pytest.mark.parametrize(
    ("start", "update", "moved", "result"),
    [
        (CallState.DIALING, CallState.RINGING, True, CallState.RINGING),
        (CallState.RINGING, CallState.IN_CALL, True, CallState.IN_CALL),
        (CallState.IN_CALL, CallState.RINGING, False, CallState.IN_CALL),
        (CallState.IN_CALL, CallState.IN_CALL, False, CallState.IN_CALL),
        (CallState.ENDED, CallState.IN_CALL, False, CallState.ENDED),
        (CallState.ENDED, CallState.ERROR, False, CallState.ENDED),
        (CallState.RINGING, CallState.ERROR, True, CallState.ERROR),
    ],
)
def test_line_only_moves_forward(
    start: CallState, update: CallState, moved: bool, result: CallState
) -> None:
    session = CallSession(call_id="c1", purpose="doctor_appointment", line=start)
    assert session.advance(update) is moved
    assert session.line is result


def test_speaking_state_only_while_live() -> None:
    session = live_session()
    session.approve("t1", TEXT)
    session.line = CallState.ERROR
    assert session.state is CallState.ERROR
