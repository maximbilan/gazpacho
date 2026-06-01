from __future__ import annotations

import base64
import json
import logging
from functools import cached_property

import boto3
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class GazpachoSecrets(BaseModel):
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = Field(default=None, min_length=1)
    telethon_string_session: str | None = Field(default=None, min_length=1)
    telegram_bot_token: str | None = Field(default=None, min_length=1)
    telegram_webhook_secret: str | None = Field(default=None, min_length=1)
    anthropic_api_key: str | None = Field(default=None, min_length=1)

    def require_reader(self) -> "ReaderSecrets":
        return ReaderSecrets.model_validate(self.model_dump())

    def require_bot(self) -> "BotSecrets":
        return BotSecrets.model_validate(self.model_dump())

    def require_webhook(self) -> "WebhookSecrets":
        return WebhookSecrets.model_validate(self.model_dump())


class ReaderSecrets(BaseModel):
    telegram_api_id: int
    telegram_api_hash: str
    telethon_string_session: str
    telegram_bot_token: str
    anthropic_api_key: str


class BotSecrets(BaseModel):
    telegram_bot_token: str
    anthropic_api_key: str


class WebhookSecrets(BaseModel):
    telegram_bot_token: str
    telegram_webhook_secret: str
    anthropic_api_key: str


class SecretsManagerLoader:
    def __init__(self, secret_id: str, region_name: str | None = None) -> None:
        self.secret_id = secret_id
        self.region_name = region_name

    @cached_property
    def client(self):
        kwargs = {"region_name": self.region_name} if self.region_name else {}
        return boto3.client("secretsmanager", **kwargs)

    @cached_property
    def secrets(self) -> GazpachoSecrets:
        response = self.client.get_secret_value(SecretId=self.secret_id)
        raw_secret = response.get("SecretString")

        if raw_secret is None and "SecretBinary" in response:
            raw_secret = base64.b64decode(response["SecretBinary"]).decode("utf-8")

        if raw_secret is None:
            raise RuntimeError(f"Secret {self.secret_id!r} did not contain a value")

        try:
            payload = json.loads(raw_secret)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Secret {self.secret_id!r} must be a JSON object with Gazpacho keys"
            ) from exc

        if not isinstance(payload, dict):
            raise RuntimeError(f"Secret {self.secret_id!r} must be a JSON object")

        logger.info("Loaded Gazpacho secret metadata from Secrets Manager")
        return GazpachoSecrets.model_validate(payload)

