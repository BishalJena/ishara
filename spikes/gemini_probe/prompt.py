"""The only text Gemini sees besides the clip: a fixed instruction and the shuffled word list.

Pure functions, no file access: the caller passes the candidate words, so this module
can't read the answer key, file names, sources or anything else about a clip.
"""
from __future__ import annotations

import random
from collections.abc import Sequence

UNSURE = "unsure"
TEMPLATE = (
    "The video shows one person signing a single word in Indian Sign Language (ISL). "
    "The video has no sound. Which word is being signed?\n"
    "Choose exactly one word from the candidate list below. If you cannot tell, answer \"unsure\".\n"
    "Reply with JSON only: {{\"word\": <one candidate exactly as written, or \"unsure\">, "
    "\"confidence\": <probability from 0 to 1 that your word is correct>}}.\n\n"
    "Candidate words: {candidates}"
)


def shuffled(candidates: Sequence[str], rng: random.Random) -> list[str]:
    """A fresh order per query, so position in the list carries no information."""
    if len(set(candidates)) != len(candidates) or UNSURE in candidates:
        raise ValueError("Candidates must be distinct words and must not include 'unsure'")
    words = list(candidates)
    rng.shuffle(words)
    return words


def build_prompt(words: Sequence[str]) -> str:
    return TEMPLATE.format(candidates=", ".join(words))


def response_schema(words: Sequence[str]) -> dict:
    """Structured output: the word must be a list item or 'unsure'; confidence in [0, 1]."""
    return {"type": "object",
            "properties": {"word": {"type": "string", "enum": [*words, UNSURE]},
                           "confidence": {"type": "number", "minimum": 0, "maximum": 1}},
            "required": ["word", "confidence"]}
