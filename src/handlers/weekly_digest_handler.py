from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from src.common.config import AppConfig, config_from_env
from src.common.secrets import SecretsManagerLoader
from src.notifier.telegram_bot import TelegramBotNotifier
from src.reader.telegram_reader import TelegramReader
from src.summarizer.summarizer import Summarizer

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logging.getLogger("httpx").setLevel(logging.WARNING)


@dataclass(frozen=True)
class WeeklyDigestCredentials:
    telegram_api_id: int
    telegram_api_hash: str
    telethon_string_session: str
    telegram_bot_token: str
    openai_api_key: str | None = None


@dataclass(frozen=True)
class WeeklyDigestResult:
    messages_read: int
    images_downloaded: int
    digest_chars: int
    telegram_parts_sent: int


async def run_weekly_digest(
    config: AppConfig,
    credentials: WeeklyDigestCredentials,
    *,
    download_dir: Path,
    send_digest: bool = True,
) -> WeeklyDigestResult:
    async with TelegramReader(
        credentials.telegram_api_id,
        credentials.telegram_api_hash,
        credentials.telethon_string_session,
    ) as reader:
        reader_result = await reader.read_recent(
            config.source_chat_ids,
            lookback_days=config.lookback_days,
            download_dir=download_dir,
        )

    logger.info(
        "Read %s Telegram message(s) and downloaded %s image(s)",
        len(reader_result.messages),
        len(reader_result.images),
    )

    digest = Summarizer(config, openai_api_key=credentials.openai_api_key).summarize(
        reader_result.messages,
        reader_result.images,
    )

    parts_sent = 0
    if send_digest:
        notifier = TelegramBotNotifier(credentials.telegram_bot_token)
        try:
            parts_sent = notifier.send_text(config.target_chat_id, digest).parts_sent
        finally:
            notifier.close()

    return WeeklyDigestResult(
        messages_read=len(reader_result.messages),
        images_downloaded=len(reader_result.images),
        digest_chars=len(digest),
        telegram_parts_sent=parts_sent,
    )


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    config = config_from_env(load_local_env=False)
    secrets = SecretsManagerLoader(
        config.secrets_manager_secret_id,
        region_name=config.aws_region,
    ).secrets
    reader_secrets = secrets.require_reader()
    openai_api_key = secrets.openai_api_key
    if config.llm_provider == "openai":
        openai_api_key = secrets.require_openai().openai_api_key

    credentials = WeeklyDigestCredentials(
        telegram_api_id=reader_secrets.telegram_api_id,
        telegram_api_hash=reader_secrets.telegram_api_hash,
        telethon_string_session=reader_secrets.telethon_string_session,
        telegram_bot_token=reader_secrets.telegram_bot_token,
        openai_api_key=openai_api_key,
    )

    send_digest = not bool(event.get("dry_run"))
    with TemporaryDirectory(prefix="gazpacho-weekly-") as temp_dir:
        result = asyncio.run(
            run_weekly_digest(
                config,
                credentials,
                download_dir=Path(temp_dir),
                send_digest=send_digest,
            )
        )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "messages_read": result.messages_read,
                "images_downloaded": result.images_downloaded,
                "digest_chars": result.digest_chars,
                "telegram_parts_sent": result.telegram_parts_sent,
            }
        ),
    }
