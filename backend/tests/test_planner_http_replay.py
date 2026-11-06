"""Synthetic provider-contract and phone-free HTTP replays of general steer calls."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
import pytest
from pydantic import SecretStr

from app.delegate import Brain, DelegateState, Exchange, brief_from, build_brief
from app.groq_client import GroqClient
from app.protocol import BriefRequest, Profile
from tests.test_delegate import AUTH, Flow, build_flow

MODEL = "openai/gpt-oss-120b"


def action(kind: str, **values: object) -> dict:
    resolutions = values.pop("resolutions", [])
    if kind == "finish":
        values.setdefault("blocked", False)
    return {"action": {"kind": kind, **values}, "resolutions": resolutions}


def bind_question_action(prompt: dict, selected: dict) -> dict:
    """Bind mock fixtures to the actual pending question, just as a provider must."""
    chosen = selected["action"]
    if chosen["kind"] not in {"answer_question", "need_caller"}:
        return selected
    pending = prompt["pending_receiver_questions"]
    chosen.setdefault("question_id", next(reversed(pending), "not-a-pending-question"))
    if chosen["kind"] == "answer_question" and "source_id" in chosen:
        chosen["spans"] = [{"source_id": chosen.pop("source_id"), "quote": chosen.pop("quote")}]
    return selected


@dataclass
class Provider:
    choose: Callable[[dict], dict | str]
    requests: list[dict] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/openai/v1/chat/completions"
        body = json.loads(request.content)
        self.requests.append(body)
        prompt = json.loads(body["messages"][1]["content"])
        selected = self.choose(prompt)
        content = (
            selected
            if isinstance(selected, str)
            else json.dumps(bind_question_action(prompt, selected))
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 30, "completion_tokens": 20},
            },
        )


def client_for(provider: Callable) -> GroqClient:
    return GroqClient(SecretStr("synthetic-key"), MODEL, transport=httpx.MockTransport(provider))


def state_for(request: str, **profile_values: object) -> DelegateState:
    body = BriefRequest(
        purpose="general", profile=Profile(name="Test Caller", **profile_values), request=request
    )
    return DelegateState(
        brief_from(body, build_brief(body)), attended=False, steer=True, opened=True
    )


def start_general(f: Flow, request: str, *, mode="steer", **profile: object) -> str:
    response = f.client.post(
        "/briefs",
        json={
            "purpose": "general",
            "profile": {"name": "Test Caller", **profile},
            "request": request,
        },
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    response = f.client.post(
        "/calls",
        json={
            "contact_id": "clinic",
            "purpose": "general",
            "mode": mode,
            "brief_id": response.json()["brief_id"],
        },
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    return response.json()["call_id"]


def make_caller_present(f: Flow, call_id: str) -> None:
    from app.protocol import PresenceMessage

    f.manager._steer_window = lambda _text: 0
    f.client.portal.call(
        f.manager._on_presence,
        f.manager._sessions[call_id],
        PresenceMessage(type="presence", present=True),
    )


def assert_closed_schema(node: object) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
        for value in node.values():
            assert_closed_schema(value)
    elif isinstance(node, list):
        for value in node:
            assert_closed_schema(value)


@pytest.mark.parametrize("malformed", ["not json", '{"action":"finish"}', '{"say":"Yes"}'])
async def test_malformed_provider_output_cannot_answer_or_finish(malformed: str) -> None:
    provider = Provider(lambda _: malformed)
    client = client_for(provider)
    try:
        result = await Brain(client).reply(
            state_for("Ask about replacing my passport."), "When was the passport issued?"
        )
        assert not result.done
        assert result.follow_up == "When was the passport issued?"
        assert "2019" not in result.say
    finally:
        await client.aclose()


@pytest.mark.parametrize("failure", ["timeout", "http"])
async def test_provider_failure_leaves_missing_information_with_the_caller(failure: str) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        return httpx.Response(503)

    client = client_for(fail)
    try:
        result = await Brain(client).reply(
            state_for("Ask about replacing my passport."), "Have you lost the old passport?"
        )
        assert result.follow_up == "Have you lost the old passport?"
        assert not result.done
    finally:
        await client.aclose()


@pytest.mark.parametrize("model", [MODEL, "qwen/qwen3.8-27b"])
async def test_current_provider_contract_requires_closed_schema_and_suppresses_reasoning(
    model,
) -> None:
    provider = Provider(lambda _: action("need_caller"))
    client = GroqClient(SecretStr("synthetic-key"), model, transport=httpx.MockTransport(provider))
    try:
        decision = await Brain(client).reply(
            state_for("Ask about replacing my passport."), "When was the passport issued?"
        )
        assert decision.follow_up == "When was the passport issued?"
        assert len(provider.requests) == 1
        payload = provider.requests[0]
        assert payload["model"] == model
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["strict"] is True
        schema = payload["response_format"]["json_schema"]["schema"]
        assert_closed_schema(schema)
        assert schema["type"] == "object"
        assert set(schema["properties"]) == {"action", "resolutions"}
        assert len(schema["properties"]["action"]["anyOf"]) == 7
        if model.startswith("openai/gpt-oss"):
            assert payload["include_reasoning"] is False
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    ("goal", "questions"),
    [
        (
            "Ask how to replace my passport.",
            ("When was your passport issued?", "Have you lost the old passport?"),
        ),
        (
            "Ask a plumber about a blocked drain.",
            ("What caused the blockage?", "Did grease cause the blockage?"),
        ),
    ],
)
def test_receiver_questions_reach_the_live_caller_and_remain_unresolved_in_notes(
    goal: str, questions: tuple[str, ...]
) -> None:
    provider = Provider(lambda _: action("need_caller"))
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_general(f, goal)
        make_caller_present(f, call_id)
        with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
            assert f.receive(ws)["type"] == "status"
            f.live(call_id)
            f.speak_last(call_id)
            for question in questions:
                spoken = f.listen_turn(call_id, question)
                assert "2019" not in spoken and "grease caused" not in spoken.lower()
                assert f.drain_until(ws, "follow_up")["text"] == question
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] != "done"
        assert notes["follow_ups"] == list(questions)
        assert all(any(q in line for line in notes["open_questions"]) for q in questions)


def source_with(prompt: dict, text: str) -> dict:
    return next(source for source in prompt["approved_sources"] if text in source["text"])


def resolution(prompt: dict, goal_index: int = 0, *, quote: str | None = None) -> dict:
    receiver = prompt["current_receiver_turn"]
    return {
        "goal_id": prompt["goals"][goal_index]["goal_id"],
        "source_id": receiver["source_id"],
        "quote": quote or receiver["text"],
    }


async def test_approved_exact_answer_can_be_repeated_when_receiver_asks_again() -> None:
    def choose(prompt: dict) -> dict:
        source = source_with(prompt, "17 June 2019")
        return action("answer_question", source_id=source["source_id"], quote="17 June 2019")

    provider = Provider(choose)
    client = client_for(provider)
    state = state_for(
        "Ask about passport replacement.",
        details=[{"label": "Passport issue date", "value": "17 June 2019"}],
    )
    try:
        for _ in range(2):
            heard = "When was your passport issued?"
            state.observe_receiver(heard)
            decision = await Brain(client).reply(state, heard)
            assert "17 June 2019" in decision.say
            assert decision.follow_up is None and not decision.done
            state.exchanges.append(Exchange(heard, decision.say))
    finally:
        await client.aclose()


@pytest.mark.parametrize("quote", ["Grease caused the blockage", "I agree to the 40 credit fee"])
async def test_model_cannot_invent_cause_or_convert_receiver_quote_to_consent(quote: str) -> None:
    def choose(prompt: dict) -> dict:
        source = source_with(prompt, "blocked drain")
        return action("answer_question", source_id=source["source_id"], quote=quote)

    provider = Provider(choose)
    client = client_for(provider)
    try:
        decision = await Brain(client).reply(
            state_for("Ask a plumber about a blocked drain."),
            "The inspection fee is 40 credits. Do you accept the charge?",
        )
        assert decision.follow_up is not None
        assert quote not in decision.say
        assert not decision.done
    finally:
        await client.aclose()


async def test_receiver_fee_is_not_an_approved_consent_source() -> None:
    provider = Provider(
        lambda prompt: action(
            "answer_question",
            source_id=prompt["current_receiver_turn"]["source_id"],
            quote="The inspection fee is 40 credits.",
        )
    )
    client = client_for(provider)
    try:
        decision = await Brain(client).reply(
            state_for("Ask what a drain inspection costs."),
            "The inspection fee is 40 credits. Do you accept the charge?",
        )
        assert decision.follow_up is not None and not decision.done
        assert "40" not in decision.say
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    ("goal", "heard", "finished"),
    [
        ("Register my passport replacement request.", "I can log the passport request.", False),
        ("Register my passport replacement request.", "Your library request is registered.", False),
        (
            "Register my passport replacement request.",
            "Your passport request was registered last year.",
            False,
        ),
        ("Register my passport replacement request.", "Your passport request is registered.", True),
        ("Ask what the passport fee is.", "Your library request is registered.", False),
        ("Ask what the passport fee is.", "The passport fee is 40 credits.", True),
    ],
)
async def test_finish_requires_relevant_completed_evidence(goal, heard, finished) -> None:
    provider = Provider(lambda prompt: action("finish", resolutions=[resolution(prompt)]))
    client = client_for(provider)
    try:
        decision = await Brain(client).reply(state_for(goal), heard)
        assert decision.done is finished
        assert not decision.callback
    finally:
        await client.aclose()


async def test_multi_part_goal_cannot_finish_after_one_answer() -> None:
    provider = Provider(lambda prompt: action("finish", resolutions=[resolution(prompt)]))
    client = client_for(provider)
    state = state_for("Ask when the library opens and what the membership fee is.")
    try:
        first = await Brain(client).reply(state, "The library opens at 9 am.")
        assert not first.done
        assert len(provider.requests[0]["messages"]) == 2
        first_prompt = json.loads(provider.requests[0]["messages"][1]["content"])
        assert len(first_prompt["goals"]) == 2
        state.exchanges.append(Exchange("The library opens at 9 am.", first.say))
        provider.choose = lambda prompt: action("finish", resolutions=[resolution(prompt, 1)])
        second = await Brain(client).reply(state, "The membership fee is 20 credits.")
        assert second.done and not second.callback
    finally:
        await client.aclose()


async def test_old_answer_cannot_override_a_current_correction() -> None:
    old: list[dict] = []

    def choose(prompt: dict) -> dict:
        if not old:
            old.append(resolution(prompt))
            return action("wait", resolutions=old)
        return action("finish", resolutions=old)

    provider = Provider(choose)
    client = client_for(provider)
    state = state_for("Ask what the library membership fee is.")
    try:
        first = await Brain(client).reply(state, "The library membership fee is 20 credits.")
        state.exchanges.append(Exchange("The library membership fee is 20 credits.", first.say))
        corrected = await Brain(client).reply(
            state, "Correction, the membership fee is not confirmed yet."
        )
        assert not corrected.done
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    ("goal", "heard", "finished"),
    [
        (
            "I'd like to order a replacement passport after losing it abroad",
            "You can apply online for a replacement passport.",
            False,
        ),
        (
            "I'd like to order a replacement passport after losing it abroad",
            "Your replacement passport order has been registered.",
            True,
        ),
        (
            "Ask how to order a replacement passport after losing it abroad",
            "You can apply online for a replacement passport.",
            True,
        ),
        ("Ask whether the plumber visits on weekends.", "No, we only visit weekdays.", True),
        (
            "Ask where passport collection is available.",
            "You can collect the passport at the counter.",
            True,
        ),
        ("Register my passport replacement request.", "Okay then we can", False),
        ("Register my passport replacement request.", "Okay then good we can log in", False),
    ],
)
async def test_natural_goals_distinguish_completed_work_from_information(goal, heard, finished):
    provider = Provider(lambda prompt: action("finish", resolutions=[resolution(prompt)]))
    client = client_for(provider)
    try:
        decision = await Brain(client).reply(state_for(goal), heard)
        assert decision.done is finished
        assert not decision.callback
    finally:
        await client.aclose()


@pytest.mark.parametrize(
    ("goal", "question"),
    [
        (
            "I'd like to order a replacement passport after losing it abroad",
            "okay when did they get their old passport",
        ),
        (
            "I'd like to order a replacement passport after losing it abroad",
            "When did you lose the passport?",
        ),
        ("Ask a plumber about repairing a pipe.", "How did the pipe get damaged?"),
    ],
)
async def test_missing_facts_follow_current_question_even_with_an_unrelated_plan(goal, question):
    provider = Provider(lambda _: action("ask_operator", question="What are the next steps?"))
    client = client_for(provider)
    try:
        decision = await Brain(client).reply(state_for(goal), question)
        assert decision.follow_up == question
        assert not decision.done
        assert "next steps" not in decision.say
    finally:
        await client.aclose()


async def test_attached_document_is_quoted_exactly_and_can_be_repeated():
    exact = "Category: replacement (lost abroad)."
    provider = Provider(lambda _: action("answer_question", source_id="document:0", quote=exact))
    client = client_for(provider)
    state = state_for(
        "Ask how to order a replacement passport.",
        documents=[{"name": "Synthetic form", "text": exact}],
    )
    try:
        for _ in range(2):
            state.observe_receiver("Which category is printed on the form?")
            decision = await Brain(client).reply(state, "Which category is printed on the form?")
            assert decision.say == exact
            assert decision.follow_up is None and not decision.done
    finally:
        await client.aclose()


async def test_long_history_retains_resolved_goal_and_asks_only_outstanding_question():
    def choose(prompt):
        if len(provider.requests) == 1:
            return action(
                "ask_operator",
                question="Which documents are required?",
                resolutions=[resolution(prompt)],
            )
        assert prompt["goals"][0]["evidence"]["text"] == "The passport fee is 40 credits."
        assert prompt["goals"][1]["evidence"] is None
        return action("ask_operator", question="Which documents are required?")

    provider = Provider(choose)
    client = client_for(provider)
    state = state_for("Ask what the passport fee is and which documents are required.")
    try:
        first = await Brain(client).reply(state, "The passport fee is 40 credits.")
        state.exchanges.append(Exchange("The passport fee is 40 credits.", first.say))
        for index in range(12):
            state.observe_receiver(f"Administrative update {index}.")
            state.exchanges.append(Exchange(f"Administrative update {index}.", "Thank you."))
        decision = await Brain(client).reply(state, "I am ready to continue.")
        assert decision.say == "Which documents are required?"
        assert not decision.done
    finally:
        await client.aclose()


async def test_completed_goal_can_close_when_operator_asks_anything_else():
    provider = Provider(lambda prompt: action("wait", resolutions=[resolution(prompt)]))
    client = client_for(provider)
    state = state_for("Ask what the passport fee is.")
    try:
        await Brain(client).reply(state, "The passport fee is 40 credits.")
        provider.choose = lambda _: action("finish")
        decision = await Brain(client).reply(state, "Anything else?")
        assert decision.done and not decision.callback
        assert decision.follow_up is None
    finally:
        await client.aclose()


async def test_extended_partial_question_supersedes_partial_pending_question():
    provider = Provider(lambda _: action("need_caller"))
    client = client_for(provider)
    state = state_for("Ask about replacing a lost passport.")
    try:
        await Brain(client).reply(state, "When did you")
        complete = "When did you lose the passport?"
        decision = await Brain(client).reply(state, complete)
        assert decision.follow_up == complete
        assert list(state.planner.pending.values()) == [complete]
        state.caller_question_by_turn["synthetic-send"] = state.planner.current_question_turn
        state.delivered_caller_reply("synthetic-send", "Yesterday.")
        assert not state.planner.pending
    finally:
        await client.aclose()


@pytest.mark.parametrize("interruption", ["new_caption", "delivered_reply"])
def test_new_caption_or_delivered_reply_invalidates_in_flight_planner(interruption):
    import asyncio
    import threading

    from app.protocol import SayMessage

    started, release = threading.Event(), threading.Event()
    prompts = []

    async def delayed(request):
        body = json.loads(request.content)
        prompt = json.loads(body["messages"][1]["content"])
        prompts.append(prompt)
        if len(prompts) == 1:
            started.set()
            while not release.is_set():
                await asyncio.sleep(0.001)
            selected = action("need_caller")
        elif interruption == "new_caption":
            selected = action("need_caller")
        else:
            assert not prompt["pending_receiver_questions"]
            assert any(
                s["source_id"].startswith("caller:") and s["text"] == "Yesterday."
                for s in prompt["approved_sources"]
            )
            selected = action("ask_operator", question="What are the next steps?")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(selected)}, "finish_reason": "stop"}]
            },
        )

    client = client_for(delayed)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client, timeout_s=3))
        call_id = start_general(
            f, "I'd like to order a replacement passport after losing it abroad"
        )
        with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
            f.receive(ws)
            f.live(call_id)
            f.speak_last(call_id)
            result, errors = [], []

            def listen():
                try:
                    result.append(f.listen_turn(call_id, "When did you lose the passport?"))
                except BaseException as error:
                    errors.append(error)

            worker = threading.Thread(target=listen)
            worker.start()
            try:
                assert started.wait(2)
                if interruption == "new_caption":
                    latest = "Where did you lose the passport?"
                    f.client.portal.call(f.manager.record_caption, call_id, latest)
                else:
                    session = f.manager._sessions[call_id]
                    f.client.portal.call(
                        f.manager._on_say, session, SayMessage(type="say", text="Yesterday.")
                    )
                    assert f.speak_last(call_id) == "Yesterday."
                release.set()
                worker.join(timeout=4)
                assert not worker.is_alive() and not errors
                assert len(prompts) == 2
                if interruption == "new_caption":
                    assert prompts[-1]["current_receiver_turn"]["text"] == latest
                    assert f.drain_until(ws, "follow_up")["text"] == latest
                else:
                    assert result == ["What are the next steps?"]
                    assert not f.manager._sessions[call_id].delegate.follow_ups
            finally:
                release.set()
                worker.join(timeout=4)
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] != "done"
        if interruption == "delivered_reply":
            assert not notes["follow_ups"]
            assert any("Yesterday." in line for line in notes["summary"])


@pytest.mark.parametrize("blocked", [False, True])
def test_http_completed_request_and_blocked_request_have_honest_notes(blocked):
    def choose(prompt):
        return action(
            "finish", blocked=blocked, resolutions=[] if blocked else [resolution(prompt)]
        )

    provider = Provider(choose)
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_general(
            f, "I'd like to order a replacement passport after losing it abroad"
        )
        f.live(call_id)
        f.speak_last(call_id)
        heard = (
            "We cannot register the replacement passport without a police report."
            if blocked
            else "Your replacement passport order has been registered."
        )
        spoken = f.listen_turn(call_id, heard)
        assert "I have registered" not in spoken
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] == ("unclear" if blocked else "done")
        assert any(entry["text"] == heard for entry in notes["transcript"])


async def test_document_paraphrase_cannot_be_spoken_as_an_exact_source_answer():
    provider = Provider(
        lambda _: action(
            "answer_question", source_id="document:0", quote="The category is renewal."
        )
    )
    client = client_for(provider)
    try:
        decision = await Brain(client).reply(
            state_for(
                "Ask how to replace a passport.",
                documents=[
                    {"name": "Synthetic form", "text": "Category: replacement (lost abroad)."}
                ],
            ),
            "Which category is printed on the form?",
        )
        assert decision.follow_up == "Which category is printed on the form?"
        assert "renewal" not in decision.say and not decision.done
    finally:
        await client.aclose()


def test_delivered_answer_to_extended_question_clears_partial_follow_up_in_notes():
    provider = Provider(lambda _: action("need_caller"))
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_general(
            f, "I'd like to order a replacement passport after losing it abroad"
        )
        make_caller_present(f, call_id)
        with f.client.websocket_connect(f"/calls/{call_id}/ws", headers=AUTH) as ws:
            f.receive(ws)
            f.live(call_id)
            f.speak_last(call_id)
            for question in ("When did you", "When did you lose the passport?"):
                f.listen_turn(call_id, question)
                assert f.drain_until(ws, "follow_up")["text"] == question
            ws.send_json({"type": "say", "text": "Yesterday."})
            f.drain_until(ws, "status")
            assert f.speak_last(call_id) == "Yesterday."
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["follow_ups"] == []
        assert not any("When did you" in question for question in notes["open_questions"])


@pytest.mark.parametrize("failure", ["schema", "timeout", "budget", "http"])
async def test_replay_cli_never_counts_provider_failure_as_model_quality(failure, capsys):
    import asyncio
    import runpy
    from pathlib import Path

    replay = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/planner_replay.py"))
    run = replay["run"]
    run.__globals__["SCENARIOS"] = (replay["SCENARIOS"][0],)
    client_type = replay["ReplayClient"]
    if failure == "budget":
        run.__globals__["MAX_REQUESTS"] = 0
    elif failure == "timeout":

        async def slow(_self, _request):
            await asyncio.Event().wait()
            raise AssertionError("production deadline should cancel this request")

        client_type.mock = slow
    elif failure == "http":
        client_type.mock = lambda _self, _request: httpx.Response(
            503, json={"error": "synthetic provider detail must stay private"}
        )
    else:
        client_type.mock = lambda _self, _request: httpx.Response(
            200, json={"choices": [{"message": {"content": "not json"}, "finish_reason": "stop"}]}
        )
    assert await run(False) == 1
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows[1]["pass"] is False
    assert rows[1]["rejection"] == failure
    assert rows[-1]["model_requests"] <= 12
    assert rows[-1]["evidence"] == "mock_contract_only"
    if failure in {"schema", "http"}:
        assert rows[1]["diagnostic"]["http_status"] == (503 if failure == "http" else 200)


@pytest.mark.parametrize("wrong_action", ["answer_question", "finish", "wait"])
async def test_replay_quality_rejects_safe_but_useless_actions_for_outstanding_goal(
    wrong_action, capsys
):
    import runpy
    from pathlib import Path

    replay = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/planner_replay.py"))
    run = replay["run"]
    original = replay["SCENARIOS"][-1]
    run.__globals__["SCENARIOS"] = (
        replay["Scenario"](original.name, original.goal, original.steps[:1]),
    )

    def wrong(_self, request):
        prompt = json.loads(json.loads(request.content)["messages"][1]["content"])
        values = {}
        if wrong_action == "answer_question":
            values = {"source_id": "request", "quote": prompt["caller_goal"]}
        elif wrong_action == "finish":
            values = {"resolutions": [resolution(prompt)]}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                bind_question_action(prompt, action(wrong_action, **values))
                            )
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    replay["ReplayClient"].mock = wrong
    assert await run(False) == 1
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows[1]["pass"] is False
    assert rows[1]["rejection"] == "unexpected_action"
    assert rows[1]["model_quality"] is True


async def test_replay_private_capture_excludes_request_and_uses_private_permissions(
    tmp_path, capsys
):
    import runpy
    from pathlib import Path

    replay = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/planner_replay.py"))
    run = replay["run"]
    run.__globals__["SCENARIOS"] = (replay["SCENARIOS"][0],)
    directory = tmp_path / "private-capture"
    assert await run(False, directory) == 0
    capture = directory / "response-01.json"
    assert directory.stat().st_mode & 0o777 == 0o700
    assert capture.stat().st_mode & 0o777 == 0o600
    captured = capture.read_text()
    assert "synthetic-key" not in captured and "Authorization" not in captured
    assert "messages" not in captured and "Bearer" not in captured
    assert "need_caller" in captured
    output = capsys.readouterr().out
    assert "synthetic-key" not in output
    assert "old passport" not in output


def test_replay_private_capture_refuses_repository_paths():
    import runpy
    from pathlib import Path

    repository = Path(__file__).resolve().parents[2]
    replay = runpy.run_path(str(repository / "scripts/planner_replay.py"))
    target = repository / "replay-capture-must-not-be-created"
    with pytest.raises(ValueError, match="outside the repository"):
        replay["prepare_capture"](target)
    assert not target.exists()


@pytest.mark.parametrize(
    ("quote", "passed"),
    [
        ("replacement (lost abroad)", True),
        ("replacement (lost abroad).", True),
        ("Category: replacement (lost abroad).", True),
        ("Category: replacement (lost abroad)", True),
        ("collection at counter", False),
        ("Delivery method: collection at counter.", False),
        ("lost abroad", False),
    ],
)
async def test_replay_document_oracle_accepts_complete_requested_field_only(quote, passed, capsys):
    import runpy
    from pathlib import Path

    replay = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/planner_replay.py"))
    run = replay["run"]
    scenario = next(s for s in replay["SCENARIOS"] if s.name == "document_repeat")
    run.__globals__["SCENARIOS"] = (scenario,)

    def selected_quote(_self, request):
        prompt = json.loads(json.loads(request.content)["messages"][1]["content"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                bind_question_action(
                                    prompt,
                                    action("answer_question", source_id="document:0", quote=quote),
                                )
                            )
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    replay["ReplayClient"].mock = selected_quote
    assert await run(False) == (0 if passed else 1)
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert all(row["pass"] is passed for row in rows[1:-1])
    if not passed:
        assert all(
            row["rejection"] in {"wrong_document_field", "action_guard"} for row in rows[1:-1]
        )


@pytest.mark.parametrize("interval", [-1, 30.1, float("nan"), float("inf")])
async def test_replay_rejects_out_of_range_pacing_before_any_provider_request(interval):
    import runpy
    from pathlib import Path

    replay = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/planner_replay.py"))
    with pytest.raises(ValueError, match="between 0 and 30"):
        await replay["run"](False, interval_seconds=interval)


async def test_replay_paces_before_starting_production_brain(monkeypatch, capsys):
    import runpy
    from pathlib import Path

    replay = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/planner_replay.py"))
    run = replay["run"]
    run.__globals__["SCENARIOS"] = (replay["SCENARIOS"][0],)
    events = []
    original_brain = replay["Brain"]

    async def pause(seconds):
        events.append(("pause", seconds))

    class ObservedBrain(original_brain):
        async def reply(self, *args):
            events.append(("brain", self.timeout_s))
            return await super().reply(*args)

    monkeypatch.setattr(replay["asyncio"], "sleep", pause)
    run.__globals__["Brain"] = ObservedBrain
    assert await run(False, interval_seconds=12) == 0
    assert events == [("pause", 12), ("brain", original_brain(None).timeout_s)]
    capsys.readouterr()


async def test_replay_external_offer_accepts_context_but_rejects_false_model_finish(capsys):
    import runpy
    from pathlib import Path

    replay = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/planner_replay.py"))
    run = replay["run"]
    scenario = next(s for s in replay["SCENARIOS"] if s.name == "autonomous_order")
    run.__globals__["SCENARIOS"] = (scenario,)
    assert await run(False) == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows[1]["action"] == "accept_offer"
    assert rows[1]["status"] == "open"
    assert rows[1]["closed"] is False
    assert rows[1]["pass"] is True
    assert rows[2]["action"] == "finish"
    assert rows[2]["status"] == "done"
    assert rows[2]["pass"] is True
    run.__globals__["SCENARIOS"] = (
        replay["Scenario"](
            scenario.name, scenario.goal, scenario.steps[:1], caller_available=False
        ),
    )

    def wrong_finish(_self, request):
        prompt = json.loads(json.loads(request.content)["messages"][1]["content"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                action("finish", resolutions=[resolution(prompt)])
                            )
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    replay["ReplayClient"].mock = wrong_finish
    assert await run(False) == 1
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows[1]["action"] == "finish"
    assert rows[1]["status"] != "done"
    assert rows[1]["pass"] is False
    assert rows[1]["rejection"] == "unexpected_action"


def accept_current_offer(prompt: dict) -> dict:
    current = prompt["current_receiver_turn"]
    return action(
        "accept_offer",
        goal_id=prompt["goals"][0]["goal_id"],
        source_id=current["source_id"],
        quote=current["text"],
    )


def test_unattended_authorized_offer_waits_for_actual_confirmation_before_done_notes():
    def choose(prompt):
        if len(provider.requests) == 1:
            return accept_current_offer(prompt)
        return action("finish", resolutions=[resolution(prompt)])

    provider = Provider(choose)
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_general(
            f, "I'd like to order a replacement passport after losing it abroad"
        )
        f.live(call_id)
        f.speak_last(call_id)
        first = f.listen_turn(call_id, "I can register the replacement passport order.")
        assert first and "registered" not in first.lower()
        assert f.manager._sessions[call_id].delegate.outcome is None
        assert not f.manager._sessions[call_id].delegate.planner.completed
        confirmation = "Your replacement passport order has been registered."
        f.listen_turn(call_id, confirmation)
        assert f.manager._sessions[call_id].delegate.planner.completed
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] == "done"
        assert notes["stepped_in"] == 0
        assert any(entry["text"] == confirmation for entry in notes["transcript"])


def test_absent_caller_missing_essential_fact_closes_with_honest_follow_up_notes():
    provider = Provider(lambda _: action("need_caller"))
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_general(
            f, "I'd like to order a replacement passport after losing it abroad"
        )
        f.live(call_id)
        f.speak_last(call_id)
        question = "When was the passport issued?"
        f.listen_turn(call_id, question)
        delegate = f.manager._sessions[call_id].delegate
        assert delegate.outcome == "unclear"
        assert not delegate.planner.completed
        assert delegate.follow_ups == [question]
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] == "unclear"
        assert notes["follow_ups"] == [question]
        assert not any("promised to call back" in line for line in notes["open_questions"])


async def test_unattended_generic_permission_cannot_accept_retained_unapproved_fee():
    provider = Provider(accept_current_offer)
    client = client_for(provider)
    state = state_for("I'd like to order a replacement passport after losing it abroad")
    state.caller_available = False
    state.observe_receiver("Registering the replacement passport costs 40 credits.")
    heard = "Should I register the replacement passport order?"
    try:
        decision = await Brain(client).reply(state, heard)
        assert decision.kind != "accept"
        assert decision.follow_up == heard
        assert decision.done and not state.planner.completed
    finally:
        await client.aclose()


async def test_information_only_appointment_fee_goal_cannot_authorize_booking():
    provider = Provider(accept_current_offer)
    client = client_for(provider)
    state = state_for("Ask what the appointment fee is.")
    state.caller_available = False
    try:
        decision = await Brain(client).reply(state, "I can book an appointment for you.")
        assert decision.kind != "accept"
        assert not state.planner.completed
        assert "Yes" not in decision.say
    finally:
        await client.aclose()


async def test_replay_current_confirmation_requires_resolution_before_success(capsys):
    import runpy
    from pathlib import Path

    replay = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/planner_replay.py"))
    run = replay["run"]
    scenario = next(s for s in replay["SCENARIOS"] if s.name == "autonomous_order")
    run.__globals__["SCENARIOS"] = (
        replay["Scenario"](
            scenario.name, scenario.goal, scenario.steps[-1:], caller_available=False
        ),
    )
    replay["ReplayClient"].mock = lambda _self, _request: httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"content": json.dumps(action("finish"))}, "finish_reason": "stop"}
            ]
        },
    )
    assert await run(False) == 1
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows[1]["action"] == "finish"
    assert rows[1]["pass"] is False
    assert rows[1]["status"] != "done"


async def test_replay_reports_application_failure_without_raw_exception_details(capsys):
    import runpy
    from pathlib import Path

    replay = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/planner_replay.py"))
    run = replay["run"]
    run.__globals__["SCENARIOS"] = (replay["SCENARIOS"][0],)

    class BrokenBrain(replay["Brain"]):
        async def reply(self, *_args):
            raise RuntimeError("synthetic exception detail must stay private")

    run.__globals__["Brain"] = BrokenBrain
    assert await run(False) == 1
    output = capsys.readouterr().out
    rows = [json.loads(line) for line in output.splitlines()]
    assert rows[1]["pass"] is False
    assert rows[1]["rejection"] == "application_error"
    assert rows[1]["diagnostic"]["error_type"] == "RuntimeError"
    assert "synthetic exception detail" not in output


def test_operation_permission_question_is_not_a_greeting():
    def choose(prompt):
        current = prompt["current_receiver_turn"]
        assert current["expects_reply"] is True
        return action(
            "accept_offer", goal_id="goal:0", source_id=current["source_id"], quote=current["text"]
        )

    provider = Provider(choose)
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        cid = start_general(f, "Register my replacement passport request.")
        f.live(cid)
        f.speak_last(cid)
        if not f.manager._sessions[cid].delegate.opened:
            f.listen_turn(cid, "Hello, how can I help?")
        spoken = f.listen_turn(
            cid, "I can register the replacement passport request. Shall I go ahead?"
        )
        assert len(provider.requests) == 1
        assert spoken == "Yes, please proceed with the caller's request."
        state = f.manager._sessions[cid].delegate
        assert state.planner.goals[0].accepted_offer is not None
        assert not state.planner.completed and state.outcome is None


# This is the inline label/value layout returned by PDFKit, with synthetic identities.
CLINICAL_REPORT = """Demonstration Clinic
Patient health summary
Patient
Name: Test Caller
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


def start_clinical(f: Flow, *, mode="steer", attended=False, request=None) -> str:
    response = f.client.post(
        "/briefs",
        json={
            "purpose": "general",
            "profile": {
                "name": "Test Caller",
                "documents": [{"name": "Synthetic health report", "text": CLINICAL_REPORT}],
            },
            "request": request or "Book an appointment with the doctor in the attached report.",
        },
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    response = f.client.post(
        "/calls",
        json={
            "contact_id": "clinic",
            "purpose": "general",
            "mode": mode,
            "attended": attended,
            "brief_id": response.json()["brief_id"],
        },
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    call_id = response.json()["call_id"]
    f.live(call_id)
    f.speak_last(call_id)
    f.manager._sessions[call_id].delegate.opened = True
    return call_id


@pytest.mark.parametrize(
    ("heard", "quote", "required"),
    [
        ("What is the patient's registration number?", "Patient ID: DEMO-2714", ("DEMO-2714",)),
        ("What is the doctor's name?", "Doctor: Dr. Nisha Shah, General Medicine", ("Nisha Shah",)),
        (
            "Can you tell me if they had any allergy or what was the blood pressure "
            "at their last checkup?",
            ("Allergies: Penicillin", "Last visit: 12 August 2026 · BP 138/88 mmHg"),
            ("Penicillin", "138/88"),
        ),
    ],
)
@pytest.mark.parametrize("mode", ["steer", "delegated"])
def test_pdfkit_clinical_facts_survive_real_http_path(mode, heard, quote, required):
    provider = Provider(
        lambda _: action(
            "answer_question",
            spans=[
                {"source_id": "document:0", "quote": part}
                for part in (quote if isinstance(quote, tuple) else (quote,))
            ],
        )
    )
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_clinical(f, mode=mode)
        spoken = f.listen_turn(call_id, heard)
        assert all(value in spoken for value in required), spoken
        delegate = f.manager._sessions[call_id].delegate
        assert delegate.follow_ups == []
        assert delegate.outcome is None
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["follow_ups"] == []
        assert all(
            any(value in entry["text"] for entry in notes["transcript"]) for value in required
        )


@pytest.mark.parametrize("proposal", ["wait", "need_caller"])
def test_receiver_acknowledgement_does_not_end_unattended_clinical_call(proposal):
    provider = Provider(lambda _: action(proposal))
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_clinical(f)
        f.listen_turn(call_id, "Okay.")
        delegate = f.manager._sessions[call_id].delegate
        assert delegate.outcome is None
        assert delegate.follow_ups == []
        assert not delegate.planner.completed
        assert provider.requests == []


@pytest.mark.parametrize("mode", ["steer", "delegated"])
@pytest.mark.parametrize("present", [True, False])
def test_clinical_document_questions_booking_confirmation_and_notes(mode, present):
    answers = (
        (
            "Does the patient have an allergy and what was the last BP?",
            ("Allergies: Penicillin", "Last visit: 12 August 2026 · BP 138/88 mmHg"),
        ),
        ("Is the patient registered and what is their patient ID?", ("Patient ID: DEMO-2714",)),
        ("What is the doctor's name?", ("Doctor: Dr. Nisha Shah, General Medicine",)),
    )

    def choose(prompt):
        heard = prompt["current_receiver_turn"]["text"]
        for question, parts in answers:
            if heard == question:
                return action(
                    "answer_question",
                    spans=[{"source_id": "document:0", "quote": part} for part in parts],
                )
        if heard.startswith("I can book"):
            return accept_current_offer(prompt)
        return action("finish", resolutions=[resolution(prompt)])

    provider = Provider(choose)
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_clinical(f, mode=mode, attended=present)
        if present and mode == "steer":
            make_caller_present(f, call_id)
        for question, parts in answers:
            spoken = f.listen_turn(call_id, question)
            assert all(part in spoken for part in parts), spoken
        offered = "I can book an appointment with Dr. Nisha Shah. Shall I proceed?"
        spoken = f.listen_turn(call_id, offered)
        delegate = f.manager._sessions[call_id].delegate
        assert spoken and delegate.outcome is None
        assert not delegate.planner.completed
        confirmed = "Your appointment with Dr. Nisha Shah has been booked."
        f.listen_turn(call_id, confirmed)
        assert delegate.planner.completed
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] in {"done", "booked"}
        assert notes["follow_ups"] == []
        assert notes["stepped_in"] == 0
        assert any(entry["text"] == confirmed for entry in notes["transcript"])


@pytest.mark.parametrize("mode", ["steer", "delegated"])
@pytest.mark.parametrize(
    ("question", "quote", "forbidden"),
    [
        ("What is the doctor's name?", "Name: Test Caller", "Test Caller"),
        (
            "What is the patient's registration number?",
            "Last visit: 12 August 2026 · BP 138/88 mmHg",
            "138/88",
        ),
        ("What is the patient's address?", "Demonstration Clinic", "Demonstration Clinic"),
    ],
)
def test_clinical_valid_quote_from_wrong_entity_or_field_cannot_answer(
    mode, question, quote, forbidden
):
    provider = Provider(lambda _: action("answer_question", source_id="document:0", quote=quote))
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_clinical(f, mode=mode)
        spoken = f.listen_turn(call_id, question)
        assert forbidden not in spoken
        delegate = f.manager._sessions[call_id].delegate
        assert not delegate.planner.completed
        assert delegate.follow_ups == [question]
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] != "done"
        assert notes["follow_ups"] == [question]


def test_fragmented_registration_question_can_answer_pending_question_after_ack():
    def choose(prompt):
        if len(provider.requests) == 1:
            return action("wait")
        return action("answer_question", source_id="document:0", quote="Patient ID: DEMO-2714")

    provider = Provider(choose)
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_clinical(f, attended=True)
        make_caller_present(f, call_id)
        f.listen_turn(call_id, "Is the patient registered at the clinic?")
        spoken = f.listen_turn(call_id, "and if so tell me their registration number")
        assert "DEMO-2714" in spoken, spoken
        delegate = f.manager._sessions[call_id].delegate
        assert delegate.follow_ups == []
        assert delegate.planner.pending == {}


async def test_clinical_replay_is_bounded_and_checks_meaning_not_only_valid_json(capsys):
    import runpy
    from pathlib import Path

    replay = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/planner_replay.py"))
    assert await replay["run"](False, suite="clinical") == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows[-1]["pass"] is True
    assert rows[-1]["model_requests"] <= 12
    assert rows[-1]["evidence"] == "mock_contract_only"
    assert all(row["pass"] for row in rows[1:-1])
    assert rows[-1]["model_requests"] == 10
    quiet = next(row for row in rows if row.get("case") == "clinical_acknowledgement")
    assert quiet["action"] == "rules" and quiet["model_quality"] is False
    assert quiet["diagnostic"] == {}


@pytest.mark.parametrize("quote", ["Allergies: Penicillin", "Patient ID: DEMO-2714"])
async def test_clinical_replay_oracle_rejects_partial_compound_or_unrelated_answer(quote, capsys):
    import runpy
    from pathlib import Path

    replay = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/planner_replay.py"))
    original = replay["CLINICAL_SCENARIOS"][0]
    replay["run"].__globals__["CLINICAL_SCENARIOS"] = (
        replay["Scenario"](
            original.name, original.goal, original.steps[:1], document=original.document
        ),
    )

    def partial(_self, request):
        prompt = json.loads(json.loads(request.content)["messages"][1]["content"])
        selected = bind_question_action(
            prompt, action("answer_question", source_id="document:0", quote=quote)
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(selected)}, "finish_reason": "stop"}]
            },
        )

    replay["ReplayClient"].mock = partial
    assert await replay["run"](False, suite="clinical") == 1
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows[1]["pass"] is False
    assert rows[1]["rejection"] in {"wrong_document_field", "action_guard"}


@pytest.mark.parametrize("mode", ["steer", "delegated"])
def test_one_document_fact_does_not_silently_resolve_a_compound_receiver_question(mode):
    provider = Provider(
        lambda _: action(
            "answer_question", spans=[{"source_id": "document:0", "quote": "Allergies: Penicillin"}]
        )
    )
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_clinical(f, mode=mode)
        question = "What are the patient's allergies and the blood pressure at their last checkup?"
        f.listen_turn(call_id, question)
        delegate = f.manager._sessions[call_id].delegate
        assert not delegate.planner.completed
        assert question in delegate.planner.pending.values() or question in delegate.follow_ups
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] != "done"
        assert question in notes["follow_ups"]


def test_stale_answer_question_id_cannot_clear_new_clinical_question():
    def choose(prompt):
        if len(provider.requests) == 1:
            return action("answer_question", source_id="document:0", quote="Patient ID: DEMO-2714")
        return action(
            "answer_question",
            question_id=first_question_id,
            spans=[{"source_id": "document:0", "quote": "Allergies: Penicillin"}],
        )

    provider = Provider(choose)
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_clinical(f, attended=True)
        make_caller_present(f, call_id)
        question = "What is the patient's registration number?"
        assert "DEMO-2714" in f.listen_turn(call_id, question)
        first_prompt = json.loads(provider.requests[0]["messages"][1]["content"])
        first_question_id = next(iter(first_prompt["pending_receiver_questions"]))
        allergy_question = "What allergy does the patient have?"
        spoken = f.listen_turn(call_id, allergy_question)
        assert "Penicillin" not in spoken
        delegate = f.manager._sessions[call_id].delegate
        assert allergy_question in delegate.planner.pending.values()
        assert not delegate.planner.completed


async def test_clinical_http_replay_checks_saved_notes_and_never_uses_telephony(capsys):
    import runpy
    from pathlib import Path

    replay = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/planner_replay.py"))
    assert await replay["run_http"](False) == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows[0]["telephony"] is False
    assert rows[0]["transport"] == "local_http"
    assert rows[-1]["evidence"] == "mock_http_contract_only"
    assert rows[-1]["model_requests"] == 10
    quiet = next(row for row in rows if row.get("case") == "clinical_acknowledgement")
    assert quiet["action"] == "rules" and quiet["model_quality"] is False
    assert quiet["diagnostic"] == {}
    assert all(row["pass"] for row in rows[1:-1])
    assert any(row.get("stage") == "notes" and row["outcome"] == "done" for row in rows)


@pytest.mark.parametrize("failure", ["schema", "http", "budget"])
async def test_clinical_http_replay_cannot_count_guarded_fallback_as_model_quality(failure, capsys):
    import runpy
    from pathlib import Path

    replay = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/planner_replay.py"))
    run = replay["run_http"]
    original = replay["CLINICAL_SCENARIOS"][0]
    run.__globals__["CLINICAL_SCENARIOS"] = (
        replay["Scenario"](
            original.name, original.goal, original.steps[:1], document=original.document
        ),
    )
    if failure == "budget":
        run.__globals__["MAX_REQUESTS"] = 0
    elif failure == "schema":
        replay["ReplayClient"].mock = lambda _self, _request: httpx.Response(
            200, json={"choices": [{"message": {"content": "not json"}, "finish_reason": "stop"}]}
        )
    else:
        replay["ReplayClient"].mock = lambda _self, _request: httpx.Response(
            503, json={"error": "private provider response must not be logged"}
        )
    assert await run(False) == 1
    output = capsys.readouterr().out
    rows = [json.loads(line) for line in output.splitlines()]
    assert rows[1]["pass"] is False
    assert rows[1]["rejection"] == failure
    assert "private provider response" not in output
    assert rows[-1]["model_requests"] <= 12


@pytest.mark.parametrize(
    ("heard", "quote", "required"),
    [
        ("Is the patient allergic to anything?", "Allergies: Penicillin", "Penicillin"),
        (
            "Which tablets is the patient currently taking?",
            "Medication: Amlodipine 5 mg, once a day",
            "Amlodipine",
        ),
        (
            "Who is the patient's treating consultant?",
            "Doctor: Dr. Nisha Shah, General Medicine",
            "Nisha Shah",
        ),
    ],
)
def test_clinical_question_paraphrases_preserve_grounded_model_answer(heard, quote, required):
    provider = Provider(lambda _: action("answer_question", source_id="document:0", quote=quote))
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_clinical(f)
        spoken = f.listen_turn(call_id, heard)
        assert required in spoken, spoken
        delegate = f.manager._sessions[call_id].delegate
        assert delegate.follow_ups == []
        assert delegate.outcome is None


@pytest.mark.parametrize("mode", ["steer", "delegated"])
def test_four_document_facts_are_delivered_in_one_http_turn_without_completing_booking(mode):
    parts = (
        "Patient ID: DEMO-2714",
        "Allergies: Penicillin",
        "Date of birth: 14 March 1994",
        "Medication: Amlodipine 5 mg, once a day",
    )
    provider = Provider(
        lambda _: action(
            "answer_question", spans=[{"source_id": "document:0", "quote": part} for part in parts]
        )
    )
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_clinical(f, mode=mode)
        spoken = f.listen_turn(
            call_id, "Please give the patient's ID, allergies, date of birth and medication."
        )
        assert all(part in spoken for part in parts)
        delegate = f.manager._sessions[call_id].delegate
        assert delegate.follow_ups == [] and delegate.outcome is None
        assert not delegate.planner.completed
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] != "done"
        assert notes["follow_ups"] == []


@pytest.mark.parametrize("mode", ["steer", "delegated"])
def test_http_booking_confirmation_answers_final_question_before_closing_and_saving_done(mode):
    proof = "Your appointment with Dr. Nisha Shah has been booked."

    def choose(prompt):
        return action(
            "answer_question",
            source_id="document:0",
            quote="Allergies: Penicillin",
            resolutions=[resolution(prompt, quote=proof)],
        )

    provider = Provider(choose)
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_clinical(f, mode=mode)
        heard = proof + " What allergies should we note?"
        spoken = f.listen_turn(call_id, heard)
        assert "Allergies: Penicillin" in spoken
        delegate = f.manager._sessions[call_id].delegate
        assert delegate.outcome is None and delegate.planner.completed
        f.listen_turn(call_id, "Thank you.")
        assert delegate.outcome == "done"
        assert len(provider.requests) == 1
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] == "done"
        assert notes["follow_ups"] == []
        assert any(entry["text"] == heard for entry in notes["transcript"])
        assert any("Penicillin" in entry["text"] for entry in notes["transcript"])


def test_http_question_followed_by_hold_still_delivers_known_document_answer():
    provider = Provider(
        lambda _: action("answer_question", source_id="document:0", quote="Allergies: Penicillin")
    )
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_clinical(f)
        spoken = f.listen_turn(call_id, "What allergy does the patient have? Please hold.")
        assert "Penicillin" in spoken and len(provider.requests) == 1
        delegate = f.manager._sessions[call_id].delegate
        assert delegate.follow_ups == [] and delegate.outcome is None


@pytest.mark.parametrize("mode", ["steer", "delegated"])
def test_http_unconstrained_appointment_accepts_routine_fee_and_time_then_finishes(mode):
    def choose(prompt):
        if "Shall I book" in prompt["current_receiver_turn"]["text"]:
            return accept_current_offer(prompt)
        return action("finish", resolutions=[resolution(prompt)])

    provider = Provider(choose)
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_clinical(f, mode=mode)
        offered = (
            "We can book an appointment with Dr. Nisha Shah on Monday at 9 pm "
            "for 800 rupees. Shall I book it?"
        )
        spoken = f.listen_turn(call_id, offered)
        delegate = f.manager._sessions[call_id].delegate
        assert spoken and "caller's input" not in spoken
        assert delegate.follow_ups == [] and delegate.outcome is None
        assert not delegate.planner.completed
        proof = (
            "Your appointment with Dr. Nisha Shah on Monday at 9 pm for 800 rupees has been booked."
        )
        f.listen_turn(call_id, proof)
        assert delegate.planner.completed
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] == "done"
        assert notes["follow_ups"] == [] and notes["stepped_in"] == 0
        assert any(entry["text"] == proof for entry in notes["transcript"])


@pytest.mark.parametrize("constraint", ["The maximum fee is 500 rupees.", "It must be on Tuesday."])
def test_http_explicit_fee_or_day_limit_still_blocks_nonmatching_offer(constraint):
    provider = Provider(accept_current_offer)
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_clinical(
            f, request=("Book an appointment with the doctor in the attached report. " + constraint)
        )
        offered = (
            "We can book an appointment with Dr. Nisha Shah on Monday at 9 pm "
            "for 800 rupees. Shall I book it?"
        )
        spoken = f.listen_turn(call_id, offered)
        delegate = f.manager._sessions[call_id].delegate
        assert "Yes, please proceed" not in spoken
        assert not delegate.planner.completed
        assert delegate.agent_answers == []
        assert delegate.planner.goals[0].accepted_offer is None
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] != "done"


def test_http_autonomy_does_not_invent_unknown_national_identity_number():
    provider = Provider(lambda _: action("need_caller"))
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_general(f, "Order a replacement passport after losing it abroad.")
        f.live(call_id)
        f.speak_last(call_id)
        f.manager._sessions[call_id].delegate.opened = True
        question = "What is the applicant's national identity number?"
        spoken = f.listen_turn(call_id, question)
        delegate = f.manager._sessions[call_id].delegate
        assert not any(character.isdigit() for character in spoken)
        assert delegate.follow_ups == [question]
        assert not delegate.planner.completed
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] != "done" and notes["follow_ups"] == [question]


def choose_current_option(prompt: dict, option: str) -> dict:
    current = prompt["current_receiver_turn"]
    return action(
        "choose_option",
        goal_id=prompt["goals"][0]["goal_id"],
        source_id=current["source_id"],
        quote=current["text"],
        option=option,
    )


@pytest.mark.parametrize("mode", ["steer", "delegated"])
def test_http_agent_selects_ordinary_booklet_then_waits_for_actual_confirmation(mode):
    def choose(prompt):
        if "32-pager" in prompt["current_receiver_turn"]["text"]:
            return choose_current_option(prompt, "32-pager")
        return action("finish", resolutions=[resolution(prompt)])

    provider = Provider(choose)
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_general(
            f, "Order a replacement passport after losing it abroad.", mode=mode
        )
        f.live(call_id)
        f.speak_last(call_id)
        f.manager._sessions[call_id].delegate.opened = True
        offered = "Do you want a 32-pager or a 64-pager?"
        spoken = f.listen_turn(call_id, offered)
        assert "32" in spoken and "64" not in spoken
        delegate = f.manager._sessions[call_id].delegate
        assert delegate.outcome is None and delegate.follow_ups == []
        assert not delegate.planner.completed
        confirmation = "Your replacement passport order has been registered."
        f.listen_turn(call_id, confirmation)
        assert delegate.planner.completed
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] == "done" and notes["follow_ups"] == []
        assert notes["stepped_in"] == 0


@pytest.mark.parametrize(
    ("goal", "heard", "option"),
    [
        (
            "Order a replacement passport after losing it abroad.",
            "We offer a 32-page booklet or a 64-page booklet. Which would you like?",
            "128-page booklet",
        ),
        (
            "Order a replacement passport after losing it abroad.",
            "Is the applicant's national identity number 12345 or 67890?",
            "12345",
        ),
        (
            "Order a replacement passport with a 64-page booklet.",
            "We offer a 32-page booklet or a 64-page booklet. Which would you like?",
            "32-page booklet",
        ),
    ],
)
def test_http_option_autonomy_cannot_invent_options_personal_facts_or_override_preference(
    goal, heard, option
):
    provider = Provider(lambda prompt: choose_current_option(prompt, option))
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_general(f, goal)
        f.live(call_id)
        f.speak_last(call_id)
        f.manager._sessions[call_id].delegate.opened = True
        spoken = f.listen_turn(call_id, heard)
        delegate = f.manager._sessions[call_id].delegate
        assert option not in spoken
        assert not delegate.planner.completed
        assert delegate.planner.goals[0].accepted_offer is None
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] != "done"


@pytest.mark.parametrize("http", [False, True])
async def test_autonomy_replay_is_bounded_and_checks_outcomes_instead_of_only_schema(http, capsys):
    import runpy
    from pathlib import Path

    replay = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/planner_replay.py"))
    run = replay["run_http"] if http else replay["run"]
    assert await run(False, suite="autonomy") == 0
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows[-1]["pass"] is True and rows[-1]["model_requests"] <= 12
    assert all(row["pass"] for row in rows[1:-1])
    assert rows[-1]["model_requests"] >= 7


@pytest.mark.parametrize("mode", ["steer", "delegated"])
def test_http_natural_slot_then_fee_turns_use_active_booking_context_without_extra_user_input(mode):
    def choose(prompt):
        heard = prompt["current_receiver_turn"]["text"]
        if "booked" in heard:
            return action("finish", resolutions=[resolution(prompt)])
        return accept_current_offer(prompt)

    provider = Provider(choose)
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_general(f, "Book with Dr. Rao.", mode=mode)
        f.live(call_id)
        f.speak_last(call_id)
        f.manager._sessions[call_id].delegate.opened = True
        for heard in (
            "We have Monday at 9 pm. Is that okay?",
            "The clinic treatment is ₹800. Shall we proceed?",
        ):
            spoken = f.listen_turn(call_id, heard)
            delegate = f.manager._sessions[call_id].delegate
            assert spoken and "caller's input" not in spoken, spoken
            assert delegate.outcome is None and delegate.follow_ups == []
            assert delegate.agent_answers
            assert not delegate.planner.completed
        proof = "You are booked with Dr. Rao for Monday at 9 pm."
        f.listen_turn(call_id, proof)
        assert delegate.planner.completed
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] == "done" and notes["follow_ups"] == []
        assert notes["stepped_in"] == 0


@pytest.mark.parametrize("mode", ["steer", "delegated"])
def test_http_natural_plumber_access_question_uses_document_and_finishes_after_answer(mode):
    proof = "Your plumber visit to repair the leak is booked."
    provider = Provider(
        lambda prompt: action(
            "answer_question",
            source_id="document:0",
            quote="Access instructions: Use the side gate",
            resolutions=[resolution(prompt, quote=proof)],
        )
    )
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_general(
            f,
            "Arrange a plumber visit to repair the leak.",
            mode=mode,
            documents=[
                {"name": "Visit instructions", "text": "Access instructions: Use the side gate"}
            ],
        )
        f.live(call_id)
        f.speak_last(call_id)
        f.manager._sessions[call_id].delegate.opened = True
        spoken = f.listen_turn(call_id, proof + " How will they get inside?")
        assert "Use the side gate" in spoken, spoken
        delegate = f.manager._sessions[call_id].delegate
        assert delegate.follow_ups == [] and delegate.outcome is None
        f.listen_turn(call_id, "Thank you.")
        assert delegate.outcome == "done" and delegate.planner.completed
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] == "done" and notes["follow_ups"] == []


@pytest.mark.parametrize("http", [False, True])
@pytest.mark.parametrize("explicit", [False, True])
async def test_replay_choice_allows_answer_question_only_for_supplied_preference(
    http, explicit, capsys
):
    import runpy
    from pathlib import Path

    replay = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/planner_replay.py"))
    run = replay["run_http"] if http else replay["run"]
    scenario_name = (
        "autonomy_explicit_booklet_preference" if explicit else "autonomy_passport_booklet_choice"
    )
    scenario = next(item for item in replay["AUTONOMY_SCENARIOS"] if item.name == scenario_name)
    run.__globals__["AUTONOMY_SCENARIOS"] = (scenario,)
    original_mock = replay["ReplayClient"].mock

    def answer_preference(client, request):
        if client.step.expected != "choice":
            return original_mock(client, request)
        prompt = json.loads(json.loads(request.content)["messages"][1]["content"])
        selected = bind_question_action(
            prompt,
            action(
                "answer_question",
                source_id="request",
                quote="64-page booklet" if explicit else "32-pager",
            ),
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(selected)}, "finish_reason": "stop"}]
            },
        )

    replay["ReplayClient"].mock = answer_preference
    assert await run(False, suite="autonomy") == (0 if explicit else 1)
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    first = rows[1]
    assert first["action"] == "answer_question"
    assert first["pass"] is explicit
    assert first["rejection"] == (None if explicit else "unexpected_action")
    if explicit:
        assert all(row["pass"] for row in rows[1:-1])
        assert rows[-1]["pass"] is True
        if http:
            assert any(row.get("stage") == "notes" and row["outcome"] == "done" for row in rows)


@pytest.mark.parametrize("http", [False, True])
@pytest.mark.parametrize("valid_review", [False, True])
async def test_replay_distinguishes_actionless_resolution_review_and_validates_actual_recovery(
    http,
    valid_review,
    capsys,
):
    import runpy
    from pathlib import Path

    replay = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/planner_replay.py"))
    run = replay["run_http"] if http else replay["run"]
    scenario = next(
        item
        for item in replay["AUTONOMY_SCENARIOS"]
        if item.name == "autonomy_confirmation_and_final_question"
    )
    run.__globals__["AUTONOMY_SCENARIOS"] = (scenario,)
    original_mock = replay["ReplayClient"].mock
    protocols = []

    def omit_initial_proof(client, request):
        body = json.loads(request.content)
        properties = body["response_format"]["json_schema"]["schema"]["properties"]
        is_review = set(properties) == {"resolutions"}
        protocols.append("review" if is_review else "planner")
        response = original_mock(client, request)
        envelope = response.json()
        selected = json.loads(envelope["choices"][0]["message"]["content"])
        if not is_review:
            selected["resolutions"] = []
        elif not valid_review:
            # A planner action is not a valid actionless evidence-review response.
            selected["action"] = {"kind": "finish", "blocked": False}
        envelope["choices"][0]["message"]["content"] = json.dumps(selected)
        return httpx.Response(200, json=envelope)

    replay["ReplayClient"].mock = omit_initial_proof
    assert await run(False, suite="autonomy") == (0 if valid_review else 1)
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    closing = next(row for row in rows if row.get("step") == 2)
    assert closing["action"] == "rules"
    assert closing["resolution_review"] is True
    assert closing["model_quality"] is True
    assert closing["pass"] is valid_review
    assert closing["rejection"] == (None if valid_review else "schema")
    assert protocols == ["planner", "review"]
    assert rows[-1]["model_requests"] == 2
    if http and valid_review:
        assert any(row.get("stage") == "notes" and row["outcome"] == "done" for row in rows)


@pytest.mark.parametrize("amount", ["₹1,800", "1,800 rupees", "$1,800.00"])
def test_http_explicit_budget_rejects_grouped_currency_amounts(amount):
    provider = Provider(accept_current_offer)
    client = client_for(provider)
    currency_limit = "$800" if amount.startswith("$") else "₹800"
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_general(
            f, "Order a replacement passport. Pay at most " + currency_limit + "."
        )
        f.live(call_id)
        f.speak_last(call_id)
        f.manager._sessions[call_id].delegate.opened = True
        offered = f"I can register the replacement passport order for {amount}. Shall I proceed?"
        f.listen_turn(call_id, offered)
        delegate = f.manager._sessions[call_id].delegate
        assert delegate.agent_answers == []
        assert not delegate.planner.completed
        assert delegate.planner.goals[0].accepted_offer is None
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] != "done"


def test_http_option_substring_cannot_hide_full_current_turn_price_from_budget_guard():
    def choose(prompt):
        selected = choose_current_option(prompt, "32-pager")
        selected["action"]["quote"] = "A 32-pager or 64-pager"
        return selected

    provider = Provider(choose)
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_general(f, "Order a replacement passport. Pay at most ₹800.")
        f.live(call_id)
        f.speak_last(call_id)
        f.manager._sessions[call_id].delegate.opened = True
        f.listen_turn(call_id, "A 32-pager or 64-pager costs ₹1800. Which booklet would you like?")
        delegate = f.manager._sessions[call_id].delegate
        assert delegate.agent_answers == []
        assert not delegate.planner.completed
        assert delegate.planner.goals[0].accepted_offer is None
        f.finish()
        notes = f.client.get(f"/calls/{call_id}/notes", headers=AUTH).json()
        assert notes["outcome"] != "done"


@pytest.mark.parametrize(
    ("question", "option"),
    [
        ("Are you allergic to penicillin or latex?", "penicillin"),
        ("Is the patient a new or existing customer?", "new"),
    ],
)
def test_http_unknown_personal_facts_are_not_autonomous_operational_choices(question, option):
    provider = Provider(lambda prompt: choose_current_option(prompt, option))
    client = client_for(provider)
    with contextlib.ExitStack() as stack:
        f = build_flow(stack, brain=Brain(client))
        call_id = start_general(f, "Book with Dr. Rao.")
        f.live(call_id)
        f.speak_last(call_id)
        f.manager._sessions[call_id].delegate.opened = True
        spoken = f.listen_turn(call_id, question)
        delegate = f.manager._sessions[call_id].delegate
        assert option not in spoken
        assert delegate.agent_answers == []
        assert not delegate.planner.completed
        assert delegate.planner.goals[0].accepted_offer is None


@pytest.mark.parametrize("http", [False, True])
@pytest.mark.parametrize("request_cap", [1, 12])
async def test_replay_semantic_choice_encoding_repair_uses_same_transport_budget(
    http, request_cap, capsys
):
    import runpy
    from pathlib import Path

    replay = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/planner_replay.py"))
    run = replay["run_http"] if http else replay["run"]
    original = next(
        item
        for item in replay["AUTONOMY_SCENARIOS"]
        if item.name == "autonomy_passport_booklet_choice"
    )
    scenario = replay["Scenario"](
        original.name,
        original.goal,
        original.steps if request_cap == 12 else original.steps[:1],
        caller_available=False,
    )
    run.__globals__["AUTONOMY_SCENARIOS"] = (scenario,)
    run.__globals__["MAX_REQUESTS"] = request_cap
    original_mock = replay["ReplayClient"].mock
    feedback_seen = []

    def wrong_encoding_then_repair(client, request):
        prompt = json.loads(json.loads(request.content)["messages"][1]["content"])
        feedback_seen.append("validation_feedback" in prompt)
        response = original_mock(client, request)
        if client.step.expected == "choice" and "validation_feedback" not in prompt:
            selected = bind_question_action(
                prompt,
                action(
                    "answer_question",
                    source_id="request",
                    quote="32-pager",
                ),
            )
            envelope = response.json()
            envelope["choices"][0]["message"]["content"] = json.dumps(selected)
            return httpx.Response(200, json=envelope)
        return response

    replay["ReplayClient"].mock = wrong_encoding_then_repair
    assert await run(False, suite="autonomy") == (0 if request_cap == 12 else 1)
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert rows[-1]["model_requests"] == (3 if request_cap == 12 else 1)
    assert rows[-1]["model_requests"] <= request_cap
    if request_cap == 12:
        assert feedback_seen == [False, True, False]
        assert rows[1]["action"] == "choose_option" and rows[1]["pass"] is True
        assert all(row["pass"] for row in rows[1:-1])
        if http:
            assert any(row.get("stage") == "notes" and row["outcome"] == "done" for row in rows)
    else:
        assert feedback_seen == [False]
        assert rows[1]["pass"] is False and rows[1]["rejection"] == "budget"


@pytest.mark.parametrize("http", [False, True])
@pytest.mark.parametrize("proof_state", ["valid", "missing", "wrong_source"])
async def test_replay_separates_verified_runtime_close_from_stale_model_action(
    http, proof_state, capsys
):
    import runpy
    from pathlib import Path

    replay = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/planner_replay.py"))
    run = replay["run_http"] if http else replay["run"]
    scenario = next(item for item in replay["SCENARIOS"] if item.name == "autonomous_order")
    run.__globals__["AUTONOMY_SCENARIOS"] = (scenario,)
    original_mock = replay["ReplayClient"].mock

    def stale_action(client, request):
        response = original_mock(client, request)
        if client.step.expected != "done":
            return response
        prompt = json.loads(json.loads(request.content)["messages"][1]["content"])
        envelope = response.json()
        selected = json.loads(envelope["choices"][0]["message"]["content"])
        selected["action"] = accept_current_offer(prompt)["action"]
        if proof_state == "missing":
            selected["resolutions"] = []
        elif proof_state == "wrong_source":
            selected["resolutions"][0]["source_id"] = "receiver:invented"
        envelope["choices"][0]["message"]["content"] = json.dumps(selected)
        return httpx.Response(200, json=envelope)

    replay["ReplayClient"].mock = stale_action
    valid = proof_state == "valid"
    assert await run(False, suite="autonomy") == (0 if valid else 1)
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    closing = next(row for row in rows if row.get("step") == 2)
    assert closing["action"] == "accept_offer"
    assert closing["pass"] is valid
    assert closing["action_correction"] == ("closed_from_verified_resolutions" if valid else None)
    assert closing["model_rejection"] == "unexpected_action"
    if valid:
        assert closing["model_quality"] is False
        assert closing["rejection"] is None
        if http:
            assert any(row.get("stage") == "notes" and row["outcome"] == "done" for row in rows)
    else:
        assert closing["rejection"] == "unexpected_action"
    assert rows[-1]["corrected_model_actions"] == int(valid)
    assert rows[-1]["model_requests"] == 2
