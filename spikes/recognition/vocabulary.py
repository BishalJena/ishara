"""The sign vocabulary the backend accepts (decision D8), shared by the Mac tools.

Mirrors backend/app/protocol.py: TEMPLATE_SIGNS are the original 12 the fixed templates
know; ASL_SIGNS are the service-call glosses of the public ASL Signs model that the
composer accepts generically. Change the three copies (here, protocol.py, Vocabulary.swift)
together; test_vocabulary checks this one against the backend's.
"""
from __future__ import annotations

TEMPLATE_SIGNS = ("hello", "thankyou", "yes", "no", "sorry", "doctor",
                  "today", "tomorrow", "morning", "afternoon", "evening", "time")
ASL_SIGNS = ("please", "now", "wait", "night", "yesterday", "later", "can", "where", "who",
             "why", "have", "finish", "callonphone", "sick", "hungry", "drink", "water",
             "home", "go", "see", "hear", "read")
SIGNS = TEMPLATE_SIGNS + ASL_SIGNS

# The words rehearsed for the demo, in the order the probe asks for them (D8).
REHEARSED = ("hello", "thankyou", "yes", "no", "now", "please", "tomorrow", "wait", "morning")
