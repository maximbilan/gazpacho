#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from typing import Any

import boto3
import httpx

from src.common.config import load_dotenv


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Register the Telegram Bot API webhook.")
    parser.add_argument("--url", required=True, help="API Gateway webhook URL")
    parser.add_argument("--secret-id", default=os.getenv("SECRETS_MANAGER_SECRET_ID", "gazpacho/secrets"))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "eu-west-1"))
    parser.add_argument("--profile", default=os.getenv("AWS_PROFILE"))
    parser.add_argument("--bot-token", default=os.getenv("TELEGRAM_BOT_TOKEN"))
    parser.add_argument("--webhook-secret", default=os.getenv("TELEGRAM_WEBHOOK_SECRET"))
    parser.add_argument(
        "--drop-pending-updates",
        action="store_true",
        help="Ask Telegram to discard pending updates before switching webhook.",
    )
    args = parser.parse_args()

    bot_token = args.bot_token
    webhook_secret = args.webhook_secret
    if not bot_token or not webhook_secret:
        secret = _load_secret(args.secret_id, args.region, args.profile)
        bot_token = bot_token or secret.get("telegram_bot_token")
        webhook_secret = webhook_secret or secret.get("telegram_webhook_secret")

    if not bot_token:
        raise SystemExit("telegram_bot_token is missing")
    if not webhook_secret:
        raise SystemExit("telegram_webhook_secret is missing")

    response = httpx.post(
        f"https://api.telegram.org/bot{bot_token}/setWebhook",
        json={
            "url": args.url,
            "secret_token": webhook_secret,
            "drop_pending_updates": args.drop_pending_updates,
            "allowed_updates": ["message", "edited_message"],
        },
        timeout=20,
    )
    response.raise_for_status()
    body = response.json()
    if not body.get("ok"):
        raise SystemExit(f"Telegram setWebhook failed: {body}")
    print(f"webhook_set={args.url}")


def _load_secret(secret_id: str, region: str, profile: str | None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"region_name": region}
    if profile:
        session = boto3.Session(profile_name=profile)
        client = session.client("secretsmanager", region_name=region)
    else:
        client = boto3.client("secretsmanager", **kwargs)
    response = client.get_secret_value(SecretId=secret_id)
    raw = response.get("SecretString")
    if not raw:
        raise SystemExit(f"Secret {secret_id!r} does not contain SecretString")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise SystemExit(f"Secret {secret_id!r} must be a JSON object")
    return parsed


if __name__ == "__main__":
    main()
