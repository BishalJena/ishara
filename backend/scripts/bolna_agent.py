"""Render the Bolna graph agent, or register/create/update it on the real Bolna API.

    uv run python -m scripts.bolna_agent render                # no network
    uv run python -m scripts.bolna_agent register-llm --yes    # custom LLM model
    uv run python -m scripts.bolna_agent create --yes          # prints the new agent id
    uv run python -m scripts.bolna_agent update --yes          # replaces BOLNA_AGENT_ID's config

Write commands refuse to run without --yes and the env names they need. They print
only ids and names, never keys, the webhook URL (it holds a secret) or Bolna responses.
`create`/`update` point the agent's status webhook at our /bolna/webhook/<token> route
unless --webhook-url is given; without it the backend only learns the call connected
from the first caption, and SEND is refused until then.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import cast

import httpx
from pydantic import SecretStr

from app.bolna_agent import (
    CUSTOM_LLM_FAMILY,
    CUSTOM_LLM_MODEL,
    PLACEHOLDER_PUBLIC_BASE_URL,
    build_agent_payload,
    custom_llm_base_url,
    render_agent_json,
)
from app.bolna_client import BolnaError, HttpBolnaClient
from app.config import Settings, get_settings
from app.markers import WEBHOOK_PATH

REQUIRED_ENV = {
    "register-llm": ("PUBLIC_BASE_URL", "BOLNA_API_KEY", "CUSTOM_LLM_TOKEN"),
    "create": ("PUBLIC_BASE_URL", "BOLNA_API_KEY", "CUSTOM_LLM_TOKEN"),
    "update": ("PUBLIC_BASE_URL", "BOLNA_API_KEY", "BOLNA_AGENT_ID", "CUSTOM_LLM_TOKEN"),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bolna_agent", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    render = commands.add_parser("render", help="print the agent payload (no network)")
    render.add_argument("--public-base-url", default=PLACEHOLDER_PUBLIC_BASE_URL)
    commands.add_parser("register-llm", help="register our endpoint as a Bolna custom model")
    for name in ("create", "update"):
        command = commands.add_parser(name, help=f"{name} the agent on Bolna")
        command.add_argument("--webhook-url", default=None)
    for name in REQUIRED_ENV:
        commands.choices[name].add_argument(
            "--yes", action="store_true", help="confirm a real, account-changing Bolna call"
        )
    return parser


def status_webhook_url(public_base_url: str, secret: SecretStr) -> str:
    """The calls.py webhook route; the secret must match CUSTOM_LLM_TOKEN."""
    return f"{public_base_url.rstrip('/')}{WEBHOOK_PATH}/{secret.get_secret_value()}"


async def _run(
    args: argparse.Namespace, settings: Settings, transport: httpx.AsyncBaseTransport | None
) -> None:
    # main() has already refused when any REQUIRED_ENV name for the command is unset.
    api_key = cast(SecretStr, settings.bolna_api_key)
    base_url = custom_llm_base_url(cast(str, settings.public_base_url))
    async with HttpBolnaClient(api_key, settings.bolna_agent_id, transport=transport) as client:
        if args.command == "register-llm":
            token = cast(SecretStr, settings.custom_llm_token)
            await client.register_custom_model(CUSTOM_LLM_MODEL, base_url, token, CUSTOM_LLM_FAMILY)
            print(f"Registered custom model {CUSTOM_LLM_MODEL} at {base_url}")
            return
        webhook_url = args.webhook_url or status_webhook_url(
            cast(str, settings.public_base_url), cast(SecretStr, settings.custom_llm_token)
        )
        payload = build_agent_payload(base_url, webhook_url)
        if args.command == "create":
            print(await client.create_agent(payload))
            print("Put this id in BOLNA_AGENT_ID (Heroku config and the local .env).")
            return
        await client.update_agent(cast(str, settings.bolna_agent_id), payload)
        print("Updated the agent in BOLNA_AGENT_ID.")


def main(
    argv: list[str] | None = None,
    *,
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    args = _parser().parse_args(argv)
    if args.command == "render":
        payload = build_agent_payload(custom_llm_base_url(args.public_base_url), None)
        sys.stdout.write(render_agent_json(payload))
        return 0
    if not args.yes:
        print(f"Refusing: {args.command} calls the real Bolna API. Add --yes.", file=sys.stderr)
        return 2
    settings = settings or get_settings()
    present = settings.presence()
    missing = [name for name in REQUIRED_ENV[args.command] if not present[name]]
    if missing:
        print(f"Refusing: missing {', '.join(missing)}. No request sent.", file=sys.stderr)
        return 2
    try:
        asyncio.run(_run(args, settings, transport))
    except BolnaError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
