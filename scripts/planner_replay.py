#!/usr/bin/env python3
"""Phone-free synthetic steer replay. Defaults to mocked provider responses.

Run with backend/.venv/bin/python scripts/planner_replay.py. --live spends provider
credits and requires task authorization before execution. It reads only GROQ_API_KEY
and GROQ_MODEL, sends synthetic fixtures, and makes at most twelve model requests.
"""

from __future__ import annotations

import argparse
import asyncio
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


@dataclass(frozen=True)
class Scenario:
    name: str
    goal: str
    steps: tuple[Step, ...]
    document: bool = False
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
        (Step("Which category is printed on the form?", "answer", "answer_question"),)
        * 2,
        document=True,
    ),
    Scenario(
        "fee_consent",
        "Ask what a drain inspection costs.",
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
            Step(
                "Your replacement passport order has been registered.", "done", "finish"
            ),
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
    def __init__(
        self, key: SecretStr, model: str, *, live: bool, capture_dir: Path | None = None
    ):
        self.requests = 0
        self.step: Step | None = None
        self.last_action: str | None = None
        self.rejection: str | None = None
        self.diagnostic: dict = {}
        self.capture_dir = capture_dir
        self._capture_key = key
        super().__init__(
            key, model, transport=None if live else httpx.MockTransport(self.mock)
        )
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
        if (
            not isinstance(choices, list)
            or not choices
            or not isinstance(choices[0], dict)
        ):
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
        self.last_action = selected.action.kind
        return selected

    def mock(self, request: httpx.Request) -> httpx.Response:
        assert self.step is not None
        payload = json.loads(request.content)
        assert payload["response_format"]["json_schema"]["strict"] is True
        prompt = json.loads(payload["messages"][1]["content"])
        step = self.step
        selected = action(step.proposal)
        if step.proposal == "finish" or step.resolve:
            current = prompt["current_receiver_turn"]
            selected["resolutions"] = [
                {
                    "goal_id": prompt["goals"][step.goal_index]["goal_id"],
                    "source_id": current["source_id"],
                    "quote": current["text"],
                }
            ]
        if step.proposal == "answer_question":
            selected["action"].update(source_id="document:0", quote=DOCUMENT_QUOTE)
        elif step.proposal == "accept_offer":
            current = prompt["current_receiver_turn"]
            selected["action"].update(
                goal_id=prompt["goals"][step.goal_index]["goal_id"],
                source_id=current["source_id"],
                quote=current["text"],
            )
        elif step.proposal == "ask_operator":
            selected["action"]["question"] = step.question
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
        documents=[{"name": "Synthetic form", "text": DOCUMENT_TEXT}]
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
        return (
            decision.follow_up == step.heard
            and not decision.done
            and "40" not in decision.say
        )
    if step.expected == "unavailable":
        return (
            decision.follow_up == step.heard
            and decision.done
            and not decision.callback
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
    if step.expected == "answer":
        return (
            decision.say in DOCUMENT_ANSWERS
            and not decision.done
            and decision.follow_up is None
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


def rejection_for(
    step: Step, decision, selected: str | None, state: DelegateState
) -> str | None:
    if step.provider_expected and selected != step.proposal:
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
    live: bool, capture_dir: Path | None = None, interval_seconds: float = 0
) -> int:
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
    print(
        json.dumps(
            {
                "mode": "live" if live else "mock",
                "request_cap": MAX_REQUESTS,
                "telephony": False,
                "private_capture": capture_dir is not None,
                "interval_seconds": interval_seconds,
            }
        )
    )
    try:
        for scenario in SCENARIOS:
            state = state_for(scenario)
            for index, step in enumerate(scenario.steps):
                client.step = step
                client.last_action = client.rejection = None
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
                                "model_quality": step.provider_expected,
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
                    step, decision, client.last_action, state
                )
                passed = check(step, decision, state) and rejected is None
                failures += not passed
                print(
                    json.dumps(
                        {
                            "case": scenario.name,
                            "step": index + 1,
                            "pass": passed,
                            "action": client.last_action or "rules",
                            "model_quality": step.provider_expected,
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
                "evidence": "live_synthetic" if live else "mock_contract_only",
            }
        )
    )
    return 1 if failures else 0


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
        help="Create a new private directory outside the repository for synthetic provider response bodies. No request or headers are captured.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=0,
        help="Pause 0 to 30 seconds before each replay step, outside the production response deadline.",
    )
    args = parser.parse_args()
    try:
        return asyncio.run(run(args.live, args.capture_dir, args.interval_seconds))
    except (ValueError, FileExistsError, PermissionError) as error:
        parser.exit(2, f"configuration_error: {type(error).__name__}\n")


if __name__ == "__main__":
    raise SystemExit(main())
