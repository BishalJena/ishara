#!/usr/bin/env python3
"""Phone-free general and clinical replays. Defaults to mocked provider responses.

Use --suite clinical for document questions and autonomous booking, or --http for
those fixtures through real local HTTP routes and saved notes with fake telephony.
Use --suite autonomy (with or without --http) for routine choices and explicit limits.
Run with backend/.venv/bin/python scripts/planner_replay.py. --live spends provider
credits and requires task authorization before execution. It reads only GROQ_API_KEY
and GROQ_MODEL, sends synthetic fixtures, and makes at most twelve model requests.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx
from pydantic import SecretStr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.delegate import Brain, DelegateState, Exchange, brief_from, build_brief
from app.groq_client import GroqClient, GroqError
from app.protocol import BriefRequest, Profile
from app.steer_planner import ResolutionReview

MAX_REQUESTS = 12
DEFAULT_MODEL = "openai/gpt-oss-120b"
PASSPORT_GOAL = "I'd like to order a replacement passport after losing it abroad"
DOCUMENT_VALUE = "replacement (lost abroad)"
DOCUMENT_QUOTE = f"Category: {DOCUMENT_VALUE}."
DOCUMENT_TEXT = f"{DOCUMENT_QUOTE}\nDelivery method: collection at counter."
DOCUMENT_ANSWERS = frozenset(
    (
        DOCUMENT_VALUE,
        f"{DOCUMENT_VALUE}.",
        DOCUMENT_QUOTE,
        DOCUMENT_QUOTE.removesuffix("."),
    )
)


def action(kind: str, **values: object) -> dict:
    resolutions = values.pop("resolutions", [])
    if kind == "finish":
        values.setdefault("blocked", False)
    return {"action": {"kind": kind, **values}, "resolutions": resolutions}


@dataclass(frozen=True)
class Step:
    heard: str
    expected: str
    proposal: str
    goal_index: int = 0
    question: str | None = None
    focus: tuple[str, ...] = ()
    resolve: bool = False
    provider_expected: bool = True
    answer_spans: tuple[str, ...] = ()
    required: tuple[str, ...] = ()
    resolution_quote: str | None = None
    option: str | None = None
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class Scenario:
    name: str
    goal: str
    steps: tuple[Step, ...]
    document: bool | str = False
    caller_available: bool = True


SCENARIOS = (
    Scenario(
        "passport_history",
        PASSPORT_GOAL,
        (
            Step(
                "okay when did they get their old passport",
                "need_caller",
                "need_caller",
            ),
        ),
    ),
    Scenario(
        "passport_loss_date",
        PASSPORT_GOAL,
        (Step("When did you lose the passport?", "need_caller", "need_caller"),),
    ),
    Scenario(
        "plumber_unknown_cause",
        "Ask a plumber about repairing a pipe.",
        (Step("How did the pipe get damaged?", "unavailable", "need_caller"),),
        caller_available=False,
    ),
    Scenario(
        "document_repeat",
        PASSPORT_GOAL,
        (Step("Which category is printed on the form?", "answer", "answer_question"),) * 2,
        document=True,
    ),
    Scenario(
        "explicit_fee_limit",
        "Ask what a drain inspection costs. My maximum budget is 20 credits.",
        (
            Step(
                "The inspection fee is 40 credits. Do you accept the charge?",
                "need_caller",
                "answer_question",
                provider_expected=False,
            ),
        ),
    ),
    Scenario(
        "autonomous_order",
        PASSPORT_GOAL,
        (
            Step(
                "I can register the replacement passport order.",
                "accept",
                "accept_offer",
            ),
            Step("Your replacement passport order has been registered.", "done", "finish"),
        ),
        caller_available=False,
    ),
    Scenario(
        "informational_procedure",
        "Ask how to order a replacement passport after losing it abroad",
        (Step("You can apply online for a replacement passport.", "done", "finish"),),
    ),
    Scenario(
        "informational_negative",
        "Ask whether the plumber visits on weekends.",
        (Step("No, we only visit weekdays.", "done", "finish"),),
    ),
    Scenario(
        "informational_capability",
        "Ask where passport collection is available.",
        (Step("You can collect the passport at the counter.", "done", "finish"),),
    ),
    Scenario(
        "multipart_information",
        "Ask when the library opens and what the membership fee is.",
        (
            Step(
                "The library opens at 9 am.",
                "ask_operator",
                "ask_operator",
                question="What is the membership fee?",
                focus=("fee", "cost", "charge"),
                resolve=True,
            ),
            Step("The membership fee is 20 credits.", "done", "finish", 1),
        ),
    ),
)


# Same inline label/value formatting emitted by native PDFKit; all identities are synthetic.
CLINICAL_REPORT = """Demonstration Clinic
Patient health summary
Patient
Name: Synthetic Caller
Patient ID: DEMO-2714
Date of birth: 14 March 1994
Doctor: Dr. Nisha Shah, General Medicine
Clinical summary
Condition: Hypertension (diagnosed 2023)
Allergies: Penicillin
Medication: Amlodipine 5 mg, once a day
Last visit: 12 August 2026 · BP 138/88 mmHg
Plan: Review blood pressure in 3 months; bring recent reports
Synthetic record for a product demonstration. Not a real patient."""
CLINICAL_GOAL = "Book an appointment with the doctor in the attached health report."
CLINICAL_SCENARIOS = (
    Scenario(
        "clinical_unattended_booking",
        CLINICAL_GOAL,
        (
            Step(
                "Does the patient have any allergy and what was the BP at their last checkup?",
                "answer",
                "answer_question",
                answer_spans=(
                    "Allergies: Penicillin",
                    "Last visit: 12 August 2026 · BP 138/88 mmHg",
                ),
                required=("Penicillin", "138/88"),
            ),
            Step(
                "Is the patient registered and what is their patient ID?",
                "answer",
                "answer_question",
                answer_spans=("Patient ID: DEMO-2714",),
                required=("DEMO-2714",),
            ),
            Step(
                "What is the doctor's name?",
                "answer",
                "answer_question",
                answer_spans=("Doctor: Dr. Nisha Shah, General Medicine",),
                required=("Nisha Shah",),
            ),
            Step(
                "I can book an appointment with Dr. Nisha Shah. Shall I proceed?",
                "accept",
                "accept_offer",
            ),
            Step("Your appointment with Dr. Nisha Shah has been booked.", "done", "finish"),
        ),
        document=CLINICAL_REPORT,
        caller_available=False,
    ),
    Scenario(
        "clinical_repeated_allergy",
        CLINICAL_GOAL,
        tuple(
            Step(
                question,
                "answer",
                "answer_question",
                answer_spans=("Allergies: Penicillin",),
                required=("Penicillin",),
            )
            for question in (
                "What allergy does the patient have?",
                "Sorry, could you repeat the patient's allergy?",
            )
        ),
        document=CLINICAL_REPORT,
        caller_available=False,
    ),
    Scenario(
        "clinical_unknown_address",
        CLINICAL_GOAL,
        (Step("What is the patient's home address?", "unavailable", "need_caller"),),
        document=CLINICAL_REPORT,
        caller_available=False,
    ),
    Scenario(
        "clinical_four_facts",
        CLINICAL_GOAL,
        (
            Step(
                "Please give the patient's ID, allergies, date of birth and medication.",
                "answer",
                "answer_question",
                answer_spans=(
                    "Patient ID: DEMO-2714",
                    "Allergies: Penicillin",
                    "Date of birth: 14 March 1994",
                    "Medication: Amlodipine 5 mg, once a day",
                ),
                required=("DEMO-2714", "Penicillin", "14 March 1994", "Amlodipine", "5 mg"),
            ),
        ),
        document=CLINICAL_REPORT,
        caller_available=False,
    ),
    Scenario(
        "clinical_acknowledgement",
        CLINICAL_GOAL,
        (Step("Okay.", "wait", "wait", provider_expected=False),),
        document=CLINICAL_REPORT,
        caller_available=False,
    ),
    Scenario(
        "clinical_unknown_allergy_without_document",
        CLINICAL_GOAL,
        (Step("Does the patient have any allergies?", "unavailable", "need_caller"),),
        caller_available=False,
    ),
)


AUTONOMY_SCENARIOS = (
    Scenario(
        "autonomy_routine_time_and_fee",
        "Book with Dr. Rao.",
        (
            Step(
                "We have Monday at 9 pm. Is that okay?",
                "accept_rules",
                "accept_offer",
                provider_expected=False,
            ),
            Step("The clinic treatment is ₹800. Shall we proceed?", "accept", "accept_offer"),
            Step("You are booked with Dr. Rao for Monday at 9 pm.", "done", "finish"),
        ),
        caller_available=False,
    ),
    Scenario(
        "autonomy_passport_booklet_choice",
        "Order a replacement passport after losing it abroad.",
        (
            Step(
                "Do you want a 32-pager or a 64-pager?",
                "choice",
                "choose_option",
                option="32-pager",
                choices=("32", "64"),
            ),
            Step(
                "Your replacement passport order for the selected booklet has been registered.",
                "done",
                "finish",
            ),
        ),
        caller_available=False,
    ),
    Scenario(
        "autonomy_explicit_booklet_preference",
        "Order a replacement passport with a 64-page booklet.",
        (
            Step(
                "We offer a 32-page booklet and a 64-page booklet. "
                "Which passport booklet would you like?",
                "choice",
                "choose_option",
                option="64-page booklet",
                choices=("32", "64"),
                required=("64",),
            ),
            Step(
                "Your replacement passport order for the selected booklet has been registered.",
                "done",
                "finish",
            ),
        ),
        caller_available=False,
    ),
    Scenario(
        "autonomy_explicit_budget_limit",
        "Arrange a plumber visit to repair the kitchen pipe. Spend at most 500 rupees.",
        (
            Step(
                "I can book a plumber visit to repair the kitchen pipe for 800 rupees. "
                "Shall I proceed?",
                "unavailable",
                "need_caller",
                provider_expected=False,
            ),
        ),
        caller_available=False,
    ),
    Scenario(
        "autonomy_unknown_personal_identifier",
        "Order a replacement passport after losing it abroad.",
        (Step("What is the applicant's national identity number?", "unavailable", "need_caller"),),
        caller_available=False,
    ),
    Scenario(
        "autonomy_confirmation_and_final_question",
        "Arrange a plumber visit to repair the leak.",
        (
            Step(
                "Your plumber visit to repair the leak is booked. How will they get inside?",
                "answer",
                "answer_question",
                resolve=True,
                answer_spans=("Access instructions: Use the side gate",),
                required=("Use the side gate",),
                resolution_quote="Your plumber visit to repair the leak is booked.",
            ),
            Step("Thank you.", "closed", "finish", provider_expected=False),
        ),
        document="Access instructions: Use the side gate",
        caller_available=False,
    ),
)


def value_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    return "other"


class ReplayClient(GroqClient):
    def __init__(self, key: SecretStr, model: str, *, live: bool, capture_dir: Path | None = None):
        self.requests = 0
        self.step: Step | None = None
        self.last_action: str | None = None
        self.resolution_review = False
        self.rejection: str | None = None
        self.diagnostic: dict = {}
        self.capture_dir = capture_dir
        self._capture_key = key
        super().__init__(key, model, transport=None if live else httpx.MockTransport(self.mock))
        self._http.event_hooks["response"] = [self.inspect_response]

    async def inspect_response(self, response: httpx.Response) -> None:
        await response.aread()
        self.diagnostic["http_status"] = response.status_code
        if self.capture_dir is not None:
            target = self.capture_dir / f"response-{self.requests:02d}.json"
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as capture:
                json.dump(
                    {
                        "http_status": response.status_code,
                        "body": response.text.replace(
                            self._capture_key.get_secret_value(), "[redacted]"
                        ),
                    },
                    capture,
                )
        try:
            envelope = response.json()
        except ValueError:
            self.diagnostic["envelope_type"] = "non_json"
            return
        self.diagnostic["envelope_type"] = value_type(envelope)
        if not isinstance(envelope, dict):
            return
        choices = envelope.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return
        choice = choices[0]
        finish = choice.get("finish_reason")
        self.diagnostic["finish_reason"] = (
            finish if finish in (None, "stop", "length", "content_filter") else "other"
        )
        message = choice.get("message")
        if not isinstance(message, dict):
            return
        content = message.get("content")
        self.diagnostic["content_type"] = value_type(content)
        if not isinstance(content, str):
            return
        try:
            selected = json.loads(content)
        except ValueError:
            self.diagnostic["json_type"] = "non_json"
            return
        self.diagnostic["json_type"] = value_type(selected)
        if isinstance(selected, dict):
            self.diagnostic["action_type"] = value_type(selected.get("action"))

    async def _request(self, body):
        if self.requests >= MAX_REQUESTS:
            self.rejection = "budget"
            raise GroqError("replay request budget exhausted", category="budget")
        self.requests += 1
        self.diagnostic["request_index"] = self.requests
        return await super()._request(body)

    async def complete_structured(self, system, user, response_model):
        if response_model is ResolutionReview:
            self.resolution_review = True
            self.diagnostic["response_kind"] = "resolution_review"
        try:
            selected = await super().complete_structured(system, user, response_model)
        except asyncio.CancelledError:
            self.rejection = "timeout"
            raise
        except GroqError as error:
            self.rejection = error.category
            if getattr(error, "validation_errors", ()):
                self.diagnostic["schema_errors"] = list(error.validation_errors)
            if getattr(error, "status_code", None) is not None:
                self.diagnostic["http_status"] = error.status_code
            raise
        if not isinstance(selected, ResolutionReview):
            self.last_action = selected.action.kind
        return selected

    def mock(self, request: httpx.Request) -> httpx.Response:
        assert self.step is not None
        payload = json.loads(request.content)
        assert payload["response_format"]["json_schema"]["strict"] is True
        prompt = json.loads(payload["messages"][1]["content"])
        step = self.step
        properties = payload["response_format"]["json_schema"]["schema"]["properties"]
        if set(properties) == {"resolutions"}:
            receiver = prompt["receiver"]
            # Quote the supplied proof clause, excluding a following receiver question.
            quote = re.split(
                r"(?<=[.!])\s+(?=(?:what|which|how|can|could|would|do|is|are)\b)",
                receiver["text"],
                maxsplit=1,
                flags=re.I,
            )[0]
            selected = {
                "resolutions": [
                    {"goal_id": goal["goal_id"], "source_id": receiver["source_id"], "quote": quote}
                    for goal in prompt["goals"]
                ]
            }
        else:
            selected = action(step.proposal)
            if step.proposal == "finish" or step.resolve:
                current = prompt["current_receiver_turn"]
                selected["resolutions"] = [
                    {
                        "goal_id": prompt["goals"][step.goal_index]["goal_id"],
                        "source_id": current["source_id"],
                        "quote": step.resolution_quote or current["text"],
                    }
                ]
            if step.proposal == "answer_question":
                selected["action"].update(
                    spans=[
                        {"source_id": "document:0", "quote": quote}
                        for quote in (step.answer_spans or (DOCUMENT_QUOTE,))
                    ]
                )
            elif step.proposal in {"accept_offer", "choose_option"}:
                current = prompt["current_receiver_turn"]
                selected["action"].update(
                    goal_id=prompt["goals"][step.goal_index]["goal_id"],
                    source_id=current["source_id"],
                    quote=current["text"],
                )
                if step.proposal == "choose_option":
                    selected["action"]["option"] = step.option
            elif step.proposal == "ask_operator":
                selected["action"]["question"] = step.question
            if step.proposal in {"answer_question", "need_caller"}:
                selected["action"]["question_id"] = next(
                    reversed(prompt["pending_receiver_questions"]), "not-a-pending-question"
                )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": json.dumps(selected)},
                        "finish_reason": "stop",
                    }
                ]
            },
        )


def state_for(scenario: Scenario) -> DelegateState:
    profile = Profile(
        name="Synthetic Caller",
        documents=[
            {
                "name": "Synthetic form",
                "text": scenario.document if isinstance(scenario.document, str) else DOCUMENT_TEXT,
            }
        ]
        if scenario.document
        else [],
    )
    request = BriefRequest(purpose="general", profile=profile, request=scenario.goal)
    return DelegateState(
        brief_from(request, build_brief(request)),
        attended=False,
        steer=True,
        opened=True,
        caller_available=scenario.caller_available,
    )


def check(step: Step, decision, state: DelegateState) -> bool:
    if step.expected == "need_caller":
        return decision.follow_up == step.heard and not decision.done and "40" not in decision.say
    if step.expected == "unavailable":
        return (
            decision.follow_up == step.heard
            and decision.done
            and not decision.callback
            and not state.planner.completed
        )
    if step.expected == "accept_rules":
        return (
            decision.kind == "accept"
            and not decision.done
            and decision.follow_up is None
            and not state.planner.pending
            and not state.planner.completed
        )
    if step.expected == "accept":
        return (
            decision.kind == "accept"
            and decision.source == "llm"
            and not decision.done
            and decision.follow_up is None
            and state.planner.goals[step.goal_index].evidence is None
        )
    if step.expected == "wait":
        return not decision.done and decision.follow_up is None and not state.planner.completed
    if step.expected == "answer":
        return (
            (
                all(value in decision.say for value in step.required)
                if step.required
                else decision.say in DOCUMENT_ANSWERS
            )
            and not decision.done
            and decision.follow_up is None
        )
    if step.expected == "closed":
        return (
            decision.done
            and not decision.callback
            and decision.follow_up is None
            and state.planner.completed
            and all(goal.evidence for goal in state.planner.goals)
        )
    if step.expected == "choice":
        return (
            decision.source == "llm"
            and not decision.done
            and decision.follow_up is None
            and not state.planner.pending
            and not state.planner.completed
            and all(value in decision.say for value in step.required)
            and sum(
                bool(re.search(r"\b" + re.escape(option) + r"\b", decision.say))
                for option in step.choices
            )
            == 1
        )
    if step.expected == "done":
        evidence = state.planner.goals[step.goal_index].evidence
        return (
            decision.done
            and not decision.callback
            and decision.follow_up is None
            and state.planner.completed
            and evidence is not None
            and evidence.source_id == state.planner.receiver[-1].source_id
            and evidence.text in step.heard
        )
    if step.expected == "ask_operator":
        words = set(re.findall(r"[a-z]+", decision.say.lower()))
        return (
            decision.source == "llm"
            and not decision.done
            and decision.follow_up is None
            and decision.say.endswith("?")
            and bool(words.intersection(step.focus))
        )
    return False


def expected_actions(step: Step) -> frozenset[str]:
    # A supplied preference is already a caller fact. An unspecified operational
    # choice needs ChooseOption rather than pretending the caller supplied it.
    actions = {step.proposal}
    if step.expected == "choice" and step.required:
        actions.add("answer_question")
    return frozenset(actions)


def rejection_for(
    step: Step,
    decision,
    selected: str | None,
    state: DelegateState,
    *,
    resolution_review: bool = False,
) -> str | None:
    if resolution_review and step.expected != "closed":
        return "unexpected_resolution_review"
    if not step.provider_expected and selected is not None:
        return "unexpected_model_request"
    if step.provider_expected and selected not in expected_actions(step):
        return "unexpected_action"
    if (
        (selected == "answer_question" and decision.kind != "share")
        or (selected == "accept_offer" and decision.kind != "accept")
        or (selected == "finish" and not decision.done)
        or (selected in {"ask_operator", "wait"} and decision.source != "llm")
    ):
        return "action_guard"
    if step.expected == "ask_operator" and not check(step, decision, state):
        return "off_goal_question"
    if step.expected == "answer" and not check(step, decision, state):
        return "wrong_document_field"
    if not check(step, decision, state):
        return "unexpected_outcome"
    return None


def verified_close_correction(
    step: Step,
    selected: str | None,
    state: DelegateState,
    runtime_success: bool,
    model_rejection: str | None,
) -> str | None:
    """Report a stale model action separately from a correctly proven runtime close."""
    if (
        step.expected not in {"done", "closed"}
        or selected is None
        or not runtime_success
        or model_rejection not in {"unexpected_action", "action_guard", "unexpected_model_request"}
        or not state.planner.completed
    ):
        return None
    for goal in state.planner.goals:
        proof = goal.evidence
        if proof is None or not any(
            turn.source_id == proof.source_id and proof.text in turn.text
            for turn in state.planner.receiver
        ):
            return None
    return "closed_from_verified_resolutions"


def prepare_capture(directory: Path | None) -> Path | None:
    if directory is None:
        return None
    target = directory.resolve()
    repository = Path(__file__).resolve().parents[1]
    if target.is_relative_to(repository):
        raise ValueError("Private response capture must be outside the repository.")
    target.mkdir(mode=0o700)
    return target


async def run(
    live: bool,
    capture_dir: Path | None = None,
    interval_seconds: float = 0,
    *,
    suite: str = "general",
) -> int:
    if suite not in {"general", "clinical", "autonomy"}:
        raise ValueError("Unknown replay suite.")
    if not 0 <= interval_seconds <= 30:
        raise ValueError("Interval must be between 0 and 30 seconds.")
    key = os.environ.get("GROQ_API_KEY") if live else "synthetic-key"
    if not key:
        print(json.dumps({"mode": "live", "pass": False, "rejection": "missing_key"}))
        return 2
    model = os.environ.get("GROQ_MODEL", DEFAULT_MODEL) if live else DEFAULT_MODEL
    capture_dir = prepare_capture(capture_dir)
    previous_logging_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    client = ReplayClient(SecretStr(key), model, live=live, capture_dir=capture_dir)
    failures = 0
    corrected_actions = 0
    print(
        json.dumps(
            {
                "mode": "live" if live else "mock",
                "suite": suite,
                "request_cap": MAX_REQUESTS,
                "telephony": False,
                "private_capture": capture_dir is not None,
                "interval_seconds": interval_seconds,
            }
        )
    )
    try:
        for scenario in (
            AUTONOMY_SCENARIOS
            if suite == "autonomy"
            else CLINICAL_SCENARIOS
            if suite == "clinical"
            else SCENARIOS
        ):
            state = state_for(scenario)
            for index, step in enumerate(scenario.steps):
                client.step = step
                client.last_action = client.rejection = None
                client.resolution_review = False
                client.diagnostic = {}
                if interval_seconds:
                    await asyncio.sleep(interval_seconds)
                state.observe_receiver(step.heard)
                try:
                    decision = await Brain(client).reply(state, step.heard)
                except Exception as error:  # noqa: BLE001 - keep raw provider details out of CLI errors
                    failures += 1
                    print(
                        json.dumps(
                            {
                                "case": scenario.name,
                                "step": index + 1,
                                "pass": False,
                                "action": client.last_action or "rules",
                                "model_quality": step.provider_expected or client.resolution_review,
                                "resolution_review": client.resolution_review,
                                "status": "error",
                                "closed": False,
                                "rejection": "application_error",
                                "diagnostic": {
                                    **client.diagnostic,
                                    "error_type": type(error).__name__,
                                },
                            }
                        )
                    )
                    continue
                rejected = client.rejection or rejection_for(
                    step,
                    decision,
                    client.last_action,
                    state,
                    resolution_review=client.resolution_review,
                )
                runtime_success = check(step, decision, state)
                model_rejection = rejected
                correction = verified_close_correction(
                    step, client.last_action, state, runtime_success, model_rejection
                )
                if correction:
                    rejected = None
                    corrected_actions += 1
                passed = runtime_success and rejected is None
                failures += not passed
                print(
                    json.dumps(
                        {
                            "case": scenario.name,
                            "step": index + 1,
                            "pass": passed,
                            "action": client.last_action or "rules",
                            "model_quality": (step.provider_expected or client.resolution_review)
                            and correction is None,
                            "resolution_review": client.resolution_review,
                            "model_rejection": model_rejection,
                            "action_correction": correction,
                            "status": "follow_up"
                            if decision.follow_up
                            else "done"
                            if decision.done and state.planner.completed
                            else "unclear"
                            if decision.done
                            else "open",
                            "closed": decision.done,
                            "rejection": rejected,
                            "diagnostic": client.diagnostic,
                        }
                    )
                )
                state.exchanges.append(Exchange(step.heard, decision.say))
    finally:
        await client.aclose()
        logging.disable(previous_logging_disable)
    print(
        json.dumps(
            {
                "pass": failures == 0,
                "failed_steps": failures,
                "model_requests": client.requests,
                "corrected_model_actions": corrected_actions,
                "evidence": "live_synthetic" if live else "mock_contract_only",
            }
        )
    )
    return 1 if failures else 0


def _http_step_passed(step: Step, spoken: str, state: DelegateState) -> bool:
    if step.expected == "answer":
        return (
            bool(step.required)
            and all(value in spoken for value in step.required)
            and not state.follow_ups
            and state.outcome is None
        )
    if step.expected == "accept_rules":
        return (
            bool(spoken)
            and state.outcome is None
            and bool(state.agent_answers)
            and not state.follow_ups
            and not state.planner.pending
            and not state.planner.completed
        )
    if step.expected == "accept":
        return (
            bool(spoken)
            and state.outcome is None
            and state.planner.goals[step.goal_index].accepted_offer is not None
            and not state.planner.completed
        )
    if step.expected == "choice":
        return (
            state.outcome is None
            and not state.follow_ups
            and not state.planner.pending
            and not state.planner.completed
            and all(value in spoken for value in step.required)
            and sum(
                bool(re.search(r"\b" + re.escape(option) + r"\b", spoken))
                for option in step.choices
            )
            == 1
        )
    if step.expected in {"done", "closed"}:
        evidence = state.planner.goals[step.goal_index].evidence
        return (
            state.planner.completed
            and state.outcome == "done"
            and not state.follow_ups
            and (
                step.expected == "closed"
                or (
                    evidence is not None
                    and evidence.source_id == state.planner.receiver[-1].source_id
                    and evidence.text in step.heard
                )
            )
        )
    if step.expected == "unavailable":
        return state.outcome == "unclear" and state.follow_ups == [step.heard]
    if step.expected == "wait":
        return state.outcome is None and not state.follow_ups and not state.planner.completed
    return False


async def run_http(
    live: bool,
    capture_dir: Path | None = None,
    interval_seconds: float = 0,
    *,
    suite: str = "clinical",
) -> int:
    """Exercise real FastAPI/custom-LLM routes with the repository's fake telephony.

    Requires backend development dependencies. Only Groq can use a real transport;
    credentials, calls, webhook events and contact allowlisting are all synthetic.
    """
    if suite not in {"clinical", "autonomy"}:
        raise ValueError("Unknown HTTP replay suite.")
    if not 0 <= interval_seconds <= 30:
        raise ValueError("Interval must be between 0 and 30 seconds.")
    key = os.environ.get("GROQ_API_KEY") if live else "synthetic-key"
    if not key:
        print(json.dumps({"mode": "live", "pass": False, "rejection": "missing_key"}))
        return 2
    model = os.environ.get("GROQ_MODEL", DEFAULT_MODEL) if live else DEFAULT_MODEL
    capture_dir = prepare_capture(capture_dir)
    previous_logging_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)

    def replay() -> int:
        # This is deliberately the same HTTP driver used by integration tests; no
        # production telephony or environment-backed Settings object is constructed.
        from tests.test_delegate import AUTH, build_flow

        client = ReplayClient(SecretStr(key), model, live=live, capture_dir=capture_dir)
        failures = 0
        corrected_actions = 0
        print(
            json.dumps(
                {
                    "mode": "live" if live else "mock",
                    "suite": suite,
                    "request_cap": MAX_REQUESTS,
                    "telephony": False,
                    "transport": "local_http",
                    "private_capture": capture_dir is not None,
                    "interval_seconds": interval_seconds,
                }
            )
        )
        with contextlib.ExitStack() as stack:
            flow = build_flow(stack, brain=Brain(client))
            try:
                for scenario in AUTONOMY_SCENARIOS if suite == "autonomy" else CLINICAL_SCENARIOS:
                    request = state_for(scenario).brief
                    profile = {
                        "name": request.name,
                        "documents": [
                            {"name": item.name, "text": item.text} for item in request.documents
                        ],
                    }
                    brief = flow.client.post(
                        "/briefs",
                        json={"purpose": "general", "profile": profile, "request": scenario.goal},
                        headers=AUTH,
                    )
                    if brief.status_code != 200:
                        raise ValueError("Synthetic brief could not be created.")
                    started = flow.client.post(
                        "/calls",
                        json={
                            "contact_id": "clinic",
                            "purpose": "general",
                            "mode": "steer",
                            "brief_id": brief.json()["brief_id"],
                        },
                        headers=AUTH,
                    )
                    if started.status_code != 200:
                        raise ValueError("Synthetic call could not be created.")
                    call_id = started.json()["call_id"]
                    flow.live(call_id)
                    flow.speak_last(call_id)
                    state = flow.manager._sessions[call_id].delegate
                    state.opened = True
                    for index, step in enumerate(scenario.steps):
                        client.step = step
                        client.last_action = client.rejection = None
                        client.resolution_review = False
                        client.diagnostic = {}
                        correction = model_rejection = None
                        if interval_seconds:
                            flow.client.portal.call(asyncio.sleep, interval_seconds)
                        try:
                            spoken = flow.listen_turn(call_id, step.heard)
                            rejected = client.rejection
                            if (
                                not rejected
                                and client.resolution_review
                                and step.expected != "closed"
                            ):
                                rejected = "unexpected_resolution_review"
                            if (
                                not rejected
                                and not step.provider_expected
                                and client.last_action is not None
                            ):
                                rejected = "unexpected_model_request"
                            if (
                                not rejected
                                and step.provider_expected
                                and client.last_action not in expected_actions(step)
                            ):
                                rejected = "unexpected_action"
                            runtime_success = _http_step_passed(step, spoken, state)
                            model_rejection = rejected
                            correction = verified_close_correction(
                                step, client.last_action, state, runtime_success, model_rejection
                            )
                            if correction:
                                rejected = None
                                corrected_actions += 1
                            passed = runtime_success and rejected is None
                            if not passed and rejected is None:
                                rejected = "http_outcome"
                        except Exception as error:  # noqa: BLE001 - retain no raw provider details
                            passed, rejected = False, "application_error"
                            client.diagnostic["error_type"] = type(error).__name__
                        failures += not passed
                        print(
                            json.dumps(
                                {
                                    "case": scenario.name,
                                    "step": index + 1,
                                    "pass": passed,
                                    "action": client.last_action or "rules",
                                    "model_quality": (
                                        step.provider_expected or client.resolution_review
                                    )
                                    and correction is None,
                                    "resolution_review": client.resolution_review,
                                    "model_rejection": model_rejection,
                                    "action_correction": correction,
                                    "rejection": rejected,
                                    "diagnostic": client.diagnostic,
                                }
                            )
                        )
                    flow.finish()
                    notes = flow.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
                    expected_done = scenario.steps[-1].expected in {"done", "closed"}
                    notes_passed = notes["ready"] and (
                        notes["outcome"] == "done" and not notes["follow_ups"]
                        if expected_done
                        else notes["outcome"] != "done"
                    )
                    if scenario.steps[-1].expected == "unavailable":
                        notes_passed = notes_passed and notes["follow_ups"] == [
                            scenario.steps[-1].heard
                        ]
                    failures += not notes_passed
                    print(
                        json.dumps(
                            {
                                "case": scenario.name,
                                "stage": "notes",
                                "pass": bool(notes_passed),
                                "outcome": notes["outcome"],
                            }
                        )
                    )
            finally:
                flow.client.portal.call(client.aclose)
        print(
            json.dumps(
                {
                    "pass": failures == 0,
                    "failed_steps": failures,
                    "model_requests": client.requests,
                    "corrected_model_actions": corrected_actions,
                    "evidence": "live_synthetic_http" if live else "mock_http_contract_only",
                }
            )
        )
        return 1 if failures else 0

    try:
        return await asyncio.to_thread(replay)
    finally:
        logging.disable(previous_logging_disable)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--live",
        action="store_true",
        help="Spend provider credits on synthetic fixtures after explicit task authorization.",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Use mocked provider responses (the default).",
    )
    parser.add_argument(
        "--capture-dir",
        type=Path,
        help=(
            "Create a new private directory outside the repository for synthetic provider "
            "response bodies. No request or headers are captured."
        ),
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=0,
        help=(
            "Pause 0 to 30 seconds before each replay step, "
            "outside the production response deadline."
        ),
    )
    parser.add_argument(
        "--suite",
        choices=("general", "clinical", "autonomy"),
        default="general",
        help="Run general, clinical-document, or autonomous operational-choice fixtures.",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run clinical fixtures through local HTTP, fake telephony, and saved notes.",
    )
    args = parser.parse_args()
    try:
        if args.http:
            return asyncio.run(
                run_http(
                    args.live,
                    args.capture_dir,
                    args.interval_seconds,
                    suite="autonomy" if args.suite == "autonomy" else "clinical",
                )
            )
        return asyncio.run(
            run(args.live, args.capture_dir, args.interval_seconds, suite=args.suite)
        )
    except (ValueError, FileExistsError, PermissionError) as error:
        parser.exit(2, f"configuration_error: {type(error).__name__}\n")


if __name__ == "__main__":
    raise SystemExit(main())
