"""Bounded sentence templates, optional local LLM, and one-use approval.

No network inference, speech generation, or call control lives in this module.
Qwen usage follows its pinned model card; no remote Python code is loaded.
"""
from __future__ import annotations

import json
import time
import uuid

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from slgcn import ARTIFACTS, SUPPORTED

LLM_ID = "Qwen/Qwen2.5-0.5B-Instruct"
LLM_REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"
LLM_DIR = ARTIFACTS / "qwen2.5-0.5b-instruct"
INTENTS = {
    "": "No explicit purpose supplied",
    "greet": "Greet the other person",
    "thank": "Thank the other person",
    "request_appointment": "Ask to arrange an appointment; do not claim it is booked",
    "ask_location": "Ask where the mentioned place is",
    "specify_day": "State the requested day",
}
SYSTEM_PROMPT = """Write the exact words the signer could say to a receptionist.
Use first person (I/my) for the signer, or ask the receptionist a direct question.
Preserve the supplied concepts and the purpose explicitly selected by the signer.
Do not describe the signer as "you" or explain the input.
Do not add names, dates, clock times, prices, symptoms, or booking confirmations.
Return one short sentence only. For a greeting alone, simply say Hello.
Example: concepts hospital, location; purpose ask location -> Where is the hospital?"""


def validate_concepts(concepts, intent):
    if not isinstance(concepts, list) or not 1 <= len(concepts) <= 8:
        raise ValueError("Supply 1–8 supported concepts")
    if any(not isinstance(x, str) or x not in SUPPORTED for x in concepts):
        raise ValueError("An input concept is unsupported; composition cannot repair it")
    if not isinstance(intent, str) or intent not in INTENTS:
        raise ValueError("Unknown explicit purpose")
    return list(dict.fromkeys(concepts))


class SentenceTemplates:
    """Only explicit intent and supported concepts determine the sentence."""
    name = "Fixed intent templates v1"

    def suggest(self, concepts, intent=""):
        concepts = validate_concepts(concepts, intent)
        words = set(concepts)
        if not intent:
            intent = {"hello": "greet", "thankyou": "thank"}.get(concepts[0], "") if len(words) == 1 else ""
        if not intent:
            return {"status": "needs_intent", "text": None, "concepts": concepts,
                    "reason": "Choose the purpose of these concepts before composing."}
        if {"today", "tomorrow"} <= words:
            return {"status": "needs_review", "text": None, "concepts": concepts,
                    "reason": "Choose one requested day; today and tomorrow conflict."}
        text = None
        if intent == "greet" and words == {"hello"}:
            text = "Hello."
        elif intent == "thank" and words == {"thankyou"}:
            text = "Thank you."
        elif intent == "request_appointment" and words <= {"doctor", "hospital", "today", "tomorrow"}:
            text = "I would like an appointment"
            if "doctor" in words:
                text += " with a doctor"
            if "hospital" in words:
                text += " at the hospital"
            if words & {"today", "tomorrow"}:
                text += " today" if "today" in words else " tomorrow"
            text += "."
        elif intent == "ask_location" and words <= {"doctor", "hospital", "location"}:
            if "doctor" in words:
                text = "Where can I find a doctor" + (" at the hospital?" if "hospital" in words else "?")
            elif "hospital" in words:
                text = "Where is the hospital?"
        elif intent == "specify_day" and words in ({"today"}, {"tomorrow"}):
            text = f"I would like {concepts[0]}."
        if text is None:
            return {"status": "needs_review", "text": None, "concepts": concepts,
                    "reason": "These concepts do not fit that purpose. Review the concepts or choose another purpose."}
        return {"status": "draft", "text": text, "concepts": concepts, "intent": intent,
                "source": "fixed_template", "model": self.name,
                "semantic_correctness": "template_requires_user_review"}


class SentenceModel:
    name = LLM_ID

    def __init__(self):
        self.model = self.tokenizer = None

    def suggest(self, concepts, intent=""):
        concepts = validate_concepts(concepts, intent)
        if not intent and concepts not in (["hello"], ["thankyou"]):
            return {"status": "needs_intent", "text": None, "concepts": concepts,
                    "reason": "These fragments do not say whether to ask, request, or confirm. Choose a purpose."}
        start = time.perf_counter()
        cold = self.model is None
        if cold:
            self.tokenizer = AutoTokenizer.from_pretrained(
                LLM_DIR, local_files_only=True, trust_remote_code=False)
            self.model = AutoModelForCausalLM.from_pretrained(
                LLM_DIR, local_files_only=True, trust_remote_code=False,
                dtype=torch.float32).eval().requires_grad_(False)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({
                "concepts": concepts, "explicit_purpose": INTENTS[intent]
            })},
        ]
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(prompt, return_tensors="pt")
        with torch.inference_mode():
            output = self.model.generate(
                **inputs, max_new_tokens=80, do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id)
        generated = output[0, inputs["input_ids"].shape[1]:]
        text = self.tokenizer.decode(generated, skip_special_tokens=True).strip()
        if not text or len(text) > 500:
            raise ValueError("Language model did not produce a bounded sentence")
        return {"status": "draft", "text": text, "concepts": concepts, "intent": intent,
                "source": "local_llm", "model": LLM_ID, "revision": LLM_REVISION,
                "cold_load": cold, "elapsed_ms": 1000 * (time.perf_counter() - start),
                "generated_tokens": len(generated), "semantic_correctness": "not_verified"}


class Approval:
    """Invalidate stale drafts and record the exact edited text, never auto-send."""
    def __init__(self):
        self.pending = None

    def clear(self):
        self.pending = None

    def stage(self, suggestion):
        self.clear()
        if suggestion["status"] != "draft":
            return suggestion
        self.pending = {**suggestion, "draft_id": uuid.uuid4().hex}
        return self.pending.copy()

    def approve(self, draft_id, text):
        if not self.pending or self.pending["draft_id"] != draft_id:
            raise ValueError("Draft expired or already approved; generate a new suggestion")
        if not isinstance(text, str) or not text.strip() or len(text) > 500:
            raise ValueError("Approved text must contain 1–500 characters")
        result = {"status": "approved", "text": text, "draft_id": draft_id,
                  "suggested_text": self.pending["text"],
                  "edited": text != self.pending["text"],
                  "concepts_source": self.pending.get("concepts_source"),
                  "speech_status": "not_connected", "sent_to_bolna": False}
        self.clear()
        return result
