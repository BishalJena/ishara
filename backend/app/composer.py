"""Composer port implementations (decision D4, PLAN §4).

GroqComposer asks the LLM to reword the chips, validates the draft and falls back
to the template when the LLM is slow (> 1.5 s), fails, or adds facts.
TemplateComposer is used when no GROQ_API_KEY is configured.
"""

from __future__ import annotations

import asyncio
import json
import logging

import httpx

from app.config import Settings
from app.groq_client import GroqClient, GroqError
from app.ports import Composer
from app.protocol import ComposeRequest, Draft, DraftSource, Purpose
from app.templates import compose_template
from app.validator import validate

logger = logging.getLogger(__name__)

LLM_TIMEOUT_S = 1.5
PURPOSE_TEXT: dict[Purpose, str] = {
    "doctor_appointment": "asking a clinic for a doctor's appointment",
}

SYSTEM_PROMPT = """\
You write the exact words a Deaf caller will say on a phone call to a clinic receptionist.
The caller signed a few words ("chips", in order). Turn them into what the caller says.
Rules:
- Speak as the caller, in the first person, directly to the receptionist.
- Reword only. Keep the meaning of every chip: "no" declines, "yes" agrees.
- Add no new facts: no days, dates, times, numbers, names, symptoms or booking confirmations.
- You may reuse days, times and numbers the receptionist just said.
- One or two short sentences, at most 25 words.
- Output only the sentence: no quotes, labels, markdown or explanations.
Example: chips ["no", "morning"]; receptionist said "We have 4 pm tomorrow. Does that work?"
Output: No, sorry, 4 pm doesn't work. Is there anything tomorrow morning?"""


def user_message(request: ComposeRequest) -> str:
    return json.dumps(
        {
            "chips": list(dict.fromkeys(request.chips)),
            "purpose": PURPOSE_TEXT[request.purpose],
            "receptionist_last_said": request.last_caption,
        }
    )


def _template_draft(request: ComposeRequest) -> Draft:
    text = compose_template(request.chips, request.purpose)
    return Draft(turn_id=request.turn_id, text=text, source=DraftSource.TEMPLATE)


class TemplateComposer:
    async def compose(self, request: ComposeRequest) -> Draft:
        return _template_draft(request)


class GroqComposer:
    def __init__(self, client: GroqClient | None, timeout_s: float = LLM_TIMEOUT_S) -> None:
        self.client = client
        self.timeout_s = timeout_s

    async def compose(self, request: ComposeRequest) -> Draft:
        text = await self._llm_text(self.client, request) if self.client else None
        if text is None:
            return _template_draft(request)
        return Draft(turn_id=request.turn_id, text=text, source=DraftSource.LLM)

    async def _llm_text(self, client: GroqClient, request: ComposeRequest) -> str | None:
        """A validated LLM sentence, or None when the template should be used."""
        turn = request.turn_id
        try:
            raw = await asyncio.wait_for(
                client.complete(SYSTEM_PROMPT, user_message(request)), self.timeout_s
            )
        except TimeoutError:
            logger.warning("turn %s: LLM slower than %.1f s, using template", turn, self.timeout_s)
            return None
        except GroqError as exc:
            logger.warning("turn %s: LLM failed (%s), using template", turn, exc)
            return None
        text = raw.strip()
        reasons = validate(text, request)
        if reasons:
            logger.info(
                "turn %s: LLM draft rejected (%s), using template", turn, "; ".join(reasons)
            )
            return None
        return text


def build_composer(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> Composer:
    """Templates only when GROQ_API_KEY is missing; otherwise Groq with template fallback."""
    if settings.groq_api_key is None:
        return TemplateComposer()
    return GroqComposer(GroqClient(settings.groq_api_key, settings.groq_model, transport=transport))
