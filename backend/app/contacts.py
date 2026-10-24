"""Allowlisted contacts from ALLOWED_RECIPIENTS (`contact_id=+E164`, comma separated).

The app only ever sends a contact id; the number stays on the backend. Error messages
name the contact id at most, never the number.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

CONTACT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
E164 = re.compile(r"^\+[1-9]\d{6,14}$")


class InvalidContacts(ValueError):
    """ALLOWED_RECIPIENTS is malformed. Raised at startup so a bad config fails loudly."""


def parse_contacts(entries: Iterable[str]) -> dict[str, str]:
    """Map contact id -> E.164 number. Every entry must be `contact_id=+E164`."""
    contacts: dict[str, str] = {}
    for entry in entries:
        contact_id, separator, number = (part.strip() for part in entry.partition("="))
        if not separator or not CONTACT_ID.fullmatch(contact_id):
            raise InvalidContacts(
                "ALLOWED_RECIPIENTS entries must look like contact_id=+E164 (value not shown)"
            )
        if not E164.fullmatch(number):
            raise InvalidContacts(f"ALLOWED_RECIPIENTS contact {contact_id!r} is not E.164")
        if contact_id in contacts:
            raise InvalidContacts(f"ALLOWED_RECIPIENTS lists contact {contact_id!r} twice")
        contacts[contact_id] = number
    return contacts
