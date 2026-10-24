"""Settings loaded from the environment (Heroku config) or the repo-root `.env`.

Run `python -m app.config` to see which keys are present. Values are never printed.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_PATH_B = (
    "APP_TOKEN",
    "BOLNA_API_KEY",
    "BOLNA_AGENT_ID",
    "CUSTOM_LLM_TOKEN",
    "BOLNA_WEBHOOK_SECRET",
    "GROQ_API_KEY",
    "ALLOWED_RECIPIENTS",
)
OPTIONAL = ("SARVAM_API_KEY", "PUBLIC_BASE_URL")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", Path(__file__).resolve().parents[1] / ".env"),
        extra="ignore",
    )

    app_token: SecretStr | None = None
    bolna_api_key: SecretStr | None = None
    bolna_agent_id: str | None = None
    custom_llm_token: SecretStr | None = None
    bolna_webhook_secret: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-120b"
    sarvam_api_key: SecretStr | None = None
    allowed_recipients: Annotated[frozenset[str], NoDecode] = Field(default_factory=frozenset)
    public_base_url: str | None = None

    @field_validator(
        "app_token",
        "bolna_api_key",
        "custom_llm_token",
        "bolna_webhook_secret",
        "groq_api_key",
        "sarvam_api_key",
        "bolna_agent_id",
        "public_base_url",
        mode="before",
    )
    @classmethod
    def _blank_is_missing(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("allowed_recipients", mode="before")
    @classmethod
    def _split_recipients(cls, value: object) -> object:
        if isinstance(value, str):
            return frozenset(part.strip() for part in value.split(",") if part.strip())
        return value

    def presence(self) -> dict[str, bool]:
        """Which env names are set. Names only, never values."""
        return {name: bool(getattr(self, name.lower())) for name in REQUIRED_PATH_B + OPTIONAL}

    def missing_required(self) -> list[str]:
        present = self.presence()
        return [name for name in REQUIRED_PATH_B if not present[name]]


@lru_cache
def get_settings() -> Settings:
    return Settings()


if __name__ == "__main__":
    for name, present in get_settings().presence().items():
        tag = "required" if name in REQUIRED_PATH_B else "optional"
        print(f"{'OK     ' if present else 'MISSING'} {name} ({tag})")
    raise SystemExit(1 if get_settings().missing_required() else 0)
