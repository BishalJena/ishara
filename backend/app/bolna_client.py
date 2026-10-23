"""HTTP client for the Bolna API (implements ports.BolnaClient).

Errors carry only the operation and HTTP status: Bolna's error bodies can contain
account identifiers, and the API key must never reach a message or log.
"""

from __future__ import annotations

import re
from typing import Any

import httpx
from pydantic import SecretStr

DEFAULT_BASE_URL = "https://api.bolna.ai"
_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")


class BolnaError(Exception):
    def __init__(self, status_code: int | None, operation: str, reason: str = "failed") -> None:
        self.status_code = status_code
        self.operation = operation
        status = f"HTTP {status_code}" if status_code is not None else "no response"
        super().__init__(f"Bolna {operation} {reason} ({status})")


def _path_id(value: str) -> str:
    if not _ID.fullmatch(value):
        raise ValueError("Bolna ids are UUID-like strings")
    return value


def _json(operation: str, response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        raise BolnaError(response.status_code, operation, "returned no JSON object")
    return body


def _json_field(operation: str, response: httpx.Response, field: str) -> str:
    value = _json(operation, response).get(field)
    if not isinstance(value, str) or not value:
        raise BolnaError(response.status_code, operation, f"returned no {field}")
    return value


class HttpBolnaClient:
    def __init__(
        self,
        api_key: SecretStr,
        agent_id: str | None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self._agent_id = agent_id
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
            timeout=httpx.Timeout(timeout_s),
            follow_redirects=False,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> HttpBolnaClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def _request(
        self, operation: str, method: str, path: str, body: dict[str, Any] | None = None
    ) -> httpx.Response:
        try:
            response = await self._http.request(method, path, json=body)
        except httpx.TransportError as exc:
            raise BolnaError(None, operation) from exc
        if not response.is_success:
            raise BolnaError(response.status_code, operation)
        return response

    async def start_call(self, recipient: str, user_data: dict[str, str]) -> str:
        """`POST /call` from the account's default number (no `from_phone_number`)."""
        if not self._agent_id:
            raise ValueError("BOLNA_AGENT_ID is not set")
        body = {
            "agent_id": self._agent_id,
            "recipient_phone_number": recipient,
            "user_data": user_data,
        }
        response = await self._request("start_call", "POST", "/call", body)
        # Bolna returns `execution_id`; the events endpoint calls the same value run_id.
        return _json_field("start_call", response, "execution_id")

    async def send_event(self, run_id: str, event: str, properties: dict[str, str]) -> None:
        path = f"/v1/call/{_path_id(run_id)}/events"
        await self._request("send_event", "POST", path, {"event": event, "properties": properties})

    async def create_agent(self, payload: dict[str, Any]) -> str:
        response = await self._request("create_agent", "POST", "/v2/agent", payload)
        return _json_field("create_agent", response, "agent_id")

    async def update_agent(self, agent_id: str, payload: dict[str, Any]) -> None:
        await self._request("update_agent", "PUT", f"/v2/agent/{_path_id(agent_id)}", payload)

    async def get_agent(self, agent_id: str) -> dict[str, Any]:
        response = await self._request("get_agent", "GET", f"/v2/agent/{_path_id(agent_id)}")
        return _json("get_agent", response)

    async def register_custom_model(
        self, name: str, base_url: str, key: SecretStr, family: str
    ) -> None:
        """`POST /user/model/custom`: Bolna stores `key` and sends it as our bearer token."""
        body = {
            "custom_model_name": name,
            "custom_model_url": base_url,
            "custom_model_key": key.get_secret_value(),
            "custom_model_family": family,
        }
        await self._request("register_custom_model", "POST", "/user/model/custom", body)
