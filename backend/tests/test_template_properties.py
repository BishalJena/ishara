"""Live mode after D8: every sign the protocol accepts has a template and a validator
meaning, and the template for any chip combination passes the validator.

Templates depend only on the set of signs (order and duplicates don't matter), so the
properties are checked exhaustively up to three signs, exhaustively over every
combination of the signs the template logic models (with the longest plain phrases
filling the rest of the MAX_CHIPS slots), and on a fixed random sample up to MAX_CHIPS.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Iterator, Sequence

import pytest

from app.protocol import (
    ASL_SIGNS,
    MAX_CHIPS,
    MAX_SPOKEN_CHARS,
    SIGNS,
    TEMPLATE_SIGNS,
    ComposeRequest,
    Sign,
)
from app.templates import _PLAIN, compose_template
from app.validator import _MEANINGS, _SIGN_FACTS, validate

# Issue #62: the 25-word limit applies to LLM drafts only. A template is deterministic and
# the user reads it before SEND, so with many plain-phrase signs it may run longer.
WORD_LIMIT_REASON = "too many words"
MODELLED = tuple(s for s in SIGNS if s not in _PLAIN)
LONGEST_PLAIN = sorted(_PLAIN, key=lambda s: (-len(_PLAIN[s].split()), s))


def reasons_for(chips: Sequence[Sign]) -> list[str]:
    text = compose_template(chips, "doctor_appointment")
    request = ComposeRequest(turn_id="t1", chips=list(chips), purpose="doctor_appointment")
    return validate(text, request)


def content_reasons(chips: Sequence[Sign]) -> list[str]:
    """Every validator rule except the LLM-only word limit."""
    return [r for r in reasons_for(chips) if not r.startswith(WORD_LIMIT_REASON)]


def small_combinations() -> Iterator[tuple[Sign, ...]]:
    for size in (1, 2, 3):
        yield from itertools.combinations(SIGNS, size)


def packed_combinations() -> Iterator[tuple[Sign, ...]]:
    """Every subset of the modelled signs, padded with the longest plain phrases."""
    for size in range(MAX_CHIPS + 1):
        for modelled in itertools.combinations(MODELLED, size):
            chips = modelled + tuple(LONGEST_PLAIN[: MAX_CHIPS - size])
            if chips:
                yield chips


def sampled_combinations(count: int = 3000) -> Iterator[tuple[Sign, ...]]:
    rng = random.Random(20261028)
    for _ in range(count):
        yield tuple(rng.sample(SIGNS, rng.randint(4, MAX_CHIPS)))


def test_every_protocol_sign_has_a_template_and_a_validator_meaning() -> None:
    assert set(SIGNS) == set(TEMPLATE_SIGNS) | set(ASL_SIGNS)
    assert len(SIGNS) == len(set(SIGNS))
    # A sign is checked either as a meaning pattern or as a day / part-of-day fact.
    assert set(SIGNS) == set(_MEANINGS) | set(_SIGN_FACTS)
    assert not set(_MEANINGS) & set(_SIGN_FACTS)
    for sign in SIGNS:
        assert compose_template([sign], "doctor_appointment").strip(), sign


@pytest.mark.parametrize("sign", SIGNS)
def test_each_sign_alone_passes_the_validator(sign: Sign) -> None:
    assert reasons_for([sign]) == []


def test_every_combination_up_to_three_signs_passes_the_validator() -> None:
    failures = {chips: r for chips in small_combinations() if (r := reasons_for(chips))}
    assert failures == {}


def test_order_and_duplicates_do_not_change_the_template() -> None:
    for chips in itertools.islice(sampled_combinations(), 300):
        text = compose_template(chips, "doctor_appointment")
        assert compose_template(tuple(reversed(chips)), "doctor_appointment") == text
        assert compose_template(chips + chips[:1], "doctor_appointment") == text


def test_every_modelled_combination_up_to_max_chips_keeps_its_meanings_and_facts() -> None:
    failures = {chips: r for chips in packed_combinations() if (r := content_reasons(chips))}
    assert failures == {}


def test_sampled_combinations_up_to_max_chips_keep_their_meanings_and_facts() -> None:
    failures = {chips: r for chips in sampled_combinations() if (r := content_reasons(chips))}
    assert failures == {}


# The rehearsed demo words (D8) and their two candidates.
REHEARSED: tuple[Sign, ...] = (
    "hello",
    "thankyou",
    "yes",
    "no",
    "now",
    "please",
    "tomorrow",
    "morning",
    "wait",
)


def test_every_combination_of_the_rehearsed_words_passes_in_full() -> None:
    failures = {
        chips: r
        for size in range(1, MAX_CHIPS + 1)
        for chips in itertools.combinations(REHEARSED, size)
        if (r := reasons_for(chips))
    }
    assert failures == {}


def test_every_template_fits_what_one_approve_may_carry() -> None:
    """The character cap is a protocol limit (ApproveMessage), so it binds templates too."""
    too_long = {
        chips: len(text)
        for chips in itertools.chain(packed_combinations(), sampled_combinations())
        if len(text := compose_template(chips, "doctor_appointment")) > MAX_SPOKEN_CHARS
    }
    assert too_long == {}
