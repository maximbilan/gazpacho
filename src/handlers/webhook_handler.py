from __future__ import annotations

import json
import logging
import os
from typing import Any

import boto3

from src.common.config import AppConfig, config_from_env
from src.common.llm import make_llm_client
from src.common.secrets import SecretsManagerLoader
from src.common.storage import DigestStorage
from src.notifier.telegram_bot import TelegramBotNotifier
from src.qa_bot.prompts import QA_SYSTEM_PROMPT, build_qa_prompt

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logging.getLogger("httpx").setLevel(logging.WARNING)

TELEGRAM_SECRET_HEADER = "x-telegram-bot-api-secret-token"


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    config = config_from_env(load_local_env=False)
    secrets = SecretsManagerLoader(
        config.secrets_manager_secret_id,
        region_name=config.aws_region,
    ).secrets
    webhook_secrets = secrets.require_webhook()

    if not _verify_telegram_secret(event, webhook_secrets.telegram_webhook_secret):
        logger.warning("Rejected Telegram webhook with invalid secret token")
        return _response(401, {"ok": False})

    update = _parse_json_body(event)
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    text = str(message.get("text") or "").strip()

    if not chat_id or not text:
        return _response(200, {"ok": True})

    notifier = TelegramBotNotifier(webhook_secrets.telegram_bot_token)
    try:
        if text.startswith("/start"):
            notifier.send_text(
                chat_id,
                "Я Gazpacho. Я надсилаю український дайджест шкільних повідомлень "
                "і відповідаю на питання про збережені оновлення.\n\n"
                f"chat_id: {chat_id}",
            )
        elif text.startswith("/summary"):
            _send_latest_summary(config, notifier, chat_id)
        elif text.startswith("/refresh"):
            _start_refresh(config)
            notifier.send_text(
                chat_id,
                "Запустив оновлення. Коли дайджест буде готовий, я надішлю його сюди.",
            )
        elif chat_id not in config.target_chat_ids:
            logger.info("Ignoring non-target chat_id %s", chat_id)
            notifier.send_text(chat_id, f"Цей бот налаштований для іншого chat_id.\nchat_id: {chat_id}")
        else:
            try:
                answer = _answer_question(config, secrets.openai_api_key, chat_id, text)
            except Exception:
                logger.exception("Failed to answer Telegram Q&A message")
                answer = (
                    "Не вдалося відповісти через технічну помилку. "
                    "Я вже записав помилку в логи, спробуй ще раз трохи пізніше."
                )
            notifier.send_text(chat_id, answer)
    finally:
        notifier.close()

    return _response(200, {"ok": True})


def _verify_telegram_secret(event: dict[str, Any], expected: str) -> bool:
    headers = event.get("headers") or {}
    for key, value in headers.items():
        if key.lower() == TELEGRAM_SECRET_HEADER:
            return str(value) == expected
    return False


def _parse_json_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64

        body = base64.b64decode(body).decode("utf-8")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _send_latest_summary(config: AppConfig, notifier: TelegramBotNotifier, chat_id: str) -> None:
    storage = DigestStorage(config.dynamodb_table_name, region_name=config.aws_region)
    latest = storage.get_latest_digest_run()
    if not latest:
        notifier.send_text(chat_id, "Поки немає збереженого дайджесту. Запусти /refresh.")
        return
    notifier.send_text(chat_id, str(latest.get("summary") or "Збережений дайджест порожній."))


def _start_refresh(config: AppConfig) -> None:
    function_name = config.scheduled_digest_function_name
    if not function_name:
        raise RuntimeError("SCHEDULED_DIGEST_FUNCTION_NAME is not configured")
    client = boto3.client("lambda", region_name=config.aws_region)
    client.invoke(
        FunctionName=function_name,
        InvocationType="Event",
        Payload=json.dumps({"source": "telegram_refresh"}).encode("utf-8"),
    )


def _answer_question(
    config: AppConfig,
    openai_api_key: str | None,
    chat_id: str,
    question: str,
) -> str:
    storage = DigestStorage(config.dynamodb_table_name, region_name=config.aws_region)
    digest_runs = storage.get_digest_runs(include_raw_messages=False)
    latest = storage.get_latest_digest_run()
    raw_message_runs = [latest] if latest else []
    recent_conversation = storage.get_recent_conversation(chat_id)

    if config.llm_provider == "openai" and not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI Q&A")

    llm = make_llm_client(
        config.llm_provider,
        region_name=config.aws_region,
        openai_api_key=openai_api_key,
    )
    answer = llm.complete(
        model_id=config.llm_model_qa,
        system_prompt=QA_SYSTEM_PROMPT,
        user_text=build_qa_prompt(
            question=question,
            digest_runs=digest_runs,
            raw_message_runs=raw_message_runs,
            recent_conversation=recent_conversation,
        ),
        max_tokens=1200,
        temperature=0.1,
    )
    if not answer:
        answer = "Не вдалося сформувати відповідь. Спробуй ще раз або запусти /refresh."

    storage.append_conversation_turn(chat_id=chat_id, question=question, answer=answer)
    return answer


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }
