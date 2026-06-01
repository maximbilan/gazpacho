from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator


DEFAULT_SUMMARY_MODEL = "gpt-4.1-mini"
DEFAULT_QA_MODEL = "gpt-5-mini"


class AppConfig(BaseModel):
    source_chat_ids: list[str] = Field(min_length=1)
    target_chat_ids: list[str] = Field(min_length=1)
    timezone: str = "Europe/Madrid"
    source_lang: str = "es"
    output_lang: str = "uk"
    schedule_cron: str = "cron(0 18 * * ? *)"
    lookback_days: int = Field(default=7, ge=1, le=31)
    llm_provider: Literal["bedrock", "openai", "anthropic"] = "openai"
    llm_model_summary: str = DEFAULT_SUMMARY_MODEL
    llm_model_qa: str = DEFAULT_QA_MODEL
    aws_region: str | None = None
    secrets_manager_secret_id: str = Field(default="gazpacho/secrets", min_length=1)
    dynamodb_table_name: str = Field(default="gazpacho", min_length=1)
    scheduled_digest_function_name: str | None = None
    weekly_digest_function_name: str | None = None

    @field_validator("source_chat_ids", mode="before")
    @classmethod
    def parse_source_chat_ids(cls, value: object) -> list[str]:
        return _parse_string_list(value, "SOURCE_CHAT_IDS")

    @field_validator("target_chat_ids", mode="before")
    @classmethod
    def parse_target_chat_ids(cls, value: object) -> list[str]:
        return _parse_string_list(value, "TARGET_CHAT_IDS")

    @property
    def target_chat_id(self) -> str:
        return self.target_chat_ids[0]


def _parse_string_list(value: object, env_name: str) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            parsed = json.loads(stripped)
            if not isinstance(parsed, list):
                raise ValueError(f"{env_name} JSON must be a list")
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip() for item in stripped.split(",") if item.strip()]
    raise ValueError(f"{env_name} must be a comma-separated string or JSON list")


def load_dotenv(path: str | Path = ".env") -> None:
    """Load a simple KEY=VALUE .env file without overriding existing environment values."""
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def config_from_env(load_local_env: bool = True) -> AppConfig:
    if load_local_env:
        load_dotenv()

    data = {
        "source_chat_ids": os.getenv("SOURCE_CHAT_IDS", ""),
        "target_chat_ids": os.getenv("TARGET_CHAT_IDS") or os.getenv("TARGET_CHAT_ID", ""),
        "timezone": os.getenv("TIMEZONE", "Europe/Madrid"),
        "source_lang": os.getenv("SOURCE_LANG", "es"),
        "output_lang": os.getenv("OUTPUT_LANG", "uk"),
        "schedule_cron": os.getenv("SCHEDULE_CRON", "cron(0 18 * * ? *)"),
        "lookback_days": os.getenv("LOOKBACK_DAYS", "7"),
        "llm_provider": os.getenv("LLM_PROVIDER", "openai"),
        "llm_model_summary": os.getenv("LLM_MODEL_SUMMARY", DEFAULT_SUMMARY_MODEL),
        "llm_model_qa": os.getenv("LLM_MODEL_QA", DEFAULT_QA_MODEL),
        "aws_region": os.getenv("AWS_REGION"),
        "secrets_manager_secret_id": os.getenv(
            "SECRETS_MANAGER_SECRET_ID", "gazpacho/secrets"
        ),
        "dynamodb_table_name": os.getenv("DYNAMODB_TABLE_NAME", "gazpacho"),
        "scheduled_digest_function_name": os.getenv("SCHEDULED_DIGEST_FUNCTION_NAME")
        or os.getenv("WEEKLY_DIGEST_FUNCTION_NAME"),
        "weekly_digest_function_name": os.getenv("WEEKLY_DIGEST_FUNCTION_NAME")
        or os.getenv("SCHEDULED_DIGEST_FUNCTION_NAME"),
    }
    try:
        return AppConfig.model_validate(data)
    except ValidationError as exc:
        raise RuntimeError(f"Invalid Gazpacho configuration: {exc}") from exc
