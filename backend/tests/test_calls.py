from __future__ import annotations

import pytest

from app.contacts import InvalidContacts, parse_contacts

CLINIC = "+910000000001"
PHARMACY = "+910000000002"


def test_contacts_map_ids_to_numbers() -> None:
    entries = [f"clinic={CLINIC}", f" pharmacy = {PHARMACY} "]
    assert parse_contacts(entries) == {"clinic": CLINIC, "pharmacy": PHARMACY}


@pytest.mark.parametrize(
    "entry",
    [
        CLINIC,
        f"={CLINIC}",
        f"bad id={CLINIC}",
        "clinic=910000000001",
        "clinic=+010000000001",
        "clinic=+91000",
        "clinic=+9100000000011234",
        "clinic=+91000000000a",
        "clinic=",
    ],
)
def test_malformed_contact_entries_fail_loudly(entry: str) -> None:
    with pytest.raises(InvalidContacts):
        parse_contacts([entry])


def test_duplicate_contact_ids_rejected() -> None:
    with pytest.raises(InvalidContacts, match="twice"):
        parse_contacts([f"clinic={CLINIC}", f"clinic={PHARMACY}"])


@pytest.mark.parametrize("entry", [CLINIC, "clinic=+91000000000a"])
def test_contact_errors_never_echo_the_number(entry: str) -> None:
    with pytest.raises(InvalidContacts) as error:
        parse_contacts([entry])
    assert "910000000" not in str(error.value)
